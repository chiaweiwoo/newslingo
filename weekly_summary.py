"""
NewsLingo weekly summary job — runs every Monday to generate This Week digest.

Pulls the last 7 days of translated headlines, asks Claude Sonnet to identify
the most important topic clusters, and writes 2-3 sentence summaries per topic
into the weekly_summary table.

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

SUMMARY_MODEL = "claude-opus-4-6"

SUMMARY_SYSTEM_PROMPT = (
    "You are a bilingual news editor for NewsLingo, summarising the week's most "
    "important stories for readers who follow Singapore, Malaysia, and world news.\n\n"

    "You will receive a list of translated headlines from the past 7 days, tagged by "
    "region (International / Malaysia / Singapore).\n\n"

    "Produce a JSON object with this exact structure:\n"
    "{\n"
    '  "topics": [\n'
    "    {\n"
    '      "title": "Short topic label (max 8 words)",\n'
    '      "summary": "2-3 sentences covering key developments and why it matters.",\n'
    '      "region": "International" | "Malaysia" | "Singapore"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"

    "Rules:\n"
    "- Pick 5-8 of the most important or widely-covered topics from the week\n"
    "- Spread across regions where the news allows — don't cluster everything under one region\n"
    "- Title: noun phrase, max 8 words, no punctuation at the end\n"
    "- Summary: plain English, no jargon, no markdown inside the strings, 2-3 sentences max\n"
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
        f"[weekly] failed to parse JSON object from Claude response. "
        f"Body (first 400): {body[:400]!r}"
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_previous_summary() -> dict | None:
    result = (
        supabase.table("weekly_summary")
        .select("id")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_recent_headlines(since: str) -> list[dict]:
    """Pull translated headlines published since the given ISO timestamp."""
    result = (
        supabase.table("headlines")
        .select("title_zh, title_en, category, published_at")
        .gte("published_at", since)
        .not_.is_("title_en", "null")
        .order("published_at", desc=True)
        .limit(500)
        .execute()
    )
    return result.data or []


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
        if cat in by_region:
            by_region[cat].append(h)

    parts: list[str] = [f"HEADLINES FROM THE PAST 7 DAYS ({len(headlines)} total):"]
    for region, items in by_region.items():
        if not items:
            continue
        parts.append(f"\n[{region.upper()}] — {len(items)} headlines")
        for h in items[:80]:  # cap per region to avoid huge prompts
            parts.append(f"  • {h['title_en']}  ({h['title_zh']})")

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def _main() -> None:
    print("[weekly] NewsLingo weekly summary job starting", flush=True)

    try:
        now       = datetime.now(timezone.utc)
        week_end  = now.date()
        week_start = (now - timedelta(days=7)).date()
        since_iso = (now - timedelta(days=7)).isoformat()

        print(f"[weekly] window: {week_start} → {week_end}", flush=True)

        headlines = _load_recent_headlines(since_iso)
        print(f"[weekly] {len(headlines)} headlines loaded", flush=True)

        if not headlines:
            print("[weekly] no headlines found — skipping", flush=True)
            return

        content = _build_content(headlines)
        payload = _call_summary(content)
        topic_count = len(payload.get("topics", []))
        print(f"[weekly] generated {topic_count} topic clusters", flush=True)

        # Rotate: deactivate old, insert new
        previous = _load_previous_summary()
        if previous:
            supabase.table("weekly_summary").update({"active": False}).eq("id", previous["id"]).execute()

        supabase.table("weekly_summary").insert({
            "week_start": week_start.isoformat(),
            "week_end":   week_end.isoformat(),
            "payload":    payload,
            "active":     True,
        }).execute()

        print("[weekly] weekly summary updated successfully", flush=True)

    except Exception as e:
        # Non-fatal — keep the last good summary, log the error, exit cleanly
        print(f"[weekly] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    _main()
