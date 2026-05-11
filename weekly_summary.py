"""
NewsLingo This Week summary job — runs daily at 09:00 SGT.

Always pulls the past 7 days of headlines so the summary is never more than
1 day old and always has a full week of context. The window rolls forward
every day — no artificial Monday boundary.

Non-fatal: any failure is logged and the job exits 0 so the workflow never
blocks production or raises a GitHub Actions alarm.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import anthropic
from dotenv import load_dotenv

from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)

SUMMARY_MODEL    = "claude-sonnet-4-6"
LOOKBACK_DAYS    = 7
MIN_NEW_HEADLINES = 30   # skip regeneration if fewer new headlines since last run

SUMMARY_SYSTEM_PROMPT = (
    "You are a bilingual news editor for NewsLingo, summarising the most "
    "important recent stories for readers who follow Singapore, Malaysia, and world news.\n\n"

    "You will receive translated headlines from the past 7 days, tagged by "
    "region (International / Malaysia / Singapore).\n\n"

    "Produce a JSON object with this exact structure:\n"
    "{\n"
    '  "topics": [\n'
    "    {\n"
    '      "title": "Short topic label (max 8 words)",\n'
    '      "summary": "One tight sentence (max 20 words) capturing what happened.",\n'
    '      "region": "International" | "Malaysia" | "Singapore"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"

    "Rules:\n"
    "- Pick 5-8 of the most important or widely-covered topics\n"
    "- Spread across regions where the news allows — don't cluster everything under one region\n"
    "- Title: noun phrase, max 8 words, no punctuation at the end\n"
    "- Summary: ONE sentence only, max 20 words, plain English, no jargon, no markdown\n"
    "- region: assign based on where the story is primarily about\n"
    "- Skip minor or repetitive stories — quality over quantity\n"
    "- Return ONLY the JSON object. No preamble, no explanation, no markdown fences.\n"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json_object(text: str) -> str | None:
    """Best-effort extract a JSON object from text that may contain prose."""
    first = text.find("{")
    last  = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


def _call_summary(content: str) -> dict:
    """Call Claude Sonnet expecting a JSON object response."""
    msg = claude.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=4000,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    body = msg.content[0].text if msg.content else ""
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict) and "topics" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(
        f"[summary] failed to parse JSON object from Claude response. "
        f"Body (first 400): {body[:400]!r}"
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_previous_summary() -> dict | None:
    result = (
        supabase.table("weekly_summary")
        .select("id, created_at")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_recent_headlines(since_iso: str) -> list[dict]:
    """Pull translated headlines published in the past LOOKBACK_DAYS days."""
    result = (
        supabase.table("headlines")
        .select("title_zh, title_en, category, published_at")
        .gte("published_at", since_iso)
        .not_.is_("title_en", "null")
        .order("published_at", desc=True)
        .limit(500)
        .execute()
    )
    return result.data or []


def _count_new_headlines(since_iso: str) -> int:
    """Count headlines published after the given timestamp."""
    result = (
        supabase.table("headlines")
        .select("id", count="exact", head=True)
        .gte("published_at", since_iso)
        .not_.is_("title_en", "null")
        .execute()
    )
    return result.count or 0


# ── Summary generation ────────────────────────────────────────────────────────

def _build_content(headlines: list[dict]) -> str:
    """Format headlines for the Claude prompt."""
    by_region: dict[str, list[dict]] = {
        "International": [],
        "Malaysia": [],
        "Singapore": [],
    }
    for h in headlines:
        cat = h.get("category") or "International"
        bucket = cat if cat in by_region else "International"
        by_region[bucket].append(h)

    parts: list[str] = [f"HEADLINES FROM THE PAST {LOOKBACK_DAYS} DAYS ({len(headlines)} total):"]
    for region, items in by_region.items():
        if not items:
            continue
        parts.append(f"\n[{region.upper()}] — {len(items)} headlines")
        for h in items[:80]:  # cap per region to avoid huge prompts
            parts.append(f"  • {h['title_en']}  ({h['title_zh']})")

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def _main() -> None:
    print("[summary] NewsLingo This Week summary job starting", flush=True)

    try:
        now      = datetime.now(timezone.utc)
        since_iso = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()

        # Skip if not enough new headlines since the last summary was generated
        previous = _load_previous_summary()
        if previous:
            new_count = _count_new_headlines(previous["created_at"])
            print(f"[summary] {new_count} new headlines since last summary", flush=True)
            if new_count < MIN_NEW_HEADLINES:
                print(
                    f"[summary] fewer than {MIN_NEW_HEADLINES} new headlines — skipping",
                    flush=True,
                )
                return

        headlines = _load_recent_headlines(since_iso)
        print(f"[summary] {len(headlines)} headlines in past {LOOKBACK_DAYS} days", flush=True)

        if not headlines:
            print("[summary] no headlines found — skipping", flush=True)
            return

        content = _build_content(headlines)
        payload = _call_summary(content)
        topic_count = len(payload.get("topics", []))
        print(f"[summary] generated {topic_count} topic clusters", flush=True)

        # Rotate: deactivate old, insert new
        if previous:
            supabase.table("weekly_summary").update({"active": False}).eq("id", previous["id"]).execute()

        supabase.table("weekly_summary").insert({
            "week_start": (now - timedelta(days=LOOKBACK_DAYS)).date().isoformat(),
            "week_end":   now.date().isoformat(),
            "payload":    payload,
            "active":     True,
        }).execute()

        print("[summary] summary updated successfully", flush=True)

    except Exception as e:
        print(f"[summary] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    _main()
