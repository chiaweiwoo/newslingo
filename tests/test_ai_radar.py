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
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("GEMINI_API_KEY", "fake-gemini-key")

with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        with patch("google.genai.Client", return_value=MagicMock()):
            import ai_radar


def _usage(input_tokens: int, output_tokens: int):
    return types.SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def _make_deepseek_response(text: str, in_tok: int = 100, out_tok: int = 200):
    msg = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg.content = [block]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


class TestModelAndPromptConfig:
    def test_models_use_gemini_and_deepseek(self):
        assert ai_radar.AI_RADAR_MODEL == "gemini-3.5-flash"
        assert ai_radar.AI_RADAR_DISCOVERY_MODEL == "gemini-3.5-flash"
        assert ai_radar.AI_RADAR_TRANSLATION_MODEL == "deepseek-v4-flash"

    def test_translation_prompt_contract_present(self):
        prompt = ai_radar.AI_RADAR_TRANSLATION_SYSTEM_PROMPT
        assert '"title_zh"' in prompt
        assert '"description_zh"' in prompt
        assert "Return ONLY the JSON array" in prompt

    def test_search_prompt_contract_present(self):
        prompt = ai_radar.AI_RADAR_SYSTEM_PROMPT
        assert '"sources"' in prompt
        assert "last 7 days" in prompt
        assert "Return ONLY the JSON object" in prompt


class TestJsonParsing:
    def test_extract_json_object_from_prose_output(self):
        text = 'Here you go:\n{"items": []}\nDone.'
        assert ai_radar._extract_json_object(text) == '{"items": []}'

    def test_parse_items_payload_accepts_valid_object(self):
        payload = ai_radar._parse_items_payload('{"items": []}')
        assert payload == {"items": []}

    def test_normalize_items_filters_bad_rows(self):
        items = ai_radar._normalize_items(
            {
                "items": [
                    {"title": "A", "description": "B", "sources": [{"title": "S", "url": "https://x"}]},
                    {"title": "", "description": "B", "sources": []},
                ]
            }
        )
        assert len(items) == 1
        assert items[0]["sources"][0]["title"] == "S"


class TestCallAiRadar:
    def test_call_category_uses_grounded_gemini(self):
        with patch.object(
            ai_radar,
            "_call_gemini_json",
            return_value=(
                json.dumps({"items": [{"title": "A", "description": "B", "sources": [{"title": "S", "url": "https://x"}]}]}),
                _usage(10, 5),
            ),
        ) as call_gemini:
            result, usage = ai_radar._call_category(
                ai_radar.CATEGORY_SPECS[0],
                datetime(2026, 5, 20, tzinfo=timezone.utc),
            )

        kwargs = call_gemini.call_args.kwargs
        assert kwargs["use_search"] is True
        assert result["key"] == "governance"
        assert usage.input_tokens == 10

    def test_call_ai_radar_combines_category_results(self):
        with patch.object(
            ai_radar,
            "_call_category",
            side_effect=[
                (
                    {"key": "governance", "title": "AI Governance Radar", "items": [{"title": "A", "description": "B", "sources": []}]},
                    _usage(100, 50),
                ),
                (
                    {"key": "product", "title": "AI Product Radar", "items": []},
                    _usage(120, 40),
                ),
                (
                    {"key": "infrastructure", "title": "AI Infrastructure Radar", "items": []},
                    _usage(80, 30),
                ),
            ],
        ), patch.object(
            ai_radar,
            "_translate_categories_to_zh",
            return_value=(
                [
                    {"key": "governance", "title": "AI Governance Radar", "items": [{"title": "A", "description": "B", "title_zh": "甲", "description_zh": "乙", "sources": []}]},
                    {"key": "product", "title": "AI Product Radar", "items": []},
                    {"key": "infrastructure", "title": "AI Infrastructure Radar", "items": []},
                ],
                _usage(20, 10),
            ),
        ):
            payload, usage = ai_radar._call_ai_radar(datetime(2026, 5, 20, tzinfo=timezone.utc))

        assert [category["key"] for category in payload["categories"]] == ["governance", "product", "infrastructure"]
        assert usage.input_tokens == 320
        assert usage.output_tokens == 130

    def test_translate_categories_to_zh_merges_fields(self):
        ai_radar.deepseek = MagicMock()
        ai_radar.deepseek.messages.create.return_value = _make_deepseek_response(
            '[{"idx":0,"title_zh":"标题","description_zh":"描述"}]'
        )

        categories, usage = ai_radar._translate_categories_to_zh(
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

        ai_radar.supabase = MagicMock()
        ai_radar.supabase.table.return_value = mock_table

        ai_radar._store_radar(
            datetime(2026, 5, 20, tzinfo=timezone.utc),
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
                    "window_start": "2026-05-13",
                    "window_end": "2026-05-20",
                    "payload": {"categories": []},
                    "active": True,
                }
            ),
            call().insert().execute(),
        ]
