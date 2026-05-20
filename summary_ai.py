"""
NewsLingo AI Radar job - runs daily at 09:30 SGT.

This job uses Gemini with Google Search grounding to discover important AI
developments across governance, product, and infrastructure, then uses
DeepSeek to translate the final payload into Simplified Chinese.
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
    raise RuntimeError("DEEPSEEK_API_KEY is required for summary_ai.py")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is required for summary_ai.py")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
gemini = genai.Client(api_key=GEMINI_API_KEY)
deepseek = anthropic.Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/anthropic",
    timeout=120.0,
)

AI_RADAR_DISCOVERY_MODEL = "gemini-3.5-flash"
AI_RADAR_MODEL = "gemini-3.5-flash"
AI_RADAR_TRANSLATION_MODEL = "deepseek-v4-flash"
LOOKBACK_DAYS = 7
AI_RADAR_MAX_TOKENS = 3000
AI_RADAR_TRANSLATION_MAX_TOKENS = 2200
AI_RADAR_TRANSLATION_BATCH_SIZE = 10
THINKING_DISABLED = {"type": "disabled"}

DISCOVERY_TOOL = genai_types.Tool(google_search=genai_types.GoogleSearch())

CATEGORY_SPECS = [
    {
        "key": "governance",
        "title": "AI Governance Radar",
        "focus": (
            "AI incidents, failures, harmful behavior, lawsuits, copyright disputes, governance breakdowns, "
            "public backlash, enforcement actions, enterprise AI mistakes, and major policy or regulatory actions."
        ),
    },
    {
        "key": "product",
        "title": "AI Product Radar",
        "focus": (
            "Major product launches, feature releases, agents, copilots, strategy shifts, enterprise workflow changes, "
            "adoption signals, and meaningful user experience improvements."
        ),
    },
    {
        "key": "infrastructure",
        "title": "AI Infrastructure Radar",
        "focus": (
            "GPUs, AI chips, datacenters, cloud AI infrastructure, inference optimization, compute shortages, "
            "energy and cooling issues, and model efficiency breakthroughs."
        ),
    },
]

AI_RADAR_SYSTEM_PROMPT = (
    "You are a senior AI radar analyst preparing a concise briefing for busy professionals.\n"
    "Use Google Search grounding to discover the most important AI developments from the last 7 days.\n"
    "You will handle exactly one category per request.\n\n"
    "OUTPUT FORMAT:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "title": "Short English title",\n'
    '      "description": "One concise English sentence, about 8 to 14 words"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "RULES:\n"
    "  - Include only developments from the last 7 days.\n"
    "  - Prefer strategic, operational, financial, political, legal, or social impact.\n"
    "  - Avoid duplicates, minor follow-ons, and hype.\n"
    "  - If the category is quiet, return fewer items rather than padding.\n"
    "  - Keep all fields in English only.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the output is valid JSON with exactly one top-level key: items.\n"
    "  - Confirm every item has title and description.\n"
    "  - Confirm every item is grounded in searched material from the last 7 days.\n\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences."
)

AI_RADAR_TRANSLATION_SYSTEM_PROMPT = (
    "You are a news translator. Translate English AI news titles and descriptions into Simplified Chinese.\n\n"
    "You will receive a numbered list of items in this format:\n"
    "  IDX: <integer>\n"
    "  TITLE: <English title>\n"
    "  DESCRIPTION: <English description>\n\n"
    "For each item output one JSON object with exactly three keys:\n"
    '  {"idx": <same integer>, "title_zh": "<Simplified Chinese title>", "description_zh": "<Simplified Chinese description>"}\n\n'
    "Rules:\n"
    "  - Translate faithfully and keep concise news style.\n"
    "  - Use standard Simplified Chinese proper nouns where they exist.\n"
    "  - Keep product names, model names, chip names, and protocol names in English when that is clearer.\n"
    "  - If an item's English text is empty, return empty Chinese strings.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the output is a JSON array.\n"
    "  - Confirm every object has idx, title_zh, and description_zh.\n\n"
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

        # Quick check: if we're in the middle of a string, close it
        # (This is a heuristic, but good enough for news summaries)
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

        # Basic cleanup: remove trailing commas or incomplete tokens before closing
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


def _call_gemini_json(
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    use_search: bool,
    max_output_tokens: int,
) -> tuple[str, types.SimpleNamespace]:
    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
        tools=[DISCOVERY_TOOL] if use_search else None,
    )
    response = gemini.models.generate_content(
        model=model,
        contents=user_prompt,
        config=config,
    )
    return _gemini_text(response), _gemini_usage(response)


def _parse_items_payload(body: str) -> dict:
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(f"[ai-radar] failed to parse JSON. Body (first 400): {body[:400]!r}")


def _normalize_items(payload: dict) -> list[dict]:
    items = payload.get("items")
    normalized = []
    for item in items if isinstance(items, list) else []:
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title or not description:
            continue
        normalized.append(
            {
                "title": title,
                "description": description,
            }
        )
    return normalized


def _normalize_payload(categories: list[dict]) -> dict:
    return {"categories": categories}


def _call_category(category: dict, today_utc: datetime) -> tuple[dict, object]:
    today_label = today_utc.date().isoformat()
    user_prompt = (
        f"Today's UTC date is {today_label}.\n"
        f"Compile {category['title']} for the last {LOOKBACK_DAYS} days.\n"
        f"Focus only on this category: {category['focus']}"
    )
    body, usage = _call_gemini_json(
        AI_RADAR_MODEL,
        AI_RADAR_SYSTEM_PROMPT,
        user_prompt,
        use_search=True,
        max_output_tokens=AI_RADAR_MAX_TOKENS,
    )
    items = _normalize_items(_parse_items_payload(body))
    return {
        "key": category["key"],
        "title": category["title"],
        "items": items,
    }, usage


def _translate_categories_to_zh(categories: list[dict]) -> tuple[list[dict], object]:
    rows: list[tuple[int, dict]] = []
    for category in categories:
        for item in category.get("items", []):
            rows.append((len(rows), item))

    if not rows:
        return categories, types.SimpleNamespace(input_tokens=0, output_tokens=0)

    flat_items = [item for _idx, item in rows]
    total_input = 0
    total_output = 0

    for start in range(0, len(rows), AI_RADAR_TRANSLATION_BATCH_SIZE):
        batch = rows[start : start + AI_RADAR_TRANSLATION_BATCH_SIZE]
        lines: list[str] = []
        for idx, item in batch:
            lines.append(f"IDX: {idx}")
            lines.append(f"TITLE: {item.get('title', '')}")
            lines.append(f"DESCRIPTION: {item.get('description', '')}")
            lines.append("")
        slim_input = "\n".join(lines).strip()

        msg = deepseek.messages.create(
            model=AI_RADAR_TRANSLATION_MODEL,
            max_tokens=AI_RADAR_TRANSLATION_MAX_TOKENS,
            system=AI_RADAR_TRANSLATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": slim_input}],
            thinking=THINKING_DISABLED,
        )
        usage = _deepseek_usage(msg)
        total_input += usage.input_tokens
        total_output += usage.output_tokens

        raw = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                raw += getattr(block, "text", "")

        extracted = _extract_json_array(raw)
        if not extracted:
            raise ValueError(
                f"[ai-radar] translation pass failed to return JSON array. Body (first 400): {raw[:400]!r}"
            )

        translated = json.loads(extracted)
        if not isinstance(translated, list):
            raise ValueError(
                f"[ai-radar] translation pass returned non-list payload. Body (first 400): {raw[:400]!r}"
            )

        for entry in translated:
            idx = entry.get("idx")
            if isinstance(idx, int) and 0 <= idx < len(flat_items):
                flat_items[idx]["title_zh"] = entry.get("title_zh", "")
                flat_items[idx]["description_zh"] = entry.get("description_zh", "")

    return categories, types.SimpleNamespace(input_tokens=total_input, output_tokens=total_output)


@observe(name="ai-radar:generate", as_type="generation")
def _call_ai_radar(today_utc: datetime) -> tuple[dict, object]:
    categories = []
    total_input = 0
    total_output = 0

    for spec in CATEGORY_SPECS:
        result, usage = _call_category(spec, today_utc)
        categories.append(result)
        total_input += getattr(usage, "input_tokens", 0) or 0
        total_output += getattr(usage, "output_tokens", 0) or 0

    categories, translation_usage = _translate_categories_to_zh(categories)
    total_input += getattr(translation_usage, "input_tokens", 0) or 0
    total_output += getattr(translation_usage, "output_tokens", 0) or 0

    _langfuse_client().update_current_generation(
        model=AI_RADAR_MODEL,
        usage_details={"input": total_input, "output": total_output},
    )

    payload = _normalize_payload(categories)
    combined_usage = types.SimpleNamespace(input_tokens=total_input, output_tokens=total_output)
    return payload, combined_usage


def _load_previous_radar() -> dict | None:
    result = (
        supabase.table("ai_radar")
        .select("id, created_at")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _store_radar(now: datetime, payload: dict, previous: dict | None) -> None:
    if previous:
        supabase.table("ai_radar").update({"active": False}).eq("id", previous["id"]).execute()

    supabase.table("ai_radar").insert(
        {
            "window_start": (now - timedelta(days=LOOKBACK_DAYS)).date().isoformat(),
            "window_end": now.date().isoformat(),
            "payload": payload,
            "active": True,
        }
    ).execute()


def _main() -> None:
    print("[ai-radar] NewsLingo AI Radar job starting", flush=True)

    try:
        now = datetime.now(timezone.utc)
        previous = _load_previous_radar()
        payload, _usage = _call_ai_radar(now)
        total_items = sum(len(category.get("items", [])) for category in payload.get("categories", []))
        print(f"[ai-radar] generated {total_items} items across 3 categories", flush=True)
        _store_radar(now, payload, previous)
        print("[ai-radar] AI Radar updated successfully", flush=True)
    except Exception as e:
        print(f"[ai-radar] ERROR: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _main()
    _langfuse_client().flush()
