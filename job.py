"""
News aggregator job — runs both Astro (YouTube) and Zaobao scrapers,
translates/classifies, upserts to Supabase, logs to job_runs.
"""

import os
import re
import sys
import json
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
from supabase import create_client
from dotenv import load_dotenv
import anthropic

import astro_scraper
import zaobao_scraper

load_dotenv(override=True)

SUPABASE_URL        = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
YOUTUBE_API_KEY     = os.getenv("YOUTUBE_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CLAUDE_BATCH_SIZE = 50

# ── System prompts ────────────────────────────────────────────────────────────

ASTRO_SYSTEM_PROMPT = (
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
    "- 推事庭/推事法庭 → Magistrate's Court\n\n"

    "POLITICAL PARTIES & COALITIONS:\n"
    "Keep all acronyms: PKR, DAP, UMNO, Bersatu, Amanah, MCA, MIC, GPS, GRS, "
    "BN (Barisan Nasional), PH (Pakatan Harapan), PN (Perikatan Nasional)\n\n"

    "PLACE NAMES — keep all Malaysian place names in Malay:\n"
    "States: Johor, Kedah, Kelantan, Melaka, Negeri Sembilan, Pahang, Perak, Perlis, "
    "Pulau Pinang, Sabah, Sarawak, Selangor, Terengganu, Kuala Lumpur, Putrajaya, Labuan\n\n"

    "CURRENCY: 令吉/马币 → ringgit (use RM prefix, e.g. RM1.1 billion)\n\n"

    "STYLE: Malaysian English, concise headlines, keep proper nouns.\n\n"

    "Return ONLY a JSON array, one object per input line, same order.\n"
    "Each object must have exactly two keys: \"title_en\" and \"category\".\n"
    "Example: [{\"title_en\": \"PM meets king\", \"category\": \"Malaysia\"}, "
    "{\"title_en\": \"Trump signs bill\", \"category\": \"International\"}]"
)

ZAOBAO_SYSTEM_PROMPT = (
    "You are an expert Singapore news translator and classifier. For each headline:\n"
    "1. Translate from Chinese to Singapore English\n"
    "2. Classify as 'Singapore' (local SG news) or 'International' (foreign/world news)\n\n"

    "CLASSIFICATION RULES:\n"
    "- 'Singapore': news about Singapore politics, people, places, companies, courts, or events\n"
    "- 'International': news about other countries, world leaders, global events, foreign incidents\n"
    "- When in doubt (e.g. Singapore reaction to world event): classify by WHERE the event happened\n\n"

    "POLITICAL TITLES:\n"
    "- 总理 → Prime Minister\n"
    "- 副总理 → Deputy Prime Minister\n"
    "- 国务资政/资政 → Senior Minister\n"
    "- 部长 → Minister\n"
    "- 国会议员 → Member of Parliament (MP)\n"
    "- 总统 → President\n\n"

    "GOVERNMENT AGENCIES (use official names/abbreviations):\n"
    "- 建屋局/建屋发展局 → Housing Development Board (HDB)\n"
    "- 公积金/公积金局 → Central Provident Fund (CPF)\n"
    "- 金融管理局 → Monetary Authority of Singapore (MAS)\n"
    "- 陆路交通管理局 → Land Transport Authority (LTA)\n"
    "- 移民与关卡局 → Immigration and Checkpoints Authority (ICA)\n"
    "- 警察部队/新加坡警察 → Singapore Police Force (SPF)\n"
    "- 卫生部 → Ministry of Health (MOH)\n"
    "- 教育部 → Ministry of Education (MOE)\n"
    "- 人力部 → Ministry of Manpower (MOM)\n"
    "- 律政部/检察总长 → Attorney-General's Chambers (AGC)\n\n"

    "POLITICAL PARTIES:\n"
    "- 人民行动党 → People's Action Party (PAP)\n"
    "- 工人党 → Workers' Party (WP)\n"
    "- 前进党 → Progress Singapore Party (PSP)\n\n"

    "COURTS:\n"
    "- 上诉庭/上诉法院 → Court of Appeal\n"
    "- 高庭/高等法院 → High Court\n"
    "- 国家法院 → State Courts\n"
    "- 推事庭 → Magistrate's Court\n\n"

    "CURRENCY: 新元/坡元/元 → S$ (e.g. S$1.2 million)\n\n"

    "STYLE: Singapore English, concise headlines, keep proper nouns.\n\n"

    "Return ONLY a JSON array, one object per input line, same order.\n"
    "Each object must have exactly two keys: \"title_en\" and \"category\".\n"
    "Example: [{\"title_en\": \"PM meets President\", \"category\": \"Singapore\"}, "
    "{\"title_en\": \"Trump signs bill\", \"category\": \"International\"}]"
)

ASSESS_SYSTEM_PROMPT = (
    "You are a Chinese-to-English translation quality assessor for news headlines.\n\n"

    "For each numbered pair (ZH: Chinese | EN: English), assess the translation:\n\n"

    "Mark ok=TRUE when:\n"
    "- Meaning is accurate — key facts, names, and events match the Chinese\n"
    "- Translation reads naturally (not word-for-word literal)\n"
    "- Grammar is acceptable (minor imperfections are fine)\n\n"

    "Mark ok=FALSE only when:\n"
    "- Wrong meaning — key facts are changed or lost\n"
    "- Important named entities are mistranslated or missing\n"
    "- Grammar is so broken the headline is unreadable\n\n"

    "Return ONLY a JSON array, one object per input, same order:\n"
    "[{\"ok\": true}, {\"ok\": false, \"reason\": \"brief note\"}, ...]\n"
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_last_published_at(channel: str) -> datetime | None:
    """Return the latest published_at for a specific channel, or None."""
    result = (
        supabase.table("headlines")
        .select("published_at")
        .eq("channel", channel)
        .order("published_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        ts = result.data[0]["published_at"]
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return None


# ── Translation ───────────────────────────────────────────────────────────────

def _call_claude(system: str, content: str) -> list[dict]:
    msg = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def translate_zaobao(rows: list[dict]) -> list[dict]:
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(f"{j+1}. {r['title_zh']}" for j, r in enumerate(batch))
        results = _call_claude(ZAOBAO_SYSTEM_PROMPT, f"Translate these headlines:\n{numbered}")
        for j, t in enumerate(results):
            rows[i + j]["title_en"] = t["title_en"]
            rows[i + j]["category"] = t["category"]
        print(f"[zaobao] translated batch {i // CLAUDE_BATCH_SIZE + 1} ({len(batch)} items)", flush=True)
    return rows


def translate_astro(rows: list[dict]) -> list[dict]:
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(f"{j+1}. {r['title_zh']}" for j, r in enumerate(batch))
        results = _call_claude(ASTRO_SYSTEM_PROMPT, f"Translate these headlines:\n{numbered}")
        for j, t in enumerate(results):
            rows[i + j]["title_en"] = t["title_en"]
            rows[i + j]["category"] = t["category"]
        print(f"[astro] translated batch {i // CLAUDE_BATCH_SIZE + 1} ({len(batch)} items)", flush=True)
    return rows


def assess_translations(rows: list[dict], source: str) -> list[dict]:
    """Filter rows whose translation fails quality assessment."""
    passed, failed_count = [], 0
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. ZH: {r['title_zh']} | EN: {r['title_en']}"
            for j, r in enumerate(batch)
        )
        results = _call_claude(ASSESS_SYSTEM_PROMPT, f"Assess these translations:\n{numbered}")
        for j, result in enumerate(results):
            row = batch[j]
            if result.get("ok", True):
                passed.append(row)
            else:
                failed_count += 1
                print(
                    f"  [{source}] ASSESS FAIL: {row['title_zh'][:30]} → "
                    f"{(row.get('title_en') or '')[:40]} | {result.get('reason', '')}",
                    flush=True,
                )
        batch_passed = sum(1 for r in results if r.get("ok", True))
        print(f"[{source}] assessed batch {i // CLAUDE_BATCH_SIZE + 1}: {batch_passed}/{len(batch)} passed", flush=True)
    print(f"[{source}] assessment: {len(passed)} passed, {failed_count} rejected", flush=True)
    return passed


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_rows(rows: list[dict]) -> None:
    for row in rows:
        supabase.table("headlines").upsert(row, on_conflict="source_url").execute()
        print(
            f"  [{row.get('category', '?')}] {row['source_url'].split('/')[-1][:20]} | "
            f"{row['title_zh'][:30]}... → {(row.get('title_en') or '')[:40]}...",
            flush=True,
        )


# ── Main ──────────────────────────────────────────────────────────────────────

start_time = time.time()
items_found = 0
items_processed = 0
status = "success"
error_msg = None

try:
    # ── Zaobao ────────────────────────────────────────────────────────────────
    zaobao_since = get_last_published_at(zaobao_scraper.CHANNEL)
    print(f"[zaobao] since_dt = {zaobao_since}", flush=True)
    zaobao_rows = zaobao_scraper.scrape(zaobao_since)

    if zaobao_rows:
        zaobao_rows = translate_zaobao(zaobao_rows)
        zaobao_rows = assess_translations(zaobao_rows, "zaobao")
        upsert_rows(zaobao_rows)

    # ── Astro ─────────────────────────────────────────────────────────────────
    # channel column stores channelTitle (e.g. "Astro 本地圈"), not the channel ID
    astro_since = get_last_published_at("Astro 本地圈")
    print(f"[astro]  since_dt = {astro_since}", flush=True)
    astro_rows = astro_scraper.scrape(astro_since, YOUTUBE_API_KEY)

    if astro_rows:
        astro_rows = translate_astro(astro_rows)
        astro_rows = assess_translations(astro_rows, "astro")
        upsert_rows(astro_rows)

    items_found     = len(zaobao_rows) + len(astro_rows)
    items_processed = items_found

except Exception as e:
    status = "error"
    error_msg = str(e)
    print(f"ERROR: {e}", flush=True)
    raise

finally:
    duration = round(time.time() - start_time, 2)
    supabase.table("job_runs").insert({
        "items_found":     items_found,
        "items_processed": items_processed,
        "status":          status,
        "error_msg":       error_msg,
        "duration_seconds": duration,
    }).execute()
    print(
        f"Done: {status} | found={items_found} processed={items_processed} duration={duration}s",
        flush=True,
    )
