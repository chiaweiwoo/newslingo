"""
NewsLingo Top Stories summary job - runs daily at 09:00 SGT.

This version uses Google Gemini with Google Search grounding to discover and
rank important general news across International, Singapore, and Malaysia, then
uses DeepSeek to translate the final payload into Simplified Chinese.
"""

import json
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import anthropic
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from langfuse import get_client as _langfuse_client
from langfuse import observe

from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
os.environ.setdefault("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY is required for summary_top_stories.py")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is required for summary_top_stories.py")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
gemini = genai.Client(api_key=GEMINI_API_KEY)
deepseek = anthropic.Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/anthropic",
    timeout=120.0,
)

SUMMARY_DISCOVERY_MODEL = "gemini-2.5-flash-lite"
SUMMARY_MODEL = "gemini-3.5-flash"
SUMMARY_TRANSLATION_MODEL = "deepseek-v4-flash"
LOOKBACK_DAYS = 7
MIN_NEW_HEADLINES = 30
SUMMARY_DISCOVERY_MAX_TOKENS = 1800
SUMMARY_SELECTION_MAX_TOKENS = 1800
SUMMARY_TRANSLATION_MAX_TOKENS = 2200
SUMMARY_REPAIR_MODEL = "deepseek-v4-flash"
SUMMARY_REPAIR_SYSTEM_PROMPT = (
    "You are a JSON repair specialist. You will receive a malformed or truncated JSON response from another AI model.\n"
    "Your goal is to fix the JSON structure so it can be parsed, preserving as much content as possible.\n\n"
    "Rules:\n"
    "- If the JSON is truncated, close any open strings, arrays, or objects.\n"
    "- If the JSON is malformed (e.g. missing brackets), correct the syntax.\n"
    "- Return ONLY the valid JSON object. No preamble, no explanation, no markdown fences.\n"
    "- If the content is unsalvageable, return an empty items/topics list as appropriate."
)
THINKING_DISABLED = {"type": "disabled"}


def _repair_json_with_deepseek(body: str) -> str | None:
    """Fallback: use DeepSeek to fix malformed or truncated JSON."""
    try:
        msg = deepseek.messages.create(
            model=SUMMARY_REPAIR_MODEL,
            max_tokens=1500,
            system=SUMMARY_REPAIR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": body}],
            thinking=THINKING_DISABLED,
        )

        raw = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                raw += getattr(block, "text", "")

        # Use extraction on DeepSeek's output too
        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last != -1 and last > first:
            return raw[first : last + 1]
        return raw if raw.strip() else None
    except Exception as e:
        print(f"  [summary] DeepSeek repair failed: {e}", flush=True)
        return None


THEMES = ["Politics", "Economy", "Society", "Security", "Technology", "Environment"]
VALID_REGIONS = {"International", "Singapore", "Malaysia"}
VALID_THEMES = set(THEMES)

DISCOVERY_TOOL = genai_types.Tool(google_search=genai_types.GoogleSearch())
DISCOVERY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "region": {"type": "string"},
                    "theme": {"type": "string"},
                },
                "required": ["title", "summary", "region", "theme"],
            },
        }
    },
    "required": ["items"],
}
SELECTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "region": {"type": "string"},
                    "theme": {"type": "string"},
                },
                "required": ["title", "summary", "region", "theme"],
            },
        }
    },
    "required": ["topics"],
}

REGION_DISCOVERY_SPECS = [
    {
        "region": "International",
        "count_guidance": "Find around 6 to 8 strong candidate stories.",
        "focus": (
            "Be highly selective. Prefer wars, elections, major policy shifts, trade disputes, "
            "financial shocks, public health alerts, large disasters, sanctions, and major technology moves."
        ),
    },
    {
        "region": "Singapore",
        "count_guidance": "Find around 4 to 6 strong candidate stories.",
        "focus": (
            "Prefer policy, elections, cost of living, housing, transport, courts, public safety, "
            "health, and major business or labour developments."
        ),
    },
    {
        "region": "Malaysia",
        "count_guidance": "Find around 4 to 6 strong candidate stories.",
        "focus": (
            "Prefer policy, parliament, courts, cost of living, public safety, health, trade, "
            "major infrastructure, and important corporate or state-level developments."
        ),
    },
]

DISCOVERY_SYSTEM_PROMPT = (
    "You are a senior news editor building a candidate list for a daily Top Stories briefing.\n"
    "Use Google Search grounding to discover only the most important developments from the last 7 days.\n\n"
    "OUTPUT FORMAT:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "title": "Short topic label, max 8 words",\n'
    '      "summary": "One sentence, max 25 words, concrete and factual",\n'
    '      "region": "International" | "Singapore" | "Malaysia",\n'
    '      "theme": "Politics" | "Economy" | "Society" | "Security" | "Technology" | "Environment"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "RULES:\n"
    "  - Use searched material from this run only.\n"
    "  - Include only developments from the last 7 days.\n"
    "  - Prefer concrete impact over commentary, ceremony, entertainment, sports, and trivia.\n"
    "  - Keep titles and summaries in English only.\n"
    "  - Do not include citations, URLs, source lists, or extra keys.\n"
    "  - Do not invent facts, figures, or named entities.\n"
    "  - If fewer stories meet the standard, return fewer items rather than padding.\n"
    "  - Every item must use one valid region and one valid theme.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the output is valid JSON.\n"
    "  - Confirm every item falls within the last 7 days.\n"
    "  - Confirm every item is supported by grounded search results.\n"
    "  - Confirm titles are short and summaries stay under 25 words.\n\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences."
)

SELECTION_SYSTEM_PROMPT = (
    "You are a senior news editor curating a Top Stories briefing for busy professionals.\n"
    "You will receive candidate items that were already discovered from grounded web search.\n"
    "Your job is to select and refine only the most important stories.\n\n"
    "SELECTION STANDARD:\n"
    "  - Prioritize stories with strategic, operational, financial, political, legal, social, or public-health impact.\n"
    "  - International news must be held to a higher bar because the pool is much larger.\n"
    "  - Avoid duplicates, minor updates, ceremony, celebrity, sports, isolated low-signal crime, and fluff.\n"
    "  - Return fewer stories rather than weak filler.\n"
    "  - Aim for 8 to 10 total topics, but do not force the count.\n"
    "  - Do not force equal region balance.\n\n"
    "OUTPUT FORMAT:\n"
    "{\n"
    '  "topics": [\n'
    "    {\n"
    '      "title": "Short topic label (max 8 words)",\n'
    '      "summary": "WHO did WHAT WHERE, one sentence, max 25 words",\n'
    '      "region": "International" | "Singapore" | "Malaysia",\n'
    '      "theme": "Politics" | "Economy" | "Society" | "Security" | "Technology" | "Environment"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "FACTUAL DISCIPLINE:\n"
    "  - Use only the candidate list provided.\n"
    "  - Do not add new facts beyond the candidate summaries.\n"
    "  - Do not include citations, URLs, source lists, or extra keys.\n"
    "  - If a candidate seems weak or ambiguous, exclude it rather than guessing.\n"
    "  - Keep the tense consistent with the candidate summary.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the output is valid JSON with a top-level topics array.\n"
    "  - Confirm every topic uses a valid region and valid theme.\n"
    "  - Confirm each summary is one sentence and no more than 25 words.\n"
    "  - Confirm every selected topic is stronger than the omitted ones.\n\n"
    "Write all fields in English.\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences."
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
    "  - For proper nouns with no established Simplified Chinese equivalent, keep the English term inline.\n"
    "  - Translate faithfully and do not add context that is not in the English source.\n"
    "  - Preserve concise journalistic tone.\n"
    "  - Keep future events in future tense.\n\n"
    "Self-check: confirm every item in the output has idx, title_zh, and summary_zh. "
    "If an item's English input is empty, return {\"idx\": N, \"title_zh\": \"\", \"summary_zh\": \"\"}.\n\n"
    "Return a JSON array [...] containing one object per input item, in order.\n"
    "Return ONLY the JSON array. No preamble, no explanation, no markdown fences."
)


def _extract_json_object(text: str) -> str | None:
    first = text.find("{")
    if first == -1:
        return None

    body = text[first:]

    # Try standard rfind approach first
    last = body.rfind("}")
    if last != -1:
        candidate = body[: last + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Repair logic for truncated JSON:
    # We try to find the longest valid prefix by iteratively shortening the string
    # and attempting to close the braces/brackets.
    for i in range(len(body), 0, -1):
        candidate_body = body[:i]

        stack = []
        in_string = False
        escaped = False
        for char in candidate_body:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == "{":
                    stack.append("}")
                elif char == "[":
                    stack.append("]")
                elif char == "}":
                    if stack and stack[-1] == "}":
                        stack.pop()
                elif char == "]":
                    if stack and stack[-1] == "]":
                        stack.pop()

        repaired = candidate_body
        if in_string:
            repaired += '"'

        repaired = repaired.strip()
        while repaired and repaired[-1] in (",", "[", "{", ":", " "):
            repaired = repaired[:-1].strip()

        if stack:
            repaired += "".join(reversed(stack))

        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            continue

    return None


def _extract_json_array(text: str) -> str | None:
    first = text.find("[")
    if first == -1:
        return None

    body = text[first:]

    # Standard rfind
    last = body.rfind("]")
    if last != -1:
        candidate = body[: last + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Basic repair
    stack = []
    in_string = False
    escaped = False
    for char in body:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == "[":
                stack.append("]")
            elif char == "{":
                stack.append("}")
            elif char == "]":
                if stack and stack[-1] == "]":
                    stack.pop()
            elif char == "}":
                if stack and stack[-1] == "}":
                    stack.pop()

    repaired = body
    if in_string:
        repaired += '"'
    else:
        repaired = repaired.rstrip().rstrip(",")

    if stack:
        repaired += "".join(reversed(stack))

    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        return None


def _gemini_text(response: object) -> str:
    text = getattr(response, "text", None)
    if text:
        return text

    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            maybe = getattr(part, "text", None)
            if maybe:
                parts.append(maybe)
    return "\n".join(parts).strip()


def _gemini_usage(response: object) -> types.SimpleNamespace:
    usage = getattr(response, "usage_metadata", None)
    input_tokens = (
        getattr(usage, "prompt_token_count", 0)
        or getattr(usage, "input_token_count", 0)
        or getattr(usage, "total_token_count", 0)
        or 0
    )
    output_tokens = (
        getattr(usage, "candidates_token_count", 0)
        or getattr(usage, "output_token_count", 0)
        or 0
    )
    return types.SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


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

    # Fallback to DeepSeek repair
    print(f"  [summary] {label}: manual repair failed, attempting DeepSeek repair...", flush=True)
    repaired = _repair_json_with_deepseek(body)
    if repaired:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict) and isinstance(parsed.get("topics"), list):
                print(f"  [summary] {label}: DeepSeek repair successful", flush=True)
                return parsed
        except json.JSONDecodeError:
            pass

    raise ValueError(f"[summary] {label}: failed to parse JSON. Body (first 400): {body[:400]!r}")


def _parse_items(body: str, label: str) -> list[dict]:
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            items = parsed.get("items")
            if isinstance(items, list):
                return items
        except json.JSONDecodeError:
            pass

    extracted_array = _extract_json_array(body)
    if extracted_array:
        try:
            parsed = json.loads(extracted_array)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback to DeepSeek repair
    print(f"  [summary] {label}: manual repair failed, attempting DeepSeek repair...", flush=True)
    repaired = _repair_json_with_deepseek(body)
    if repaired:
        try:
            parsed = json.loads(repaired)
            items = parsed.get("items")
            if isinstance(items, list):
                print(f"  [summary] {label}: DeepSeek repair successful", flush=True)
                return items
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


def _call_gemini_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    use_search: bool,
    max_output_tokens: int,
    response_schema: dict,
) -> tuple[str, types.SimpleNamespace]:
    config_kwargs = {
        "system_instruction": system_prompt,
        "max_output_tokens": max_output_tokens,
        "tools": [DISCOVERY_TOOL] if use_search else None,
    }
    if not use_search:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema

    config = genai_types.GenerateContentConfig(**config_kwargs)
    response = gemini.models.generate_content(
        model=model,
        contents=user_prompt,
        config=config,
    )
    return _gemini_text(response), _gemini_usage(response)


def _translate_to_zh(topics: list[dict]) -> tuple[dict, object]:
    lines: list[str] = []
    for i, t in enumerate(topics):
        lines.append(f"IDX: {i}")
        lines.append(f"TITLE: {t['title']}")
        lines.append(f"SUMMARY: {t['summary']}")
        lines.append("")

    slim_input = "\n".join(lines).strip()
    msg = deepseek.messages.create(
        model=SUMMARY_TRANSLATION_MODEL,
        max_tokens=SUMMARY_TRANSLATION_MAX_TOKENS,
        system=CHINESE_TRANSLATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": slim_input}],
        thinking=THINKING_DISABLED,
    )

    raw = ""
    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text":
            raw += getattr(block, "text", "")

    extracted = _extract_json_array(raw)
    if not extracted:
        raise ValueError(f"[summary] pass-zh: failed to parse JSON array. Body (first 400): {raw[:400]!r}")

    translated = json.loads(extracted)
    for entry in translated:
        idx = entry.get("idx")
        if isinstance(idx, int) and 0 <= idx < len(topics):
            topics[idx]["title_zh"] = entry.get("title_zh", "")
            topics[idx]["summary_zh"] = entry.get("summary_zh", "")

    return {"topics": topics}, _deepseek_usage(msg)


@observe(name="summary:generate", as_type="generation")
def _call_summary(today_utc: datetime) -> tuple[dict, object]:
    all_candidates: list[dict] = []
    total_input = 0
    total_output = 0

    for spec in REGION_DISCOVERY_SPECS:
        region = spec["region"]
        print(f"  [summary] discovering candidates for {region}...", flush=True)

        today_label = today_utc.date().isoformat()
        user_prompt = (
            f"Today's UTC date is {today_label}.\n"
            f"Discover important {region} news from the last {LOOKBACK_DAYS} days.\n"
            f"{spec['count_guidance']}\n"
            f"Focus: {spec['focus']}"
        )

        body, usage = _call_gemini_json(
            SUMMARY_DISCOVERY_MODEL,
            DISCOVERY_SYSTEM_PROMPT,
            user_prompt,
            use_search=True,
            max_output_tokens=SUMMARY_DISCOVERY_MAX_TOKENS,
            response_schema=DISCOVERY_RESPONSE_SCHEMA,
        )
        total_input += usage.input_tokens
        total_output += usage.output_tokens

        items = _parse_items(body, f"discover-{region.lower()}")
        for it in items:
            it["region"] = region  # enforce consistency
            all_candidates.append(it)

    print(f"  [summary] selecting top stories from {len(all_candidates)} candidates...", flush=True)
    candidate_lines = []
    for i, it in enumerate(all_candidates):
        candidate_lines.append(f"IDX: {i}")
        candidate_lines.append(f"REGION: {it.get('region')}")
        candidate_lines.append(f"TITLE: {it.get('title')}")
        candidate_lines.append(f"SUMMARY: {it.get('summary')}")
        candidate_lines.append("")

    selection_user_prompt = "CANDIDATE LIST:\n\n" + "\n".join(candidate_lines).strip()
    body, usage = _call_gemini_json(
        SUMMARY_MODEL,
        SELECTION_SYSTEM_PROMPT,
        selection_user_prompt,
        use_search=False,
        max_output_tokens=SUMMARY_SELECTION_MAX_TOKENS,
        response_schema=SELECTION_RESPONSE_SCHEMA,
    )
    total_input += usage.input_tokens
    total_output += usage.output_tokens

    topics_payload = _parse_topics(body, "select")
    raw_topics = topics_payload.get("topics", [])
    sanitized = []
    for t in raw_topics:
        st = _sanitize_topic(t)
        if st:
            sanitized.append(st)

    print(f"  [summary] translating {len(sanitized)} topics to Chinese...", flush=True)
    payload, trans_usage = _translate_to_zh(sanitized)
    total_input += trans_usage.input_tokens
    total_output += trans_usage.output_tokens

    _langfuse_client().update_current_generation(
        model=SUMMARY_MODEL,
        usage_details={"input": total_input, "output": total_output},
    )

    combined_usage = types.SimpleNamespace(input_tokens=total_input, output_tokens=total_output)
    return payload, combined_usage


def _get_new_headlines_count(window_start: str) -> int:
    result = (
        supabase.table("headlines")
        .select("id", count="exact")
        .gte("created_at", window_start)
        .execute()
    )
    return result.count or 0


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
        window_start = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()

        new_count = _get_new_headlines_count(window_start)
        if new_count < MIN_NEW_HEADLINES:
            print(f"[summary] skipping: only {new_count} headlines in last {LOOKBACK_DAYS} days", flush=True)
            return

        previous = _load_previous_summary()
        payload, _usage = _call_summary(now)
        total_topics = len(payload.get("topics", []))
        print(f"[summary] generated {total_topics} topics from {new_count} headlines", flush=True)

        _store_summary(now, payload, previous)
        print("[summary] summary updated successfully", flush=True)
    except Exception as e:
        print(f"[summary] ERROR: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _main()
    _langfuse_client().flush()
