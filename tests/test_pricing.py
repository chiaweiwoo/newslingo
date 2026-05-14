"""
Pricing tests — unit-level checks for pricing.py and token_usage insert invariants.

Covers:
  - get_model_rates() shape and fallback behaviour
  - compute_cost_usd() arithmetic
  - All token_usage insert sites must carry price snapshot columns
  - schema.sql must declare the price snapshot columns
"""

import importlib
import os
import re
import sys

import pytest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def read_source(path: str) -> str:
    full = os.path.join(PROJECT_ROOT, path)
    with open(full, encoding="utf-8") as f:
        return f.read()


# ── pricing.py unit tests ─────────────────────────────────────────────────────

class TestGetModelRates:
    """get_model_rates() must return a dict with float input/output keys."""

    @pytest.fixture(autouse=True)
    def import_pricing(self):
        # Force a fresh import in case a previous test mutated the module
        if "pricing" in sys.modules:
            del sys.modules["pricing"]
        sys.path.insert(0, PROJECT_ROOT)
        import pricing as p
        self.pricing = p
        yield
        sys.path.pop(0)

    def test_returns_dict_with_input_output_keys(self):
        # Use any model that is tracked in rates.json
        rates = self.pricing.get_model_rates("claude-sonnet-4-6")
        assert isinstance(rates, dict), "get_model_rates must return a dict"
        assert "input" in rates, "rates dict must have 'input' key"
        assert "output" in rates, "rates dict must have 'output' key"

    def test_values_are_positive_floats(self):
        for model in ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"]:
            rates = self.pricing.get_model_rates(model)
            assert isinstance(rates["input"], float), f"{model} input rate must be float"
            assert isinstance(rates["output"], float), f"{model} output rate must be float"
            assert rates["input"] > 0, f"{model} input rate must be positive"
            assert rates["output"] > 0, f"{model} output rate must be positive"

    def test_unknown_model_falls_back_to_fallback(self):
        """Unknown model should return _FALLBACK values, not raise."""
        rates = self.pricing.get_model_rates("claude-unknown-model-xyz")
        assert "input" in rates
        assert "output" in rates
        assert rates["input"] == self.pricing._FALLBACK["input"]
        assert rates["output"] == self.pricing._FALLBACK["output"]

    def test_returns_copy_not_reference(self):
        """Mutating the returned dict must not affect PRICING or _FALLBACK."""
        rates = self.pricing.get_model_rates("claude-sonnet-4-6")
        original_input = rates["input"]
        rates["input"] = 9999.0
        # Re-fetch — must not be affected
        rates2 = self.pricing.get_model_rates("claude-sonnet-4-6")
        assert rates2["input"] == original_input, (
            "get_model_rates must return a copy — mutating it must not affect future calls"
        )

    def test_compute_cost_usd_uses_rates(self):
        """compute_cost_usd arithmetic: cost = (in * rate_in + out * rate_out) / 1M."""
        rates = self.pricing.get_model_rates("claude-sonnet-4-6")
        in_tok, out_tok = 100_000, 200_000
        expected = round(
            (in_tok * rates["input"] + out_tok * rates["output"]) / 1_000_000, 6
        )
        actual = self.pricing.compute_cost_usd("claude-sonnet-4-6", in_tok, out_tok)
        assert actual == expected, f"compute_cost_usd returned {actual}, expected {expected}"


# ── token_usage insert invariants ────────────────────────────────────────────

class TestTokenUsagePriceSnapshotInvariant:
    """Every token_usage insert must include price_input_per_1m and price_output_per_1m."""

    INSERT_FILES = [
        ("job.py",             "_record_token_usage"),
        ("digest.py",          "Record token usage"),
        ("weekly_summary.py",  "Record token usage"),
    ]

    def _extract_insert_block(self, src: str, anchor: str) -> str:
        """Return the text from the anchor comment/function up to the next .execute() call."""
        idx = src.find(anchor)
        assert idx != -1, f"anchor {anchor!r} not found in source"
        # Grab from anchor to first .execute() after it
        after = src[idx:]
        end = after.find(".execute()")
        assert end != -1, f"no .execute() after anchor {anchor!r}"
        return after[: end + len(".execute()")]

    @pytest.mark.parametrize("filename,anchor", INSERT_FILES)
    def test_insert_includes_price_input(self, filename, anchor):
        src = read_source(filename)
        block = self._extract_insert_block(src, anchor)
        assert "price_input_per_1m" in block, (
            f"{filename}: token_usage insert near '{anchor}' is missing 'price_input_per_1m'. "
            "Every insert must snapshot the rate used to calculate cost_usd."
        )

    @pytest.mark.parametrize("filename,anchor", INSERT_FILES)
    def test_insert_includes_price_output(self, filename, anchor):
        src = read_source(filename)
        block = self._extract_insert_block(src, anchor)
        assert "price_output_per_1m" in block, (
            f"{filename}: token_usage insert near '{anchor}' is missing 'price_output_per_1m'. "
            "Every insert must snapshot the rate used to calculate cost_usd."
        )

    @pytest.mark.parametrize("filename,anchor", INSERT_FILES)
    def test_insert_calls_get_model_rates(self, filename, anchor):
        src = read_source(filename)
        block = self._extract_insert_block(src, anchor)
        assert "get_model_rates" in block, (
            f"{filename}: token_usage insert near '{anchor}' must call get_model_rates() "
            "to fetch the current rates before inserting."
        )


# ── schema.sql column invariants ─────────────────────────────────────────────

class TestSchemaSnapshotColumns:
    """schema.sql must declare the two price snapshot columns on token_usage."""

    def test_schema_has_price_input_per_1m(self):
        src = read_source("supabase/migrations/schema.sql")
        assert "price_input_per_1m" in src, (
            "schema.sql token_usage table is missing 'price_input_per_1m' column. "
            "Run: ALTER TABLE public.token_usage ADD COLUMN IF NOT EXISTS "
            "price_input_per_1m NUMERIC(10,6);"
        )

    def test_schema_has_price_output_per_1m(self):
        src = read_source("supabase/migrations/schema.sql")
        assert "price_output_per_1m" in src, (
            "schema.sql token_usage table is missing 'price_output_per_1m' column. "
            "Run: ALTER TABLE public.token_usage ADD COLUMN IF NOT EXISTS "
            "price_output_per_1m NUMERIC(10,6);"
        )

    def test_token_usage_table_definition_is_coherent(self):
        """Both columns appear inside the token_usage CREATE TABLE block."""
        src = read_source("supabase/migrations/schema.sql")
        # Find the token_usage block between CREATE TABLE and the closing );
        match = re.search(
            r"CREATE TABLE IF NOT EXISTS public\.token_usage\s*\((.+?)\);",
            src,
            re.DOTALL,
        )
        assert match, "token_usage CREATE TABLE block not found in schema.sql"
        table_block = match.group(1)
        assert "price_input_per_1m" in table_block, (
            "price_input_per_1m not inside the token_usage CREATE TABLE block"
        )
        assert "price_output_per_1m" in table_block, (
            "price_output_per_1m not inside the token_usage CREATE TABLE block"
        )
