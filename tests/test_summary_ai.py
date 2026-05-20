"""
Unit tests for summary_ai.py.
"""

import json
import os
import sys
import types
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
        import summary_ai


def _make_claude_response(text: str, stop_reason: str = "end_turn", in_tok: int = 100, out_tok: int = 200):
    msg = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg.content = [block]
    msg.stop_reason = stop_reason
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


class TestModelAndToolConfig:
    def test_models_use_claude_and_deepseek(self):
        assert summary_ai.AI_RADAR_MODEL == "claude-haiku-4-5"
        assert summary_ai.AI_RADAR_FALLBACK_MODEL == "claude-sonnet-4-6"
        assert summary_ai.AI_RADAR_TRANSLATION_MODEL == "deepseek-v4-flash"

    def test_web_search_tool_is_configured(self):
        tool = summary_ai.WEB_SEARCH_TOOL
        assert tool["type"] == "web_search_20260209"
        assert tool["name"] == "web_search"
        assert tool["max_uses"] == summary_ai.WEB_SEARCH_MAX_USES
        assert tool["allowed_callers"] == ["direct"]


class TestPromptContract:
    def test_search_prompt_is_broad_and_json_only(self):
        prompt = summary_ai.AI_RADAR_SYSTEM_PROMPT
        assert '"sources"' in prompt
        assert "Return as many qualifying items as fit" in prompt
        assert "Return ONLY the JSON object" in prompt

    def test_translation_prompt_is_json_array(self):
        prompt = summary_ai.AI_RADAR_TRANSLATION_SYSTEM_PROMPT
        assert '"title_zh"' in prompt
        assert '"description_zh"' in prompt
        assert "Return ONLY the JSON array" in prompt


class TestHelpers:
    def test_extract_json_object_from_prose(self):
        text = 'Here:\n{"items": []}\nDone.'
        assert summary_ai._extract_json_object(text) == '{"items": []}'

    def test_parse_items_payload_strips_citation_markup(self):
        raw = """```json
{
  "items": [
    {
      "title": "OpenAI Update",
      "description": "<cite index="2-1">OpenAI launched a feature</cite> for enterprise users.",
      "sources": [{"title": "OpenAI", "url": "https://example.com"}]
    }
  ]
}
```"""
        payload = summary_ai._parse_items_payload(raw)
        assert payload["items"][0]["description"] == " for enterprise users."

    def test_normalize_items_keeps_sources(self):
        items = summary_ai._normalize_items(
            {
                "items": [
                    {"title": "A", "description": "B", "sources": [{"title": "S", "url": "u"}]},
                    {"title": "", "description": "B", "sources": []},
                ]
            }
        )
        assert len(items) == 1
        assert items[0]["sources"] == [{"title": "S", "url": "u"}]


class TestCallAiRadar:
    def test_call_category_uses_claude_web_search(self):
        summary_ai.claude = MagicMock()
        summary_ai.claude.messages.create.return_value = _make_claude_response(
            json.dumps({"items": [{"title": "A", "description": "B", "sources": []}]})
        )

        result, usage = summary_ai._call_category(
            summary_ai.CATEGORY_SPECS[0],
            datetime(2026, 5, 20, tzinfo=timezone.utc),
            summary_ai.AI_RADAR_MODEL,
        )

        kwargs = summary_ai.claude.messages.create.call_args.kwargs
        assert kwargs["model"] == summary_ai.AI_RADAR_MODEL
        assert kwargs["tools"] == [summary_ai.WEB_SEARCH_TOOL]
        assert kwargs["max_tokens"] == summary_ai.AI_RADAR_MAX_TOKENS
        assert result["key"] == "governance"
        assert usage.input_tokens == 100

    def test_call_category_handles_pause_turn(self):
        summary_ai.claude = MagicMock()
        first = _make_claude_response("Searching...", stop_reason="pause_turn")
        second = _make_claude_response(json.dumps({"items": [{"title": "A", "description": "B", "sources": []}]}))
        summary_ai.claude.messages.create.side_effect = [first, second]

        result, _usage = summary_ai._call_category(
            summary_ai.CATEGORY_SPECS[0],
            datetime(2026, 5, 20, tzinfo=timezone.utc),
            summary_ai.AI_RADAR_MODEL,
        )

        assert result["key"] == "governance"
        assert summary_ai.claude.messages.create.call_count == 2

    def test_call_category_emits_count_logs(self):
        summary_ai.claude = MagicMock()
        summary_ai.claude.messages.create.return_value = _make_claude_response(
            json.dumps({"items": [{"title": "A", "description": "B", "sources": []}]})
        )

        with patch("builtins.print") as mock_print:
            summary_ai._call_category(
                summary_ai.CATEGORY_SPECS[0],
                datetime(2026, 5, 20, tzinfo=timezone.utc),
                summary_ai.AI_RADAR_MODEL,
            )

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        assert "[ai-radar] governance items: parsed=1 normalized=1" in printed

    def test_call_ai_radar_falls_back_when_model_missing(self):
        with patch.object(
            summary_ai,
            "_call_category",
            side_effect=[
                Exception("404 not_found_error model: claude-haiku-4-5"),
                (
                    {"key": "governance", "title": "AI Governance Radar", "items": []},
                    types.SimpleNamespace(input_tokens=10, output_tokens=5),
                ),
                (
                    {"key": "product", "title": "AI Product Radar", "items": []},
                    types.SimpleNamespace(input_tokens=10, output_tokens=5),
                ),
                (
                    {"key": "infrastructure", "title": "AI Infrastructure Radar", "items": []},
                    types.SimpleNamespace(input_tokens=10, output_tokens=5),
                ),
            ],
        ):
            payload, usage = summary_ai._call_ai_radar(datetime(2026, 5, 20, tzinfo=timezone.utc))

        assert [category["key"] for category in payload["categories"]] == ["governance", "product", "infrastructure"]
        assert usage.input_tokens == 30
        assert usage.output_tokens == 15

    def test_translate_categories_to_zh_merges_fields(self):
        summary_ai.deepseek = MagicMock()
        summary_ai.deepseek.messages.create.return_value = _make_claude_response(
            '[{"idx":0,"title_zh":"标题","description_zh":"描述"}]'
        )

        categories, usage = summary_ai._translate_categories_to_zh(
            [
                {
                    "key": "governance",
                    "title": "AI Governance Radar",
                    "items": [{"title": "Title", "description": "Desc", "sources": []}],
                }
            ]
        )

        item = categories[0]["items"][0]
        assert item["title_zh"] == "标题"
        assert item["description_zh"] == "描述"
        assert usage.input_tokens == 100
        assert usage.output_tokens == 200


class TestRotation:
    def test_store_radar_deactivates_previous_before_insert(self):
        mock_table = MagicMock()
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_table.insert.return_value.execute.return_value = MagicMock()

        summary_ai.supabase = MagicMock()
        summary_ai.supabase.table.return_value = mock_table

        summary_ai._store_radar(
            datetime(2026, 5, 20, tzinfo=timezone.utc),
            {"categories": []},
            {"id": "old-id"},
        )

        assert summary_ai.supabase.table.mock_calls == [
            call("ai_radar"),
            call().update({"active": False}),
            call().update().eq("id", "old-id"),
            call().update().eq().execute(),
            call("ai_radar"),
            call().insert(
                {
                    "window_start": "2026-05-13",
                    "window_end": "2026-05-20",
                    "payload": {"categories": []},
                    "active": True,
                }
            ),
            call().insert().execute(),
        ]
