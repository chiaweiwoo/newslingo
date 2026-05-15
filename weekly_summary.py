"""
NewsLingo Top Stories summary job — runs daily at 09:00 SGT.

Three-pass generation:
  Pass 1 — Generate 8-10 must-know topic clusters with full analysis
            (title, summary, so_what, lesson, region, theme).
  Pass 2 — Self-critique: fact-check every specific claim against the
            original headlines; remove or correct anything not directly
            supported.
  Pass 3 — Translate title and summary into Simplified Chinese, adding
            title_zh and summary_zh to each topic.

The window rolls forward every day (rolling 14-day, no Monday boundary).
Smart-skip: regeneration is skipped if fewer than MIN_NEW_HEADLINES have
arrived since the last run to avoid pointless churn.

Non-fatal: any failure is logged and the job exits 0.
"""

import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import anthropic
from dotenv import load_dotenv

from pricing import compute_cost_usd, get_model_rates
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)

SUMMARY_MODEL     = "claude-sonnet-4-6"
LOOKBACK_DAYS     = 14
MIN_NEW_HEADLINES = 0    # TEMP: force run to verify pass-3 fix (restore to 60)

THEMES = ["Politics", "Economy", "Society", "Security", "Technology", "Environment"]

# ── Prompts ───────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM_PROMPT = (
    "You are a senior news editor curating a weekly briefing for busy professionals.\n"
    "Your reader has limited time and wants to know what actually matters — not everything, "
    "just the things they would feel a gap without knowing.\n\n"

    "You will receive translated headlines from the past 14 days, tagged by region "
    "(International / Malaysia / Singapore).\n\n"

    "Produce a JSON object with this exact structure:\n"
    "{\n"
    '  "topics": [\n'
    "    {\n"
    '      "title":   "Short topic label (max 8 words)",\n'
    '      "summary": "WHO did WHAT WHERE — one sentence, concrete names and places.",\n'
    '      "so_what": "Why this matters — 2-3 sentences. Start with the general impact, '
    'then narrow to specific groups affected.",\n'
    '      "lesson":  ["narrative bullet", "narrative bullet"],\n'
    '      "region":  "International" | "Malaysia" | "Singapore",\n'
    '      "theme":   "Politics" | "Economy" | "Society" | "Security" | "Technology" | "Environment"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"

    "SELECTION — include a story only if it passes the must-know test:\n"
    "  • Does this change what people pay, their safety, their legal rights, or their future options?\n"
    "  • Does it represent a structural shift — political, economic, geopolitical — with compounding "
    "consequences over months or years?\n"
    "  • Does it carry a public health signal worth awareness, even if the outcome is still uncertain "
    "(think: early COVID-like pattern)?\n"
    "Exclude: single accidents or crimes without a systemic pattern behind them; ceremonial events "
    "with no signed outcome; local decisions with limited reach.\n\n"

    "FACTUAL DISCIPLINE — only state that an event occurred if a provided headline directly says it "
    "did. For high-stakes claims (meetings, visits, deaths, signed deals, financial figures): be "
    "conservative. If headlines imply something but do not confirm it, write around the ambiguity — "
    "do not assert it as fact.\n\n"

    "TENSE DISCIPLINE — match the tense of your source headlines exactly.\n"
    "  • If headlines say 'will visit', 'plans to', 'is set to', 'expected to' → use future language: "
    "'is set to visit', 'plans to meet'. Never convert a planned event into a completed one.\n"
    "  • If headlines say 'visited', 'signed', 'announced', 'killed' → past tense is correct.\n"
    "  • When in doubt, use present or future tense — it is safer to under-claim than to assert "
    "something happened that has not.\n\n"

    "CONFIDENCE HEDGING — calibrate certainty to source coverage:\n"
    "  • Claim confirmed by multiple independent headlines → state it directly\n"
    "  • Specific claim (visit, meeting, deal, arrest, figure, death) appearing in only one "
    "headline → prefix with 'reportedly' or 'according to reports'\n"
    "  • Claim inferred or synthesised without any direct headline confirmation → do not state "
    "it as fact; write around it or omit it entirely\n\n"

    "FIELD INSTRUCTIONS:\n"
    "  title   — noun phrase, max 8 words, no trailing punctuation\n"
    "  summary — one sentence. Must answer WHO, WHAT, WHERE with concrete names. Max 25 words.\n"
    "  so_what — 2-3 sentences. Lead with the broad impact, then narrow to who feels it most.\n"
    "  lesson  — 2-4 narrative bullets. No label prefixes like 'Short term:' or 'Long term:'.\n"
    "            Write natural sentences. Include a 'worth watching' point only when the outcome\n"
    "            is genuinely uncertain and observation is warranted.\n"
    "            Each bullet must be specific to this week's events — no generic observations\n"
    "            that could apply to any week.\n"
    "  region  — International | Malaysia | Singapore\n"
    "  theme   — Politics | Economy | Society | Security | Technology | Environment\n\n"

    "Theme definitions:\n"
    "  Politics:    elections, government, parliament, policy, diplomacy\n"
    "  Economy:     markets, trade, business, corporate news, cost of living\n"
    "  Society:     crime, courts, culture, education, public health, religion\n"
    "  Security:    armed conflicts, military, terrorism, weapons, sanctions\n"
    "  Technology:  AI, software, infrastructure, cybersecurity, science\n"
    "  Environment: climate, natural disasters, energy, conservation\n\n"

    "QUANTITY — aim for 8-10 strong stories. Missing something is acceptable; a weak story is not. "
    "Spread across regions and themes where stories genuinely qualify — do not force coverage.\n\n"

    "Before returning, re-read each topic and verify: (1) every named entity is supported by "
    "a provided headline, (2) tense matches the source, (3) single-source claims use 'reportedly'.\n\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences.\n"
)

CHINESE_TRANSLATION_SYSTEM_PROMPT = (
    "You are a news translator. Translate English news titles and summaries into Simplified Chinese.\n\n"

    "You will receive a JSON array of objects, each with an 'idx', 'title', and 'summary' field.\n"
    "For each item, return ONLY the two translations — do not repeat any other fields.\n\n"

    "Output schema (one object per input item, same order):\n"
    "  {\"idx\": <same integer>, \"title_zh\": \"<Simplified Chinese title>\", "
    "\"summary_zh\": \"<Simplified Chinese summary>\"}\n\n"

    "Rules:\n"
    "  • Use standard Simplified Chinese proper-noun equivalents where they exist\n"
    "    (e.g. Donald Trump → 唐纳德·特朗普, Singapore → 新加坡, Malaysia → 马来西亚)\n"
    "  • Preserve journalistic tone — factual, concise, third-person\n"
    "  • TENSE PRESERVATION — if the English uses future language (is set to, plans to, will),\n"
    "    use the Chinese equivalent (预计, 将, 计划) — do not convert future events to past tense\n\n"

    "Self-check: confirm every item has idx, title_zh, and summary_zh before returning.\n\n"
    "Return: {\"translations\": [...]}\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences.\n"
)

FACT_CHECK_SYSTEM_PROMPT = (
    "You are a fact-checker for a news summary. You will receive:\n"
    "  1. HEADLINES — the source headlines used to generate the summary\n"
    "  2. TOPICS — the generated summary topics\n\n"

    "For each topic, verify every specific factual claim against the provided headlines.\n"
    "A specific factual claim includes: named meetings or visits, deaths or injuries with counts, "
    "arrests, signed agreements, financial figures, military actions.\n\n"

    "Rules:\n"
    "  • Claim directly matched by a headline → keep unchanged\n"
    "  • Claim not matched but general theme is supported → soften to what headlines actually support\n"
    "    Example: 'Trump arrived in Beijing for talks' → 'Trump-Xi tensions escalated over trade'\n"
    "  • Topic whose core claim cannot be matched to any headline → remove the topic entirely\n"
    "  • Do not add new topics\n"
    "  • Only update so_what or lesson if the factual correction makes them wrong\n\n"

    "TENSE CHECK — this is the most common error; check every topic:\n"
    "  • If a topic uses past tense (visited, met, traveled, signed, announced) but the matching\n"
    "    headlines use future tense (will visit, plans to, is set to, expected to) → correct the\n"
    "    tense to match the headlines. A planned event must never be written as a completed event.\n"
    "  • Example: 'Trump traveled to Beijing for talks with Xi' when headlines say 'Trump set to\n"
    "    visit Beijing' → correct to 'Trump is set to visit Beijing for talks with Xi Jinping'.\n\n"

    "HEDGING CHECK — verify confidence language:\n"
    "  • For each specific claim (visit, meeting, deal, arrest, figure, death): count how many\n"
    "    provided headlines independently support it.\n"
    "  • Supported by multiple headlines → direct language is fine\n"
    "  • Supported by only one headline → add 'reportedly' or 'according to reports' if not\n"
    "    already present\n"
    "  • Not supported by any headline → remove the claim\n\n"

    "Return the complete topic list — include unchanged topics verbatim, not just edited ones.\n"
    "Before returning, do a final tense scan: check every topic for past-tense verbs where "
    "the matching headline used future tense. This is the most common error to miss.\n\n"
    "Return the corrected list as: {\"topics\": [...]}\n"
    "Return ONLY the JSON object. No explanation.\n"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json_object(text: str) -> str | None:
    """Best-effort extract a JSON object from text that may contain prose."""
    first = text.find("{")
    last  = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


def _parse_topics(body: str, label: str) -> dict:
    """Parse a JSON object with a 'topics' key from Claude response body."""
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict) and "topics" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(
        f"[summary] {label}: failed to parse JSON from Claude response. "
        f"Body (first 400): {body[:400]!r}"
    )


def _call_summary(content: str) -> tuple[dict, object]:
    """Two-pass generation: produce topics then fact-check them.

    Returns (corrected_payload, combined_usage) where combined_usage has
    input_tokens and output_tokens summed across both API calls.
    """
    # ── Pass 1: generate ──────────────────────────────────────────────────────
    msg1 = claude.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=6000,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    payload = _parse_topics(msg1.content[0].text if msg1.content else "", "pass-1")
    topic_count_before = len(payload.get("topics", []))
    print(f"[summary] pass-1: {topic_count_before} topics generated", flush=True)

    # ── Pass 2: fact-check ────────────────────────────────────────────────────
    fact_check_input = (
        f"HEADLINES:\n{content}\n\n"
        f"TOPICS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    msg2 = claude.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=6000,
        system=FACT_CHECK_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": fact_check_input}],
    )
    corrected = _parse_topics(msg2.content[0].text if msg2.content else "", "pass-2")
    topic_count_after = len(corrected.get("topics", []))
    removed = topic_count_before - topic_count_after
    if removed:
        print(f"[summary] pass-2: {removed} topic(s) removed or corrected by fact-check", flush=True)
    else:
        print("[summary] pass-2: all topics verified", flush=True)

    # ── Pass 3: Chinese translation ───────────────────────────────────────────
    # Send only idx + title + summary — no large fields — so output stays small.
    slim_input = json.dumps({
        "translations": [
            {"idx": i, "title": t["title"], "summary": t["summary"]}
            for i, t in enumerate(corrected.get("topics", []))
        ]
    }, ensure_ascii=False)
    msg3 = claude.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=2000,
        system=CHINESE_TRANSLATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": slim_input}],
    )
    try:
        raw3 = msg3.content[0].text if msg3.content else ""
        extracted3 = _extract_json_object(raw3)
        if not extracted3:
            raise ValueError(f"no JSON object found in pass-3 response: {raw3[:200]!r}")
        parsed3 = json.loads(extracted3)
        zh_list = parsed3.get("translations", [])
        # Merge title_zh / summary_zh back into the corrected payload by idx
        topics = corrected.get("topics", [])
        for zh in zh_list:
            idx = zh.get("idx")
            if isinstance(idx, int) and 0 <= idx < len(topics):
                topics[idx]["title_zh"]   = zh.get("title_zh", "")
                topics[idx]["summary_zh"] = zh.get("summary_zh", "")
        translated = {"topics": topics}
        print(f"[summary] pass-3: {len(zh_list)} topics translated to Chinese", flush=True)
    except Exception as e:
        print(f"[summary] pass-3 FAILED (falling back to pass-2 result): {e}", flush=True)
        translated = corrected

    # Combine usage from all three calls
    combined = types.SimpleNamespace(
        input_tokens  = (msg1.usage.input_tokens  + msg2.usage.input_tokens
                         + msg3.usage.input_tokens),
        output_tokens = (msg1.usage.output_tokens + msg2.usage.output_tokens
                         + msg3.usage.output_tokens),
    )
    return translated, combined


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
        .limit(1000)
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
        for h in items[:120]:  # cap per region to avoid huge prompts
            parts.append(f"  • {h['title_en']}  ({h['title_zh']})")

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def _main() -> None:
    print("[summary] NewsLingo This Week summary job starting", flush=True)

    try:
        now       = datetime.now(timezone.utc)
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
        payload, usage = _call_summary(content)
        topic_count = len(payload.get("topics", []))
        print(f"[summary] final: {topic_count} topic clusters", flush=True)

        # Rotate: deactivate old, insert new
        if previous:
            supabase.table("weekly_summary").update({"active": False}).eq("id", previous["id"]).execute()

        supabase.table("weekly_summary").insert({
            "week_start": (now - timedelta(days=LOOKBACK_DAYS)).date().isoformat(),
            "week_end":   now.date().isoformat(),
            "payload":    payload,
            "active":     True,
        }).execute()

        # Record token usage (combined across both passes)
        in_tok  = getattr(usage, "input_tokens", 0)
        out_tok = getattr(usage, "output_tokens", 0)
        rates   = get_model_rates(SUMMARY_MODEL)
        cost    = compute_cost_usd(SUMMARY_MODEL, in_tok, out_tok)
        supabase.table("token_usage").insert({
            "task":                "insights",
            "model":               SUMMARY_MODEL,
            "input_tokens":        in_tok,
            "output_tokens":       out_tok,
            "cost_usd":            cost,
            "price_input_per_1m":  rates["input"],
            "price_output_per_1m": rates["output"],
        }).execute()
        print(f"[summary] in={in_tok} out={out_tok} cost=${cost:.4f}", flush=True)

        print("[summary] summary updated successfully", flush=True)

    except Exception as e:
        print(f"[summary] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    _main()
