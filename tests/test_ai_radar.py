"""
Unit tests for ai_radar.py.
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
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key")

with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        import ai_radar


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
    def test_model_is_web_search_compatible_haiku(self):
        assert ai_radar.AI_RADAR_MODEL == "claude-haiku-4-5"
        assert "haiku" in ai_radar.AI_RADAR_MODEL.lower()
        assert ai_radar.AI_RADAR_FALLBACK_MODEL == "claude-sonnet-4-6"

    def test_web_search_tool_is_configured(self):
        tool = ai_radar.WEB_SEARCH_TOOL
        assert tool["type"] == "web_search_20260209"
        assert tool["name"] == "web_search"
        assert tool["max_uses"] == ai_radar.WEB_SEARCH_MAX_USES
        assert tool["allowed_callers"] == ["direct"]

    def test_category_calls_use_smaller_budgets(self):
        assert ai_radar.LOOKBACK_DAYS == 7
        assert ai_radar.WEB_SEARCH_MAX_USES == 2
        assert ai_radar.AI_RADAR_MAX_TOKENS == 1400


class TestPromptContract:
    def test_json_only_instruction_present(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "Return ONLY the JSON object" in prompt
        assert "markdown fences" in prompt

    def test_requires_sources_and_self_check(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert '"sources"' in prompt
        assert "SELF-CHECK" in prompt
        assert "exactly 1 source object" in prompt
        assert "Do not include inline citation markup" in prompt
        assert "10 to 16 words" in prompt

    def test_contains_three_category_keys(self):
        keys = [spec["key"] for spec in ai_radar.CATEGORY_SPECS]
        assert keys == ["governance", "product", "infrastructure"]

    def test_includes_confidence_hedging_and_escalation(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "CONFIDENCE HEDGING" in prompt
        assert "ESCALATION RULE" in prompt

    def test_explicitly_requires_english_output(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "English only" in prompt


class TestJsonParsing:
    def test_extract_json_object_from_fenced_output(self):
        text = '```json\n{"items": []}\n```'
        result = ai_radar._extract_json_object(text)
        assert result == '{"items": []}'

    def test_extract_json_object_from_prose_output(self):
        text = 'Here you go:\n{"items": []}\nDone.'
        result = ai_radar._extract_json_object(text)
        assert result == '{"items": []}'

    def test_parse_items_payload_accepts_valid_object(self):
        payload = ai_radar._parse_items_payload('{"items": []}')
        assert payload == {"items": []}

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
        payload = ai_radar._parse_items_payload(raw)
        assert payload["items"][0]["description"] == " for enterprise users."


class TestCallAiRadar:
    def test_call_category_uses_web_search_tool(self):
        ai_radar.claude = MagicMock()
        ai_radar.claude.messages.create.return_value = _make_claude_response(
            json.dumps({"items": []})
        )

        ai_radar._call_category(ai_radar.CATEGORY_SPECS[0], datetime(2026, 5, 19, tzinfo=timezone.utc), ai_radar.AI_RADAR_MODEL)

        kwargs = ai_radar.claude.messages.create.call_args.kwargs
        assert kwargs["model"] == ai_radar.AI_RADAR_MODEL
        assert kwargs["tools"] == [ai_radar.WEB_SEARCH_TOOL]
        assert kwargs["max_tokens"] == ai_radar.AI_RADAR_MAX_TOKENS

    def test_call_category_pause_turn_retries_with_assistant_content(self):
        ai_radar.claude = MagicMock()
        first = _make_claude_response("Searching...", stop_reason="pause_turn")
        second = _make_claude_response(json.dumps({"items": []}))
        ai_radar.claude.messages.create.side_effect = [first, second]

        ai_radar._call_category(ai_radar.CATEGORY_SPECS[0], datetime(2026, 5, 19, tzinfo=timezone.utc), ai_radar.AI_RADAR_MODEL)

        assert ai_radar.claude.messages.create.call_count == 2
        second_call = ai_radar.claude.messages.create.call_args_list[1].kwargs
        assert second_call["messages"][1]["role"] == "assistant"

    def test_call_ai_radar_combines_category_results(self):
        with patch.object(
            ai_radar,
            "_call_category",
            side_effect=[
                (
                    {"key": "governance", "title": "AI Governance Radar", "items": [{"title": "A", "description": "B", "sources": []}]},
                    types.SimpleNamespace(input_tokens=100, output_tokens=50),
                ),
                (
                    {"key": "product", "title": "AI Product Radar", "items": []},
                    types.SimpleNamespace(input_tokens=120, output_tokens=40),
                ),
                (
                    {"key": "infrastructure", "title": "AI Infrastructure Radar", "items": []},
                    types.SimpleNamespace(input_tokens=80, output_tokens=30),
                ),
            ],
        ):
            payload, usage = ai_radar._call_ai_radar(datetime(2026, 5, 19, tzinfo=timezone.utc))
        keys = [category["key"] for category in payload["categories"]]
        assert keys == ["governance", "product", "infrastructure"]
        assert usage.input_tokens == 300
        assert usage.output_tokens == 120

    def test_call_category_retries_rate_limit_errors(self):
        ai_radar.claude = MagicMock()
        ai_radar.claude.messages.create.side_effect = [
            Exception("429 rate_limit_error"),
            _make_claude_response(json.dumps({"items": []})),
        ]

        with patch("ai_radar.time.sleep") as sleep:
            result, _usage = ai_radar._call_category(ai_radar.CATEGORY_SPECS[0], datetime(2026, 5, 19, tzinfo=timezone.utc), ai_radar.AI_RADAR_MODEL)

        assert result["key"] == "governance"
        sleep.assert_called_once()

    def test_call_ai_radar_falls_back_when_model_missing(self):
        with patch.object(
            ai_radar,
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
            payload, usage = ai_radar._call_ai_radar(datetime(2026, 5, 19, tzinfo=timezone.utc))

        assert [category["key"] for category in payload["categories"]] == ["governance", "product", "infrastructure"]
        assert usage.input_tokens == 30
        assert usage.output_tokens == 15


class TestRotation:
    def test_store_radar_deactivates_previous_before_insert(self):
        mock_table = MagicMock()
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_table.insert.return_value.execute.return_value = MagicMock()

        ai_radar.supabase = MagicMock()
        ai_radar.supabase.table.return_value = mock_table

        ai_radar._store_radar(
            datetime(2026, 5, 19, tzinfo=timezone.utc),
            {"categories": []},
            {"id": "old-id"},
        )

        assert ai_radar.supabase.table.mock_calls == [
            call("ai_radar"),
            call().update({"active": False}),
            call().update().eq("id", "old-id"),
            call().update().eq().execute(),
            call("ai_radar"),
            call().insert(
                {
                    "window_start": "2026-05-12",
                    "window_end": "2026-05-19",
                    "payload": {"categories": []},
                    "active": True,
                }
            ),
            call().insert().execute(),
        ]
