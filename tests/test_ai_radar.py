"""
Unit tests for ai_radar.py.
"""

import json
import os
import sys
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
    def test_model_is_exactly_sonnet_46(self):
        assert ai_radar.AI_RADAR_MODEL == "claude-sonnet-4-6"
        assert "haiku" not in ai_radar.AI_RADAR_MODEL.lower()

    def test_web_search_tool_is_configured(self):
        tool = ai_radar.WEB_SEARCH_TOOL
        assert tool["type"] == "web_search_20260209"
        assert tool["name"] == "web_search"
        assert tool["max_uses"] == 8


class TestPromptContract:
    def test_json_only_instruction_present(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "Return ONLY the JSON object" in prompt
        assert "markdown fences" in prompt

    def test_requires_sources_and_self_check(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert '"sources"' in prompt
        assert "SELF-CHECK" in prompt

    def test_contains_three_category_keys(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "governance" in prompt
        assert "product" in prompt
        assert "infrastructure" in prompt

    def test_includes_confidence_hedging_and_escalation(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "CONFIDENCE HEDGING" in prompt
        assert "ESCALATION RULE" in prompt

    def test_explicitly_requires_english_output(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert "English only" in prompt


class TestJsonParsing:
    def test_extract_json_object_from_fenced_output(self):
        text = '```json\n{"categories": []}\n```'
        result = ai_radar._extract_json_object(text)
        assert result == '{"categories": []}'

    def test_extract_json_object_from_prose_output(self):
        text = 'Here you go:\n{"categories": []}\nDone.'
        result = ai_radar._extract_json_object(text)
        assert result == '{"categories": []}'

    def test_parse_payload_accepts_valid_object(self):
        payload = ai_radar._parse_payload('{"categories": []}')
        assert payload == {"categories": []}


class TestCallAiRadar:
    def test_claude_call_uses_web_search_tool(self):
        ai_radar.claude = MagicMock()
        ai_radar.claude.messages.create.return_value = _make_claude_response(
            json.dumps(
                {
                    "categories": [
                        {"key": "governance", "title": "AI Governance Radar", "items": []},
                        {"key": "product", "title": "AI Product Radar", "items": []},
                        {"key": "infrastructure", "title": "AI Infrastructure Radar", "items": []},
                    ]
                }
            )
        )

        ai_radar._call_ai_radar(datetime(2026, 5, 19, tzinfo=timezone.utc))

        kwargs = ai_radar.claude.messages.create.call_args.kwargs
        assert kwargs["model"] == ai_radar.AI_RADAR_MODEL
        assert kwargs["tools"] == [ai_radar.WEB_SEARCH_TOOL]

    def test_pause_turn_retries_with_assistant_content(self):
        ai_radar.claude = MagicMock()
        first = _make_claude_response("Searching...", stop_reason="pause_turn")
        second = _make_claude_response(
            json.dumps(
                {
                    "categories": [
                        {"key": "governance", "title": "AI Governance Radar", "items": []},
                        {"key": "product", "title": "AI Product Radar", "items": []},
                        {"key": "infrastructure", "title": "AI Infrastructure Radar", "items": []},
                    ]
                }
            )
        )
        ai_radar.claude.messages.create.side_effect = [first, second]

        ai_radar._call_ai_radar(datetime(2026, 5, 19, tzinfo=timezone.utc))

        assert ai_radar.claude.messages.create.call_count == 2
        second_call = ai_radar.claude.messages.create.call_args_list[1].kwargs
        assert second_call["messages"][1]["role"] == "assistant"

    def test_normalizes_missing_categories(self):
        ai_radar.claude = MagicMock()
        ai_radar.claude.messages.create.return_value = _make_claude_response(
            json.dumps(
                {
                    "categories": [
                        {"key": "product", "title": "AI Product Radar", "items": [{"title": "X", "description": "Y", "sources": []}]}
                    ]
                }
            )
        )

        payload, _usage = ai_radar._call_ai_radar(datetime(2026, 5, 19, tzinfo=timezone.utc))
        keys = [category["key"] for category in payload["categories"]]
        assert keys == ["governance", "product", "infrastructure"]


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
                    "window_start": "2026-05-05",
                    "window_end": "2026-05-19",
                    "payload": {"categories": []},
                    "active": True,
                }
            ),
            call().insert().execute(),
        ]
