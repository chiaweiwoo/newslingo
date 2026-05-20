"""
Unit tests for feed_ingest.py LLM calling infrastructure.

Tests JSON extraction, provider routing, and DeepSeek thinking policy
without hitting real external APIs.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault("supabase", MagicMock())
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("YOUTUBE_API_KEY", "fake-key")

with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        import feed_ingest


def _make_response(text: str, stop_reason: str = "end_turn", in_tok: int = 10, out_tok: int = 20):
    msg = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    msg.content = [content_block]
    msg.stop_reason = stop_reason
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


class TestExtractJsonArray:
    def test_clean_array(self):
        result = feed_ingest._extract_json_array('[{"a": 1}, {"b": 2}]')
        assert result == '[{"a": 1}, {"b": 2}]'

    def test_prose_before_array(self):
        text = 'Here is the result: [{"title_en": "hello"}] done.'
        result = feed_ingest._extract_json_array(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed[0]["title_en"] == "hello"

    def test_no_brackets_returns_none(self):
        assert feed_ingest._extract_json_array("No JSON here at all.") is None

    def test_code_fenced(self):
        text = '```json\n[{"title_en": "test"}]\n```'
        result = feed_ingest._extract_json_array(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed[0]["title_en"] == "test"


class TestCallModel:
    def _patch_deepseek(self, text: str):
        feed_ingest.deepseek = MagicMock()
        feed_ingest.deepseek.messages.create.return_value = _make_response(text)

    def test_clean_json_array(self):
        self._patch_deepseek('{"title_en": "PM meets King"}, {"title_en": "Flood hits Johor"}]')
        result = feed_ingest._call_model(feed_ingest.deepseek, "model", "system", "content")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["title_en"] == "PM meets King"

    def test_no_prefill_mode_extracts_from_prose(self):
        self._patch_deepseek('Here are the results:\n[{"score": 4}, {"score": 2, "reason": "bad"}]')
        result = feed_ingest._call_model(feed_ingest.deepseek, "model", "system", "content", use_prefill=False)
        assert isinstance(result, list)
        assert result[1]["reason"] == "bad"

    def test_raises_after_two_failures(self):
        self._patch_deepseek("I am totally unable to help with this request.")
        with pytest.raises(ValueError, match="_call_model failed after 2 attempts"):
            feed_ingest._call_model(feed_ingest.deepseek, "model", "system", "content")

    def test_passes_thinking_and_output_config(self):
        self._patch_deepseek('[{"rule": "x"}]')
        feed_ingest._call_model(
            feed_ingest.deepseek,
            "deepseek-v4-pro",
            "system",
            "content",
            thinking=feed_ingest.THINKING_ENABLED,
            output_config=feed_ingest.DISTILL_OUTPUT_CONFIG,
            use_prefill=False,
        )
        kwargs = feed_ingest.deepseek.messages.create.call_args.kwargs
        assert kwargs["thinking"] == {"type": "enabled"}
        assert kwargs["output_config"] == {"effort": "high"}


class TestTranslateBatch:
    def _rows(self, n: int = 3) -> list[dict]:
        return [
            {
                "title_zh": f"title{i}",
                "title_en": None,
                "category": "Singapore",
                "source_url": f"https://zaobao.com/news/singapore/story{i}",
            }
            for i in range(n)
        ]

    def _astro_rows(self, n: int = 2) -> list[dict]:
        return [
            {
                "title_zh": f"astro{i}",
                "title_en": None,
                "category": None,
                "source_url": f"https://youtube.com/watch?v=vid{i}",
            }
            for i in range(n)
        ]

    def test_classify_false_does_not_overwrite_category(self):
        feed_ingest.deepseek = MagicMock()
        feed_ingest.deepseek.messages.create.return_value = _make_response(
            '[{"title_en": "Title 0"}, {"title_en": "Title 1"}, {"title_en": "Title 2"}]'
        )
        rows = self._rows(3)
        result = feed_ingest._translate_batch("zaobao", rows, "prompt", classify=False)
        for row in result:
            assert row["category"] == "Singapore"

    def test_classify_true_sets_category_from_llm(self):
        feed_ingest.deepseek = MagicMock()
        feed_ingest.deepseek.messages.create.return_value = _make_response(
            '[{"title_en": "Local news", "category": "Malaysia"}, '
            '{"title_en": "World event", "category": "International"}]'
        )
        rows = self._astro_rows(2)
        result = feed_ingest._translate_batch("astro", rows, "prompt", classify=True)
        assert result[0]["category"] == "Malaysia"
        assert result[1]["category"] == "International"

    def test_translation_uses_deepseek_flash_with_thinking_disabled(self):
        feed_ingest.deepseek = MagicMock()
        feed_ingest.deepseek.messages.create.return_value = _make_response('[{"title_en": "Only one result"}]')
        rows = self._rows(1)
        feed_ingest._translate_batch("zaobao", rows, "prompt", classify=False)
        kwargs = feed_ingest.deepseek.messages.create.call_args.kwargs
        assert kwargs["model"] == feed_ingest.TRANSLATE_MODEL
        assert kwargs["thinking"] == feed_ingest.THINKING_DISABLED


class TestAssessmentAndDistillRouting:
    def test_assessment_uses_deepseek_pro_with_thinking_disabled(self):
        feed_ingest.deepseek = MagicMock()
        feed_ingest.deepseek.messages.create.return_value = _make_response('[{"score": 5}]')
        rows = [{"title_zh": "x", "title_en": "y"}]
        feed_ingest.assess_translations(rows, "astro")
        kwargs = feed_ingest.deepseek.messages.create.call_args.kwargs
        assert kwargs["model"] == feed_ingest.ASSESS_MODEL
        assert kwargs["thinking"] == feed_ingest.THINKING_DISABLED

    def test_distill_uses_deepseek_pro_with_thinking_enabled(self):
        feed_ingest.deepseek = MagicMock()
        feed_ingest.deepseek.messages.create.return_value = _make_response('["Use official titles"]')
        mock_result = MagicMock()
        mock_result.data = [{"sample_failures": [{"zh": "a", "en": "b", "suggestion": "c", "reason": "d"}]}]
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.not_.is_.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        mock_table.update.return_value.eq.return_value.execute.return_value = None
        mock_table.insert.return_value.execute.return_value = None
        feed_ingest.supabase = MagicMock()
        feed_ingest.supabase.table.return_value = mock_table

        feed_ingest._distill_rules("astro", 3)
        kwargs = feed_ingest.deepseek.messages.create.call_args.kwargs
        assert kwargs["model"] == feed_ingest.DISTILL_MODEL
        assert kwargs["thinking"] == feed_ingest.THINKING_ENABLED
        assert kwargs["output_config"] == feed_ingest.DISTILL_OUTPUT_CONFIG


class TestConfig:
    def test_models_are_deepseek(self):
        assert feed_ingest.TRANSLATE_MODEL == "deepseek-v4-flash"
        assert feed_ingest.ASSESS_MODEL == "deepseek-v4-pro"
        assert feed_ingest.DISTILL_MODEL == "deepseek-v4-pro"

    def test_missing_deepseek_key_fails_import(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        module_path = Path(__file__).resolve().parents[1] / "feed_ingest.py"
        spec = importlib.util.spec_from_file_location("feed_ingest_missing_deepseek", module_path)
        module = importlib.util.module_from_spec(spec)
        with patch("supabase.create_client", return_value=MagicMock()):
            with patch("anthropic.Anthropic", return_value=MagicMock()):
                with patch("dotenv.load_dotenv", return_value=None):
                    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
                        assert spec.loader is not None
                        spec.loader.exec_module(module)
