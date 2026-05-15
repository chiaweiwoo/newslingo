"""
Unit tests for job.py Claude calling infrastructure.

Tests _call_claude and _extract_json_array without hitting the real API.
Uses unittest.mock to simulate various Claude response shapes:
  - Normal JSON array
  - Prose before JSON (prefill bypass — should still parse)
  - Code-fenced JSON
  - Truncated array (max_tokens hit mid-response)
  - Length mismatch between results and batch
"""

import json
import os

# job.py imports supabase + anthropic at module level, so we mock those before import
import sys
from unittest.mock import MagicMock, patch

import pytest

# Patch external deps before importing job
sys.modules.setdefault("supabase", MagicMock())
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key")
os.environ.setdefault("YOUTUBE_API_KEY", "fake-key")

# Patch create_client at module level so job.py doesn't connect to real Supabase
with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        import job


def _make_response(text: str):
    """Build a mock anthropic response object with the given text body."""
    msg = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    msg.content = [content_block]
    msg.stop_reason = "end_turn"
    return msg


class TestExtractJsonArray:
    def test_clean_array(self):
        result = job._extract_json_array('[{"a": 1}, {"b": 2}]')
        assert result == '[{"a": 1}, {"b": 2}]'

    def test_prose_before_array(self):
        text = 'Here is the result: [{"title_en": "hello"}] done.'
        result = job._extract_json_array(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed[0]["title_en"] == "hello"

    def test_no_brackets_returns_none(self):
        assert job._extract_json_array("No JSON here at all.") is None

    def test_only_open_bracket_returns_none(self):
        assert job._extract_json_array("[no closing") is None

    def test_code_fenced(self):
        text = '```json\n[{"title_en": "test"}]\n```'
        result = job._extract_json_array(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed[0]["title_en"] == "test"


class TestCallClaude:
    def _patch_claude(self, text: str):
        """Return a context manager that makes claude.messages.create return text."""
        job.claude = MagicMock()
        job.claude.messages.create.return_value = _make_response(text)

    def test_clean_json_array(self):
        # Response body (after prefill '[') completes a valid array
        self._patch_claude('{"title_en": "PM meets King"}, {"title_en": "Flood hits Johor"}]')
        result = job._call_claude("model", "system", "content")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["title_en"] == "PM meets King"

    def test_code_fenced_response(self):
        # Model emits ```json ... ``` despite prefill — extraction fallback must handle it
        body = '```json\n[{"title_en": "Breaking news"}]\n```'
        self._patch_claude(body)
        result = job._call_claude("model", "system", "content")
        assert isinstance(result, list)
        assert result[0]["title_en"] == "Breaking news"

    def test_truncated_array(self):
        # max_tokens hit mid-array — last ']' truncation must recover partial results.
        # Body contains a complete first item then trailing garbage (simulates truncation).
        body_truncated = '{"title_en": "Article one"}]  some trailing garbage'
        self._patch_claude(body_truncated)
        # Should not raise — truncation to last ] recovers the valid part
        result = job._call_claude("model", "system", "content")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_raises_after_two_failures(self):
        # Complete garbage — all parse strategies fail
        self._patch_claude("I am totally unable to help with this request.")
        with pytest.raises(ValueError, match="failed after 2 attempts"):
            job._call_claude("model", "system", "content")

    def test_no_prefill_mode_parses_clean_array(self):
        # use_prefill=False (Sonnet mode): model returns a complete JSON array without prefill
        self._patch_claude('[{"score": 5}, {"score": 3}]')
        result = job._call_claude("model", "system", "content", use_prefill=False)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["score"] == 5

    def test_no_prefill_mode_extracts_from_prose(self):
        # Model emits brief preamble then JSON — extraction fallback must recover it
        self._patch_claude('Here are the results:\n[{"score": 4}, {"score": 2, "reason": "bad"}]')
        result = job._call_claude("model", "system", "content", use_prefill=False)
        assert isinstance(result, list)
        assert result[1]["reason"] == "bad"


class TestTranslateBatch:
    """Tests for _translate_batch — verifying classify flag behaviour."""

    def _rows(self, n: int = 3) -> list[dict]:
        return [
            {
                "title_zh": f"标题{i}",
                "title_en": None,
                "category": "Singapore",  # pre-set by URL for zaobao
                "source_url": f"https://zaobao.com/news/singapore/story{i}",
            }
            for i in range(n)
        ]

    def _astro_rows(self, n: int = 2) -> list[dict]:
        return [
            {
                "title_zh": f"马来西亚新闻{i}",
                "title_en": None,
                "category": None,  # filled by LLM for astro
                "source_url": f"https://youtube.com/watch?v=vid{i}",
            }
            for i in range(n)
        ]

    def test_classify_false_does_not_overwrite_category(self):
        """Zaobao: category set by URL must survive translation (classify=False)."""
        job.claude = MagicMock()
        job.claude.messages.create.return_value = _make_response(
            '[{"title_en": "Title 0"}, {"title_en": "Title 1"}, {"title_en": "Title 2"}]'
        )
        rows = self._rows(3)
        result = job._translate_batch("zaobao", rows, "prompt", classify=False)
        # All categories must still be "Singapore" (not overwritten by LLM)
        for row in result:
            assert row["category"] == "Singapore", (
                f"classify=False must never overwrite category, but got {row['category']!r}"
            )

    def test_classify_true_sets_category_from_llm(self):
        """Astro: category must be filled by the LLM result (classify=True)."""
        job.claude = MagicMock()
        job.claude.messages.create.return_value = _make_response(
            '[{"title_en": "Local news", "category": "Malaysia"}, '
            '{"title_en": "World event", "category": "International"}]'
        )
        rows = self._astro_rows(2)
        result = job._translate_batch("astro", rows, "prompt", classify=True)
        assert result[0]["category"] == "Malaysia"
        assert result[1]["category"] == "International"

    def test_length_mismatch_does_not_raise(self):
        """Claude returning fewer items than batch must not raise IndexError."""
        job.claude = MagicMock()
        # Only 1 result for 3 inputs
        job.claude.messages.create.return_value = _make_response(
            '[{"title_en": "Only one result"}]'
        )
        rows = self._rows(3)
        # Must not raise — missing items keep their original title_zh as title_en
        result = job._translate_batch("zaobao", rows, "prompt", classify=False)
        assert len(result) == 3
        assert result[0]["title_en"] == "Only one result"
        assert result[1]["title_en"] == "标题1"  # fallback to title_zh
        assert result[2]["title_en"] == "标题2"


class TestValidateZaobaoCategories:
    def test_passes_when_all_categories_set(self):
        rows = [{"category": "Singapore"}, {"category": "International"}]
        # Should not raise
        job._validate_zaobao_categories(rows, "test-stage")

    def test_raises_on_none_category(self):
        rows = [{"category": "Singapore"}, {"category": None, "source_url": "https://example.com/bad"}]
        with pytest.raises(AssertionError, match="INVARIANT VIOLATION"):
            job._validate_zaobao_categories(rows, "test-stage")

    def test_raises_on_empty_string_category(self):
        rows = [{"category": ""}]
        with pytest.raises(AssertionError, match="INVARIANT VIOLATION"):
            job._validate_zaobao_categories(rows, "test-stage")
