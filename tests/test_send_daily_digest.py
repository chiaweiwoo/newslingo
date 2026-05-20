import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules.setdefault("supabase", MagicMock())
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-key")
os.environ.setdefault("DIGEST_EMAIL_TO", "chiaweiwoo123@gmail.com")
os.environ.setdefault("DIGEST_EMAIL_FROM", "chiaweiwoo123@gmail.com")
os.environ.setdefault("GMAIL_SMTP_USER", "chiaweiwoo123@gmail.com")

with patch("supabase.create_client", return_value=MagicMock()):
    import send_daily_digest


def _summary_row():
    return {
        "created_at": "2026-05-20T09:09:52.117196+00:00",
        "payload": {
            "topics": [
                {
                    "title": "Deepfake video impersonates Singapore PM",
                    "title_zh": "深度伪造视频冒充新加坡总理",
                    "summary": "Police exposed a deepfake used in a fraud case.",
                    "summary_zh": "警方揭露一段被用于诈骗案件的深度伪造视频。",
                    "region": "Singapore",
                    "theme": "Technology",
                }
            ]
        },
    }


def _ai_row():
    return {
        "created_at": "2026-05-20T09:53:11.688792+00:00",
        "payload": {
            "categories": [
                {
                    "key": "governance",
                    "title": "Governance",
                    "items": [
                        {
                            "title": "EU advances AI standards",
                            "title_zh": "欧盟推进 AI 标准",
                            "description": "European regulators advanced a new compliance framework.",
                            "description_zh": "欧洲监管机构推进新的合规框架。",
                        }
                    ],
                }
            ]
        },
    }


class TestRenderer:
    def test_html_uses_single_language_english(self):
        html = send_daily_digest.render_digest_html(_summary_row(), _ai_row(), "en")
        assert "NewsLingo Daily Brief" in html
        assert "深度伪造视频冒充新加坡总理" not in html
        assert "Deepfake video impersonates Singapore PM" in html

    def test_html_uses_single_language_chinese(self):
        html = send_daily_digest.render_digest_html(_summary_row(), _ai_row(), "zh")
        assert "NewsLingo 每日简报" in html
        assert "Deepfake video impersonates Singapore PM" not in html
        assert "深度伪造视频冒充新加坡总理" in html

    def test_html_shows_not_available_for_missing_sections(self):
        html = send_daily_digest.render_digest_html(None, None, "en")
        assert "Not available today." in html

    def test_text_output_is_linear_sections(self):
        text = send_daily_digest.render_digest_text(_summary_row(), _ai_row(), "en")
        assert "Top Stories" in text
        assert "Singapore" in text
        assert "- Deepfake video impersonates Singapore PM" in text
        assert "AI" in text
        assert "Governance" in text


class TestHelpers:
    def test_split_recipients(self):
        assert send_daily_digest._split_recipients("a@test.com, b@test.com") == ["a@test.com", "b@test.com"]

    def test_subject_uses_date(self):
        subject = send_daily_digest._subject_for("2026-05-20T09:09:52.117196+00:00", "en")
        assert subject == "NewsLingo Daily Brief · 20 May"

    def test_write_preview_files(self, tmp_path: Path):
        out = tmp_path / "digest_preview"
        send_daily_digest.write_preview_files(out, "Subject", "<html></html>", "plain")
        assert (out / "subject.txt").read_text(encoding="utf-8").strip() == "Subject"
        assert (out / "digest_preview.html").exists()
        assert (out / "digest_preview.txt").exists()
