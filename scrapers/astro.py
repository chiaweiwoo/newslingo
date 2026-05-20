"""
Astro 本地圈 (YouTube) scraper.
Fetches videos from the channel incrementally since a given datetime.
Returns rows matching the headlines DB schema — title_en and category are
left None and filled by the caller (feed_ingest.py).

Uses the PlaylistItems API (uploads playlist) rather than the Search API.
The Search API has an indexing delay of several hours for newly uploaded
videos, causing recent content to be silently missed. The uploads playlist
reflects new videos immediately on upload.

Uploads playlist ID trick: replace the 'UC' channel prefix with 'UU'.
  UCURes72wqcEpid6EKNXWfxw  →  UUURes72wqcEpid6EKNXWfxw
No extra API call needed.
"""

import html
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone

CHANNEL_ID          = "UCURes72wqcEpid6EKNXWfxw"  # Astro 本地圈 (Malaysia)
UPLOADS_PLAYLIST_ID = "UU" + CHANNEL_ID[2:]         # UUURes72wqcEpid6EKNXWfxw
CHANNEL             = "Astro 本地圈"
SOURCE_URL_PREFIX   = "https://www.youtube.com/watch?v="
DEFAULT_LOOKBACK_HOURS = 120  # 5 days — ensures first repull after data reset has sufficient coverage

PLAYLIST_URL = (
    "https://www.googleapis.com/youtube/v3/playlistItems"
    "?part=snippet&playlistId={playlist_id}&maxResults=50&key={api_key}"
)


def scrape(since_dt: datetime | None, youtube_api_key: str) -> list[dict]:
    """
    Fetch YouTube videos published after since_dt.
    since_dt=None  → last DEFAULT_LOOKBACK_HOURS hours (first run).
    Returns list of rows; title_en and category are None (filled by feed_ingest.py).
    Shorts (tagged #Shorts in the title) are excluded — they have no news value.
    """
    if since_dt is None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)
    else:
        cutoff = since_dt + timedelta(seconds=1)

    items = _fetch_all_since(cutoff, youtube_api_key)
    shorts = [i for i in items if _is_short(i)]
    items  = [i for i in items if not _is_short(i)]
    if shorts:
        print(f"[astro] excluded {len(shorts)} Shorts", flush=True)
    print(f"[astro] fetched {len(items)} videos so far...", flush=True)
    return [_item_to_row(item) for item in items]


# ── Internal ─────────────────────────────────────────────────────────────────

def _fetch_all_since(cutoff: datetime, api_key: str) -> list:
    """
    Fetch playlist items newest-first, stopping as soon as we hit a video
    published before cutoff. Returns only items published >= cutoff.

    The PlaylistItems API returns in reverse chronological order (newest first),
    so we can stop pagination early once we've passed the cutoff date — no need
    to scan the entire channel history.
    """
    items = []
    next_page_token = None
    base_url = PLAYLIST_URL.format(playlist_id=UPLOADS_PLAYLIST_ID, api_key=api_key)

    while True:
        url = base_url + (f"&pageToken={next_page_token}" if next_page_token else "")
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())

        for item in data.get("items", []):
            published_at_str = item["snippet"].get("publishedAt", "")
            if not published_at_str:
                continue
            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
            if published_at < cutoff:
                # Playlist is ordered newest-first — everything from here is older
                return items
            items.append(item)

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return items


def _is_short(item: dict) -> bool:
    """YouTube Shorts are tagged #Shorts (or #Short) in the title by the channel."""
    raw_title = item["snippet"].get("title", "")
    return bool(re.search(r"#[Ss]horts?\b", raw_title))


def _clean_title(raw: str) -> str:
    title = html.unescape(raw)
    title = re.sub(r"\s*\|.*$", "", title).strip()
    title = re.sub(r"\s*#\S+", "", title).strip()
    return title


def _item_to_row(item: dict) -> dict:
    snippet  = item["snippet"]
    video_id = snippet["resourceId"]["videoId"]  # playlistItems uses resourceId, not id.videoId
    return {
        "id":            video_id,
        "title_zh":      _clean_title(snippet["title"]),
        "title_en":      None,
        "thumbnail_url": (snippet.get("thumbnails", {}).get("high", {}) or {}).get("url"),
        "published_at":  snippet["publishedAt"],
        "channel":       snippet.get("channelTitle") or CHANNEL,
        "category":      None,
        "source_url":    SOURCE_URL_PREFIX + video_id,
    }
