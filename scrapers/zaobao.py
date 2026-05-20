"""
Zaobao Singapore news scraper.
Uses the monthly sitemap for URL discovery + exact timestamps,
then fetches each article page for og:title and og:image.
Returns rows matching the headlines DB schema — title_en is left None
and filled by the caller (feed_ingest.py).
"""

import hashlib
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://www.zaobao.com.sg"
SITEMAP_BASE = "https://www.zaobao.com.sg/sitemaps/sitemap-{yyyymm}.xml"
CHANNEL = "联合早报"
DEFAULT_LOOKBACK_DAYS = 5
MAX_WORKERS = 10

# URL-section → category mapping.
# singapore and world are deterministic (no LLM needed).
# sea returns None — these articles are LLM-classified in the translate step.
# china is intentionally excluded — out of scope for this app.
_SECTION_CATEGORY: dict[str, str | None] = {
    "singapore": "Singapore",
    "world":     "International",
    "sea":       None,   # LLM-classified: International / Singapore / Malaysia
}

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
    Returns list of rows; title_en is None (filled by feed_ingest.py).
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
    count_sea = 0
    for url, lastmod in entries:
        title_zh, thumbnail_url = meta.get(url, (None, None))
        if title_zh is None:
            skip_no_title += 1
            print(f"[zaobao] skip (no title): {url}", flush=True)
            continue
        if _AUDIO_BRIEF_RE.search(title_zh):
            skip_audio += 1
            continue
        category = _category_from_url(url)   # None for /sea/ — LLM-classified later
        if category is None:
            count_sea += 1
        rows.append({
            "id":            _make_id(url),
            "title_zh":      title_zh,
            "title_en":      None,
            "thumbnail_url": thumbnail_url,
            "published_at":  lastmod,
            "channel":       CHANNEL,
            "category":      category,
            "source_url":    url,
        })

    print(
        f"[zaobao] {len(rows)} rows ready ({count_sea} sea/pending-classify) | "
        f"skipped: {skip_audio} audio briefs, {skip_no_title} fetch failures",
        flush=True,
    )
    return rows


# ── Internal ──────────────────────────────────────────────────────────────────

def _make_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _category_from_url(url: str) -> str | None:
    """Category from URL section.

    singapore → 'Singapore', world → 'International' (deterministic, no LLM).
    sea       → None (LLM-classified in the translate step).
    Unknown sections fall back to 'International'.
    """
    for section, category in _SECTION_CATEGORY.items():
        if f"/news/{section}/" in url:
            return category          # None for sea, str for singapore/world
    return "International"           # safe fallback for any unknown/future section


def _fetch_html(url: str, *, retries: int = 3) -> str:
    """Fetch URL with exponential-backoff retry (1s, 2s) on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                wait = 2 ** attempt  # 1s, 2s
                print(f"[zaobao] fetch attempt {attempt + 1}/{retries} failed ({e}), retrying in {wait}s...", flush=True)
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


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
            r"<url>\s*<loc>(https://www\.zaobao\.com\.sg/news/(?:singapore|world|sea)/story[^<]+)</loc>"
            r"\s*<lastmod>([^<]+)</lastmod>",
            xml,
        ):
            dt = datetime.fromisoformat(lastmod.replace("Z", "+00:00"))
            if start_dt < dt <= end_dt:   # end_dt = now — never ingest future-dated articles
                entries.append((url, lastmod))

    entries.sort(key=lambda x: x[1], reverse=True)
    return entries


def _fetch_article_meta(url: str) -> tuple[str | None, str | None]:
    """Return (og:title, og:image) from an article page."""
    try:
        html_text = _fetch_html(url)
        soup = BeautifulSoup(html_text, "lxml")
        title_tag = soup.find("meta", property="og:title")
        image_tag = soup.find("meta", property="og:image")
        return (
            title_tag.get("content") if title_tag else None,
            image_tag.get("content") if image_tag else None,
        )
    except Exception as e:
        print(f"[zaobao] meta fetch failed {url}: {e}", flush=True)
        return None, None
