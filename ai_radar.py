"""
NewsLingo AI Radar job - runs daily at 09:30 SGT.

This job uses Claude Sonnet 4.6 with Anthropic's server-side web search tool
to compile a 14-day AI developments briefing across governance, product, and
infrastructure. Only the latest active row is shown in the frontend drawer.

Non-fatal: any failure is logged and the job exits 0.
"""

import json
import os
import sys
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

AI_RADAR_MODEL = "claude-sonnet-4-6"
LOOKBACK_DAYS = 14
WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 8,
}

AI_RADAR_SYSTEM_PROMPT = (
    "You are a senior AI radar analyst preparing a concise briefing for busy professionals.\n"
    "Your job is to extract the most important AI developments from the last 14 days using web search.\n\n"
    "WINDOW:\n"
    "  - Include only developments from the last 14 days relative to the current date.\n"
    "  - If a development falls outside the window, exclude it.\n"
    "  - Use searched and cited sources only. Do not rely on background knowledge alone.\n\n"
    "CATEGORIES:\n"
    '  - governance -> "AI Governance Radar"\n'
    '  - product -> "AI Product Radar"\n'
    '  - infrastructure -> "AI Infrastructure Radar"\n\n'
    "CATEGORY DEFINITIONS:\n"
    "  governance: AI incidents, harmful behavior, failures, lawsuits, copyright disputes,\n"
    "              enforcement, policy, regulation, operational breakdowns, public backlash\n"
    "  product: major launches, feature releases, agents, copilots, product strategy shifts,\n"
    "           enterprise workflow changes, strong adoption signals, meaningful UX improvements\n"
    "  infrastructure: GPUs, AI chips, datacenters, cloud AI capacity, inference optimization,\n"
    "                  compute shortages, energy and cooling issues, efficiency breakthroughs\n\n"
    "SELECTION STANDARD:\n"
    "  - Include as many items as pass the importance bar. Do not force an exact count.\n"
    "  - Prefer strategic, operational, financial, political, legal, or social significance.\n"
    "  - Prefer concrete real-world impact over hype or speculation.\n"
    "  - Avoid duplicates, incremental minor updates, and repetitive follow-ons.\n"
    "  - If two stories are materially the same development, merge them into one stronger item.\n\n"
    "ITEM RULES:\n"
    "  - title: short English title, no hype, no date\n"
    "  - description: one concise sentence, information-dense, no date, no bullet prefix\n"
    "  - sources: 1 to 3 source objects pulled from the searched/cited material\n"
    "  - Each source object must contain exactly: title, url\n"
    "  - Use reputable primary or strong reporting sources when available.\n\n"
    "OUTPUT FORMAT:\n"
    "{\n"
    '  "categories": [\n'
    "    {\n"
    '      "key": "governance" | "product" | "infrastructure",\n'
    '      "title": "AI Governance Radar" | "AI Product Radar" | "AI Infrastructure Radar",\n'
    '      "items": [\n'
    "        {\n"
    '          "title": "Short title",\n'
    '          "description": "One concise explanation.",\n'
    '          "sources": [{"title": "Source title", "url": "https://example.com"}]\n'
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "REQUIRED SHAPE:\n"
    "  - Return all three categories in this order: governance, product, infrastructure.\n"
    "  - If a category has no qualifying items, return an empty items array for that category.\n"
    "  - Return only valid JSON.\n\n"
    "FACTUAL DISCIPLINE:\n"
    "  - Do not invent company actions, product details, legal outcomes, or infrastructure numbers.\n"
    "  - If a source is ambiguous, write around the uncertainty conservatively.\n"
    "  - Do not include unsupported claims or unattributed rumors.\n\n"
    "SELF-CHECK BEFORE RETURNING:\n"
    "  - Confirm the response is valid JSON and contains exactly three category objects.\n"
    "  - Confirm each item has title, description, and sources.\n"
    "  - Confirm every source has title and url.\n"
    "  - Confirm every item is supported by searched/cited sources from the last 14 days.\n\n"
    "Return ONLY the JSON object. No preamble, no explanation, no markdown fences."
)


def _extract_json_object(text: str) -> str | None:
    """Best-effort extract a JSON object from text that may contain prose."""
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


def _assistant_text(message: object) -> str:
    """Collect text blocks from a Claude message response."""
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(parts).strip()


def _parse_payload(body: str) -> dict:
    """Parse the JSON payload from Claude output."""
    extracted = _extract_json_object(body)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict) and isinstance(parsed.get("categories"), list):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(f"[ai-radar] failed to parse JSON. Body (first 400): {body[:400]!r}")


def _normalize_payload(payload: dict) -> dict:
    """Guarantee all three categories exist in the expected order."""
    canonical = {
        "governance": "AI Governance Radar",
        "product": "AI Product Radar",
        "infrastructure": "AI Infrastructure Radar",
    }

    seen: dict[str, dict] = {}
    for category in payload.get("categories", []):
        key = category.get("key")
        if key not in canonical:
            continue
        items = category.get("items")
        seen[key] = {
            "key": key,
            "title": canonical[key],
            "items": items if isinstance(items, list) else [],
        }

    return {
        "categories": [
            seen.get(key, {"key": key, "title": title, "items": []})
            for key, title in canonical.items()
        ]
    }


def _usage_details(message: object) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    return {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
    }


@observe(name="ai-radar:generate", as_type="generation")
def _call_ai_radar(today_utc: datetime) -> tuple[dict, object]:
    """Generate the AI radar payload using Claude web search."""
    today_label = today_utc.date().isoformat()
    user_prompt = (
        f"Today's UTC date is {today_label}.\n"
        f"Search the web and compile the AI Radar for the last {LOOKBACK_DAYS} days.\n"
        "Return the JSON object only."
    )

    msg = claude.messages.create(
        model=AI_RADAR_MODEL,
        max_tokens=5000,
        system=AI_RADAR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[WEB_SEARCH_TOOL],
    )

    # Handle the rare pause_turn path by continuing the same conversation.
    while getattr(msg, "stop_reason", None) == "pause_turn":
        msg = claude.messages.create(
            model=AI_RADAR_MODEL,
            max_tokens=5000,
            system=AI_RADAR_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": msg.content},
            ],
            tools=[WEB_SEARCH_TOOL],
        )

    usage_details = _usage_details(msg)
    _langfuse_client().update_current_generation(model=AI_RADAR_MODEL, usage_details=usage_details)

    payload = _normalize_payload(_parse_payload(_assistant_text(msg)))
    return payload, msg.usage


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
