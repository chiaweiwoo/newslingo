# NewsLingo — AI Session Memory

Auto-loaded by Claude Code. Records hard invariants and architectural decisions that
MUST be preserved across all future AI-assisted changes.

**Scope: This session is NewsLingo only (`chiaweiwoo/newslingo`). Do not commit or push to any other repository — not `personal-site`, not `tcm-diagnosis`. If the user shares code or issues from another project, discuss only — do not edit or push.**

---

## Project Overview

NewsLingo aggregates bilingual (Chinese + English) news from two sources:
- **联合早报 (Zaobao)** — Singapore newspaper, scraped via monthly sitemaps
- **Astro 本地圈** — Malaysian YouTube channel, fetched via YouTube Data API v3

The project uses a **hybrid AI stack**: DeepSeek V4 Flash/Pro for volume tasks (translation, assessment, distillation, EN→ZH passes), Claude Sonnet 4.6 for reasoning-heavy tasks (Top Stories generation + fact-check), and Claude Haiku 4.5 with Sonnet fallback for AI Radar (web-search + summarisation). Both DeepSeek models are accessed via the Anthropic-compatible SDK (`base_url="https://api.deepseek.com/anthropic"`).
Headlines are stored in Supabase. Four GitHub Actions jobs run the pipeline.
LLM observability (token counts, costs, latency) is handled by **Langfuse Cloud** (`@observe` decorator pattern).

---

## Engineering Principles

- **Do not reinvent the wheel.** Before writing custom infrastructure (retry logic, HTTP clients, date math, token tracking, HTML parsing, caching), check if a library already in the project or a well-known Python package does it. Examples of past wheel-reinvention that were replaced: custom `pricing.py` → Langfuse; regex og: tag extraction → BeautifulSoup (already in deps). When uncertain, ask.

---

## CRITICAL INVARIANTS — DO NOT VIOLATE

### 1. Zaobao: Category source depends on section

| URL section | Category source | Values |
|---|---|---|
| `/news/singapore/` | URL (deterministic) | `Singapore` |
| `/news/world/` | URL (deterministic) | `International` |
| `/news/sea/` | LLM (`ZAOBAO_SEA_SYSTEM_PROMPT`) | `International` / `Singapore` / `Malaysia` |

`/news/china/` is out of scope — not scraped, not stored.

Enforced by:
- `scrapers/zaobao.py` → `_category_from_url(url)` returns `str` for singapore/world, `None` for sea
- `feed_ingest.py` → `translate_zaobao(rows, url_prompt, sea_prompt)` splits by `category is None`:
  - singapore/world rows → `_translate_batch(..., classify=False)` with `ZAOBAO_SYSTEM_PROMPT`
  - sea rows → `_translate_batch(..., classify=True)` with `ZAOBAO_SEA_SYSTEM_PROMPT`
- `feed_ingest.py` → `_validate_zaobao_categories()`:
  - post-scrape: only fails if a singapore/world row has `category=None` (sea exempt)
  - post-translate: ALL rows including sea must have a category
- `tests/test_invariants.py` → CI verifies both classify paths exist

`classify=True` in `translate_zaobao` is correct and expected for sea rows — do NOT remove it.

### 2. Zaobao: Three sections scraped — singapore, world, sea

The sitemap regex must match `singapore`, `world`, and `sea`:

```python
r"<url>\s*<loc>(https://www\.zaobao\.com\.sg/news/(?:singapore|world|sea)/story[^<]+)</loc>"
```

`china` and `sports` are intentionally excluded. The frontend also filters by category.

### 3. Astro: YouTube PlaylistItems API — not Search API

Astro 本地圈 is a YouTube channel. The scraper (`scrapers/astro.py`) uses the
**PlaylistItems endpoint** (uploads playlist, reverse-chronological). It paginates until
hitting a video before the cutoff — same "scan until out of range" logic as Zaobao.

- Upload playlist ID derived by replacing `UC` prefix with `UU` (no extra API call)
- PlaylistItems reflects uploads immediately; Search API has a several-hour indexing delay
- `DEFAULT_LOOKBACK_HOURS = 120` ensures first-run repull has enough coverage

### 4. Astro: Category set by LLM — three valid values; Shorts excluded

Astro has no URL section. `translate_astro()` uses `classify=True`. Valid: `Malaysia`,
`Singapore`, `International`.

Sequential rules (stop at first match):
1. `Malaysia` — Malaysian politics, people, places, companies, courts, events
2. `Singapore` — exclusively Singapore, no material Malaysian angle (rare on this channel)
3. `International` — everything else

Tie-breaking: bilateral Malaysia-Singapore → `Malaysia`; SEA regional → `International`.

**Shorts exclusion:** `scrapers/astro.py` → `_is_short(item)` checks the raw title for
`#Shorts` (case-insensitive). Shorts are filtered out in `scrape()` before rows are built.
They have no news value and would pollute the feed.

### 5. Assistant prefill — disabled for all calls

All Claude calls use `use_prefill=False`. Claude Sonnet 4.6 returns HTTP 400 if the
conversation ends with an assistant turn. DeepSeek calls also use `use_prefill=False`
for consistency.

- **Never** add `use_prefill=True` to any call — it will break in production
- **Never** change `assess_translations` / `_distill_rules` to `use_prefill=True`
- JSON output reliability is enforced through strict system prompt instructions instead

### 7. Job Observability: Never fail silently

All job scripts (`feed_ingest.py`, `summary_ai.py`, `summary_top_stories.py`) MUST exit with a non-zero status (typically `sys.exit(1)`) if a fatal error occurs.
- **Never** catch an exception and exit with 0.
- **Never** assume that printing an error is sufficient for GitHub Actions.
- In `feed_ingest.py`, ensure the final `sys.exit(1)` call happens after the `finally` block logs the run status to the database, so the failure is visible both in GitHub and in the internal audit log.

---

## Architecture

```
GitHub Actions (cron: every 3h)
  └── feed_ingest.py
       ├── scrapers/zaobao.py     → scrape sitemap  → rows (singapore/world: category from URL; sea: category=None)
       ├── scrapers/astro.py      → YouTube API     → rows with category=None (Shorts excluded)
       ├── _translate_batch()     → DeepSeek Flash  → fills title_en (+ category for Astro and Zaobao /sea)
       ├── assess_translations()  → DeepSeek Pro    → scores 1–5, retry if <3
       ├── _distill_rules()       → DeepSeek Pro    → improves prompt_rules each run
       └── upsert_rows()          → Supabase        → headlines table

GitHub Actions (cron: daily 03:00 SGT)
  └── summary_top_stories.py
       ├── skips if < MIN_NEW_HEADLINES (30) since last run
       ├── pulls past 7 days of headlines (rolling window)
       ├── _call_summary() pass 1 → Claude Sonnet  → 8-10 must-know topics (title, summary,
       │                                              region, theme); so_what + lesson used
       │                                              internally as selection criteria, not emitted
       │                            [writes prompt cache on headlines block]
       ├── _call_summary() pass 2 → Claude Sonnet  → fact-check: remove/correct topics whose
       │                                              claims can't be matched; fix tense; hedging
       │                            [cache HIT on headlines block — ~90% cheaper input]
       ├── _call_summary() pass 3 → DeepSeek Flash → translate title + summary to Simplified
       │                                              Chinese; adds title_zh + summary_zh
       └── rotates weekly_summary (deactivates old, inserts new)

GitHub Actions (cron: daily 03:30 SGT)
  └── summary_ai.py
       ├── _call_category() × 3  → Claude Haiku    → web-search + summarise one AI category
       │                            (governance / product / infrastructure)
       │                            falls back to Claude Sonnet if Haiku unavailable
       ├── _translate_categories_to_zh() → DeepSeek Flash → adds title_zh + description_zh
       └── rotates ai_radar (deactivates old, inserts new)
```

**Constants (feed_ingest.py):**
- `CLAUDE_BATCH_SIZE = 50` — translation batch size
- `ASSESS_BATCH_SIZE = 20` — DeepSeek Pro drops/duplicates items at higher counts; do not raise
- `MIN_NEW_HEADLINES = 30` — weekly summary skip threshold (calibrated for 7-day window)
- `LOOKBACK_DAYS = 7` — rolling window for Top Stories summary

**Constants (summary_ai.py):**
- `LOOKBACK_DAYS = 7` — AI Radar lookback window
- `WEB_SEARCH_MAX_USES = 3` — max web searches per category call

---

## Supabase Tables

| Table | Reset on repull? | Notes |
|---|---|---|
| `headlines` | YES | All article rows |
| `assessment_logs` | YES | Per-run quality scores |
| `prompt_rules` | YES | Distilled LLM rules |
| `learning_digest` | YES | Unused — was written by digest.py (now deleted). Safe to clear. |
| `weekly_summary` | YES | Top Stories topics; rotated by summary_top_stories.py |
| `ai_radar` | YES | AI Radar payload; rotated by summary_ai.py |
| `job_runs` | NO | Audit log — preserve |
| `visits` | NO | Frontend analytics — preserve |
| `token_usage` | NO | Legacy — was written by custom pricing.py (now deleted). No longer written; Langfuse handles observability. Safe to ignore. |

---

## Models

| Task | Model | Notes |
|---|---|---|
| Translation | `deepseek-v4-flash` | All sources — high-throughput, cost-effective |
| Assessment | `deepseek-v4-pro` | Structured output; runs every 3h |
| Distillation | `deepseek-v4-pro` | Rule extraction from failures |
| Top Stories Pass 1 + 2 | `claude-sonnet-4-6` | Generate + fact-check — requires reasoning |
| Top Stories Pass 3 | `deepseek-v4-flash` | EN→ZH translation — mechanical task, cheaper |
| AI Radar (primary) | `claude-haiku-4-5` | Web search + summarisation per category |
| AI Radar (fallback) | `claude-sonnet-4-6` | Used if Haiku model is unavailable |
| AI Radar ZH translation | `deepseek-v4-flash` | Adds title_zh + description_zh per item |

Both DeepSeek models are accessed via the Anthropic-compatible SDK:
`anthropic.Anthropic(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/anthropic")`

**Model invariant for summary_top_stories.py:** `SUMMARY_MODEL` and `SUMMARY_FACTCHECK_MODEL` must be Sonnet or Opus (never Haiku or DeepSeek). `SUMMARY_TRANSLATION_MODEL` must be DeepSeek Flash. Do not swap DeepSeek into Pass 1 or Pass 2.

### Top Stories topic schema

Each topic in `weekly_summary.payload.topics` (emitted fields only):

| Field | Type | Notes |
|---|---|---|
| `title` | string | Noun phrase, max 8 words |
| `title_zh` | string | Simplified Chinese translation of title (Pass 3) |
| `summary` | string | WHO/WHAT/WHERE, one sentence, max 25 words |
| `summary_zh` | string | Simplified Chinese translation of summary (Pass 3) |
| `region` | string | `International` \| `Malaysia` \| `Singapore` |
| `theme` | string | `Politics` \| `Economy` \| `Society` \| `Security` \| `Technology` \| `Environment` |

`so_what` and `lesson` are **not emitted**. They are internal selection-thinking dimensions in the Pass 1 prompt — the model must be able to articulate both before a topic qualifies, but does not output them. Do not add them back to the output schema or the frontend `Topic` type.

**Three-pass quality design:**
- Pass 1 generates topics (4 emitted fields). Headlines injected into system with `cache_control: ephemeral`.
- Pass 2 fact-checks every specific claim against source headlines; corrects tense; applies confidence hedging. Headlines cache HIT — ~90% cheaper input tokens.
- Topics whose core claim cannot be matched to any headline are removed.
- Pass 3 (DeepSeek Flash) translates `title` and `summary` into Simplified Chinese, merging `title_zh` and `summary_zh` back by `idx`.

---

## Frontend Features

| Feature | Where | Notes |
|---|---|---|
| Vocab tap | `HeadlineCard` + `useWordDefinition` + `WordSheet` | Tap English word → bottom sheet; Free Dictionary API; module-level cache |
| Read aloud | `SpeechContext` + speaker icon in `HeadlineCard` | Web Speech API; one active at a time |
| Share | `HeadlineCard.shareHeadline()` | Web Share API on mobile; clipboard + toast on desktop |
| Font size | `FontSizeContext` + Preferences menu | S/M/L; persisted in localStorage |
| Dark mode | `theme.ts` + Preferences menu | Chakra color mode; warm dark palette |
| Search | `SearchBar` | Header icon; replaces title row when open; debounced full-text ilike on `title_zh`/`title_en`; results overlay fixed below header |
| Top Stories + AI Radar | `ThisWeekDrawer` | Header icon (4-pt sparkle SVG); two sections: General (Int/SG/MY) + AI (Governance/Product/Infra); EN\|中 language toggle; `localStorage('topStories.lang')` |
| Translation Quiz | `QuizDrawer` | Header icon (pencil SVG); pure random pick on every open; user types EN translation; scored 0–100 via `useSemanticScore` (semantic similarity) |

### Translation Quiz — Transformer.js scoring

`src/hooks/useSemanticScore.ts` — lazy-loads `@huggingface/transformers` (~558KB JS + 23MB WASM) only when the quiz is first used. Model: `Xenova/all-MiniLM-L6-v2` (sentence similarity). Module-level singleton — loaded once per session, cached by the browser.

`computeScore(userText, referenceText)` → `Promise<number>` (0–100, cosine similarity × 100).

`warmUpModel()` — call on drawer open to pre-fetch the model before the user submits.

Key Vite config: `optimizeDeps.exclude: ['@huggingface/transformers']` — prevents Vite from bundling the ONNX runtime into the main chunk. The transformers library is a separate code-split chunk.

Score bands: ≥85 Excellent · ≥65 Good · ≥45 Partially right · <45 Keep practising.

### Prompt quality baseline

All 8 system prompts were audited (2026-05-15). Every prompt must have:
- JSON-only output instruction + inline schema example
- Self-review step that checks both structure **and** content (proper nouns, tense)
- Escalation rule: what to return when the model is uncertain (null, `[]`, or `{}`)
- Anti-hallucination clause: translate/summarise only what the input supports

Run `/prompt-audit` before committing any change to a `*_PROMPT` constant.

### Theme tokens
`brand.red` is static (`#c8102e`). All others (`brand.paper/ink/muted/rule/card`) are
semantic tokens that flip between light and dark. Always use tokens — never hardcode hex.
`brand.card` is the white surface for cards, sheets, and menu backgrounds.

---

## Observability — Langfuse Cloud

All LLM observability (token counts, cost, latency, and translation quality scores) is handled by **Langfuse Cloud**. Do **not** add custom token-tracking code (`_record_token_usage`, `pricing.py`, etc.) — Langfuse handles all of it.

- **Dashboard:** cloud.langfuse.com → your project
- **Secrets:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` in GitHub Actions; `LANGFUSE_BASE_URL` is aliased to `LANGFUSE_HOST` at runtime via `os.environ.setdefault`

### Traces & Generations (feed_ingest.py)

| Trace/Generation name | Type | What it covers |
|---|---|---|
| `translate:zaobao` / `translate:astro` | generation | Each translation batch — tokens, cost, latency |
| `assess:zaobao` / `assess:astro` | **span** (parent) | Wraps all assess batches for one source; holds the quality score |
| `assess:zaobao` / `assess:astro` | generation (child) | Individual assess batch — tokens, cost, latency |
| `distill:zaobao` / `distill:astro` | generation | Rule distillation — tokens, cost |

`assess_translations()` is decorated with `@observe(as_type="span")` so assessment generations nest under it as children, and the quality score attaches to that trace.

### Translation Quality Score

After every `assess_translations()` run, the avg score (1–5 scale) is logged to Langfuse via `score_current_trace(name="translation_quality", ...)`. Visible in **Scores** tab on the dashboard. Use this to track whether distilled rules are improving quality over time.

### Traces & Generations (summary_top_stories.py)

`_call_summary` is decorated with `@observe(as_type="generation")`. The 3 individual Claude calls are wrapped as named child observations:

| Child name | What it covers |
|---|---|
| `summary:generate` | Pass 1 — topic generation |
| `summary:factcheck` | Pass 2 — fact-check and correction |
| `summary:translate-zh` | Pass 3 — Chinese translation |

### Traces & Generations (summary_ai.py)

`_call_ai_radar` is decorated with `@observe(name="ai-radar:generate", as_type="generation")`. It covers all 3 category calls plus the DeepSeek translation pass in one generation span.

### Langfuse SDK usage notes

- `from langfuse import get_client as _langfuse_client, observe` — only import from root `langfuse`; `langfuse.decorators` and `langfuse.anthropic` do not exist in v4
- `update_current_generation(name=..., model=..., usage_details={"input": N, "output": N})` — use inside `@observe(as_type="generation")` functions
- `score_current_trace(name=..., value=..., data_type="NUMERIC")` — use inside `@observe` functions to log a score on the current trace
- `_langfuse_client().flush()` — required at end of both scripts to prevent dropped async events before process exit

---

## Common Pitfalls

- **"Expecting value: line 1 column 1"** — Claude returned prose instead of JSON.
  All calls use `use_prefill=False` — JSON reliability comes from strict system prompt
  instructions. Check the system prompt ends with a "Return ONLY a JSON array" instruction
  and includes a schema example. Never add `use_prefill=True`; Sonnet returns HTTP 400.

- **IndexError: list index out of range** — results has more items than batch.
  Always iterate `enumerate(batch)` and guard with `j < len(results)`.

- **All Zaobao rows same category** — sitemap regex only matching one section.
  Verify regex includes `(?:singapore|world|sea)`.

- **Zaobao /sea rows have category=None after translation** — sea rows must go through
  `_translate_batch(..., classify=True)` with `ZAOBAO_SEA_SYSTEM_PROMPT`. Check that
  `translate_zaobao()` is correctly splitting by `r.get("category")` being None.

- **iOS Safari auto-zoom on input focus** — triggered by any `<input>` or `<textarea>`
  with `font-size < 16px`. Fix: always use `fontSize="16px"` exactly on interactive inputs,
  never Chakra size tokens (`sm` = 14px, `xs` = 12px). Affected: `SearchBar` and
  `QuizDrawer` textarea — both already fixed.

- **Actions running stale code** — `workflow_dispatch` queued before a push runs the
  old version. The startup banner confirms the running build.

---

## Testing

```bash
uv run pytest        # all tests
uv run pytest -v     # verbose
uv run pytest tests/test_invariants.py
```

| File | What it covers |
|---|---|
| `test_invariants.py` | classify routing (url vs sea), no-prefill invariant, regex scope, Shorts exclusion, sea prompt has classification |
| `test_feed_ingest.py` | `_call_claude`, `_extract_json_array`, `_translate_batch`, `_validate_zaobao_categories` |
| `test_zaobao_scraper.py` | URL→category (incl. sea→None), sitemap regex (singapore/world/sea), china excluded |
| `test_astro_scraper.py` | Row schema, title cleaning, playlist ID derivation |
| `test_summary_top_stories.py` | LOOKBACK_DAYS/MIN_NEW_HEADLINES constants, Chinese prompt quality, three-pass `_call_summary` (title_zh/summary_zh, 3 Claude calls, token sums, Pass 3 uses DeepSeek Flash, Pass 1+2 system is list with cache_control, identical headlines block across passes), `_extract_json_object`, model invariants, `_build_content` grouping |

CI runs two jobs in parallel on every push: `test` (ruff + pytest) and `build-frontend`
(catches TS/JSX errors before Vercel).

---

## Data Reset Procedure

1. Confirm code is committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`, `learning_digest`, `weekly_summary`, `ai_radar`.
3. Trigger `workflow_dispatch` on the main job workflow, then on `weekly_summary.yml`.
4. Verify: `SELECT category, COUNT(*) FROM headlines GROUP BY category`.
