"""
NewsLingo AI summary job - runs daily at 09:30 SGT.

This version restores Claude web search for broad AI coverage, then uses
DeepSeek Flash to translate the final items into Simplified Chinese.
"""

import json
import os
import re
import sys
import time
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # kept for future experiments
os.environ.setdefault("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is required for summary_ai.py")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY is required for summary_ai.py")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=180.0)
deepseek = anthropic.Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/anthropic",
    timeout=120.0,
)

AI_RADAR_MODEL = "claude-haiku-4-5"
AI_RADAR_FALLBACK_MODEL = "claude-sonnet-4-6"
AI_RADAR_TRANSLATION_MODEL = "deepseek-v4-flash"
LOOKBACK_DAYS = 7
WEB_SEARCH_MAX_USES = 3
AI_RADAR_MAX_TOKENS = 2600
AI_RADAR_TRANSLATION_MAX_TOKENS = 2200
AI_RADAR_TRANSLATION_BATCH_SIZE = 10
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_SLEEP_SECONDS = 20
THINKING_DISABLED = {"type": "disabled"}
WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": WEB_SEARCH_MAX_USES,
    "allowed_callers": ["direct"],
}

CATEGORY_SPECS = [
    {
        "key": "governance",
        "title": "AI Governance Radar",
        "focus": (
            "AI incidents, harmful behavior, failures, lawsuits, copyright disputes, "
            "enforcement, policy, regulation, operational breakdowns, and public backlash."
        ),
    },
    {
        "key": "product",
        "title": "AI Product Radar",
        "focus": (
            "Major launches, feature releases, agents, copilots, product strategy shifts, "
            "enterprise workflow changes, adoption signals, and meaningful UX improvements."
        ),
    },
    {
        "key": "infrastructure",
        "title": "AI Infrastructure Radar",
        "focus": (
            "GPUs, AI chips, datacenters, cloud AI capacity, inference optimization, compute shortages, "
            "energy and cooling issues, and efficiency breakthroughs."
        ),
    },
]

AI_RADAR_SYSTEM_PROMPT = (
    "You are a senior AI radar analyst preparing a concise briefing for busy professionals.\n"
    "Your job is to extract the most important AI developments from the last 7 days using web search.\n\n"
    "You will handle exactly ONE category per request, specified in the user message.\n\n"
    "WINDOW:\n"
    "  - Include only developments from the last 7 days relative to the current date.\n"
    "  - If a development falls outside the window, exclude it.\n"
    "  - Use searched and cited sources only. Do not rely on background knowledge alone.\n\n"
    "SELECTION STANDARD:\n"
    "  - Include all materially important items that pass the bar, not just a single top story.\n"
    "  - Prefer strategic, operational, financial, political, legal, or social significance.\n"
    "  - Prefer concrete real-world impact over hype or speculation.\n"
    "  - Avoid duplicates, incremental minor updates, and repetitive follow-ons.\n"
    "  - If two stories are materially the same development, merge them into one stronger item.\n\n"
    "OUTPUT SIZE:\n"
    "  - Return as many qualifying items as fit within the response budget.\n"
    "  - Do not stop at a fixed count if more strong items exist.\n"
    "  - Return an empty items array only if the category is truly quiet after searching.\n\n"
    "ITEM RULES:\n"
    "  - title: short English title, no hype, no date\n"
    "  - description: one very concise English sentence, about 8 to 14 words, information-dense, no date\n"
    "  - sources: 1 to 2 source objects pulled from the searched/cited material\n"
    "  - Each source object must contain exactly: title, url\n"
    "  - Prefer primary sources first; use strong reporting sources when primary sources are unavailable.\n\n"
    "OUTPUT FORMAT:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "title": "Short title",\n'
    '      "description": "One concise explanation.",\n'
    '      "sources": [{"title": "Source title", "url": "https://example.com"}]\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "REQUIRED SHAPE:\n"
    "  - Return exactly one JSON object with one top-level key: items.\n"
    "  - If the category has no qualifying items, return an empty items array.\n"
    "  - Do not include inline citation markup such as <cite ...>...</cite> anywhere in the JSON.\n"
    "  - Return only valid JSON.\n\n"
    "FACTUAL DISCIPLINE:\n"
    "  - Do not invent company actions, product details, legal outcomes, or infrastructure numbers.\n"
    "  - Every factual claim must be traceable to the searched and cited sources used in this run.\n"
    "  - If a source is ambiguous, write around the uncertainty conservatively.\n"
    "  - Do not include unsupported claims or unattributed rumors.\n\n"
    "CONFIDENCE HEDGING:\n"
    "  - If multiple reputable sources clearly support a claim, state it directly.\n"
    "  - If a claim appears in only one credible report or remains partly uncertain, use cautious wording.\n"
    "  - If you cannot support the core claim from searched and cited sources, omit the item entirely.\n\n"
    "ESCALATION RULE:\n"
    "  - If you cannot verify enough meaningful items for a category, return fewer items rather than guessing.\n"
    "  - Return an empty items array only if you genuinely cannot find even one strong, sourced item.\n"
    "  - If a source link is missing or unreliable, exclude that item rather than fabricating a citation.\n\n"
    "LANGUAGE:\n"
    "  - Write all item titles, descriptions, and source titles in English only.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the response is valid JSON with exactly one top-level key: items.\n"
    "  - Confirm each item has title, description, and sources.\n"
    "  - Confirm every source has title and url.\n"
    "  - Confirm every item is supported by searched/cited sources from the last 7 days.\n\n"
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
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


def _extract_json_array(text: str) -> str | None:
    first = text.find("[")
    last = text.rfind("]")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


def _strip_citation_markup(text: str) -> str:
    return re.sub(r"<cite\b[^>]*>.*?</cite>", "", text, flags=re.IGNORECASE | re.DOTALL)


def _assistant_text(message: object) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


def _parse_items_payload(body: str) -> dict:
    candidates = [body, _strip_citation_markup(body)]
    for candidate in candidates:
        extracted = _extract_json_object(candidate)
        if not extracted:
            continue
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                return parsed
        except json.JSONDecodeError:
            continue
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
                "sources": item.get("sources", []),
            }
        )
    return normalized


def _normalize_payload(categories: list[dict]) -> dict:
    return {"categories": categories}


def _deepseek_usage(message: object) -> types.SimpleNamespace:
    usage = getattr(message, "usage", None)
    return types.SimpleNamespace(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc)
    return "rate_limit_error" in text or "429" in text


def _is_model_not_found_error(exc: Exception) -> bool:
    text = str(exc)
    return "not_found_error" in text or "model:" in text


def _call_category(category: dict, today_utc: datetime, model: str) -> tuple[dict, object]:
    today_label = today_utc.date().isoformat()
    user_prompt = (
        f"Today's UTC date is {today_label}.\n"
        f"Search the web and compile {category['title']} for the last {LOOKBACK_DAYS} days.\n"
        f"Focus only on this category: {category['focus']}\n"
        "Use a small number of high-value searches. Return as many qualifying items as fit cleanly, "
        "1 to 2 sources per item, and no inline citation tags. Prefer primary sources. Return the JSON object only."
    )

    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            msg = claude.messages.create(
                model=model,
                max_tokens=AI_RADAR_MAX_TOKENS,
                system=AI_RADAR_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[WEB_SEARCH_TOOL],
            )

            while getattr(msg, "stop_reason", None) == "pause_turn":
                msg = claude.messages.create(
                    model=model,
                    max_tokens=AI_RADAR_MAX_TOKENS,
                    system=AI_RADAR_SYSTEM_PROMPT,
                    messages=[
                        {"role": "user", "content": user_prompt},
                        {"role": "assistant", "content": msg.content},
                    ],
                    tools=[WEB_SEARCH_TOOL],
                )

            parsed_payload = _parse_items_payload(_assistant_text(msg))
            parsed_items = parsed_payload.get("items", [])
            items = _normalize_items(parsed_payload)
            print(
                f"  [ai-radar] {category['key']} items: parsed={len(parsed_items)} normalized={len(items)}",
                flush=True,
            )
            return {
                "key": category["key"],
                "title": category["title"],
                "items": items,
            }, msg.usage
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == RATE_LIMIT_RETRIES:
                raise
            sleep_for = RATE_LIMIT_SLEEP_SECONDS * attempt
            print(
                f"[ai-radar] rate limited during {category['key']} attempt {attempt}/{RATE_LIMIT_RETRIES}; sleeping {sleep_for}s",
                flush=True,
            )
            time.sleep(sleep_for)

    raise RuntimeError(f"[ai-radar] exhausted retries for {category['key']}")


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

        raw = _assistant_text(msg)
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
    categories: list[dict] = []
    total_input = 0
    total_output = 0
    model_in_use = AI_RADAR_MODEL

    try:
        for spec in CATEGORY_SPECS:
            result, usage = _call_category(spec, today_utc, model_in_use)
            categories.append(result)
            total_input += getattr(usage, "input_tokens", 0) or 0
            total_output += getattr(usage, "output_tokens", 0) or 0
    except Exception as exc:
        if not _is_model_not_found_error(exc):
            raise

        print(
            f"[ai-radar] primary model {AI_RADAR_MODEL} unavailable; falling back to {AI_RADAR_FALLBACK_MODEL}",
            flush=True,
        )
        model_in_use = AI_RADAR_FALLBACK_MODEL
        categories = []
        total_input = 0
        total_output = 0

        for spec in CATEGORY_SPECS:
            result, usage = _call_category(spec, today_utc, model_in_use)
            categories.append(result)
            total_input += getattr(usage, "input_tokens", 0) or 0
            total_output += getattr(usage, "output_tokens", 0) or 0

    categories, translation_usage = _translate_categories_to_zh(categories)
    total_input += getattr(translation_usage, "input_tokens", 0) or 0
    total_output += getattr(translation_usage, "output_tokens", 0) or 0

    _langfuse_client().update_current_generation(
        model=model_in_use,
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
    print("[ai-radar] NewsLingo AI summary job starting", flush=True)

    try:
        now = datetime.now(timezone.utc)
        previous = _load_previous_radar()
        payload, _usage = _call_ai_radar(now)
        total_items = sum(len(category.get("items", [])) for category in payload.get("categories", []))
        print(f"[ai-radar] total final items: {total_items}", flush=True)
        print(f"[ai-radar] generated {total_items} items across 3 categories", flush=True)
        _store_radar(now, payload, previous)
        print("[ai-radar] AI summary updated successfully", flush=True)
    except Exception as exc:
        print(f"[ai-radar] ERROR: {exc}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    _main()
    _langfuse_client().flush()
