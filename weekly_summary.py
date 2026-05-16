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
from langfuse import get_client as _langfuse_client
from langfuse import observe

from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")
os.environ.setdefault("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)

SUMMARY_MODEL       = "claude-sonnet-4-6"   # Pass 1 (generate) + Pass 2 (fact-check)
SUMMARY_HAIKU_MODEL = "claude-haiku-4-5"    # Pass 3 (EN→ZH translation — mechanical task)
LOOKBACK_DAYS     = 7
MIN_NEW_HEADLINES = 30   # skip regeneration if fewer new headlines since last run

THEMES = ["Politics", "Economy", "Society", "Security", "Technology", "Environment"]

# ── Prompts ───────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM_PROMPT = (
    "You are a senior news editor curating a weekly briefing for busy professionals.\n"
    "Your reader has limited time and wants to know what actually matters — not everything, "
    "just the things they would feel a gap without knowing.\n\n"

    "You will receive translated headlines from the past 7 days, tagged by region "
    "(International / Malaysia / Singapore).\n\n"

    "SELECTION THINKING — internal process, do not emit these fields:\n"
    "Before committing to any topic, mentally ask:\n"
    "  • so_what: Why does this matter beyond the headline? Who specifically feels it — "
    "workers, businesses, governments, consumers — and how does it change their situation?\n"
    "  • lesson: What pattern, structural shift, or non-obvious dynamic does this story reveal? "
    "Must be specific to this week's events — 'instability is bad' fails the bar.\n"
    "Include a topic ONLY if you can answer both with specificity. If either answer is generic, "
    "the story does not belong regardless of how prominent it seems.\n\n"

    "SELECTION CRITERIA — include a story only if it passes:\n"
    "  • Does it change what people pay, their safety, their legal rights, or their future options?\n"
    "  • Does it represent a structural shift — political, economic, geopolitical — with compounding "
    "consequences over months or years?\n"
    "  • Does it carry a public health signal worth awareness?\n"
    "Concrete examples:\n"
    "  PASSES — New tariff on Malaysian palm oil exports: changes producer margins, ripples through "
    "supply chains, affects livelihoods downstream.\n"
    "  PASSES — Regional central bank raises rates: directly affects mortgages, business borrowing, "
    "and currency — felt by ordinary people.\n"
    "  FAILS — Minister attended ribbon-cutting with no signed outcome.\n"
    "  FAILS — Country won a regional sports event.\n"
    "  FAILS — Single accident or crime with no systemic pattern behind it.\n\n"

    "OUTPUT FORMAT — produce a JSON object with this exact structure:\n"
    "{\n"
    '  "topics": [\n'
    "    {\n"
    '      "title":   "Short topic label (max 8 words)",\n'
    '      "summary": "WHO did WHAT WHERE — one sentence, concrete names, max 25 words.",\n'
    '      "region":  "International" | "Malaysia" | "Singapore",\n'
    '      "theme":   "Politics" | "Economy" | "Society" | "Security" | "Technology" | "Environment"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"

    "FACTUAL DISCIPLINE — only state that an event occurred if a provided headline directly says it "
    "did. For high-stakes claims (meetings, visits, deaths, signed deals, financial figures): be "
    "conservative. If headlines imply something but do not confirm it, write around the ambiguity — "
    "do not assert it as fact.\n\n"

    "TENSE DISCIPLINE — match the tense of your source headlines exactly.\n"
    "  • 'will visit', 'plans to', 'is set to', 'expected to' → future: 'is set to visit', "
    "'plans to meet'. Never convert a planned event into a completed one.\n"
    "  • 'visited', 'signed', 'announced', 'killed' → past tense is correct.\n"
    "  • When in doubt, use future tense — under-claiming is safer than over-claiming.\n\n"

    "CONFIDENCE HEDGING:\n"
    "  • Claim confirmed by multiple independent headlines → state it directly\n"
    "  • Specific claim in only one headline → prefix with 'reportedly' or 'according to reports'\n"
    "  • Claim inferred without any direct headline → omit entirely\n\n"

    "FIELD INSTRUCTIONS:\n"
    "  title   — noun phrase, max 8 words, no trailing punctuation\n"
    "  summary — one sentence. WHO, WHAT, WHERE with concrete names. Max 25 words.\n"
    "  region  — International | Malaysia | Singapore\n"
    "  theme   — Politics | Economy | Society | Security | Technology | Environment\n\n"

    "Theme definitions:\n"
    "  Politics:    elections, government, parliament, policy, diplomacy\n"
    "  Economy:     markets, trade, business, corporate news, cost of living\n"
    "  Society:     crime, courts, culture, education, public health, religion\n"
    "  Security:    armed conflicts, military, terrorism, weapons, sanctions\n"
    "  Technology:  AI, software, infrastructure, cybersecurity, science\n"
    "  Environment: climate, natural disasters, energy, conservation\n\n"

    "QUANTITY — aim for 8-10 strong stories. If fewer than 8 pass the must-know test, "
    "return fewer — never pad with weak stories. Do not force coverage across regions or themes.\n\n"

    "Before returning, verify each topic: (1) every named entity is supported by a provided "
    "headline, (2) tense matches the source, (3) single-source claims use 'reportedly', "
    "(4) you can articulate a specific so_what and lesson — if you cannot, remove the topic.\n\n"
    "Write all fields in English.\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences.\n"
)

CHINESE_TRANSLATION_SYSTEM_PROMPT = (
    "You are a news translator. Translate English news titles and summaries into Simplified Chinese.\n\n"

    "You will receive a numbered list of items in this format:\n"
    "  IDX: <integer>\n"
    "  TITLE: <English title>\n"
    "  SUMMARY: <English summary>\n\n"

    "For each item output one JSON object with exactly three keys:\n"
    "  {\"idx\": <same integer>, \"title_zh\": \"<Simplified Chinese title>\", "
    "\"summary_zh\": \"<Simplified Chinese summary>\"}\n\n"

    "Rules:\n"
    "  • Use standard Simplified Chinese proper-noun equivalents where they exist\n"
    "    (e.g. Donald Trump → 唐纳德·特朗普, Singapore → 新加坡, Malaysia → 马来西亚)\n"
    "  • For proper nouns with no established Simplified Chinese equivalent, keep the English "
    "term inline — do not invent a transliteration\n"
    "    (e.g. 'Nvidia's H200 chip' → '英伟达的 H200 芯片', keeping H200 in English)\n"
    "  • Translate faithfully — do not expand, explain, or add context not in the English source\n"
    "  • Preserve journalistic tone — factual, concise, third-person\n"
    "  • TENSE PRESERVATION — future language in English (is set to, plans to, will) must use "
    "the Chinese equivalent (预计, 将, 计划) — do not convert future events to past tense\n\n"

    "Self-check: confirm every item in the output has idx, title_zh, and summary_zh. "
    "If an item's English input is empty, return {\"idx\": N, \"title_zh\": \"\", \"summary_zh\": \"\"}.\n\n"
    "Return: a JSON array [...] containing one object per input item, in order.\n"
    "Return ONLY the JSON array. No preamble, no explanation, no markdown fences.\n"
)

FACT_CHECK_SYSTEM_PROMPT = (
    "You are a fact-checker for a news summary. You will receive:\n"
    "  1. HEADLINES — the source headlines used to generate the summary\n"
    "  2. TOPICS — the generated summary topics\n\n"

    "Each topic has four fields: title, summary, region, theme.\n"
    "Verify every specific factual claim in title and summary against the provided headlines.\n"
    "A specific factual claim includes: named meetings or visits, deaths or injuries with counts, "
    "arrests, signed agreements, financial figures, military actions.\n\n"

    "Rules:\n"
    "  • Claim directly matched by a headline → keep unchanged\n"
    "  • Claim not matched but general theme is supported → soften to what headlines actually support\n"
    "    Example: 'Trump arrived in Beijing for talks' → 'Trump-Xi tensions escalated over trade'\n"
    "  • Topic whose core claim cannot be matched to any headline → remove the topic entirely\n"
    "  • Do not add new topics\n"
    "  • Only update summary if the factual correction makes it wrong; leave title/region/theme "
    "unchanged unless the factual correction requires it\n\n"

    "TENSE CHECK — most common error; check every topic:\n"
    "  • Past tense in topic (visited, met, traveled, signed) but future tense in headlines "
    "(will visit, plans to, is set to, expected to) → correct tense to match headlines.\n"
    "  • Example: 'Trump traveled to Beijing' when headlines say 'Trump set to visit Beijing' "
    "→ correct to 'Trump is set to visit Beijing for talks with Xi Jinping'.\n\n"

    "HEDGING CHECK:\n"
    "  • Multiple independent headlines support the claim → direct language is fine\n"
    "  • Only one headline → add 'reportedly' or 'according to reports' if not already present\n"
    "  • No headline supports the claim → remove it\n\n"

    "Return the complete corrected topic list — include unchanged topics verbatim.\n"
    "If TOPICS is empty or malformed, return {\"topics\": []}.\n"
    "Before returning, do a final tense scan: check every topic for past-tense verbs where "
    "the matching headline used future tense. This is the most common error to miss.\n\n"
    "Return: {\"topics\": [...]}\n"
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


@observe(as_type="generation")
def _call_summary(content: str) -> tuple[dict, object]:
    """Three-pass generation: produce topics, fact-check, then translate to Chinese.

    Returns (translated_payload, combined_usage) where combined_usage has
    input_tokens and output_tokens summed across all three API calls.

    Prompt caching: the headlines block is placed first in the system list with
    cache_control=ephemeral. Pass 1 writes the cache; Pass 2 (which fires seconds
    later) gets a cache hit — cutting Pass 2 headline input cost by ~90%.
    """
    # Shared headlines block — byte-identical across Pass 1 and Pass 2 for cache hit
    headlines_block = {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}

    # ── Pass 1: generate ──────────────────────────────────────────────────────
    with _langfuse_client().start_as_current_observation(
        name="summary:generate", as_type="generation", model=SUMMARY_MODEL
    ) as obs1:
        msg1 = claude.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=6000,
            system=[headlines_block, {"type": "text", "text": SUMMARY_SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": "Generate the topic clusters from the headlines above."}],
        )
        obs1.update(usage_details={"input": msg1.usage.input_tokens, "output": msg1.usage.output_tokens})
    payload = _parse_topics(msg1.content[0].text if msg1.content else "", "pass-1")
    topic_count_before = len(payload.get("topics", []))
    print(f"[summary] pass-1: {topic_count_before} topics generated", flush=True)

    # ── Pass 2: fact-check ────────────────────────────────────────────────────
    # Headlines stay in system (cached); only the topics JSON goes in user message.
    with _langfuse_client().start_as_current_observation(
        name="summary:factcheck", as_type="generation", model=SUMMARY_MODEL
    ) as obs2:
        msg2 = claude.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=6000,
            system=[headlines_block, {"type": "text", "text": FACT_CHECK_SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": f"TOPICS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"}],
        )
        obs2.update(usage_details={"input": msg2.usage.input_tokens, "output": msg2.usage.output_tokens})
    corrected = _parse_topics(msg2.content[0].text if msg2.content else "", "pass-2")
    topic_count_after = len(corrected.get("topics", []))
    removed = topic_count_before - topic_count_after
    if removed:
        print(f"[summary] pass-2: {removed} topic(s) removed or corrected by fact-check", flush=True)
    else:
        print("[summary] pass-2: all topics verified", flush=True)

    # ── Pass 3: Chinese translation ───────────────────────────────────────────
    # Send plain-text numbered list (not JSON) to avoid input/output format confusion.
    topics_list = corrected.get("topics", [])
    lines = []
    for i, t in enumerate(topics_list):
        lines.append(f"IDX: {i}")
        lines.append(f"TITLE: {t['title']}")
        lines.append(f"SUMMARY: {t['summary']}")
        lines.append("")
    slim_input = "\n".join(lines).strip()

    with _langfuse_client().start_as_current_observation(
        name="summary:translate-zh", as_type="generation", model=SUMMARY_HAIKU_MODEL
    ) as obs3:
        msg3 = claude.messages.create(
            model=SUMMARY_HAIKU_MODEL,
            max_tokens=2000,
            system=CHINESE_TRANSLATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": slim_input}],
        )
        obs3.update(usage_details={"input": msg3.usage.input_tokens, "output": msg3.usage.output_tokens})
    try:
        raw3 = msg3.content[0].text if msg3.content else ""
        # Model returns a JSON array [...]; extract it
        first = raw3.find("[")
        last  = raw3.rfind("]")
        if first == -1 or last == -1 or last <= first:
            raise ValueError(f"no JSON array in pass-3 response: {raw3[:200]!r}")
        zh_list = json.loads(raw3[first:last + 1])
        # Merge title_zh / summary_zh back into the corrected payload by idx
        for zh in zh_list:
            idx = zh.get("idx")
            if isinstance(idx, int) and 0 <= idx < len(topics_list):
                topics_list[idx]["title_zh"]   = zh.get("title_zh", "")
                topics_list[idx]["summary_zh"] = zh.get("summary_zh", "")
        translated = {"topics": topics_list}
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
    _langfuse_client().update_current_generation(
        model=SUMMARY_MODEL,
        usage_details={"input": combined.input_tokens, "output": combined.output_tokens},
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
        payload, _usage = _call_summary(content)
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

        print("[summary] summary updated successfully", flush=True)

    except Exception as e:
        print(f"[summary] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    _main()
    _langfuse_client().flush()  # ensure all traces are sent before process exits
