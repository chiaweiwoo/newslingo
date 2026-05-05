import os
import re
import json
import html
import urllib.request
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

CHANNEL_ID = "UCURes72wqcEpid6EKNXWfxw"
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "20"))

url = (
    f"https://www.googleapis.com/youtube/v3/search"
    f"?part=snippet&channelId={CHANNEL_ID}&maxResults={MAX_RESULTS}"
    f"&order=date&type=video&key={YOUTUBE_API_KEY}"
)

with urllib.request.urlopen(url) as r:
    data = json.loads(r.read())

items = data["items"]

titles_zh = []
for item in items:
    raw_title = html.unescape(item["snippet"]["title"])
    title_zh = re.sub(r'\s*\|.*$', '', raw_title).strip()
    title_zh = re.sub(r'\s*#\S+', '', title_zh).strip()
    titles_zh.append(title_zh)

numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles_zh))

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=4096,
    system=(
        "You are an expert Malaysian news translator. Your goal is to produce accurate, natural Malaysian English translations "
        "that help readers learn the correct official English terminology used in Malaysia.\n\n"

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
        "- Keep translations concise — these are headlines, not full sentences where unnecessary\n"
        "- Preserve names of people (romanise Chinese names only if the person has a known English name)\n"
        "- Keep the tone of the original (serious news stays serious, lighter stories can be natural)\n\n"

        "Return ONLY a JSON array of translated strings, one per input line, in the same order. "
        "No explanation, no numbering, just the JSON array. "
        "Example: [\"Title one\", \"Title two\"]"
    ),
    messages=[
        {"role": "user", "content": f"Translate these headlines:\n{numbered}"}
    ]
)

raw = message.content[0].text.strip()
raw = re.sub(r'^```(?:json)?\s*', '', raw)
raw = re.sub(r'\s*```$', '', raw)
titles_en = json.loads(raw)

for i, item in enumerate(items):
    video_id = item["id"]["videoId"]
    thumbnail_url = item["snippet"]["thumbnails"]["high"]["url"]
    published_at = item["snippet"]["publishedAt"]
    channel = item["snippet"]["channelTitle"]
    title_zh = titles_zh[i]
    title_en = titles_en[i]

    supabase.table("headlines").upsert({
        "id": video_id,
        "title_zh": title_zh,
        "title_en": title_en,
        "thumbnail_url": thumbnail_url,
        "published_at": published_at,
        "channel": channel,
    }, on_conflict="id").execute()
    print(f"Inserted/updated: {video_id} | {title_zh} -> {title_en}", flush=True)
