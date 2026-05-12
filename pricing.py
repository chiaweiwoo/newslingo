"""
Model pricing constants — USD per 1 million tokens.

Update this file when Anthropic announces price changes.
Current prices last verified: 2026-05.
"""

# USD per 1M tokens
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 1.00,  "output": 5.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":           {"input": 5.00,  "output": 25.00},
}

_FALLBACK = {"input": 3.00, "output": 15.00}  # Sonnet-class default if model unknown


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return total cost in USD for the given token counts."""
    prices = PRICING.get(model, _FALLBACK)
    return round(
        (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000,
        6,
    )
