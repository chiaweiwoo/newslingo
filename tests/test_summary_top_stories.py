"""
Unit tests for summary_top_stories.py.
"""

import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

sys.modules.setdefault("supabase", MagicMock())
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-anthropic-key")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key")

with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        import summary_top_stories


def _make_llm_response(text: str, in_tok: int = 100, out_tok: int = 200):
    msg = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg.content = [block]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


class TestConstants:
    def test_lookback_days_is_7(self):
        assert summary_top_stories.LOOKBACK_DAYS == 7

    def test_models_use_claude_and_deepseek(self):
        assert summary_top_stories.SUMMARY_MODEL == "claude-sonnet-4-6"
        assert summary_top_stories.SUMMARY_FACTCHECK_MODEL == "claude-sonnet-4-6"
        assert summary_top_stories.SUMMARY_TRANSLATION_MODEL == "deepseek-v4-flash"


class TestPromptContracts:
    def test_summary_prompt_requires_topics_json(self):
        prompt = summary_top_stories.SUMMARY_SYSTEM_PROMPT
        assert '"topics"' in prompt
        assert "8 to 10" in prompt
        assert "Return ONLY the JSON object" in prompt

    def test_factcheck_prompt_requires_topics_json(self):
        prompt = summary_top_stories.FACT_CHECK_SYSTEM_PROMPT
        assert '"topics"' in prompt
        assert "Return ONLY the JSON object" in prompt

    def test_translation_prompt_requires_json_array(self):
        prompt = summary_top_stories.CHINESE_TRANSLATION_SYSTEM_PROMPT
        assert '"title_zh"' in prompt
        assert '"summary_zh"' in prompt
        assert "Return ONLY the JSON array" in prompt


class TestHelpers:
    def test_extract_json_object_from_prose(self):
        text = 'Here:\n{"topics": [{"title": "A"}]}\nDone.'
        assert summary_top_stories._extract_json_object(text) == '{"topics": [{"title": "A"}]}'

    def test_extract_json_array_from_prose(self):
        text = 'Here:\n[{"idx": 0}]\nDone.'
        assert summary_top_stories._extract_json_array(text) == '[{"idx": 0}]'

    def test_sanitize_topic_rejects_invalid_region(self):
        assert summary_top_stories._sanitize_topic(
            {"title": "A", "summary": "B", "region": "Bad", "theme": "Politics"}
        ) is None

    def test_build_content_groups_regions(self):
        content = summary_top_stories._build_content(
            [
                {"title_en": "One", "title_zh": "一", "category": "International"},
                {"title_en": "Two", "title_zh": "二", "category": "Singapore"},
            ]
        )
        assert "[INTERNATIONAL]" in content
        assert "[SINGAPORE]" in content


class TestCallSummary:
    def test_call_summary_runs_generate_factcheck_translate(self):
        summary_top_stories.claude = MagicMock()
        summary_top_stories.deepseek = MagicMock()
        summary_top_stories.claude.messages.create.side_effect = [
            _make_llm_response(
                json.dumps(
                    {
                        "topics": [
                            {
                                "title": "A",
                                "summary": "A sum",
                                "region": "International",
                                "theme": "Politics",
                            }
                        ]
                    }
                ),
                in_tok=10,
                out_tok=5,
            ),
            _make_llm_response(
                json.dumps(
                    {
                        "topics": [
                            {
                                "title": "A",
                                "summary": "A sum",
                                "region": "International",
                                "theme": "Politics",
                            }
                        ]
                    }
                ),
                in_tok=12,
                out_tok=6,
            ),
        ]
        summary_top_stories.deepseek.messages.create.return_value = _make_llm_response(
            '[{"idx":0,"title_zh":"甲","summary_zh":"乙"}]',
            in_tok=9,
            out_tok=4,
        )

        payload, usage = summary_top_stories._call_summary("HEADLINES: x")

        assert summary_top_stories.claude.messages.create.call_count == 2
        assert summary_top_stories.deepseek.messages.create.call_count == 1
        assert payload["topics"][0]["title_zh"] == "甲"
        assert usage.input_tokens == 31
        assert usage.output_tokens == 15

    def test_call_summary_emits_count_logs(self):
        summary_top_stories.claude = MagicMock()
        summary_top_stories.deepseek = MagicMock()
        summary_top_stories.claude.messages.create.side_effect = [
            _make_llm_response(
                json.dumps(
                    {
                        "topics": [
                            {
                                "title": "A",
                                "summary": "A sum",
                                "region": "International",
                                "theme": "Politics",
                            }
                        ]
                    }
                )
            ),
            _make_llm_response(
                json.dumps(
                    {
                        "topics": [
                            {
                                "title": "A",
                                "summary": "A sum",
                                "region": "International",
                                "theme": "Politics",
                            }
                        ]
                    }
                )
            ),
        ]
        summary_top_stories.deepseek.messages.create.return_value = _make_llm_response(
            '[{"idx":0,"title_zh":"甲","summary_zh":"乙"}]'
        )

        with patch("builtins.print") as mock_print:
            summary_top_stories._call_summary("HEADLINES: x")

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        assert "[summary] pass-1: 1 topics generated" in printed
        assert "[summary] pass-2: 1 topics retained" in printed
        assert "[summary] pass-3: 1 topics translated to Chinese" in printed

    def test_pass1_and_pass2_share_cached_headlines_block(self):
        summary_top_stories.claude = MagicMock()
        summary_top_stories.deepseek = MagicMock()
        summary_top_stories.claude.messages.create.side_effect = [
            _make_llm_response('{"topics": []}'),
            _make_llm_response('{"topics": []}'),
        ]
        summary_top_stories.deepseek.messages.create.return_value = _make_llm_response("[]")

        summary_top_stories._call_summary("HEADLINES: some content")
        calls = summary_top_stories.claude.messages.create.call_args_list
        first_system = calls[0].kwargs["system"]
        second_system = calls[1].kwargs["system"]
        assert isinstance(first_system, list)
        assert isinstance(second_system, list)
        assert first_system[0]["text"] == second_system[0]["text"]
        assert first_system[0]["cache_control"] == {"type": "ephemeral"}

    def test_translation_pass_preserves_zh_fields(self):
        summary_top_stories.claude = MagicMock()
        summary_top_stories.deepseek = MagicMock()
        summary_top_stories.claude.messages.create.side_effect = [
            _make_llm_response(
                '{"topics":[{"title":"A","summary":"A sum","region":"International","theme":"Politics"}]}'
            ),
            _make_llm_response(
                '{"topics":[{"title":"A","summary":"A sum","region":"International","theme":"Politics"}]}'
            ),
        ]
        summary_top_stories.deepseek.messages.create.return_value = _make_llm_response(
            '[{"idx":0,"title_zh":"甲","summary_zh":"乙"}]'
        )

        payload, _usage = summary_top_stories._call_summary("HEADLINES: x")

        assert payload["topics"][0]["title_zh"] == "甲"
        assert payload["topics"][0]["summary_zh"] == "乙"


class TestMain:
    def test_main_runs_without_incremental_skip(self):
        with (
            patch.object(
                summary_top_stories,
                "_load_previous_summary",
                return_value={"id": "old", "created_at": "2026-05-19T00:00:00+00:00"},
            ),
            patch.object(
                summary_top_stories,
                "_load_recent_headlines",
                return_value=[{"title_en": "One", "title_zh": "一", "category": "International"}],
            ) as mock_load_recent,
            patch.object(summary_top_stories, "_build_content", return_value="HEADLINES: x"),
            patch.object(
                summary_top_stories,
                "_call_summary",
                return_value=({"topics": [{"title": "A"}]}, MagicMock()),
            ) as mock_call_summary,
            patch.object(summary_top_stories, "_store_summary") as mock_store,
            patch("builtins.print") as mock_print,
        ):
            summary_top_stories._main()

        mock_load_recent.assert_called_once()
        mock_call_summary.assert_called_once_with("HEADLINES: x")
        mock_store.assert_called_once()
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        assert "new headlines since last summary" not in printed
        assert "fewer than" not in printed


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

        assert summary_top_stories.supabase.table.call_count == 2
        assert summary_top_stories.supabase.table.call_args_list == [
            call("weekly_summary"),
            call("weekly_summary"),
        ]
        mock_table.update.assert_called_once_with({"active": False})
        mock_table.update.return_value.eq.assert_called_once_with("id", "old-id")
        mock_table.insert.assert_called_once_with(
            {
                "week_start": "2026-05-13",
                "week_end": "2026-05-20",
                "payload": {"topics": []},
                "active": True,
            }
        )
