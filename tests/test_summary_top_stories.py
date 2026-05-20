"""
Unit tests for summary_top_stories.py.
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

sys.modules.setdefault("supabase", MagicMock())
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key")

with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        with patch("google.genai.Client", return_value=MagicMock()):
            import summary_top_stories


def _usage(input_tokens: int, output_tokens: int):
    return types.SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


class TestConstants:
    def test_lookback_days_is_7(self):
        assert summary_top_stories.LOOKBACK_DAYS == 7

    def test_models_routed_to_gemini_and_deepseek(self):
        assert summary_top_stories.SUMMARY_DISCOVERY_MODEL == "gemini-3.5-flash"
        assert summary_top_stories.SUMMARY_MODEL == "gemini-3.5-flash"
        assert summary_top_stories.SUMMARY_TRANSLATION_MODEL == "deepseek-v4-flash"


class TestPromptContracts:
    def test_translation_prompt_mentions_required_fields(self):
        prompt = summary_top_stories.CHINESE_TRANSLATION_SYSTEM_PROMPT
        assert "Simplified Chinese" in prompt
        assert '"title_zh"' in prompt
        assert '"summary_zh"' in prompt
        assert "Return ONLY the JSON array" in prompt

    def test_discovery_prompt_requires_json_only(self):
        prompt = summary_top_stories.DISCOVERY_SYSTEM_PROMPT
        assert '"items"' in prompt
        assert "Return ONLY the JSON object" in prompt
        assert "last 7 days" in prompt

    def test_selection_prompt_requires_topics_schema(self):
        prompt = summary_top_stories.SELECTION_SYSTEM_PROMPT
        assert '"topics"' in prompt
        assert "8 to 10 total topics" in prompt
        assert "Return ONLY the JSON object" in prompt


class TestCallSummary:
    def test_call_summary_runs_three_discoveries_then_selects_and_translates(self):
        with patch.object(
            summary_top_stories,
            "_discover_region_candidates",
            side_effect=[
                ([{"title": "A", "summary": "A sum", "region": "International", "theme": "Politics"}], _usage(10, 5)),
                ([{"title": "B", "summary": "B sum", "region": "Singapore", "theme": "Society"}], _usage(12, 6)),
                ([{"title": "C", "summary": "C sum", "region": "Malaysia", "theme": "Economy"}], _usage(14, 7)),
            ],
        ) as discover, patch.object(
            summary_top_stories,
            "_select_topics",
            return_value=(
                {"topics": [{"title": "A", "summary": "A sum", "region": "International", "theme": "Politics"}]},
                _usage(20, 8),
            ),
        ) as select, patch.object(
            summary_top_stories,
            "_translate_topics_to_zh",
            return_value=(
                {
                    "topics": [
                        {
                            "title": "A",
                            "summary": "A sum",
                            "region": "International",
                            "theme": "Politics",
                            "title_zh": "甲",
                            "summary_zh": "乙",
                        }
                    ]
                },
                _usage(9, 4),
            ),
        ) as translate:
            payload, usage = summary_top_stories._call_summary(datetime(2026, 5, 20, tzinfo=timezone.utc))

        assert discover.call_count == 3
        select.assert_called_once()
        translate.assert_called_once()
        assert payload["topics"][0]["title_zh"] == "甲"
        assert usage.input_tokens == 65
        assert usage.output_tokens == 30

    def test_extract_json_object_recovers_from_prose(self):
        text = 'Here:\n{"topics": [{"title": "A"}]}\nDone.'
        assert summary_top_stories._extract_json_object(text) == '{"topics": [{"title": "A"}]}'

    def test_sanitize_topic_rejects_invalid_region(self):
        assert summary_top_stories._sanitize_topic(
            {"title": "A", "summary": "B", "region": "Bad", "theme": "Politics"}
        ) is None


class TestRotation:
    def test_store_summary_deactivates_previous_before_insert(self):
        mock_table = MagicMock()
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_table.insert.return_value.execute.return_value = MagicMock()

        summary_top_stories.supabase = MagicMock()
        summary_top_stories.supabase.table.return_value = mock_table

        summary_top_stories._store_summary(
            datetime(2026, 5, 20, tzinfo=timezone.utc),
            {"topics": []},
            {"id": "old-id"},
        )

        assert summary_top_stories.supabase.table.mock_calls == [
            call("weekly_summary"),
            call().update({"active": False}),
            call().update().eq("id", "old-id"),
            call().update().eq().execute(),
            call("weekly_summary"),
            call().insert(
                {
                    "week_start": "2026-05-13",
                    "week_end": "2026-05-20",
                    "payload": {"topics": []},
                    "active": True,
                }
            ),
            call().insert().execute(),
        ]
