"""
NewsLingo job — runs both Astro (YouTube) and Zaobao scrapers,
translates/classifies, upserts to Supabase, logs to job_runs.
"""

import json
import os
import sys
import time
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from langfuse import get_client as _langfuse_client
from langfuse import observe

from scrapers import astro as astro_scraper
from scrapers import zaobao as zaobao_scraper
from supabase import create_client

sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")
YOUTUBE_API_KEY      = os.getenv("YOUTUBE_API_KEY")
os.environ.setdefault("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
claude   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)  # prevent hung connections stalling the job

CLAUDE_BATCH_SIZE  = 50          # translation batch size
ASSESS_BATCH_SIZE  = 20          # assess batch — smaller; Sonnet drops/duplicates items at higher counts
TRANSLATE_MODEL    = "claude-sonnet-4-6"
ASSESS_MODEL       = "claude-sonnet-4-6"
DISTILL_MODEL      = "claude-sonnet-4-6"
ASSESS_PASS_SCORE  = 3           # score >= 3 passes, < 3 triggers retry

# ── System prompts ────────────────────────────────────────────────────────────

ASTRO_SYSTEM_PROMPT = (
    "You are an expert Malaysian news translator and classifier. For each headline:\n"
    "1. Translate from Chinese to Malaysian English\n"
    "2. Classify as 'Malaysia', 'Singapore', or 'International'\n\n"

    "CLASSIFICATION RULES (apply in order — stop at first match):\n"
    "1. 'Malaysia' — news about Malaysian politics, people, places, companies, courts, or events\n"
    "2. 'Singapore' — news exclusively about Singapore with no material Malaysian angle\n"
    "   (rare on this channel — only use when the story is clearly and solely about Singapore)\n"
    "3. 'International' — news about other countries, world leaders, global events\n\n"
    "Sequential tie-breaking:\n"
    "- Malaysia-Singapore bilateral stories → 'Malaysia' (classify from Astro's Malaysian perspective)\n"
    "- Southeast Asian regional news (Thailand, Indonesia, Vietnam, etc.) → 'International'\n"
    "- When in doubt between Malaysia and Singapore → 'Malaysia'\n"
    "- When in doubt between Singapore and International → 'International'\n\n"

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

    "FAITHFULNESS: Translate the headline as-is. Do not add context, explain abbreviations "
    "inline, or embellish with facts not present in the Chinese source.\n\n"

    "Return ONLY a JSON array, one object per input line, same order.\n"
    "Each object must have exactly two keys: \"title_en\" and \"category\".\n"
    "If a headline cannot be reliably translated, use {\"title_en\": null, \"category\": null} "
    "rather than guessing.\n"
    "Before returning, verify: (1) the array length exactly matches the number of input lines, "
    "(2) every proper noun (person, place, organisation) in your output is correctly identified — "
    "re-check any you were uncertain about; "
    "(3) if no classification rule clearly applies, default to 'International'.\n"
    "Example: [{\"title_en\": \"PM meets king\", \"category\": \"Malaysia\"}, "
    "{\"title_en\": \"Trump signs bill\", \"category\": \"International\"}, "
    "{\"title_en\": \"Singapore budget announced\", \"category\": \"Singapore\"}]"
)

ZAOBAO_SYSTEM_PROMPT = (
    # INVARIANT: Zaobao category is set from the source URL section, NOT by the LLM.
    # This prompt intentionally asks for translation ONLY — no classification.
    "You are an expert Singapore news translator. Translate each headline from Chinese "
    "to Singapore English.\n\n"

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

    "EMBEDDED TERMS: If the Chinese headline contains embedded English or Malay words, "
    "keep them unchanged — do not back-translate them.\n\n"

    "STYLE: Singapore English, concise headlines, keep proper nouns.\n\n"

    "FAITHFULNESS: Translate the headline as-is. Do not add context, explain abbreviations "
    "inline, or embellish with facts not present in the Chinese source.\n"
    "PROPER NOUNS: For non-Singaporean proper nouns (foreign leaders, international organisations, "
    "overseas place names) that you cannot confidently identify, keep the Chinese romanisation "
    "rather than guessing an English equivalent.\n\n"

    "Return ONLY a JSON array, one object per input line, same order.\n"
    "Each object must have exactly ONE key: \"title_en\".\n"
    "If a headline cannot be reliably translated, use {\"title_en\": null} rather than guessing.\n"
    "Before returning, verify: (1) the array length exactly matches the number of input lines, "
    "(2) every proper noun in your output is correctly identified.\n"
    "Example: [{\"title_en\": \"PM meets President\"}, {\"title_en\": \"Flood hits Johor\"}]"
)

ZAOBAO_SEA_SYSTEM_PROMPT = (
    # Used for Zaobao /sea (Southeast Asia) articles ONLY.
    # These articles need translation AND classification because the section covers
    # multiple countries — LLM must decide International / Singapore / Malaysia.
    "You are an expert Southeast Asia news translator and classifier. "
    "For each Zaobao headline from the /sea (Southeast Asia) section:\n"
    "1. Translate from Chinese to Singapore English\n"
    "2. Classify as 'Singapore', 'Malaysia', or 'International'\n\n"

    "CLASSIFICATION RULES (apply in order — stop at first match):\n"
    "1. 'Singapore' — story is primarily about Singapore or Singapore government actions\n"
    "2. 'Malaysia' — story is primarily about Malaysia, Malaysian politics, people, or events\n"
    "3. 'International' — all other SEA countries (Thailand, Indonesia, Vietnam, Myanmar, "
    "Philippines, Cambodia, Brunei, Laos, etc.), ASEAN-wide stories, or non-SEA content\n\n"
    "Tie-breaking:\n"
    "- Malaysia-Singapore bilateral stories → classify by which country is the primary subject\n"
    "- Broad SEA regional news without a single-country focus → 'International'\n"
    "- When uncertain between Singapore and International → 'International'\n\n"

    "POLITICAL TITLES:\n"
    "- 总理 → Prime Minister\n"
    "- 副总理 → Deputy Prime Minister\n"
    "- 国务资政/资政 → Senior Minister\n"
    "- 部长 → Minister\n"
    "- 首相 → Prime Minister (Malaysia)\n"
    "- 副首相 → Deputy Prime Minister (Malaysia)\n"
    "- 总统 → President\n\n"

    "GOVERNMENT AGENCIES:\n"
    "- 建屋局/建屋发展局 → Housing Development Board (HDB)\n"
    "- 金融管理局 → Monetary Authority of Singapore (MAS)\n"
    "- 警察部队/新加坡警察 → Singapore Police Force (SPF)\n"
    "- 反贪污委员会/反贪会 → Malaysian Anti-Corruption Commission (MACC)\n"
    "- 国家银行 → Bank Negara Malaysia (BNM)\n\n"

    "STYLE: Singapore English, concise headlines, keep proper nouns.\n\n"

    "FAITHFULNESS: Translate the headline as-is. Do not add context, explain abbreviations "
    "inline, or embellish with facts not present in the Chinese source.\n"
    "PROPER NOUNS: For non-Singapore/Malaysia proper nouns (foreign leaders, organisations, "
    "place names outside the region) that you cannot confidently identify, keep the Chinese "
    "romanisation rather than guessing an English equivalent.\n"
    "CLASSIFICATION TIE-BREAK: When genuinely unclear between two categories, prefer 'International'.\n\n"

    "THIRD-COUNTRY AGENCIES: For government agencies or organisations outside Singapore and Malaysia "
    "that you cannot confidently identify, use the official English name if widely known; otherwise "
    "keep the Chinese name as romanisation rather than guessing.\n\n"

    "Return ONLY a JSON array, one object per input line, same order.\n"
    "Each object must have exactly two keys: \"title_en\" and \"category\".\n"
    "If a headline cannot be reliably translated, use {\"title_en\": null, \"category\": null} "
    "rather than guessing.\n"
    "Before returning, verify: (1) the array length exactly matches the number of input lines, "
    "(2) every proper noun in your output is correctly identified.\n"
    "Example: [{\"title_en\": \"Thailand PM visits Singapore\", \"category\": \"International\"}, "
    "{\"title_en\": \"Malaysia floods worsen\", \"category\": \"Malaysia\"}, "
    "{\"title_en\": \"Singapore tightens border checks\", \"category\": \"Singapore\"}]"
)

ASSESS_SYSTEM_PROMPT = (
    "You are a Chinese-to-English translation quality assessor for news headlines.\n\n"

    "For each numbered pair (ZH: Chinese | EN: English), score the translation 1–5:\n"
    "  5 — perfect: accurate meaning, natural English, correct proper nouns\n"
    "  4 — good: minor style issues but fully accurate\n"
    "  3 — acceptable: meaning intact, some awkwardness; minor style omissions only\n"
    "  2 — poor: key facts or entities wrong/missing/dropped, broken grammar\n"
    "       Note: omitting a named person, place, or organisation is always score 2 or lower.\n"
    "  1 — unacceptable: wrong meaning or completely unreadable\n\n"

    "PROPER NOUN RULE — this is the most important rule:\n"
    "Person names, place names, and organisation names must be verified against your "
    "knowledge of current affairs. If a proper noun in the English translation does not "
    "match what you know the Chinese refers to — or if you are not confident the entity "
    "is correctly identified — score it 2 and provide the correct translation.\n"
    "Do NOT give a passing score (3+) to a translation with a doubtful proper noun.\n"
    "Examples of errors to catch:\n"
    "- A Chinese abbreviated name (e.g. 高市) translated as a city when it refers to a person\n"
    "- A foreign leader's name transliterated incorrectly\n"
    "- An organisation rendered as a generic description instead of its official name\n\n"

    "For scores 1–2, you MUST also provide:\n"
    "- \"reason\": one-line explanation of what is wrong\n"
    "- \"suggestion\": the correct English translation you would use instead\n\n"

    "OUTPUT FORMAT — STRICT:\n"
    "- Return ONLY a JSON array. No preamble, no explanation, no markdown.\n"
    "- Exactly one object per input, in the same order. Array length must equal input count.\n"
    "- Your response must START with '[' and END with ']'.\n"
    "If either the ZH or EN value in an input pair is null or empty, score it 1 with "
    "reason 'missing input' and suggestion ''.\n"
    "Before returning, confirm: (1) array length matches input count, "
    "(2) every score-1/2 object has both 'reason' and 'suggestion', "
    "(3) every score-4/5 has no uncertain proper noun — downgrade to 2 if in doubt.\n"
    "Example: [{\"score\": 5}, {\"score\": 2, \"reason\": \"brief note\", \"suggestion\": \"corrected headline\"}, ...]\n"
)

DISTILL_SYSTEM_PROMPT = (
    "You are a translation quality analyst. You will be given a list of Chinese news headline "
    "translation failures, each with the bad translation and a corrected version.\n\n"

    "Your task: extract 5–10 concise, actionable rules that would prevent these failures in future runs.\n\n"

    "Rules must be:\n"
    "- Specific and directive (e.g. 'Always use MACC for 反贪会, never anti-corruption body')\n"
    "- Start with an imperative verb: Always, Never, Use, Keep, or similar\n"
    "- Generalised from patterns, not just restating individual examples\n"
    "- Focused on terminology, proper nouns, and structural issues — not style preferences\n"
    "- Grounded in the provided failures — do not invent examples or patterns not present in the input\n\n"

    "If fewer than 3 failures are provided, return an empty array [] — "
    "do not fabricate patterns from insufficient data.\n\n"

    "Before returning, verify each rule can be traced back to at least one failure in the input. "
    "Remove any rule you cannot justify from the provided data.\n\n"

    "Return rules in English only.\n"
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

def _extract_json_array(text: str) -> str | None:
    """Best-effort recover a JSON array from text that may contain prose.

    Strategy: find the first '[' and last ']' and return the slice. This handles
    cases where prefill failed and the model wrapped the array in explanation,
    or used a code fence. Returns None if no array brackets found.
    """
    first = text.find("[")
    last = text.rfind("]")
    if first == -1 or last == -1 or last <= first:
        return None
    return text[first:last + 1]


@observe(as_type="generation")
def _call_claude(model: str, system: str, content: str, use_prefill: bool = True, name: str = "claude") -> list[dict]:
    """Call Claude expecting a JSON array.

    use_prefill=True  — adds {"role": "assistant", "content": "["} to force JSON output.
                        Supported by Haiku. Use for translation calls.
    use_prefill=False — ends with the user message only (required for Sonnet 4.6+
                        which returns 400 if the conversation ends with an assistant turn).
                        The system prompt must be sufficiently strict to avoid prose.

    Layered defences (applied regardless of prefill mode):
      1. Prefill '[' (when enabled) — model can't emit preamble before '['.
      2. Prepend '[' to response body (prefill mode) or extract from raw body.
      3. Regex-extract '[ ... ]' — handles code-fenced or prose-wrapped arrays.
      4. Truncate to last ']' — handles max_tokens truncation mid-array.
      5. Retry once on any failure.
      6. After 2 failures, raise with raw content for diagnosis.
    """
    last_error: Exception | None = None
    for attempt in range(2):
        messages: list[dict] = [{"role": "user", "content": content}]
        if use_prefill:
            messages.append({"role": "assistant", "content": "["})

        msg = claude.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=messages,
        )
        _langfuse_client().update_current_generation(
            name=name,
            model=model,
            usage_details={"input": msg.usage.input_tokens, "output": msg.usage.output_tokens},
        )
        body = msg.content[0].text if msg.content else ""

        candidates: list[str] = []
        if use_prefill:
            # Response body continues from '[' — prepend it back
            candidates.append("[" + body)
        # Always try extracting a [...] directly from the body
        # (handles: no prefill, code-fenced output, model re-emitting '[')
        extracted = _extract_json_array(body)
        if extracted:
            candidates.append(extracted)

        # Truncate to last ']' for each candidate (handles max_tokens truncation)
        for cand in list(candidates):
            last_close = cand.rfind("]")
            if last_close > 0 and last_close < len(cand) - 1:
                candidates.append(cand[:last_close + 1])

        for cand in candidates:
            try:
                parsed = json.loads(cand)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError as e:
                last_error = e
                continue

        # All candidates failed for this attempt — log and retry
        print(
            f"  [claude] all parse strategies failed on attempt {attempt + 1} "
            f"(model={model} stop_reason={msg.stop_reason} prefill={use_prefill})",
            flush=True,
        )
        print(f"  body (first 400): {body[:400]!r}", flush=True)
        print(f"  body (last 200): {body[-200:]!r}", flush=True)

    raise ValueError(
        f"_call_claude failed after 2 attempts (model={model}); last error: {last_error}"
    )


def _translate_batch(source: str, rows: list[dict], prompt: str, classify: bool = True) -> list[dict]:
    """Shared translation logic — defensive against length mismatch from Claude.

    classify=True  → LLM sets category (used for Astro).
    classify=False → category already set from URL; LLM only fills title_en (used for Zaobao).
    """
    for i in range(0, len(rows), CLAUDE_BATCH_SIZE):
        batch = rows[i:i + CLAUDE_BATCH_SIZE]
        numbered = "\n".join(f"{j+1}. {r['title_zh']}" for j, r in enumerate(batch))
        results = _call_claude(TRANSLATE_MODEL, prompt, f"Translate these headlines:\n{numbered}", use_prefill=False, name=f"translate:{source}")
        if len(results) != len(batch):
            print(
                f"  [{source}] WARNING: translate returned {len(results)} for {len(batch)} input items",
                flush=True,
            )
        # iterate over batch (fixed length); pair with result if available
        for j, row in enumerate(batch):
            if j < len(results) and isinstance(results[j], dict):
                t = results[j]
                row["title_en"] = t.get("title_en") or row["title_zh"]
                if classify:
                    row["category"] = t.get("category") or "International"
                # classify=False: category was set by scraper from URL — do NOT overwrite
            else:
                # no result — leave title_en blank, keep existing category
                row["title_en"] = row.get("title_en") or row["title_zh"]
                if classify:
                    row["category"] = row.get("category") or "International"
        print(f"[{source}] translated batch {i // CLAUDE_BATCH_SIZE + 1} ({len(batch)} items)", flush=True)
    return rows


def _validate_zaobao_categories(rows: list[dict], stage: str) -> None:
    """Hard crash if any Zaobao row has a None/empty category (after accounting for sea rows).

    At post-scrape:  /sea/ rows legitimately have category=None (LLM-classified later).
                     Only singapore/world rows must already have a category set from URL.
    At post-translate: ALL rows (including sea) must have a category.
    """
    if stage == "post-scrape":
        bad = [r for r in rows if not r.get("category") and "/news/sea/" not in r.get("source_url", "")]
    else:
        bad = [r for r in rows if not r.get("category")]
    if bad:
        urls = [r.get("source_url", "?") for r in bad[:5]]
        raise AssertionError(
            f"[zaobao] INVARIANT VIOLATION at {stage}: {len(bad)} rows have missing category. "
            f"First offenders: {urls}"
        )


def translate_zaobao(rows: list[dict], url_prompt: str, sea_prompt: str) -> list[dict]:
    """Translate Zaobao rows, routing by section:

    singapore/world rows — category already set from URL (classify=False).
    /sea/ rows           — category=None, LLM must classify (classify=True, sea_prompt).
    """
    url_rows = [r for r in rows if r.get("category")]     # singapore/world: URL-classified
    sea_rows = [r for r in rows if not r.get("category")] # sea: needs LLM classification

    if url_rows:
        _translate_batch("zaobao", url_rows, url_prompt, classify=False)
    if sea_rows:
        _translate_batch("zaobao-sea", sea_rows, sea_prompt, classify=True)

    return rows


def translate_astro(rows: list[dict], prompt: str) -> list[dict]:
    return _translate_batch("astro", rows, prompt, classify=True)


@observe(as_type="span")
def assess_translations(rows: list[dict], source: str) -> tuple[list[dict], list[dict], list[dict], float]:
    """Assess translation quality. Returns (passed, failed, failure_samples, avg_score).

    Defensive: if Sonnet returns wrong number of results, default missing items to score=3
    (pass) so we never crash and never falsely reject valid translations.
    Logs avg_score (1–5) to Langfuse as a 'translation_quality' score on the trace.
    """
    passed, failed, failure_samples, scores = [], [], [], []
    for i in range(0, len(rows), ASSESS_BATCH_SIZE):
        batch = rows[i:i + ASSESS_BATCH_SIZE]
        numbered = "\n".join(
            f"{j+1}. ZH: {r['title_zh']} | EN: {r['title_en']}"
            for j, r in enumerate(batch)
        )
        results = _call_claude(ASSESS_MODEL, ASSESS_SYSTEM_PROMPT, f"Assess these translations:\n{numbered}", use_prefill=False, name=f"assess:{source}")
        if len(results) != len(batch):
            print(
                f"  [{source}] WARNING: assess returned {len(results)} for {len(batch)} input items "
                f"— defaulting missing to score=3",
                flush=True,
            )
        # iterate over batch (fixed length); pair with result if available
        for j, row in enumerate(batch):
            if j < len(results) and isinstance(results[j], dict):
                result = results[j]
            else:
                result = {"score": 3}  # missing → default pass
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
        batch_passed = sum(1 for r in (results[:len(batch)]) if isinstance(r, dict) and r.get("score", 3) >= ASSESS_PASS_SCORE)
        print(f"[{source}] assessed batch {i // ASSESS_BATCH_SIZE + 1}: {batch_passed}/{len(batch)} passed", flush=True)
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    print(f"[{source}] assessment: {len(passed)} passed, {len(failed)} failed, avg_score={avg_score}", flush=True)
    _langfuse_client().score_current_trace(
        name="translation_quality",
        value=avg_score,
        data_type="NUMERIC",
        comment=f"{source}: {len(passed)}/{len(passed) + len(failed)} passed (1–5 scale)",
    )
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
        use_prefill=False,
        name=f"distill:{source}",
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

def _main() -> None:
    print("[job] NewsLingo job starting — build: hardening (post-bf21d57)", flush=True)
    start_time = time.perf_counter()
    items_found = 0
    items_processed = 0
    status = "success"
    error_msg = None
    sources_processed = []
    zaobao_rows: list[dict] = []
    astro_rows: list[dict] = []

    try:
        zaobao_url_prompt = _build_prompt("zaobao", ZAOBAO_SYSTEM_PROMPT)
        zaobao_sea_prompt = _build_prompt("zaobao", ZAOBAO_SEA_SYSTEM_PROMPT)
        astro_prompt      = _build_prompt("astro",  ASTRO_SYSTEM_PROMPT)

        # ── Zaobao ────────────────────────────────────────────────────────────────
        zaobao_since = get_last_published_at(zaobao_scraper.CHANNEL)
        print(f"[zaobao] since_dt = {zaobao_since}", flush=True)
        zaobao_rows = zaobao_scraper.scrape(zaobao_since)

        if zaobao_rows:
            sources_processed.append("zaobao")
            _validate_zaobao_categories(zaobao_rows, "post-scrape")  # sea rows exempt; sg/world must have category
            zaobao_rows = translate_zaobao(zaobao_rows, zaobao_url_prompt, zaobao_sea_prompt)
            _validate_zaobao_categories(zaobao_rows, "post-translate")  # all rows including sea must have category
            zaobao_rows, z_failed, z_samples, z_avg = assess_translations(zaobao_rows, "zaobao")
            z_retried = len(z_failed)
            z_rescued, z_still_failing = 0, 0
            if z_failed:
                print(f"[zaobao] retrying {z_retried} failed translations...", flush=True)
                z_failed = translate_zaobao(z_failed, zaobao_url_prompt, zaobao_sea_prompt)
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
        duration = round(time.perf_counter() - start_time, 2)
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

        # ── Distillation (every successful run, all sources regardless of new articles) ─
        if status == "success":
            run_count = _get_successful_run_count()
            for src in ("zaobao", "astro"):
                print(f"[distill] {src}: distilling rules from run #{run_count}...", flush=True)
                try:
                    _distill_rules(src, run_count)
                except Exception as e:
                    print(f"[distill] {src} failed: {e}", flush=True)



if __name__ == "__main__":
    _main()
    _langfuse_client().flush()  # ensure all traces are sent before process exits
