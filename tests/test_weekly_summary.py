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
        """Pass 3 must use CHINESE_TRANSLATION_SYSTEM_PROMPT as the system prompt (string)."""
        weekly_summary.claude = MagicMock()
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(self._PASS1_TOPICS)),
            _make_claude_response(_topics_json(self._PASS2_TOPICS)),
            _make_claude_response(_translations_json(self._PASS3_ZH)),
        ]

        weekly_summary._call_summary("HEADLINES: some content")
        calls = weekly_summary.claude.messages.create.call_args_list
        third_call_kwargs = calls[2][1]
        assert third_call_kwargs.get("system") == weekly_summary.CHINESE_TRANSLATION_SYSTEM_PROMPT, (
            "Pass 3 must use CHINESE_TRANSLATION_SYSTEM_PROMPT."
        )

    def _run_call_summary(self):
        """Helper: run _call_summary with standard mocks, return call_args_list."""
        weekly_summary.claude = MagicMock()
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(self._PASS1_TOPICS)),
            _make_claude_response(_topics_json(self._PASS2_TOPICS)),
            _make_claude_response(_translations_json(self._PASS3_ZH)),
        ]
        weekly_summary._call_summary("HEADLINES: some content")
        return weekly_summary.claude.messages.create.call_args_list

    def test_pass1_system_is_list_with_cache_control(self):
        """Pass 1 system must be a list with a cache_control block for prompt caching."""
        calls = self._run_call_summary()
        system = calls[0][1].get("system")
        assert isinstance(system, list), "Pass 1 system must be a list (for prompt caching)."
        assert any(
            isinstance(b, dict) and b.get("cache_control") == {"type": "ephemeral"}
            for b in system
        ), "Pass 1 system must include a block with cache_control: ephemeral."

    def test_pass2_system_is_list_with_cache_control(self):
        """Pass 2 system must share the same cacheable headlines block as Pass 1."""
        calls = self._run_call_summary()
        system = calls[1][1].get("system")
        assert isinstance(system, list), "Pass 2 system must be a list (for prompt caching)."
        assert any(
            isinstance(b, dict) and b.get("cache_control") == {"type": "ephemeral"}
            for b in system
        ), "Pass 2 system must include a block with cache_control: ephemeral."

    def test_pass1_pass2_share_identical_headlines_block(self):
        """The cached headlines block must be byte-identical between Pass 1 and Pass 2."""
        calls = self._run_call_summary()
        p1_cached = next(
            b for b in calls[0][1]["system"]
            if isinstance(b, dict) and b.get("cache_control")
        )
        p2_cached = next(
            b for b in calls[1][1]["system"]
            if isinstance(b, dict) and b.get("cache_control")
        )
        assert p1_cached["text"] == p2_cached["text"], (
            "Headlines block must be byte-identical in Pass 1 and Pass 2 for cache hit."
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


# ── Model invariants ──────────────────────────────────────────────────────────

class TestModelInvariant:
    """Pass 1 + Pass 2 must use Sonnet or Opus. Pass 3 must use Haiku."""

    def test_summary_model_is_not_haiku(self):
        assert "haiku" not in weekly_summary.SUMMARY_MODEL.lower(), (
            f"SUMMARY_MODEL={weekly_summary.SUMMARY_MODEL!r} must not be Haiku. "
            "Pass 1 and Pass 2 require Sonnet or better for reasoning."
        )

    def test_summary_model_is_sonnet_or_opus(self):
        model = weekly_summary.SUMMARY_MODEL.lower()
        assert "sonnet" in model or "opus" in model, (
            f"SUMMARY_MODEL={weekly_summary.SUMMARY_MODEL!r} — expected Sonnet or Opus."
        )

    def test_haiku_model_constant_exists(self):
        assert hasattr(weekly_summary, "SUMMARY_HAIKU_MODEL"), (
            "SUMMARY_HAIKU_MODEL must be defined — used for Pass 3 EN→ZH translation."
        )

    def test_haiku_model_is_haiku(self):
        assert "haiku" in weekly_summary.SUMMARY_HAIKU_MODEL.lower(), (
            f"SUMMARY_HAIKU_MODEL={weekly_summary.SUMMARY_HAIKU_MODEL!r} must be a Haiku model."
        )

    def test_pass3_uses_haiku_model(self):
        """Pass 3 (translate-zh) must use SUMMARY_HAIKU_MODEL, not SUMMARY_MODEL."""
        weekly_summary.claude = MagicMock()
        _PASS1 = [{"title": "Test Topic", "summary": "Summary.", "region": "International", "theme": "Politics"}]
        weekly_summary.claude.messages.create.side_effect = [
            _make_claude_response(_topics_json(_PASS1)),
            _make_claude_response(_topics_json(_PASS1)),
            _make_claude_response(_translations_json([{"title_zh": "测试", "summary_zh": "摘要"}])),
        ]
        weekly_summary._call_summary("HEADLINES: some content")
        calls = weekly_summary.claude.messages.create.call_args_list
        third_model = calls[2][1].get("model")
        assert third_model == weekly_summary.SUMMARY_HAIKU_MODEL, (
            f"Pass 3 must use SUMMARY_HAIKU_MODEL ({weekly_summary.SUMMARY_HAIKU_MODEL!r}), "
            f"got {third_model!r}."
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
