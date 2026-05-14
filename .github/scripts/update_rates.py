"""
update_rates.py — fetch Anthropic pricing page, extract model prices via Claude,
update rates.json if prices changed.

rates.json tracks:
  last_checked — updated every run (even when nothing changed)
  last_updated — updated only when prices actually change
  models       — the current prices per model

Strategy: BeautifulSoup strips the pricing page down to plain text before
sending to Claude, dropping the payload from ~1MB of HTML to ~20KB of
readable content.

Usage:
    python .github/scripts/update_rates.py

Env vars required:
    ANTHROPIC_API_KEY  — already in repo secrets
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

import anthropic
from bs4 import BeautifulSoup

RATES_FILE  = "rates.json"
PRICING_URL = "https://www.anthropic.com/pricing"
MODEL       = "claude-haiku-4-5-20251001"

TRACKED_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]

EXTRACT_SYSTEM = (
    "You are a pricing data extractor. "
    "You will receive plain-text content from the Anthropic pricing page. "
    "Extract the API input and output prices (USD per 1 million tokens) for these exact models: "
    + ", ".join(TRACKED_MODELS)
    + ". "
    "Return ONLY a JSON object with this exact structure — no markdown, no explanation:\n"
    '{"claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00}, '
    '"claude-sonnet-4-6": {"input": 3.00, "output": 15.00}, '
    '"claude-opus-4-7": {"input": 5.00, "output": 25.00}}\n'
    "Use the exact model ID strings above as keys. "
    "Values must be floats representing USD per 1M tokens. "
    "If a model is not found on the page, omit it from the output — do not guess. "
    "Return ONLY the JSON object."
)


def fetch_pricing_text() -> str:
    """Fetch the pricing page and return stripped plain text (no HTML tags)."""
    print(f"[update-rates] fetching {PRICING_URL}", flush=True)
    req = urllib.request.Request(
        PRICING_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; pricing-bot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()

    text  = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text  = "\n".join(line for line in lines if line)

    print(f"[update-rates] extracted {len(text):,} chars of plain text (from {len(html):,} bytes HTML)", flush=True)
    return text


def extract_prices_via_claude(page_text: str) -> dict[str, dict[str, float]]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print(f"[update-rates] calling Claude {MODEL} to extract prices", flush=True)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": page_text}],
    )
    body = msg.content[0].text.strip() if msg.content else ""
    print(f"[update-rates] Claude response: {body[:300]}", flush=True)

    first = body.find("{")
    last  = body.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError(f"no JSON object in Claude response: {body[:400]!r}")

    parsed = json.loads(body[first : last + 1])
    if not isinstance(parsed, dict):
        raise ValueError(f"expected dict, got {type(parsed)}")

    result: dict[str, dict[str, float]] = {}
    for model_id, prices in parsed.items():
        if model_id not in TRACKED_MODELS:
            print(f"[update-rates] ignoring unknown model: {model_id!r}", flush=True)
            continue
        if not isinstance(prices, dict) or "input" not in prices or "output" not in prices:
            print(f"[update-rates] skipping malformed entry for {model_id!r}", flush=True)
            continue
        result[model_id] = {
            "input":  float(prices["input"]),
            "output": float(prices["output"]),
        }

    if not result:
        raise ValueError("Claude returned no usable pricing data")

    # Sanity check — reject obviously wrong values
    for model_id, prices in result.items():
        for key in ("input", "output"):
            v = prices[key]
            if not (0.01 <= v <= 200.0):
                raise ValueError(f"price out of range for {model_id} {key}: {v} (expected $0.01–$200 per 1M tokens)")

    return result


def load_rates() -> dict:
    with open(RATES_FILE, encoding="utf-8") as f:
        return json.load(f)


def prices_changed(current: dict[str, dict[str, float]], fetched: dict[str, dict[str, float]]) -> bool:
    for model_id, prices in fetched.items():
        if model_id not in current:
            print(f"[update-rates] new model detected: {model_id}", flush=True)
            return True
        for key in ("input", "output"):
            if abs(current[model_id][key] - prices[key]) > 1e-9:
                print(
                    f"[update-rates] price change: {model_id} {key}: "
                    f"{current[model_id][key]} → {prices[key]}",
                    flush=True,
                )
                return True
    return False


def write_rates(rates: dict) -> None:
    with open(RATES_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rates, f, indent=2)
        f.write("\n")
    print(f"[update-rates] {RATES_FILE} written", flush=True)


def main() -> None:
    print("[update-rates] starting", flush=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        page_text = fetch_pricing_text()
        fetched   = extract_prices_via_claude(page_text)
        rates     = load_rates()
        current   = rates.get("models", {})

        print(f"[update-rates] current:  {current}", flush=True)
        print(f"[update-rates] fetched:  {fetched}", flush=True)

        changed = prices_changed(current, fetched)

        # Always record last_checked
        rates["last_checked"] = today

        if changed:
            rates["last_updated"] = today
            rates["models"]       = fetched
            write_rates(rates)
            print("[update-rates] prices updated — committing", flush=True)
            sys.exit(42)  # signal workflow to commit
        else:
            # Update last_checked on disk but don't commit — use workflow run history instead
            write_rates(rates)
            print(f"[update-rates] no price changes — last_checked updated to {today}, no commit needed", flush=True)
            sys.exit(0)

    except Exception as e:
        print(f"[update-rates] ERROR (non-fatal): {e}", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
