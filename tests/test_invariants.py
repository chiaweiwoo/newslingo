"""
Invariant tests — high-level checks that architectural rules are enforced in code.

These tests read the source code directly (not execute it) to verify that
critical invariants are present in the implementation, preventing accidental regression.
"""

import os
import re

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def read_source(path: str) -> str:
    full = os.path.join(PROJECT_ROOT, path)
    with open(full, encoding="utf-8") as f:
        return f.read()


class TestZaobaoClassificationInvariant:
    """Zaobao category MUST be set from URL — NEVER by the LLM."""

    def test_translate_zaobao_uses_classify_false(self):
        src = read_source("job.py")
        # translate_zaobao must pass classify=False to _translate_batch
        assert "classify=False" in src, (
            "translate_zaobao must call _translate_batch with classify=False. "
            "Zaobao category is set from URL, not the LLM."
        )

    def test_zaobao_prompt_has_no_classification_instruction(self):
        src = read_source("job.py")
        # Find ZAOBAO_SYSTEM_PROMPT content
        match = re.search(
            r'ZAOBAO_SYSTEM_PROMPT\s*=\s*\((.+?)^\)',
            src, re.DOTALL | re.MULTILINE
        )
        assert match, "ZAOBAO_SYSTEM_PROMPT not found in job.py"
        prompt_body = match.group(1)
        assert "classify" not in prompt_body.lower(), (
            "ZAOBAO_SYSTEM_PROMPT must not contain classification instructions — "
            "Zaobao category comes from the URL, not the LLM."
        )
        assert '"category"' not in prompt_body, (
            "ZAOBAO_SYSTEM_PROMPT must not ask for a 'category' key in the output JSON."
        )

    def test_validate_zaobao_categories_called_post_scrape(self):
        src = read_source("job.py")
        assert "post-scrape" in src, (
            "_validate_zaobao_categories must be called with 'post-scrape' stage tag "
            "to catch category=None rows before translation."
        )

    def test_validate_zaobao_categories_called_post_translate(self):
        src = read_source("job.py")
        assert "post-translate" in src, (
            "_validate_zaobao_categories must be called with 'post-translate' stage tag "
            "to catch any accidental category overwrite during translation."
        )

    def test_zaobao_regex_covers_two_sections(self):
        src = read_source("scrapers/zaobao.py")
        # Only singapore and world are in scope — china and sea are deliberately excluded
        for section in ("singapore", "world"):
            assert section in src, (
                f"scrapers/zaobao.py regex must include '{section}' section"
            )
        # china and sea must NOT appear in the regex (out of scope)
        import re as _re
        regex_match = _re.search(r'r".*?/news/\(.*?\).*?"', src)
        if regex_match:
            regex_str = regex_match.group(0)
            assert "china" not in regex_str, "china must not be in the sitemap regex — it is out of scope"
            assert "sea" not in regex_str, "sea must not be in the sitemap regex — it is out of scope"

    def test_category_from_url_function_exists(self):
        src = read_source("scrapers/zaobao.py")
        assert "def _category_from_url" in src, (
            "_category_from_url function must exist in scrapers/zaobao.py"
        )


class TestPrefillInvariant:
    """Model-specific prefill rules must be respected."""

    def test_assess_model_uses_no_prefill(self):
        """claude-sonnet-4-6 does not support prefill — assess call must use use_prefill=False."""
        src = read_source("job.py")
        # The assess call must have use_prefill=False
        assert "use_prefill=False" in src, (
            "_call_claude for assessment/distillation must pass use_prefill=False. "
            "claude-sonnet-4-6 returns HTTP 400 if conversation ends with assistant turn."
        )

    def test_translate_model_uses_prefill_by_default(self):
        """Translation (Haiku) uses prefill — the default use_prefill=True must remain."""
        src = read_source("job.py")
        # _translate_batch calls _call_claude without use_prefill arg → default True
        # Verify _translate_batch does NOT explicitly pass use_prefill=False
        import re
        match = re.search(r'def _translate_batch\(.+?(?=\ndef )', src, re.DOTALL)
        assert match, "_translate_batch not found"
        func_body = match.group(0)
        assert "use_prefill=False" not in func_body, (
            "_translate_batch must not pass use_prefill=False — "
            "Haiku supports prefill and benefits from it for reliable JSON output."
        )


class TestAstroClassificationInvariant:
    """Astro category MUST be set by the LLM in job.py — the scraper returns None."""

    def test_astro_scraper_returns_none_category(self):
        src = read_source("scrapers/astro.py")
        # The _item_to_row function must return category=None
        assert '"category":      None' in src or "'category': None" in src or '"category": None' in src, (
            "scrapers/astro.py _item_to_row must return category=None — "
            "Astro category is classified by the LLM in job.py."
        )

    def test_translate_astro_does_not_use_classify_false(self):
        src = read_source("job.py")
        # translate_astro must NOT disable classification
        # Find the translate_astro function definition
        match = re.search(r'def translate_astro\(.+?\).*?return', src, re.DOTALL)
        assert match, "translate_astro function not found in job.py"
        func_body = match.group(0)
        assert "classify=False" not in func_body, (
            "translate_astro must NOT use classify=False — "
            "Astro category MUST be set by the LLM."
        )
