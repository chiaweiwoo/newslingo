"""
NewsLingo job — runs both Astro (YouTube) and Zaobao scrapers,
translates/classifies, upserts to Supabase, logs to job_runs.
"""

import os
import re
import sys
import json
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
print("[job] NewsLingo job starting — build: retry+16k (a6aedc6+)", flush=True)
from supabase import create_client
from dotenv import load_dotenv
import anthropic

from scrapers import astro as astro_scraper
from scrapers import zaobao as zaobao_scraper

load_dotenv(override=True)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")
YOUTUBE_API_KEY      = os.getenv("YOUTUBE_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

CLAUDE_BATCH_SIZE  = 50
TRANSLATE_MODEL    = "claude-haiku-4-5-20251001"
ASSESS_MODEL       = "claude-sonnet-4-6"
DISTILL_MODEL      = "claude-sonnet-4-6"
DISTILL_EVERY_N    = 10          # distill rules every N successful job runs
ASSESS_PASS_SCORE  = 3           # score >= 3 passes, < 3 triggers retry

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

    "For each numbered pair (ZH: Chinese | EN: English), score the translation 1–5:\n"
    "  5 — perfect: accurate meaning, natural English, correct proper nouns\n"
    "  4 — good: minor style issues but fully accurate\n"
    "  3 — acceptable: meaning intact, some awkwardness or minor omissions\n"
    "  2 — poor: key facts or entities wrong/missing, broken grammar\n"
    "  1 — unacceptable: wrong meaning or completely unreadable\n\n"

    "For scores 1–2, you MUST also provide:\n"
    "- \"reason\": one-line explanation of what is wrong\n"
    "- \"suggestion\": the correct English translation you would use instead\n\n"

    "Return ONLY a JSON array, one object per input, same order:\n"
    "[{\"score\": 5}, {\"score\": 2, \"reason\": \"brief note\", \"suggestion\": \"corrected headline\"}, ...]\n"
)

DISTILL_SYSTEM_PROMPT = (
    "You are a translation quality analyst. You will be given a list of Chinese news headline "
    "translation failures, each with the bad translation and a corrected version.\n\n"

    "Your task: extract 5–10 concise, actionable rules that would prevent these failures in future runs.\n\n"

    "Rules must be:\n"
    "- Specific and directive (e.g. 'Always use MACC for 反贪会, never anti-corruption body')\n"
    "- Generalised from patterns, not just restating individual examples\n"
    "- Focused on terminology, proper nouns, and structural issues — not style preferences\n\n"

    "Return ONLY a JSON array of rule strings:\n"
    "[\"rule 1\", \"rule 2\", ...]\n"
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_last_published_at(channel: str) -> datetime | None:
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


def _get_successful_run_count() -> int:
    result = (
        supabase.table("job_runs")
        .select("id", count="exact")
        .eq("status", "success")
        .execute()
    )
    return result.count or 0


# ── Prompt construction ───────────────────────────────────────────────────────

def _load_prompt_rules(source: str) -> str:
    result = (
        supabase.table("prompt_rules")
        .select("rules")
        .eq("source", source)
        .eq("active", True)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["rules"] if result.data else ""


def _load_failure_examples(source: str, limit: int = 8) -> list[dict]:
    result = (
        supabase.table("assessment_logs")
        .select("sample_failures")
        .eq("source", source)
        .not_.is_("sample_failures", "null")
        .order("ran_at", desc=True)
        .limit(5)
        .execute()
    )
    examples: list[dict] = []
    for row in result.data:
        examples.extend(row["sample_failures"] or [])
        if len(examples) >= limit:
            break
    return examples[:limit]


def _build_prompt(source: str, base_prompt: str) -> str:
    """Assemble final prompt: static base + distilled rules + few-shot corrections."""
    prompt = base_prompt

    rules = _load_prompt_rules(source)
    if rules:
        prompt += f"\n\nDISTILLED RULES (learned from past failures — follow strictly):\n{rules}\n"

    examples = [f for f in _load_failure_examples(source) if f.get("suggestion")]
    if examples:
        block = "\n".join(
            f"- ZH: {f['zh']}\n  Correct EN: {f['suggestion']}"
            for f in examples
        )
        prompt += f"\n\nFEW-SHOT CORRECTIONS — use these as translation references:\n{block}\n"

    return prompt


# ── Translation ───────────────────────────────────────────────────────────────

def _call_claude(model: str, system: str, content: str) -> list[dict]:
    for attempt in range(2):
        msg = claude.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw).strip()
        raw = re.sub(r"\s*```$", "", raw).strip()
        if not raw:
            print(
                f"  [claude] empty response on attempt {attempt + 1} "
                f"(model={model} stop_reason={msg.stop_reason})"
                + (" — retrying" if attempt == 0 else " — giving up"),
                flush=True,
            )
            if attempt == 0:
                continue
            raise ValueError(f"Empty response from Claude after 2 attempts (model={model})")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(
                f"  [claude] JSON parse error on attempt {attempt + 1}: {e}\n"
                f"  raw (first 300 chars): {raw[:300]}",
                flush=True,
            )
            if attempt == 0:
                continue
            raise
    raise ValueError("_call_claude: unreachable")


def translate_zaobao(rows: list[dict], prompt: str) -> list[dict]:
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(f"{j+1}. {r['title_zh']}" for j, r in enumerate(batch))
        results = _call_claude(TRANSLATE_MODEL, prompt, f"Translate these headlines:\n{numbered}")
        for j, t in enumerate(results):
            rows[i + j]["title_en"] = t["title_en"]
            rows[i + j]["category"] = t["category"]
        print(f"[zaobao] translated batch {i // CLAUDE_BATCH_SIZE + 1} ({len(batch)} items)", flush=True)
    return rows


def translate_astro(rows: list[dict], prompt: str) -> list[dict]:
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(f"{j+1}. {r['title_zh']}" for j, r in enumerate(batch))
        results = _call_claude(TRANSLATE_MODEL, prompt, f"Translate these headlines:\n{numbered}")
        for j, t in enumerate(results):
            rows[i + j]["title_en"] = t["title_en"]
            rows[i + j]["category"] = t["category"]
        print(f"[astro] translated batch {i // CLAUDE_BATCH_SIZE + 1} ({len(batch)} items)", flush=True)
    return rows


def assess_translations(rows: list[dict], source: str) -> tuple[list[dict], list[dict], list[dict], float]:
    """Assess translation quality. Returns (passed, failed, failure_samples, avg_score)."""
    passed, failed, failure_samples, scores = [], [], [], []
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. ZH: {r['title_zh']} | EN: {r['title_en']}"
            for j, r in enumerate(batch)
        )
        results = _call_claude(ASSESS_MODEL, ASSESS_SYSTEM_PROMPT, f"Assess these translations:\n{numbered}")
        for j, result in enumerate(results):
            row = batch[j]
            score = result.get("score", 3)
            scores.append(score)
            if score >= ASSESS_PASS_SCORE:
                passed.append(row)
            else:
                failed.append(row)
                if len(failure_samples) < 10:
                    failure_samples.append({
                        "zh":         row["title_zh"],
                        "en":         row.get("title_en", ""),
                        "score":      score,
                        "reason":     result.get("reason", ""),
                        "suggestion": result.get("suggestion", ""),
                    })
                print(
                    f"  [{source}] ASSESS FAIL (score={score}): {row['title_zh'][:30]} → "
                    f"{(row.get('title_en') or '')[:40]} | {result.get('reason', '')}",
                    flush=True,
                )
        batch_passed = sum(1 for r in results if r.get("score", 3) >= ASSESS_PASS_SCORE)
        print(f"[{source}] assessed batch {i // CLAUDE_BATCH_SIZE + 1}: {batch_passed}/{len(batch)} passed", flush=True)
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    print(f"[{source}] assessment: {len(passed)} passed, {len(failed)} failed, avg_score={avg_score}", flush=True)
    return passed, failed, failure_samples, avg_score


def _log_assessment(
    source: str,
    total: int,
    passed: int,
    retried: int,
    passed_after_retry: int,
    still_failing: int,
    failure_samples: list[dict],
    avg_score: float,
) -> None:
    supabase.table("assessment_logs").insert({
        "source":              source,
        "model":               ASSESS_MODEL,
        "total_assessed":      total,
        "passed":              passed,
        "retried":             retried,
        "passed_after_retry":  passed_after_retry,
        "dropped":             still_failing,
        "sample_failures":     failure_samples or None,
        "avg_score":           avg_score,
    }).execute()
    print(
        f"[{source}] logged assessment: total={total} passed={passed} "
        f"retried={retried} rescued={passed_after_retry} still_failing={still_failing} avg_score={avg_score}",
        flush=True,
    )


# ── Distillation ──────────────────────────────────────────────────────────────

def _replace_prompt_rules(source: str, rules: list[str], run_count: int) -> None:
    supabase.table("prompt_rules").update({"active": False}).eq("source", source).execute()
    rules_text = "\n".join(f"- {r}" for r in rules)
    supabase.table("prompt_rules").insert({
        "source":       source,
        "rules":        rules_text,
        "run_count_at": run_count,
        "active":       True,
    }).execute()
    print(f"[{source}] prompt_rules updated ({len(rules)} rules)", flush=True)


def _distill_rules(source: str, run_count: int) -> None:
    print(f"[{source}] distilling rules from assessment history...", flush=True)
    result = (
        supabase.table("assessment_logs")
        .select("sample_failures")
        .eq("source", source)
        .not_.is_("sample_failures", "null")
        .order("ran_at", desc=True)
        .limit(50)
        .execute()
    )
    all_failures: list[dict] = []
    for row in result.data:
        all_failures.extend(row["sample_failures"] or [])

    actionable = [f for f in all_failures if f.get("suggestion")]
    if not actionable:
        print(f"[{source}] no actionable failures for distillation, skipping", flush=True)
        return

    numbered = "\n".join(
        f"{i+1}. ZH: {f['zh']}\n   Bad EN: {f['en']}\n   Correct EN: {f['suggestion']}\n   Reason: {f.get('reason', '')}"
        for i, f in enumerate(actionable[:60])
    )
    rules = _call_claude(
        DISTILL_MODEL,
        DISTILL_SYSTEM_PROMPT,
        f"Extract translation rules from these failures:\n{numbered}",
    )
    _replace_prompt_rules(source, rules, run_count)


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
sources_processed = []

try:
    zaobao_prompt = _build_prompt("zaobao", ZAOBAO_SYSTEM_PROMPT)
    astro_prompt  = _build_prompt("astro",  ASTRO_SYSTEM_PROMPT)

    # ── Zaobao ────────────────────────────────────────────────────────────────
    zaobao_since = get_last_published_at(zaobao_scraper.CHANNEL)
    print(f"[zaobao] since_dt = {zaobao_since}", flush=True)
    zaobao_rows = zaobao_scraper.scrape(zaobao_since)

    if zaobao_rows:
        sources_processed.append("zaobao")
        zaobao_rows = translate_zaobao(zaobao_rows, zaobao_prompt)
        zaobao_rows, z_failed, z_samples, z_avg = assess_translations(zaobao_rows, "zaobao")
        z_retried = len(z_failed)
        z_rescued, z_still_failing = 0, 0
        if z_failed:
            print(f"[zaobao] retrying {z_retried} failed translations...", flush=True)
            z_failed = translate_zaobao(z_failed, zaobao_prompt)
            z_retry_passed, z_remaining, z_retry_samples, _ = assess_translations(z_failed, "zaobao-retry")
            zaobao_rows.extend(z_retry_passed)
            zaobao_rows.extend(z_remaining)
            z_rescued = len(z_retry_passed)
            z_still_failing = len(z_remaining)
            z_samples.extend(z_retry_samples)
            if z_still_failing:
                print(f"[zaobao] {z_still_failing} inserted despite failing assessment (logged)", flush=True)
        _log_assessment("zaobao", len(zaobao_rows), len(zaobao_rows) - z_still_failing, z_retried, z_rescued, z_still_failing, z_samples, z_avg)
        upsert_rows(zaobao_rows)

    # ── Astro ─────────────────────────────────────────────────────────────────
    astro_since = get_last_published_at(astro_scraper.CHANNEL)
    print(f"[astro]  since_dt = {astro_since}", flush=True)
    astro_rows = astro_scraper.scrape(astro_since, YOUTUBE_API_KEY)

    if astro_rows:
        sources_processed.append("astro")
        astro_rows = translate_astro(astro_rows, astro_prompt)
        astro_rows, a_failed, a_samples, a_avg = assess_translations(astro_rows, "astro")
        a_retried = len(a_failed)
        a_rescued, a_still_failing = 0, 0
        if a_failed:
            print(f"[astro] retrying {a_retried} failed translations...", flush=True)
            a_failed = translate_astro(a_failed, astro_prompt)
            a_retry_passed, a_remaining, a_retry_samples, _ = assess_translations(a_failed, "astro-retry")
            astro_rows.extend(a_retry_passed)
            astro_rows.extend(a_remaining)
            a_rescued = len(a_retry_passed)
            a_still_failing = len(a_remaining)
            a_samples.extend(a_retry_samples)
            if a_still_failing:
                print(f"[astro] {a_still_failing} inserted despite failing assessment (logged)", flush=True)
        _log_assessment("astro", len(astro_rows), len(astro_rows) - a_still_failing, a_retried, a_rescued, a_still_failing, a_samples, a_avg)
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
        "items_found":      items_found,
        "items_processed":  items_processed,
        "status":           status,
        "error_msg":        error_msg,
        "duration_seconds": duration,
    }).execute()
    print(
        f"Done: {status} | found={items_found} processed={items_processed} duration={duration}s",
        flush=True,
    )

    # ── Distillation (every N successful runs, per source that processed rows) ─
    if status == "success" and sources_processed:
        run_count = _get_successful_run_count()
        if run_count % DISTILL_EVERY_N == 0:
            print(f"[distill] run #{run_count} — triggering rule distillation...", flush=True)
            for src in sources_processed:
                try:
                    _distill_rules(src, run_count)
                except Exception as e:
                    print(f"[distill] {src} failed: {e}", flush=True)
