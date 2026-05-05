import os
import re
import json
import html
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from supabase import create_client
from dotenv import load_dotenv
import anthropic

load_dotenv(override=True)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CHANNEL_ID = "UCURes72wqcEpid6EKNXWfxw"  # Astro 本地圈 (Malaysia)
CLAUDE_BATCH_SIZE = 50

SYSTEM_PROMPT = (
    "You are an expert Malaysian news translator and classifier. For each headline:\n"
    "1. Translate from Chinese to Malaysian English\n"
    "2. Classify as 'Malaysia' (local Malaysian news) or 'International' (foreign/world news)\n\n"

    "CLASSIFICATION RULES:\n"
    "- 'Malaysia': news about Malaysian politics, people, places, companies, courts, or events\n"
    "- 'International': news about other countries, world leaders, global events, foreign incidents\n"
    "- When in doubt (e.g. Malaysian reaction to world event): classify by WHERE the event happened\n\n"

    "POLITICAL TITLES & ROLES:\n"
    "- 首相 → Prime Minister (not Premier)\n"
    "- 副首相 → Deputy Prime Minister\n"
    "- 州务大臣 → Menteri Besar (for Peninsular Malay-majority states)\n"
    "- 首席部长 → Chief Minister (for Sabah, Sarawak, Penang, Melaka)\n"
    "- 部长 → Minister\n"
    "- 副部长 → Deputy Minister\n"
    "- 国会议员 → Member of Parliament (MP)\n"
    "- 州议员 → State Assemblyman (ADUN)\n"
    "- 最高元首/国家元首 → Yang di-Pertuan Agong\n"
    "- 苏丹/Raja → Sultan/Raja (keep as-is)\n\n"

    "GOVERNMENT AGENCIES (use official abbreviations):\n"
    "- 反贪污委员会/反贪会 → Malaysian Anti-Corruption Commission (MACC) / SPRM\n"
    "- 皇家马来西亚警察/警方 → Royal Malaysia Police (PDRM)\n"
    "- 国家银行 → Bank Negara Malaysia (BNM)\n"
    "- 内陆税收局 → Inland Revenue Board (LHDN)\n"
    "- 陆路交通局 → Road Transport Department (JPJ)\n"
    "- 移民局 → Immigration Department (JIM)\n"
    "- 卫生部 → Ministry of Health (MOH)\n"
    "- 教育部 → Ministry of Education (MOE)\n"
    "- 国防部 → Ministry of Defence (MINDEF)\n"
    "- 马来西亚武装部队 → Malaysian Armed Forces (ATM)\n"
    "- 检察官/总检察长 → Attorney General (AG)\n\n"

    "COURTS & LEGAL:\n"
    "- 联邦法院 → Federal Court\n"
    "- 上诉庭/上诉法院 → Court of Appeal\n"
    "- 高庭/高等法院 → High Court\n"
    "- 地庭/地方法院 → Sessions Court\n"
    "- 推事庭/推事法庭 → Magistrate's Court\n"
    "- 被告 → accused / defendant\n"
    "- 控罪 → charge(s)\n"
    "- 面控 → charged in court\n\n"

    "POLITICAL PARTIES & COALITIONS:\n"
    "Keep all acronyms: PKR, DAP, UMNO, Bersatu, Amanah, MCA, MIC, GPS, GRS, "
    "BN (Barisan Nasional), PH (Pakatan Harapan), PN (Perikatan Nasional)\n\n"

    "PLACE NAMES — keep all Malaysian place names in Malay:\n"
    "States: Johor, Kedah, Kelantan, Melaka, Negeri Sembilan, Pahang, Perak, Perlis, "
    "Pulau Pinang, Sabah, Sarawak, Selangor, Terengganu, Kuala Lumpur, Putrajaya, Labuan\n"
    "Cities/areas: Petaling Jaya, Shah Alam, Subang Jaya, Klang, Ipoh, Johor Bahru, "
    "Kota Kinabalu, Kuching, Bukit Aman, Cyberjaya, Putrajaya\n\n"

    "CURRENCY & NUMBERS:\n"
    "- 令吉/马币 → ringgit (use RM prefix, e.g. RM1.1 billion)\n"
    "- 亿 → billion (if 十亿) or hundred million — convert carefully\n\n"

    "STYLE GUIDELINES:\n"
    "- Use Malaysian English, not British or American English\n"
    "- Keep translations concise — these are headlines\n"
    "- Preserve names of people (romanise Chinese names only if the person has a known English name)\n"
    "- Keep the tone of the original\n\n"

    "Return ONLY a JSON array of objects, one per input line, in the same order.\n"
    "Each object must have exactly two keys: \"title_en\" and \"category\".\n"
    "Example: [{\"title_en\": \"PM meets king\", \"category\": \"Malaysia\"}, "
    "{\"title_en\": \"Trump signs bill\", \"category\": \"International\"}]"
)


def get_last_published_at() -> str | None:
    result = (
        supabase.table("headlines")
        .select("published_at")
        .order("published_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["published_at"]
    return None


def fetch_youtube_items_since(published_after: str | None) -> list:
    items = []
    next_page_token = None

    base_url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet&channelId={CHANNEL_ID}&maxResults=50"
        f"&order=date&type=video&key={YOUTUBE_API_KEY}"
    )
    if published_after:
        base_url += f"&publishedAfter={published_after}"

    while True:
        url = base_url + (f"&pageToken={next_page_token}" if next_page_token else "")
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
        items.extend(data.get("items", []))
        next_page_token = data.get("nextPageToken")
        print(f"Fetched {len(items)} videos so far...", flush=True)
        if not next_page_token:
            break

    return items


def translate_and_classify(titles: list[str]) -> list[dict]:
    results = []
    for i in range(0, len(titles), CLAUDE_BATCH_SIZE):
        batch = titles[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(f"{j+1}. {t}" for j, t in enumerate(batch))
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Translate and classify these headlines:\n{numbered}"}]
        )
        raw = message.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        results.extend(json.loads(raw))
        print(f"Translated batch {i // CLAUDE_BATCH_SIZE + 1} ({len(batch)} headlines)", flush=True)
    return results


# --- Main ---

start_time = time.time()
videos_found = 0
videos_processed = 0
status = "success"
error_msg = None

try:
    last_published_at = get_last_published_at()

    if last_published_at:
        last_dt = datetime.fromisoformat(last_published_at.replace('Z', '+00:00'))
        published_after = (last_dt + timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f"Incremental fetch: videos after {published_after}", flush=True)
    else:
        published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f"No existing data. Fetching last 24h since {published_after}", flush=True)

    items = fetch_youtube_items_since(published_after)
    videos_found = len(items)

    if videos_found == 0:
        print("No new videos found. Skipping LLM call.", flush=True)
    else:
        titles_zh = []
        for item in items:
            raw_title = html.unescape(item["snippet"]["title"])
            title_zh = re.sub(r'\s*\|.*$', '', raw_title).strip()
            title_zh = re.sub(r'\s*#\S+', '', title_zh).strip()
            titles_zh.append(title_zh)

        translations = translate_and_classify(titles_zh)

        for i, item in enumerate(items):
            video_id = item["id"]["videoId"]
            thumbnail_url = item["snippet"]["thumbnails"]["high"]["url"]
            published_at = item["snippet"]["publishedAt"]
            channel = item["snippet"]["channelTitle"]
            title_zh = titles_zh[i]
            title_en = translations[i]["title_en"]
            category = translations[i]["category"]

            supabase.table("headlines").upsert({
                "id": video_id,
                "title_zh": title_zh,
                "title_en": title_en,
                "thumbnail_url": thumbnail_url,
                "published_at": published_at,
                "channel": channel,
                "category": category,
            }, on_conflict="id").execute()
            print(f"[{category}] {video_id} | {title_zh[:30]}... -> {title_en[:40]}...", flush=True)

        videos_processed = videos_found

except Exception as e:
    status = "error"
    error_msg = str(e)
    print(f"ERROR: {e}", flush=True)
    raise

finally:
    duration = round(time.time() - start_time, 2)
    supabase.table("job_runs").insert({
        "videos_found": videos_found,
        "videos_processed": videos_processed,
        "status": status,
        "error_msg": error_msg,
        "duration_seconds": duration,
    }).execute()
    print(f"Done: {status} | found={videos_found} processed={videos_processed} duration={duration}s", flush=True)
