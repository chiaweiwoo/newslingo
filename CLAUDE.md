# NewsLingo — AI Session Memory

Auto-loaded by Claude Code. Records hard invariants and architectural decisions that
MUST be preserved across all future AI-assisted changes.

**Scope: This session is NewsLingo only (`chiaweiwoo/newslingo`). Do not commit or push to any other repository — not `personal-site`, not `tcm-diagnosis`. If the user shares code or issues from another project, discuss only — do not edit or push.**

---

## Project Overview

NewsLingo aggregates bilingual (Chinese + English) news from two sources:
- **联合早报 (Zaobao)** — Singapore newspaper, scraped via monthly sitemaps
- **Astro 本地圈** — Malaysian YouTube channel, fetched via YouTube Data API v3

News is translated by Claude Haiku, quality-assessed by Claude Sonnet, and stored in
Supabase. Three GitHub Actions jobs run the pipeline.

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
       ├── scrapers/zaobao.py     → scrape sitemap  → rows with category from URL
       ├── scrapers/astro.py      → YouTube API     → rows with category=None
       ├── _translate_batch()     → Claude Haiku    → fills title_en (+ category for Astro)
       ├── assess_translations()  → Claude Sonnet   → scores 1–5, retry if <3
       ├── _distill_rules()       → Claude Sonnet   → improves prompt_rules each run
       ├── upsert_rows()          → Supabase        → headlines table
       └── _record_token_usage()  → Supabase        → token_usage (tasks: translation, feedback)

GitHub Actions (cron: daily 08:00 SGT)
  └── digest.py
       ├── loads previous learning_digest + digest_at watermark
       ├── pulls delta assessment_logs failures + prompt_rules since watermark
       ├── _call_digest()         → Claude Sonnet   → bullet-points JSON per region
       ├── rotates learning_digest (deactivates old, inserts new)
       └── writes token_usage row (task: insights)

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
       ├── rotates weekly_summary (deactivates old, inserts new)
       └── writes token_usage row (task: insights)
```

**Constants:**
- `CLAUDE_BATCH_SIZE = 50` — translation batch size
- `ASSESS_BATCH_SIZE = 20` — Sonnet drops/duplicates items at higher counts; do not raise
- `MIN_NEW_HEADLINES = 30` — weekly summary skip threshold
- `LOOKBACK_DAYS = 7` — rolling window for weekly summary

---

## Supabase Tables

| Table | Reset on repull? | Notes |
|---|---|---|
| `headlines` | YES | All article rows |
| `assessment_logs` | YES | Per-run quality scores |
| `prompt_rules` | YES | Distilled LLM rules |
| `learning_digest` | YES | Inside AI digest; rotated by digest.py |
| `weekly_summary` | YES | This Week topics; rotated by weekly_summary.py |
| `job_runs` | NO | Audit log — preserve |
| `visits` | NO | Frontend analytics — preserve |
| `token_usage` | NO | AI cost per task per run; used by Costs drawer |

`token_usage.task` values: `translation`, `feedback`, `insights`

---

## Models

| Task | Model | Notes |
|---|---|---|
| Translation | `claude-sonnet-4-6` | All sources — better entity disambiguation |
| Assessment | `claude-sonnet-4-6` | Structured output; runs every 3h |
| Distillation | `claude-sonnet-4-6` | Rule extraction from failures |
| Inside AI digest | `claude-sonnet-4-6` | Daily; structured summarisation |
| This Week summary | `claude-sonnet-4-6` | Daily; two-pass generate + fact-check |

### This Week topic schema

Each topic in `weekly_summary.payload.topics`:

| Field | Type | Notes |
|---|---|---|
| `title` | string | Noun phrase, max 8 words |
| `summary` | string | WHO/WHAT/WHERE, one sentence, max 25 words |
| `so_what` | string? | 2-3 sentences: general impact → specific groups |
| `lesson` | string[]? | 2-4 narrative bullets, no label prefixes |
| `region` | string | `International` \| `Malaysia` \| `Singapore` |
| `theme` | string | `Politics` \| `Economy` \| `Society` \| `Security` \| `Technology` \| `Environment` |

**Two-pass quality design:**
- Pass 1 generates full analysis
- Pass 2 fact-checks every specific claim (visits, deaths, figures, signed deals) against
  source headlines; corrects tense (future-tense source = future-tense output); applies
  confidence hedging (single-headline claim → "reportedly"; multi-headline → direct)
- Topics whose core claim cannot be matched to any headline are removed

---

## Frontend Features

| Feature | Where | Notes |
|---|---|---|
| Vocab tap | `HeadlineCard` + `useWordDefinition` + `WordSheet` | Tap English word → bottom sheet; Free Dictionary API; module-level cache |
| Read aloud | `SpeechContext` + speaker icon in `HeadlineCard` | Web Speech API; one active at a time |
| Share | `HeadlineCard.shareHeadline()` | Web Share API on mobile; clipboard + toast on desktop |
| Font size | `FontSizeContext` + Preferences menu | S/M/L; persisted in localStorage |
| Dark mode | `theme.ts` + Preferences menu | Chakra color mode; warm dark palette |
| This Week | `ThisWeekDrawer` | Grouped by region; expandable per-topic accordion |
| Costs | `CostsDrawer` | token_usage past 30 days, grouped by task |

### Theme tokens
`brand.red` is static (`#c8102e`). All others (`brand.paper/ink/muted/rule/card`) are
semantic tokens that flip between light and dark. Always use tokens — never hardcode hex.
`brand.card` is the white surface for cards, sheets, and menu backgrounds.

---

## Common Pitfalls

- **"Expecting value: line 1 column 1"** — Claude returned prose instead of JSON.
  Check that `messages` in `claude.messages.create()` ends with
  `{"role": "assistant", "content": "["}` for Haiku translation calls.

- **IndexError: list index out of range** — results has more items than batch.
  Always iterate `enumerate(batch)` and guard with `j < len(results)`.

- **All Zaobao rows `category=Singapore`** — sitemap regex only matching one section.
  Verify regex includes `(?:singapore|world)`.

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
| `test_invariants.py` | classify=False on Zaobao, prefill rules, regex scope |
| `test_call_claude.py` | `_call_claude`, `_extract_json_array`, `_translate_batch`, `_validate_zaobao_categories` |
| `test_zaobao_scraper.py` | URL→category, sitemap regex, out-of-scope exclusion |
| `test_astro_scraper.py` | Row schema, title cleaning, playlist ID derivation |
| `test_digest.py` | `_extract_json_object`, model invariants, `_build_content` grouping |

CI runs two jobs in parallel on every push: `test` (ruff + pytest) and `build-frontend`
(catches TS/JSX errors before Vercel).

---

## Data Reset Procedure

1. Confirm code is committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`, `learning_digest`, `weekly_summary`.
3. Trigger `workflow_dispatch` on the main job workflow, then on `weekly_summary.yml`.
4. Verify: `SELECT category, COUNT(*) FROM headlines GROUP BY category`.
