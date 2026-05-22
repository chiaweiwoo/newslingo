"""
NewsLingo Top Stories summary job — runs daily at 03:00 SGT.

Reads recent translated headlines from Supabase, uses Claude Sonnet for
three-pass topic generation and fact-checking, then uses DeepSeek Flash for
Simplified Chinese translation.
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

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
os.environ.setdefault("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is required for summary_top_stories.py")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY is required for summary_top_stories.py")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)
deepseek = anthropic.Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/anthropic",
    timeout=120.0,
)

SUMMARY_MODEL = "claude-sonnet-4-6"
SUMMARY_FACTCHECK_MODEL = "claude-sonnet-4-6"
SUMMARY_TRANSLATION_MODEL = "deepseek-v4-flash"
LOOKBACK_DAYS = 7
SUMMARY_MAX_TOKENS = 6000
SUMMARY_TRANSLATION_MAX_TOKENS = 2200
THINKING_DISABLED = {"type": "disabled"}

THEMES = ["Politics", "Economy", "Society", "Security", "Technology", "Environment"]
VALID_REGIONS = {"International", "Malaysia", "Singapore"}
VALID_THEMES = set(THEMES)

SUMMARY_SYSTEM_PROMPT = (
    "You are a senior news editor curating a weekly briefing for busy professionals.\n"
    "Your reader has limited time and wants to know what actually matters - not everything, "
    "just the things they would feel a gap without knowing.\n\n"
    "You will receive translated headlines from the past 7 days, tagged by region "
    "(International / Malaysia / Singapore).\n\n"
    "SELECTION THINKING - internal process, do not emit these fields:\n"
    "Before committing to any topic, mentally ask:\n"
    "  - so_what: Why does this matter beyond the headline? Who specifically feels it - "
    "workers, businesses, governments, consumers - and how does it change their situation?\n"
    "  - lesson: What pattern, structural shift, or non-obvious dynamic does this story reveal? "
    "Must be specific to this week's events - 'instability is bad' fails the bar.\n"
    "Include a topic ONLY if you can answer both with specificity. If either answer is generic, "
    "the story does not belong regardless of how prominent it seems.\n\n"
    "SELECTION CRITERIA:\n"
    "  - Does it change what people pay, their safety, their legal rights, or their future options?\n"
    "  - Does it represent a structural shift with consequences over months or years?\n"
    "  - Does it carry a public health signal worth awareness?\n"
    "  - Do not include ribbon-cuttings, sports, celebrity, or isolated low-signal incidents.\n\n"
    "Concrete examples:\n"
    "  PASSES - New tariff on Malaysian palm oil exports: changes producer margins, ripples through supply chains, affects livelihoods downstream.\n"
    "  PASSES - Regional central bank raises rates: directly affects mortgages, business borrowing, and currency - felt by ordinary people.\n"
    "  FAILS - Minister attended ribbon-cutting with no signed outcome.\n"
    "  FAILS - Country won a regional sports event.\n"
    "  FAILS - Single accident or crime with no systemic pattern behind it.\n\n"
    "OUTPUT FORMAT:\n"
    "{\n"
    '  "topics": [\n'
    "    {\n"
    '      "title": "Short topic label (max 8 words)",\n'
    '      "summary": "WHO did WHAT WHERE, one sentence, concrete names, max 25 words.",\n'
    '      "region": "International" | "Malaysia" | "Singapore",\n'
    '      "theme": "Politics" | "Economy" | "Society" | "Security" | "Technology" | "Environment"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "FACTUAL DISCIPLINE:\n"
    "  - Only state that an event occurred if a provided headline directly says it did.\n"
    "  - For high-stakes claims, be conservative.\n"
    "  - If headlines imply something but do not confirm it, write around the ambiguity.\n\n"
    "TENSE DISCIPLINE:\n"
    "  - Match the tense of your source headlines exactly.\n"
    "  - Planned events must stay in future tense.\n"
    "  - When in doubt, under-claim rather than over-claim.\n\n"
    "CONFIDENCE HEDGING:\n"
    "  - Multiple independent headlines support a claim -> state it directly.\n"
    "  - Only one headline supports it -> use 'reportedly' or 'according to reports'.\n"
    "  - Inferred claim without headline support -> omit it.\n\n"
    "FIELD INSTRUCTIONS:\n"
    "  - title: noun phrase, max 8 words, no trailing punctuation\n"
    "  - summary: one sentence, max 25 words\n"
    "  - region: International | Malaysia | Singapore\n"
    "  - theme: Politics | Economy | Society | Security | Technology | Environment\n\n"
    "Theme definitions:\n"
    "  Politics: elections, government, parliament, policy, diplomacy\n"
    "  Economy: markets, trade, business, corporate news, cost of living\n"
    "  Society: crime, courts, culture, education, public health, religion\n"
    "  Security: armed conflicts, military, terrorism, weapons, sanctions\n"
    "  Technology: AI, software, infrastructure, cybersecurity, science\n"
    "  Environment: climate, natural disasters, energy, conservation\n\n"
    "REGION COVERAGE:\n"
    "  - Do not force equal balance.\n"
    "  - But do not let International crowd out Singapore or Malaysia when those regions clearly contain must-know stories.\n"
    "  - If Singapore headlines in the input include policy, public-institution, safety, court, health, cost-of-living, or economic changes that meet the bar, include at least one Singapore topic.\n"
    "  - If Malaysia headlines in the input include such must-know developments, include at least one Malaysia topic.\n"
    "  - Only omit a region entirely if its recent headlines are genuinely weaker than the final cutoff.\n\n"
    "QUANTITY:\n"
    "  - Aim for 8 to 10 strong stories.\n"
    "  - If fewer than 8 pass the bar, return fewer.\n"
    "  - Do not force region or theme balance.\n\n"
    "Before returning, verify each topic: every named entity is supported by a provided headline, "
    "tense matches the source, single-source claims use hedging, and the topic clears the significance bar.\n\n"
    "Write all fields in English.\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences."
)

FACT_CHECK_SYSTEM_PROMPT = (
    "You are a fact-checker for a news summary. You will receive:\n"
    "  1. HEADLINES - the source headlines used to generate the summary\n"
    "  2. TOPICS - the generated summary topics\n\n"
    "Verify every specific factual claim in title and summary against the provided headlines.\n\n"
    "Rules:\n"
    "  - Claim directly matched by a headline -> keep unchanged\n"
    "  - Claim not matched but general theme is supported -> soften to what headlines actually support\n"
    "  - Topic whose core claim cannot be matched to any headline -> remove the topic entirely\n"
    "  - Do not add new topics\n"
    "  - Only update title/region/theme when a factual correction requires it\n\n"
    "TENSE CHECK:\n"
    "  - If a topic uses past tense but the headlines use future tense, correct it.\n"
    "  - Planned events must remain planned.\n\n"
    "HEDGING CHECK:\n"
    "  - Multiple headlines support the claim -> direct language is fine\n"
    "  - Only one headline -> add 'reportedly' or 'according to reports'\n"
    "  - No headline supports the claim -> remove it\n\n"
    "Return the complete corrected topic list as {\"topics\": [...]}.\n"
    "If TOPICS is empty or malformed, return {\"topics\": []}.\n"
    "Return ONLY the JSON object. No explanation."
)

CHINESE_TRANSLATION_SYSTEM_PROMPT = (
    "You are a news translator. Translate English news titles and summaries into Simplified Chinese.\n\n"
    "You will receive a numbered list of items in this format:\n"
    "  IDX: <integer>\n"
    "  TITLE: <English title>\n"
    "  SUMMARY: <English summary>\n\n"
    "For each item output one JSON object with exactly three keys:\n"
    '  {"idx": <same integer>, "title_zh": "<Simplified Chinese title>", "summary_zh": "<Simplified Chinese summary>"}\n\n'
    "Rules:\n"
    "  - Use standard Simplified Chinese proper-noun equivalents where they exist.\n"
    "  - For proper nouns without an established Chinese equivalent, keep the English term inline.\n"
    "  - Translate faithfully, preserve concise journalistic tone, and keep future events in future tense.\n\n"
    "Self-check: confirm every item has idx, title_zh, and summary_zh.\n"
    "Return ONLY the JSON array. No preamble, no explanation, no markdown fences."
)


def _extract_json_object(text: str) -> str | None:
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first : last + 1]


def _extract_json_array(text: str) -> str | None:
    first = text.find("[")
    last = text.rfind("]")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first : last + 1]


def _deepseek_usage(message: object) -> types.SimpleNamespace:
    usage = getattr(message, "usage", None)
    return types.SimpleNamespace(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


def _parse_topics(body: str, label: str) -> dict:
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict) and isinstance(parsed.get("topics"), list):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(f"[summary] {label}: failed to parse JSON. Body (first 400): {body[:400]!r}")


def _sanitize_topic(topic: dict) -> dict | None:
    title = str(topic.get("title") or "").strip()
    summary = str(topic.get("summary") or "").strip()
    region = str(topic.get("region") or "").strip()
    theme = str(topic.get("theme") or "").strip()
    if not title or not summary or region not in VALID_REGIONS or theme not in VALID_THEMES:
        return None
    return {
        "title": title,
        "summary": summary,
        "region": region,
        "theme": theme,
    }


def _assistant_text(message: object) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


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


def _build_content(headlines: list[dict]) -> str:
    by_region: dict[str, list[dict]] = {
        "International": [],
        "Malaysia": [],
        "Singapore": [],
    }
    for headline in headlines:
        category = headline.get("category") or "International"
        bucket = category if category in by_region else "International"
        by_region[bucket].append(headline)

    parts: list[str] = [f"HEADLINES FROM THE PAST {LOOKBACK_DAYS} DAYS ({len(headlines)} total):"]
    for region, items in by_region.items():
        if not items:
            continue
        parts.append(f"\n[{region.upper()}] - {len(items)} headlines")
        for headline in items[:120]:
            parts.append(f"  - {headline['title_en']}  ({headline['title_zh']})")
    return "\n".join(parts)


def _translate_to_zh(payload: dict) -> tuple[dict, object]:
    topics = payload.get("topics", [])
    if not topics:
        return payload, types.SimpleNamespace(input_tokens=0, output_tokens=0)

    lines: list[str] = []
    for idx, topic in enumerate(topics):
        lines.append(f"IDX: {idx}")
        lines.append(f"TITLE: {topic['title']}")
        lines.append(f"SUMMARY: {topic['summary']}")
        lines.append("")
    slim_input = "\n".join(lines).strip()

    msg = deepseek.messages.create(
        model=SUMMARY_TRANSLATION_MODEL,
        max_tokens=SUMMARY_TRANSLATION_MAX_TOKENS,
        system=CHINESE_TRANSLATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": slim_input}],
        thinking=THINKING_DISABLED,
    )

    raw = _assistant_text(msg)
    extracted = _extract_json_array(raw)
    if not extracted:
        raise ValueError(f"[summary] pass-3: failed to parse JSON array. Body (first 400): {raw[:400]!r}")

    zh_list = json.loads(extracted)
    for zh in zh_list:
        idx = zh.get("idx")
        if isinstance(idx, int) and 0 <= idx < len(topics):
            topics[idx]["title_zh"] = zh.get("title_zh", "")
            topics[idx]["summary_zh"] = zh.get("summary_zh", "")
    return {"topics": topics}, _deepseek_usage(msg)


@observe(name="summary:generate", as_type="generation")
def _call_summary(content: str) -> tuple[dict, object]:
    headlines_block = {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}

    msg1 = claude.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=SUMMARY_MAX_TOKENS,
        system=[headlines_block, {"type": "text", "text": SUMMARY_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": "Generate the topic clusters from the headlines above."}],
    )
    payload = _parse_topics(_assistant_text(msg1), "pass-1")
    topic_count_before = len(payload.get("topics", []))
    print(f"[summary] pass-1: {topic_count_before} topics generated", flush=True)

    msg2 = claude.messages.create(
        model=SUMMARY_FACTCHECK_MODEL,
        max_tokens=SUMMARY_MAX_TOKENS,
        system=[headlines_block, {"type": "text", "text": FACT_CHECK_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": f"TOPICS:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"}],
    )
    corrected = _parse_topics(_assistant_text(msg2), "pass-2")
    corrected_topics = []
    for topic in corrected.get("topics", []):
        clean = _sanitize_topic(topic)
        if clean:
            corrected_topics.append(clean)
    corrected = {"topics": corrected_topics}
    topic_count_after = len(corrected_topics)
    print(f"[summary] pass-2: {topic_count_after} topics retained", flush=True)

    translated, translation_usage = _translate_to_zh(corrected)
    print(f"[summary] pass-3: {len(translated.get('topics', []))} topics translated to Chinese", flush=True)

    combined = types.SimpleNamespace(
        input_tokens=(
            (getattr(msg1.usage, "input_tokens", 0) or 0)
            + (getattr(msg2.usage, "input_tokens", 0) or 0)
            + translation_usage.input_tokens
        ),
        output_tokens=(
            (getattr(msg1.usage, "output_tokens", 0) or 0)
            + (getattr(msg2.usage, "output_tokens", 0) or 0)
            + translation_usage.output_tokens
        ),
    )
    _langfuse_client().update_current_generation(
        model=SUMMARY_MODEL,
        usage_details={"input": combined.input_tokens, "output": combined.output_tokens},
    )
    return translated, combined


def _store_summary(now: datetime, payload: dict, previous: dict | None) -> None:
    if previous:
        supabase.table("weekly_summary").update({"active": False}).eq("id", previous["id"]).execute()

    supabase.table("weekly_summary").insert(
        {
            "week_start": (now - timedelta(days=LOOKBACK_DAYS)).date().isoformat(),
            "week_end": now.date().isoformat(),
            "payload": payload,
            "active": True,
        }
    ).execute()


def _main() -> None:
    print("[summary] NewsLingo Top Stories job starting", flush=True)

    try:
        now = datetime.now(timezone.utc)
        since_iso = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
        previous = _load_previous_summary()

        headlines = _load_recent_headlines(since_iso)
        print(f"[summary] {len(headlines)} headlines in past {LOOKBACK_DAYS} days", flush=True)
        if not headlines:
            print("[summary] no headlines found - skipping", flush=True)
            return

        content = _build_content(headlines)
        payload, _usage = _call_summary(content)
        topic_count = len(payload.get("topics", []))
        print(f"[summary] final: {topic_count} topic clusters", flush=True)
        if not topic_count:
            print("[summary] no topics returned - skipping storage", flush=True)
            return

        _store_summary(now, payload, previous)
        print("[summary] summary updated successfully", flush=True)
    except Exception as exc:
        print(f"[summary] ERROR: {exc}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _main()
    _langfuse_client().flush()
