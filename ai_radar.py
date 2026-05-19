"""
NewsLingo AI Radar job - runs daily at 09:30 SGT.

This job uses Claude Haiku 4.5 with Anthropic's server-side web search tool
to compile a 7-day AI developments briefing across governance, product, and
infrastructure. Only the latest active row is shown in the frontend drawer.

Non-fatal: any failure is logged and the job exits 0.
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
os.environ.setdefault("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=180.0)

AI_RADAR_MODEL = "claude-haiku-4-5"
AI_RADAR_FALLBACK_MODEL = "claude-sonnet-4-6"
LOOKBACK_DAYS = 7
WEB_SEARCH_MAX_USES = 2
AI_RADAR_MAX_TOKENS = 1400
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_SLEEP_SECONDS = 20
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
    "  - Include only the strongest items that pass the importance bar.\n"
    "  - Prefer strategic, operational, financial, political, legal, or social significance.\n"
    "  - Prefer concrete real-world impact over hype or speculation.\n"
    "  - Avoid duplicates, incremental minor updates, and repetitive follow-ons.\n"
    "  - If two stories are materially the same development, merge them into one stronger item.\n\n"
    "OUTPUT SIZE:\n"
    "  - Return 1 to 3 items when qualifying developments exist.\n"
    "  - Return an empty items array if nothing is strong enough.\n\n"
    "ITEM RULES:\n"
    "  - title: short English title, no hype, no date\n"
    "  - description: one very concise English sentence, about 10 to 16 words, information-dense, no date, no bullet prefix\n"
    "  - sources: exactly 1 source object pulled from the searched/cited material\n"
    "  - Each source object must contain exactly: title, url\n"
    "  - Use reputable primary or strong reporting sources when available.\n\n"
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
    "  - If a claim appears in only one credible report or remains partly uncertain, use cautious wording "
    "such as 'reportedly' or 'according to reports'.\n"
    "  - If you cannot support the core claim from searched and cited sources, omit the item entirely.\n\n"
    "ESCALATION RULE:\n"
    "  - If you cannot verify enough meaningful items for a category, return an empty items array for that "
    "category rather than guessing.\n"
    "  - If a source link is missing or unreliable, exclude that item rather than fabricating a citation.\n\n"
    "SCOPE BOUNDARY:\n"
    "  - This is a news briefing, not legal, policy, investment, or engineering advice.\n"
    "  - Summarize only what the sourced reporting supports; do not imply certainty beyond those reports.\n\n"
    "LANGUAGE:\n"
    "  - Write all item titles, descriptions, and source titles in English only.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the response is valid JSON with exactly one top-level key: items.\n"
    "  - Confirm each item has title, description, and sources.\n"
    "  - Confirm every source has title and url.\n"
    "  - Confirm every item is supported by searched/cited sources from the last 7 days.\n\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences."
)


def _extract_json_object(text: str) -> str | None:
    """Best-effort extract a JSON object from text that may contain prose."""
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


def _strip_citation_markup(text: str) -> str:
    """Remove Anthropic inline citation tags that can break JSON strings."""
    return re.sub(r"<cite\b[^>]*>.*?</cite>", "", text, flags=re.IGNORECASE | re.DOTALL)


def _assistant_text(message: object) -> str:
    """Collect text blocks from a Claude message response."""
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


def _parse_items_payload(body: str) -> dict:
    """Parse a JSON object with an items list from Claude output."""
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
    return items if isinstance(items, list) else []


def _normalize_payload(categories: list[dict]) -> dict:
    """Guarantee all three categories exist in the expected order."""
    return {"categories": categories}


def _usage_details(message: object) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    return {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
    }


def _is_rate_limit_error(exc: Exception) -> bool:
    return "rate_limit_error" in str(exc) or "429" in str(exc)


def _is_model_not_found_error(exc: Exception) -> bool:
    return "not_found_error" in str(exc) or "model:" in str(exc)


def _call_category(category: dict, today_utc: datetime, model: str) -> tuple[dict, object]:
    """Generate one AI radar category using a smaller, lower-risk web-search request."""
    today_label = today_utc.date().isoformat()
    user_prompt = (
        f"Today's UTC date is {today_label}.\n"
        f"Search the web and compile {category['title']} for the last {LOOKBACK_DAYS} days.\n"
        f"Focus only on this category: {category['focus']}\n"
        "Use a small number of high-value searches. Return at most 3 items, exactly 1 source per item, "
        "and no inline citation tags. Return the JSON object only."
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
            items = _normalize_items(_parse_items_payload(_assistant_text(msg)))
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
                f"[ai-radar] rate limited during {category['key']} attempt {attempt}/{RATE_LIMIT_RETRIES}; "
                f"sleeping {sleep_for}s",
                flush=True,
            )
            time.sleep(sleep_for)

    raise RuntimeError(f"[ai-radar] exhausted retries for {category['key']}")


@observe(name="ai-radar:generate", as_type="generation")
def _call_ai_radar(today_utc: datetime) -> tuple[dict, object]:
    """Generate the full AI radar payload using smaller sequential category requests."""
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

    usage_details = {"input": total_input, "output": total_output}
    _langfuse_client().update_current_generation(model=model_in_use, usage_details=usage_details)

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
        print(f"[ai-radar] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    _main()
    _langfuse_client().flush()
