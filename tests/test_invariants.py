"""
Invariant tests for architectural rules that should survive refactors.
"""

import os
import re

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def read_source(path: str) -> str:
    full = os.path.join(PROJECT_ROOT, path)
    with open(full, encoding="utf-8") as f:
        return f.read()


class TestZaobaoClassificationInvariant:
    def test_translate_zaobao_url_rows_use_classify_false(self):
        src = read_source("feed_ingest.py")
        assert "classify=False" in src

    def test_translate_zaobao_sea_rows_use_classify_true(self):
        src = read_source("feed_ingest.py")
        match = re.search(r"def translate_zaobao\(.+?\).*?(?=\ndef )", src, re.DOTALL)
        assert match, "translate_zaobao function not found in feed_ingest.py"
        assert "classify=True" in match.group(0)

    def test_zaobao_prompt_has_no_classification_instruction(self):
        src = read_source("feed_ingest.py")
        match = re.search(r"ZAOBAO_SYSTEM_PROMPT\s*=\s*\((.+?)^\)", src, re.DOTALL | re.MULTILINE)
        assert match, "ZAOBAO_SYSTEM_PROMPT not found in feed_ingest.py"
        prompt_body = match.group(1)
        assert "classify" not in prompt_body.lower()
        assert '"category"' not in prompt_body

    def test_validate_zaobao_categories_called_post_scrape(self):
        src = read_source("feed_ingest.py")
        assert "post-scrape" in src

    def test_validate_zaobao_categories_called_post_translate(self):
        src = read_source("feed_ingest.py")
        assert "post-translate" in src

    def test_zaobao_regex_covers_three_sections(self):
        src = read_source("scrapers/zaobao.py")
        for section in ("singapore", "world", "sea"):
            assert section in src

    def test_category_from_url_function_exists(self):
        src = read_source("scrapers/zaobao.py")
        assert "def _category_from_url" in src


class TestAggregateModelInvariant:
    def test_deepseek_models_are_configured_for_job(self):
        src = read_source("feed_ingest.py")
        assert 'TRANSLATE_MODEL    = "deepseek-v4-flash"' in src
        assert 'ASSESS_MODEL       = "deepseek-v4-pro"' in src
        assert 'DISTILL_MODEL      = "deepseek-v4-pro"' in src

    def test_translate_model_uses_no_prefill(self):
        src = read_source("feed_ingest.py")
        match = re.search(r"def _translate_batch\(.+?(?=\ndef )", src, re.DOTALL)
        assert match, "_translate_batch not found"
        assert "use_prefill=False" in match.group(0)

    def test_assess_and_distill_use_no_prefill(self):
        src = read_source("feed_ingest.py")
        assert "use_prefill=False" in src

    def test_deepseek_thinking_policy_is_encoded(self):
        src = read_source("feed_ingest.py")
        assert 'THINKING_DISABLED  = {"type": "disabled"}' in src
        assert 'THINKING_ENABLED   = {"type": "enabled"}' in src
        assert 'DISTILL_OUTPUT_CONFIG = {"effort": "high"}' in src


class TestAstroClassificationInvariant:
    def test_astro_scraper_excludes_shorts(self):
        src = read_source("scrapers/astro.py")
        assert "_is_short" in src
        assert "Shorts" in src

    def test_astro_scraper_returns_none_category(self):
        src = read_source("scrapers/astro.py")
        assert '"category":      None' in src or "'category': None" in src or '"category": None' in src

    def test_zaobao_sea_prompt_has_classification_instruction(self):
        src = read_source("feed_ingest.py")
        match = re.search(r"ZAOBAO_SEA_SYSTEM_PROMPT\s*=\s*\((.+?)^\)", src, re.DOTALL | re.MULTILINE)
        assert match, "ZAOBAO_SEA_SYSTEM_PROMPT not found in feed_ingest.py"
        assert "category" in match.group(1)

    def test_translate_astro_does_not_use_classify_false(self):
        src = read_source("feed_ingest.py")
        match = re.search(r"def translate_astro\(.+?\).*?return", src, re.DOTALL)
        assert match, "translate_astro function not found in feed_ingest.py"
        assert "classify=False" not in match.group(0)
