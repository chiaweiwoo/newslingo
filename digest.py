"""
NewsLingo digest job — runs daily to generate the Inside AI digest.

Reads assessment failures and prompt rules accumulated since the last digest,
produces bullet-point observations per region (International / Malaysia / Singapore)
covering what the AI got right, what it got wrong, and what it improved,
and stores the result in the learning_digest table.

Non-fatal: any failure is logged and the job exits 0 so the workflow never
blocks production or raises a GitHub Actions alarm.
"""

import json
import os
import sys
from datetime import datetime, timezone

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

DIGEST_MODEL = "claude-opus-4-6"

DIGEST_SYSTEM_PROMPT = (
    "You are a bilingual news translation quality analyst for NewsLingo, an app covering:\n"
    "- International: world events (politics, conflicts, economy, technology)\n"
    "- Malaysia: local Malaysian news (from Astro 本地圈 YouTube channel)\n"
    "- Singapore: local Singapore news (from 联合早报 / Zaobao newspaper)\n\n"

    "You will receive the current digest (if any) and new translation failures since the last update.\n"
    "Each failure shows a Chinese headline (ZH), the bad English translation (Wrong), "
    "and the corrected translation (Correct).\n\n"

    "Produce an UPDATED digest JSON with this exact structure:\n"
    "{\n"
    '  "international": {\n'
    '    "points": ["concise observation 1", "concise observation 2", ...]\n'
    "  },\n"
    '  "malaysia": {"points": [...]},\n'
    '  "singapore": {"points": [...]}\n'
    "}\n\n"

    "Rules for points:\n"
    "- Each point is ONE concise sentence (max 15 words) describing a pattern or insight\n"
    "- Mix positive and negative: mistakes made AND things working well AND improvements noticed\n"
    "- Attribute each failure to a region based on place names, people, and context\n"
    "- 3-5 points per region — quality over quantity, pick the most meaningful patterns\n"
    "- If no failures for a region, write 1-2 positive observations about what is working\n"
    "- If a previous digest exists, integrate new findings: keep what is still true, "
    "update what has changed, drop patterns that are no longer recurring\n"
    "- Write in plain English — no jargon, no markdown inside the strings\n"
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


def _call_digest(content: str) -> dict:
    """Call Claude Sonnet expecting a JSON object response."""
    msg = claude.messages.create(
        model=DIGEST_MODEL,
        max_tokens=4000,
        system=DIGEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    body = msg.content[0].text if msg.content else ""
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(
        f"[digest] failed to parse JSON object from Claude response. "
        f"Body (first 400): {body[:400]!r}"
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_previous_digest() -> dict | None:
    result = (
        supabase.table("learning_digest")
        .select("id, created_at, digest_at, payload")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_delta_failures(since: str | None) -> list[dict]:
    """Pull assessment failures since the watermark (or all history if bootstrapping)."""
    q = (
        supabase.table("assessment_logs")
        .select("ran_at, source, sample_failures")
        .not_.is_("sample_failures", "null")
        .order("ran_at", desc=True)
        .limit(200)
    )
    if since:
        q = q.gt("ran_at", since)
    result = q.execute()

    failures: list[dict] = []
    for row in result.data:
        for f in (row["sample_failures"] or []):
            if f.get("suggestion"):
                failures.append({**f, "_source": row["source"]})
    return failures


def _load_delta_rules(since: str | None) -> list[dict]:
    """Pull active prompt rules updated since the watermark."""
    q = (
        supabase.table("prompt_rules")
        .select("source, rules, generated_at")
        .eq("active", True)
        .order("generated_at", desc=True)
        .limit(10)
    )
    if since:
        q = q.gt("generated_at", since)
    result = q.execute()
    return result.data or []


# ── Digest generation ─────────────────────────────────────────────────────────

def _build_content(previous: dict | None, failures: list[dict], rules: list[dict]) -> str:
    parts: list[str] = []

    if previous:
        parts.append("CURRENT DIGEST (update this with new findings):")
        parts.append(json.dumps(previous["payload"], ensure_ascii=False, indent=2))
        parts.append("")

    if failures:
        parts.append(f"NEW TRANSLATION FAILURES ({len(failures)} total since last digest):")
        for i, f in enumerate(failures[:80]):
            parts.append(
                f"{i + 1}. ZH: {f['zh']}\n"
                f"   Wrong: {f['en']}\n"
                f"   Correct: {f['suggestion']}\n"
                f"   Reason: {f.get('reason', '')}"
            )
    else:
        parts.append("No new translation failures since the last digest.")

    if rules:
        parts.append("\nNEWLY DISTILLED RULES (for context on what the AI learned):")
        for r in rules:
            parts.append(f"[{r['source']}]\n{r['rules']}")

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def _main() -> None:
    print("[digest] NewsLingo digest job starting", flush=True)

    try:
        previous = _load_previous_digest()
        since    = previous["digest_at"] if previous else None
        print(
            f"[digest] previous digest: "
            f"{'found (watermark=' + since + ')' if since else 'none — bootstrapping from full history'}",
            flush=True,
        )

        failures = _load_delta_failures(since)
        rules    = _load_delta_rules(since)
        print(f"[digest] delta: {len(failures)} failures, {len(rules)} rule sets", flush=True)

        if not failures and not rules and previous:
            print("[digest] no new data since last digest — skipping update", flush=True)
            return

        content = _build_content(previous, failures, rules)
        payload = _call_digest(content)
        print(f"[digest] generated payload for regions: {list(payload.keys())}", flush=True)

        # Rotate: deactivate old, insert new
        if previous:
            supabase.table("learning_digest").update({"active": False}).eq("id", previous["id"]).execute()

        now = datetime.now(timezone.utc).isoformat()
        supabase.table("learning_digest").insert({
            "digest_at": now,
            "payload":   payload,
            "active":    True,
        }).execute()

        print("[digest] digest updated successfully", flush=True)

    except Exception as e:
        # Non-fatal — keep the last good digest, log the error, exit cleanly
        print(f"[digest] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    _main()
