"""
NewsLingo daily digest email job.

Manual-test friendly by default:
  - reads latest active Top Stories + AI rows from Supabase
  - renders one-language HTML + plain-text digest
  - writes preview artifacts locally
  - optionally sends via Gmail SMTP when not in dry-run mode
"""

from __future__ import annotations

import argparse
import html
import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
DIGEST_EMAIL_TO = os.getenv("DIGEST_EMAIL_TO", "chiaweiwoo123@gmail.com")
DIGEST_EMAIL_FROM = os.getenv("DIGEST_EMAIL_FROM", "chiaweiwoo123@gmail.com")
GMAIL_SMTP_USER = os.getenv("GMAIL_SMTP_USER", DIGEST_EMAIL_FROM)
GMAIL_SMTP_APP_PASSWORD = os.getenv("GMAIL_SMTP_APP_PASSWORD")
DEFAULT_LANGUAGE = os.getenv("DIGEST_EMAIL_LANGUAGE", "en").lower()

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required for send_daily_digest.py")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

NEWS_SECTIONS = [
    ("International", "World"),
    ("Singapore", "Singapore"),
    ("Malaysia", "Malaysia"),
]

AI_SECTIONS = [
    ("governance", "Governance"),
    ("product", "Product"),
    ("infrastructure", "Infra"),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render and optionally send the NewsLingo daily digest email.")
    parser.add_argument("--language", choices=["en", "zh"], default=DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in {"en", "zh"} else "en")
    parser.add_argument("--dry-run", action="store_true", help="Render preview files without sending email.")
    parser.add_argument("--output-dir", default="digest_preview", help="Directory to write preview artifacts into.")
    return parser.parse_args()


def _load_latest_summary() -> dict[str, Any] | None:
    result = (
        supabase.table("weekly_summary")
        .select("created_at, payload")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return result.data or None


def _load_latest_ai() -> dict[str, Any] | None:
    result = (
        supabase.table("ai_radar")
        .select("created_at, payload")
        .eq("active", True)
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return result.data or None


def _split_recipients(raw: str) -> list[str]:
    return [email.strip() for email in raw.split(",") if email.strip()]


def _subject_for(date_str: str | None, language: str) -> str:
    if date_str:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        formatted = dt.strftime("%d %b")
    else:
        formatted = "Today"
    if language == "zh":
        return f"NewsLingo 每日简报 · {formatted}"
    return f"NewsLingo Daily Brief · {formatted}"


def _format_body(language: str, en: str | None, zh: str | None) -> str:
    return (zh if language == "zh" else en) or en or zh or ""


def _render_story_items(items: list[dict[str, Any]], language: str, kind: str) -> str:
    if not items:
        return _not_available_message(language)

    rendered: list[str] = []
    for item in items:
        if kind == "news":
            title = _format_body(language, item.get("title"), item.get("title_zh"))
            summary = _format_body(language, item.get("summary"), item.get("summary_zh"))
            eyebrow = item.get("theme") or ""
        else:
            title = _format_body(language, item.get("title"), item.get("title_zh"))
            summary = _format_body(language, item.get("description"), item.get("description_zh"))
            eyebrow = ""

        eyebrow_html = (
            f'<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#c8102e;margin-bottom:6px;">{html.escape(eyebrow)}</div>'
            if eyebrow
            else ""
        )
        rendered.append(
            (
                '<div style="padding:16px 18px;border-top:1px solid #eceff4;">'
                if rendered
                else '<div style="padding:16px 18px;">'
            )
            + eyebrow_html
            + f'<div style="font-size:16px;line-height:1.45;font-weight:700;color:#111827;font-family:Georgia, serif;">{html.escape(title)}</div>'
            + f'<div style="font-size:13px;line-height:1.75;color:#4b5563;margin-top:8px;">{html.escape(summary)}</div>'
            + "</div>"
        )
    return "".join(rendered)


def _not_available_message(language: str) -> str:
    if language == "zh":
        return '<div style="padding:16px 18px;font-size:13px;line-height:1.7;color:#6b7280;">今天暂无内容。</div>'
    return '<div style="padding:16px 18px;font-size:13px;line-height:1.7;color:#6b7280;">Not available today.</div>'


def render_digest_html(summary_row: dict[str, Any] | None, ai_row: dict[str, Any] | None, language: str) -> str:
    summary_topics = (summary_row or {}).get("payload", {}).get("topics", []) or []
    ai_categories = (ai_row or {}).get("payload", {}).get("categories", []) or []

    summary_by_region = {
        key: [topic for topic in summary_topics if topic.get("region") == key] for key, _ in NEWS_SECTIONS
    }
    ai_by_key = {
        key: next((category.get("items", []) for category in ai_categories if category.get("key") == key), [])
        for key, _ in AI_SECTIONS
    }

    hero_title = "NewsLingo 每日简报" if language == "zh" else "NewsLingo Daily Brief"
    hero_subtitle = (
        "过去七天最重要的综合新闻与 AI 动向，一封看完。"
        if language == "zh"
        else "A compact scan of the most important general and AI developments from the past 7 days."
    )

    top_stories_label = "要闻" if language == "zh" else "Top Stories"
    ai_label = "AI" if language == "zh" else "AI"
    world_label = "国际" if language == "zh" else "World"
    singapore_label = "新加坡" if language == "zh" else "Singapore"
    malaysia_label = "马来西亚" if language == "zh" else "Malaysia"
    governance_label = "治理" if language == "zh" else "Governance"
    product_label = "产品" if language == "zh" else "Product"
    infra_label = "基础设施" if language == "zh" else "Infra"

    section_labels = {
        "International": world_label,
        "Singapore": singapore_label,
        "Malaysia": malaysia_label,
        "governance": governance_label,
        "product": product_label,
        "infrastructure": infra_label,
    }

    news_sections = []
    for key, _ in NEWS_SECTIONS:
        news_sections.append(
            f"""
            <div style="margin-top:18px;">
              <div style="font-size:11px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;color:#6b7280;margin-bottom:8px;">{html.escape(section_labels[key])}</div>
              <div style="background:#ffffff;border:1px solid #e4e7ec;border-radius:18px;overflow:hidden;">
                {_render_story_items(summary_by_region[key], language, "news")}
              </div>
            </div>
            """
        )

    ai_sections = []
    for key, _ in AI_SECTIONS:
        ai_sections.append(
            f"""
            <div style="margin-top:18px;">
              <div style="font-size:11px;font-weight:700;letter-spacing:0.10em;text-transform:uppercase;color:#6b7280;margin-bottom:8px;">{html.escape(section_labels[key])}</div>
              <div style="background:#ffffff;border:1px solid #e4e7ec;border-radius:18px;overflow:hidden;">
                {_render_story_items(ai_by_key[key], language, "ai")}
              </div>
            </div>
            """
        )

    return f"""\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(hero_title)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f3f6fa;font-family:Arial, Helvetica, sans-serif;color:#111827;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f6fa;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff;border:1px solid #e5e9f0;border-radius:24px;overflow:hidden;">
            <tr>
              <td style="padding:24px 24px 18px;background:linear-gradient(180deg,#141414 0%,#1f1f1f 100%);color:#ffffff;">
                <div style="font-size:30px;line-height:1.05;font-weight:700;font-family:Georgia, serif;">{html.escape(hero_title)}</div>
                <div style="font-size:14px;line-height:1.7;color:rgba(255,255,255,0.76);margin-top:10px;">{html.escape(hero_subtitle)}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px;background:#f9fbfd;">
                <div style="font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#111827;">{html.escape(top_stories_label)}</div>
                {''.join(news_sections)}
                <div style="font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#111827;margin-top:28px;">{html.escape(ai_label)}</div>
                {''.join(ai_sections)}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def render_digest_text(summary_row: dict[str, Any] | None, ai_row: dict[str, Any] | None, language: str) -> str:
    summary_topics = (summary_row or {}).get("payload", {}).get("topics", []) or []
    ai_categories = (ai_row or {}).get("payload", {}).get("categories", []) or []

    lines: list[str] = []
    if language == "zh":
        lines.extend(["NewsLingo 每日简报", ""])
    else:
        lines.extend(["NewsLingo Daily Brief", ""])

    lines.append("Top Stories" if language == "en" else "要闻")
    for key, label in NEWS_SECTIONS:
        heading = {"International": "国际", "Singapore": "新加坡", "Malaysia": "马来西亚"}.get(key, label) if language == "zh" else label
        lines.append(f"{heading}")
        items = [topic for topic in summary_topics if topic.get("region") == key]
        if not items:
            lines.append("Not available today." if language == "en" else "今天暂无内容。")
        else:
            for item in items:
                title = pick_text(language, item.get("title"), item.get("title_zh"))
                summary = pick_text(language, item.get("summary"), item.get("summary_zh"))
                lines.append(f"- {title}")
                lines.append(f"  {summary}")
        lines.append("")

    lines.append("AI")
    for key, label in AI_SECTIONS:
        heading = {"governance": "治理", "product": "产品", "infrastructure": "基础设施"}.get(key, label) if language == "zh" else label
        lines.append(heading)
        items = next((category.get("items", []) for category in ai_categories if category.get("key") == key), [])
        if not items:
            lines.append("Not available today." if language == "en" else "今天暂无内容。")
        else:
            for item in items:
                title = pick_text(language, item.get("title"), item.get("title_zh"))
                description = pick_text(language, item.get("description"), item.get("description_zh"))
                lines.append(f"- {title}")
                lines.append(f"  {description}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def pick_text(language: str, en: str | None, zh: str | None) -> str:
    return zh or en or "" if language == "zh" else en or zh or ""


def write_preview_files(output_dir: Path, subject: str, html_body: str, text_body: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "subject.txt").write_text(subject + "\n", encoding="utf-8")
    (output_dir / "digest_preview.html").write_text(html_body, encoding="utf-8")
    (output_dir / "digest_preview.txt").write_text(text_body, encoding="utf-8")


def send_digest_email(
    sender_email: str,
    recipients: list[str],
    subject: str,
    html_body: str,
    text_body: str,
    smtp_user: str,
    smtp_password: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"NewsLingo <{sender_email}>"
    message["To"] = ", ".join(recipients)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_password)
        server.send_message(message)


def main() -> None:
    args = _parse_args()
    recipients = _split_recipients(DIGEST_EMAIL_TO)
    output_dir = Path(args.output_dir)

    print("[digest-email] NewsLingo digest email job starting", flush=True)
    summary_row = _load_latest_summary()
    ai_row = _load_latest_ai()

    subject = _subject_for((summary_row or ai_row or {}).get("created_at"), args.language)
    html_body = render_digest_html(summary_row, ai_row, args.language)
    text_body = render_digest_text(summary_row, ai_row, args.language)
    write_preview_files(output_dir, subject, html_body, text_body)

    summary_count = len((summary_row or {}).get("payload", {}).get("topics", []) or [])
    ai_count = sum(len(category.get("items", []) or []) for category in (ai_row or {}).get("payload", {}).get("categories", []) or [])
    print(f"[digest-email] prepared digest: top_stories={summary_count}, ai_items={ai_count}, language={args.language}", flush=True)
    print(f"[digest-email] wrote preview files to {output_dir}", flush=True)

    if args.dry_run:
        print("[digest-email] dry-run enabled - skipping SMTP send", flush=True)
        return

    if not GMAIL_SMTP_APP_PASSWORD:
        raise RuntimeError("GMAIL_SMTP_APP_PASSWORD is required when dry-run is disabled")

    send_digest_email(
        sender_email=DIGEST_EMAIL_FROM,
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        smtp_user=GMAIL_SMTP_USER,
        smtp_password=GMAIL_SMTP_APP_PASSWORD,
    )
    print(f"[digest-email] sent digest to {', '.join(recipients)}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[digest-email] ERROR: {exc}", flush=True)
        sys.exit(1)
