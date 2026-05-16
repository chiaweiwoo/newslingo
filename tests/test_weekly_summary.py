"""
Unit tests for weekly_summary.py.

Covers:
  1. Constants — LOOKBACK_DAYS == 14, MIN_NEW_HEADLINES == 60
  2. Chinese prompt quality — required fields and language spec present
  3. Three-pass _call_summary — Pass 3 adds title_zh / summary_zh to topics
  4. Invariant — CHINESE_TRANSLATION_SYSTEM_PROMPT exists and is wired into the module
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

# ── Patch external deps before importing ──────────────────────────────────────

sys.modules.setdefault("supabase", MagicMock())
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key")

with patch("supabase.create_client", return_value=MagicMock()):
    with patch("anthropic.Anthropic", return_value=MagicMock()):
        import weekly_summary


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_claude_response(text: str, in_tok: int = 100, out_tok: int = 200):
    """Build a mock anthropic response object."""
    msg = MagicMock()
    block = MagicMock()
    block.text = text
    msg.content = [block]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


def _topics_json(topics: list[dict]) -> str:
    return json.dumps({"topics": topics}, ensure_ascii=False)

def _translations_json(topics: list[dict]) -> str:
    """Build a pass-3 response: JSON array of {idx, title_zh, summary_zh}."""
    return json.dumps([
        {"idx": i, "title_zh": t.get("title_zh", ""), "summary_zh": t.get("summary_zh", "")}
        for i, t in enumerate(topics)
    ], ensure_ascii=False)


# ── Constants ─────────────────────────────────────────────────────────────────

class TestConstants:
    def test_lookback_days_is_7(self):
        assert weekly_summary.LOOKBACK_DAYS == 7, (
            "LOOKBACK_DAYS must be 7 — rolling 7-day window for Top Stories."
        )

    def test_min_new_headlines_is_30(self):
        assert weekly_summary.MIN_NEW_HEADLINES == 30, (
            "MIN_NEW_HEADLINES must be 30 — calibrated for the 7-day window."
        )


# ── Chinese translation prompt ────────────────────────────────────────────────

class TestChineseTranslationPrompt:
    """CHINESE_TRANSLATION_SYSTEM_PROMPT must specify language and output contract."""

    def _prompt(self) -> str:
        return weekly_summary.CHINESE_TRANSLATION_SYSTEM_PROMPT

    def test_prompt_exists(self):
        assert hasattr(weekly_summary, "CHINESE_TRANSLATION_SYSTEM_PROMPT"), (
            "CHINESE_TRANSLATION_SYSTEM_PROMPT must be defined in weekly_summary.py."
        )
        assert len(self._prompt()) > 100

    def test_specifies_simplified_chinese(self):
        assert "Simplified Chinese" in self._prompt(), (
            "Prompt must specify Simplified Chinese explicitly — "
            "prevents outputting Traditional Chinese."
        )

    def test_requires_title_zh_field(self):
        assert "title_zh" in self._prompt(), (
            "Prompt must name the 'title_zh' output field."
        )

    def test_requires_summary_zh_field(self):
        assert "summary_zh" in self._prompt(), (
            "Prompt must name the 'summary_zh' output field."
        )

    def test_json_only_instruction(self):
        prompt = self._prompt()
        assert "ONLY" in prompt and "JSON" in prompt, (
            "Prompt must include a JSON-only return instruction."
        )
        assert "markdown" in prompt.lower() or "fences" in prompt.lower(), (
            "Prompt must explicitly forbid markdown fences."
        )

    def test_output_only_translations(self):
        prompt = self._prompt()
        # New design: pass-3 returns ONLY translations (not the full payload),
        # so the prompt should describe exactly three output keys
        assert "title_zh" in prompt and "summary_zh" in prompt and "idx" in prompt, (
            "Prompt must name the three output keys: idx, title_zh, summary_zh."
        )

    def test_self_check_step(self):
        prompt = self._prompt()
        assert "check" in prompt.lower() or "confirm" in prompt.lower() or "verify" in prompt.lower(), (
            "Prompt must include a self-check step before returning."
        )


# ── Three-pass _call_summary ──────────────────────────────────────────────────

class TestCallSummaryThreePass:
    """_call_summary must run three Claude passes and return topics with title_zh/summary_zh."""

    _PASS1_TOPICS = [
        {
            "title":   "Gaza Ceasefire Talks Stall",
            "summary": "Mediators in Cairo failed to bridge gaps between Israeli and Hamas negotiators.",
            "region":  "International",
            "theme":   "Security",
        }
    ]

    _PASS2_TOPICS = [
        {
            "title":   "Gaza Ceasefire Talks Stall",
            "summary": "Mediators in Cairo reportedly failed to bridge gaps between Israeli and Hamas negotiators.",
            "region":  "International",
            "theme":   "Security",
        }
    ]

    _PASS3_ZH = [
        {"title_zh": "加沙停火谈判陷入僵局", "summary_zh": "据报道，开罗调停人未能弥合以色列和哈马斯谈判代表之间的分歧。"}
    ]

    def test_returns_topics_with_chinese_fields(self):
        """Pass 3 output must include title_zh and summary_zh on each topic."""
        weekly_summary.claude = MagicMock()
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(self._PASS1_TOPICS)),
            _make_claude_response(_topics_json(self._PASS2_TOPICS)),
            _make_claude_response(_translations_json(self._PASS3_ZH)),
        ]

        result, usage = weekly_summary._call_summary("HEADLINES: some content")
        topics = result.get("topics", [])

        assert len(topics) == 1
        topic = topics[0]
        assert "title_zh" in topic, "Pass 3 must add 'title_zh' to each topic."
        assert "summary_zh" in topic, "Pass 3 must add 'summary_zh' to each topic."
        assert topic["title_zh"] == "加沙停火谈判陷入僵局"
        assert "开罗" in topic["summary_zh"]

    def test_three_claude_calls_made(self):
        """_call_summary must call claude.messages.create exactly three times."""
        weekly_summary.claude = MagicMock()
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(self._PASS1_TOPICS)),
            _make_claude_response(_topics_json(self._PASS2_TOPICS)),
            _make_claude_response(_translations_json(self._PASS3_ZH)),
        ]

        weekly_summary._call_summary("HEADLINES: some content")
        assert weekly_summary.claude.messages.create.call_count == 3, (
            "_call_summary must make exactly 3 Claude calls (generate, fact-check, translate)."
        )

    def test_usage_tokens_summed_across_three_passes(self):
        """Combined usage must sum input and output tokens across all three passes."""
        weekly_summary.claude = MagicMock()
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(self._PASS1_TOPICS), in_tok=100, out_tok=200),
            _make_claude_response(_topics_json(self._PASS2_TOPICS), in_tok=150, out_tok=100),
            _make_claude_response(_translations_json(self._PASS3_ZH), in_tok=50, out_tok=80),
        ]

        _, usage = weekly_summary._call_summary("HEADLINES: some content")
        assert usage.input_tokens  == 300, f"Expected 300 input tokens, got {usage.input_tokens}"
        assert usage.output_tokens == 380, f"Expected 380 output tokens, got {usage.output_tokens}"

    def test_chinese_prompt_used_for_pass3(self):
        """Pass 3 must use CHINESE_TRANSLATION_SYSTEM_PROMPT as the system prompt."""
        weekly_summary.claude = MagicMock()
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(self._PASS1_TOPICS)),
            _make_claude_response(_topics_json(self._PASS2_TOPICS)),
            _make_claude_response(_translations_json(self._PASS3_ZH)),
        ]

        weekly_summary._call_summary("HEADLINES: some content")
        calls = weekly_summary.claude.messages.create.call_args_list
        # Third call must use the Chinese translation prompt
        third_call_kwargs = calls[2][1]
        assert third_call_kwargs.get("system") == weekly_summary.CHINESE_TRANSLATION_SYSTEM_PROMPT, (
            "Pass 3 must use CHINESE_TRANSLATION_SYSTEM_PROMPT."
        )


# ── _extract_json_object ──────────────────────────────────────────────────────

class TestExtractJsonObject:
    """_extract_json_object must recover a JSON object from noisy Claude output."""

    def test_clean_object(self):
        text = '{"topics": [{"title": "Gaza talks", "region": "International"}]}'
        result = weekly_summary._extract_json_object(text)
        assert result is not None
        assert "topics" in result

    def test_prose_before_object(self):
        text = 'Here is the summary:\n{"topics": [{"title": "Budget debate"}]}\nDone.'
        result = weekly_summary._extract_json_object(text)
        assert result is not None
        assert "topics" in result

    def test_no_object_returns_none(self):
        assert weekly_summary._extract_json_object("No JSON here at all.") is None

    def test_only_open_brace_returns_none(self):
        assert weekly_summary._extract_json_object("{no closing brace") is None

    def test_code_fenced_object(self):
        text = '```json\n{"topics": [{"title": "Flood warning", "region": "Malaysia"}]}\n```'
        result = weekly_summary._extract_json_object(text)
        assert result is not None
        assert "topics" in result


# ── Model invariant ───────────────────────────────────────────────────────────

class TestModelInvariant:
    """weekly_summary.py must use Sonnet or Opus — never Haiku."""

    def test_summary_model_is_not_haiku(self):
        assert "haiku" not in weekly_summary.SUMMARY_MODEL.lower(), (
            f"SUMMARY_MODEL={weekly_summary.SUMMARY_MODEL!r} must not be Haiku. "
            "Summary calls use use_prefill=False which requires Sonnet or better."
        )

    def test_summary_model_is_sonnet_or_opus(self):
        model = weekly_summary.SUMMARY_MODEL.lower()
        assert "sonnet" in model or "opus" in model, (
            f"SUMMARY_MODEL={weekly_summary.SUMMARY_MODEL!r} — expected Sonnet or Opus."
        )


# ── _build_content ────────────────────────────────────────────────────────────

class TestBuildContent:
    def _make_headline(self, title_en: str, title_zh: str, category: str) -> dict:
        return {
            "title_en": title_en,
            "title_zh": title_zh,
            "category": category,
            "published_at": "2026-05-12T10:00:00Z",
        }

    def test_groups_by_region(self):
        headlines = [
            self._make_headline("Gaza talks stall", "加沙谈判停滞", "International"),
            self._make_headline("PM meets King", "首相会见国王", "Malaysia"),
            self._make_headline("Budget debate", "预算辩论", "Malaysia"),
        ]
        content = weekly_summary._build_content(headlines)
        assert "INTERNATIONAL" in content
        assert "MALAYSIA" in content
        assert "Gaza talks stall" in content
        assert "PM meets King" in content

    def test_empty_input_does_not_raise(self):
        content = weekly_summary._build_content([])
        assert "0 total" in content

    def test_unknown_category_goes_to_international(self):
        headlines = [self._make_headline("Some story", "某新闻", "Unknown")]
        content = weekly_summary._build_content(headlines)
        assert "Some story" in content

    def test_total_count_in_header(self):
        headlines = [self._make_headline(f"Headline {i}", f"新闻{i}", "Singapore") for i in range(5)]
        content = weekly_summary._build_content(headlines)
        assert "5 total" in content
