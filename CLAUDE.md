# NewsLingo — AI Session Memory

Auto-loaded by Claude Code. Records hard invariants and architectural decisions that
MUST be preserved across all future AI-assisted changes.

**Scope: This session is NewsLingo only (`chiaweiwoo/newslingo`). Do not commit or push to any other repository — not `personal-site`, not `tcm-diagnosis`. If the user shares code or issues from another project, discuss only — do not edit or push.**

---

## Project Overview

NewsLingo aggregates bilingual (Chinese + English) news from two sources:
- **联合早报 (Zaobao)** — Singapore newspaper, scraped via monthly sitemaps
- **Astro 本地圈** — Malaysian YouTube channel, fetched via YouTube Data API v3

All AI tasks use `claude-sonnet-4-6` — translation, assessment, distillation, and weekly summary.
Headlines are stored in Supabase. Three GitHub Actions jobs run the pipeline.
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
- `job.py` → `translate_zaobao(rows, url_prompt, sea_prompt)` splits by `category is None`:
  - singapore/world rows → `_translate_batch(..., classify=False)` with `ZAOBAO_SYSTEM_PROMPT`
  - sea rows → `_translate_batch(..., classify=True)` with `ZAOBAO_SEA_SYSTEM_PROMPT`
- `job.py` → `_validate_zaobao_categories()`:
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

All Claude calls use `use_prefill=False`. Every model in use is `claude-sonnet-4-6`,
which returns HTTP 400 if the conversation ends with an assistant turn.

- **Never** add `use_prefill=True` to any call — it will break in production
- **Never** change `assess_translations` / `_distill_rules` to `use_prefill=True`
- JSON output reliability is enforced through strict system prompt instructions instead

### 6. Defensive batch iteration — never iterate results directly

```python
# CORRECT — iterate batch (fixed length), index into results safely
for j, row in enumerate(batch):
    if j < len(results) and isinstance(results[j], dict):
        ...
# WRONG — Claude can return more or fewer items than batch
for j, result in enumerate(results):
    row = batch[j]  # IndexError if len(results) > len(batch)
```

---

## Architecture

```
GitHub Actions (cron: every 3h)
  └── job.py
       ├── scrapers/zaobao.py     → scrape sitemap  → rows (singapore/world: category from URL; sea: category=None)
       ├── scrapers/astro.py      → YouTube API     → rows with category=None (Shorts excluded)
       ├── _translate_batch()     → Claude Sonnet   → fills title_en (+ category for Astro and Zaobao /sea)
       ├── assess_translations()  → Claude Sonnet   → scores 1–5, retry if <3
       ├── _distill_rules()       → Claude Sonnet   → improves prompt_rules each run
       ├── upsert_rows()          → Supabase        → headlines table
       └── _record_token_usage()  → Supabase        → token_usage (tasks: translation, feedback)

GitHub Actions (cron: daily 09:00 SGT)
  └── weekly_summary.py
       ├── skips if < MIN_NEW_HEADLINES (30) since last run
       ├── pulls past 7 days of headlines (rolling window)
       ├── _call_summary() pass 1 → Claude Sonnet  → 8-10 must-know topics
       │                                              (title, summary, so_what, lesson[],
       │                                               region, theme)
       ├── _call_summary() pass 2 → Claude Sonnet  → fact-check: remove/correct topics
       │                                              whose specific claims cannot be matched
       │                                              to headlines; fix tense; apply hedging
       ├── _call_summary() pass 3 → Claude Sonnet  → translate title + summary to Simplified
       │                                              Chinese; adds title_zh + summary_zh
       ├── rotates weekly_summary (deactivates old, inserts new)
       └── writes token_usage row (task: insights)
```

**Constants:**
- `CLAUDE_BATCH_SIZE = 50` — translation batch size
- `ASSESS_BATCH_SIZE = 20` — Sonnet drops/duplicates items at higher counts; do not raise
- `MIN_NEW_HEADLINES = 30` — weekly summary skip threshold (calibrated for 7-day window)
- `LOOKBACK_DAYS = 7` — rolling window for Top Stories summary

---

## Supabase Tables

| Table | Reset on repull? | Notes |
|---|---|---|
| `headlines` | YES | All article rows |
| `assessment_logs` | YES | Per-run quality scores |
| `prompt_rules` | YES | Distilled LLM rules |
| `learning_digest` | YES | Unused — was written by digest.py (now deleted). Safe to clear. |
| `weekly_summary` | YES | Top Stories topics; rotated by weekly_summary.py |
| `job_runs` | NO | Audit log — preserve |
| `visits` | NO | Frontend analytics — preserve |
| `token_usage` | NO | Legacy — was written by custom pricing.py (now deleted). No longer written; Langfuse handles observability. Safe to ignore. |

---

## Models

| Task | Model | Notes |
|---|---|---|
| Translation | `claude-sonnet-4-6` | All sources — better entity disambiguation |
| Assessment | `claude-sonnet-4-6` | Structured output; runs every 3h |
| Distillation | `claude-sonnet-4-6` | Rule extraction from failures |
| Top Stories summary | `claude-sonnet-4-6` | Daily; three-pass generate + fact-check + Chinese |

### Top Stories topic schema

Each topic in `weekly_summary.payload.topics`:

| Field | Type | Notes |
|---|---|---|
| `title` | string | Noun phrase, max 8 words |
| `title_zh` | string | Simplified Chinese translation of title (Pass 3) |
| `summary` | string | WHO/WHAT/WHERE, one sentence, max 25 words |
| `summary_zh` | string | Simplified Chinese translation of summary (Pass 3) |
| `so_what` | string? | 2-3 sentences: general impact → specific groups |
| `lesson` | string[]? | 2-4 narrative bullets, no label prefixes |
| `region` | string | `International` \| `Malaysia` \| `Singapore` |
| `theme` | string | `Politics` \| `Economy` \| `Society` \| `Security` \| `Technology` \| `Environment` |

**Three-pass quality design:**
- Pass 1 generates full analysis
- Pass 2 fact-checks every specific claim (visits, deaths, figures, signed deals) against
  source headlines; corrects tense (future-tense source = future-tense output); applies
  confidence hedging (single-headline claim → "reportedly"; multi-headline → direct)
- Topics whose core claim cannot be matched to any headline are removed
- Pass 3 translates `title` and `summary` into Simplified Chinese, adding `title_zh` and
  `summary_zh`; all other fields are kept unchanged

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
| Top Stories | `ThisWeekDrawer` | Header icon (4-pt sparkle SVG); 3-tab layout (Int/SG/MY); EN\|中 language toggle; no expanded analysis; `localStorage('topStories.lang')` |
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

Token counts, cost, and latency for every Claude call are tracked in **Langfuse Cloud**.

- **Dashboard:** cloud.langfuse.com → your project → Traces
- **job.py:** `_call_claude` is decorated with `@observe(as_type="generation")` — every translation, assessment, and distillation call appears as a separate generation
- **weekly_summary.py:** `_call_summary` is decorated with `@observe(as_type="generation")` — combined token usage across all 3 passes logged per run
- **Cost view:** Traces → click a trace → see input/output tokens + cost per generation
- **Secrets:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` in GitHub Actions; `LANGFUSE_BASE_URL` is aliased to `LANGFUSE_HOST` at runtime

Do **not** add any custom token-tracking code (no `_record_token_usage`, no `pricing.py`) — Langfuse handles it.

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
| `test_call_claude.py` | `_call_claude`, `_extract_json_array`, `_translate_batch`, `_validate_zaobao_categories` |
| `test_zaobao_scraper.py` | URL→category (incl. sea→None), sitemap regex (singapore/world/sea), china excluded |
| `test_astro_scraper.py` | Row schema, title cleaning, playlist ID derivation |
| `test_weekly_summary.py` | LOOKBACK_DAYS/MIN_NEW_HEADLINES constants, Chinese prompt quality, three-pass `_call_summary` (title_zh/summary_zh populated, 3 Claude calls, token sums), `_extract_json_object`, model invariant, `_build_content` grouping |

CI runs two jobs in parallel on every push: `test` (ruff + pytest) and `build-frontend`
(catches TS/JSX errors before Vercel).

---

## Data Reset Procedure

1. Confirm code is committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`, `learning_digest`, `weekly_summary`.
3. Trigger `workflow_dispatch` on the main job workflow, then on `weekly_summary.yml`.
4. Verify: `SELECT category, COUNT(*) FROM headlines GROUP BY category`.
