"""
Zaobao Singapore news scraper.
Uses the monthly sitemap for URL discovery + exact timestamps,
then fetches each article page for og:title and og:image.
Returns rows matching the headlines DB schema — title_en is left None
and filled by the caller (job.py).
"""

import re
import sys
import hashlib
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://www.zaobao.com.sg"
SITEMAP_BASE = "https://www.zaobao.com.sg/sitemaps/sitemap-{yyyymm}.xml"
CHANNEL = "联合早报"
DEFAULT_LOOKBACK_DAYS = 5
MAX_WORKERS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}

# Matches daily audio news briefing articles — not editorial content
_AUDIO_BRIEF_RE = re.compile(r"听新闻简报")


def scrape(since_dt: datetime | None) -> list[dict]:
    """
    Fetch Singapore news articles published after since_dt.
    since_dt=None  → last DEFAULT_LOOKBACK_DAYS days (first / backfill run).
    Returns list of rows; title_en is None (filled by job.py).
    Filters out daily audio briefing rows.
    """
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=DEFAULT_LOOKBACK_DAYS) if since_dt is None else since_dt

    entries = _entries_since(start_dt, now)
    print(f"[zaobao] {len(entries)} articles from sitemap, fetching with {MAX_WORKERS} workers...", flush=True)

    # Fetch all article pages in parallel
    meta: dict[str, tuple[str | None, str | None]] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(_fetch_article_meta, url): url for url, _ in entries}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            meta[url] = future.result()
            done += 1
            if done % 20 == 0:
                print(f"[zaobao] fetched {done}/{len(entries)}...", flush=True)

    # Build rows in original sitemap order (newest first)
    rows = []
    skip_no_title, skip_audio = 0, 0
    for url, lastmod in entries:
        title_zh, thumbnail_url = meta.get(url, (None, None))
        if title_zh is None:
            skip_no_title += 1
            print(f"[zaobao] skip (no title): {url}", flush=True)
            continue
        if _AUDIO_BRIEF_RE.search(title_zh):
            skip_audio += 1
            continue
        rows.append({
            "id":            _make_id(url),
            "title_zh":      title_zh,
            "title_en":      None,
            "thumbnail_url": thumbnail_url,
            "published_at":  lastmod,
            "channel":       CHANNEL,
            "category":      None,
            "source_url":    url,
        })

    print(f"[zaobao] {len(rows)} rows ready | skipped: {skip_audio} audio briefs, {skip_no_title} fetch failures", flush=True)
    return rows


# ── Internal ──────────────────────────────────────────────────────────────────

def _make_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def _sitemaps_for_range(start_dt: datetime, end_dt: datetime) -> list[str]:
    """Return sitemap URLs covering every YYYYMM between start_dt and end_dt."""
    urls = []
    cur = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur <= end_dt:
        urls.append(SITEMAP_BASE.format(yyyymm=cur.strftime("%Y%m")))
        cur = cur.replace(month=cur.month + 1) if cur.month < 12 else cur.replace(year=cur.year + 1, month=1)
    return urls


def _entries_since(start_dt: datetime, end_dt: datetime) -> list[tuple[str, str]]:
    """Return (url, lastmod) pairs from sitemap(s) where lastmod > start_dt, newest first."""
    entries = []
    for smap_url in _sitemaps_for_range(start_dt, end_dt):
        try:
            xml = _fetch_html(smap_url)
        except Exception as e:
            print(f"[zaobao] sitemap fetch failed {smap_url}: {e}", flush=True)
            continue
        for url, lastmod in re.findall(
            r"<url>\s*<loc>(https://www\.zaobao\.com\.sg/news/singapore/story[^<]+)</loc>"
            r"\s*<lastmod>([^<]+)</lastmod>",
            xml,
        ):
            dt = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
            if dt > start_dt:
                entries.append((url, lastmod))

    entries.sort(key=lambda x: x[1], reverse=True)
    return entries


def _fetch_article_meta(url: str) -> tuple[str | None, str | None]:
    """Return (og:title, og:image) from an article page."""
    try:
        html_text = _fetch_html(url)
        title_m = re.search(r'property="og:title"\s+content="([^"]+)"', html_text) or \
                  re.search(r'content="([^"]+)"\s+property="og:title"', html_text)
        image_m = re.search(r'property="og:image"\s+content="(https?://[^"]+)"', html_text) or \
                  re.search(r'content="(https?://[^"]+)"\s+property="og:image"', html_text)
        return (
            title_m.group(1) if title_m else None,
            image_m.group(1) if image_m else None,
        )
    except Exception as e:
        print(f"[zaobao] meta fetch failed {url}: {e}", flush=True)
        return None, None
