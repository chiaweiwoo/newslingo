"""
Model pricing constants — USD per 1 million tokens.

Prices are stored in rates.json and auto-updated daily by the update-rates
GitHub Actions workflow. Do not edit the PRICING dict manually — edit rates.json
or let the workflow update it.
"""

import json
import os

_RATES_FILE = os.path.join(os.path.dirname(__file__), "rates.json")

with open(_RATES_FILE, encoding="utf-8") as _f:
    _rates = json.load(_f)

# USD per 1M tokens — loaded from rates.json
PRICING: dict[str, dict[str, float]] = _rates["models"]

_FALLBACK = {"input": 3.00, "output": 15.00}  # Sonnet-class default if model unknown


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return total cost in USD for the given token counts."""
    prices = PRICING.get(model, _FALLBACK)
    return round(
        (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000,
        6,
    )
