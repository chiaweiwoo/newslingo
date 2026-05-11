# NewsLingo — AI Session Memory

This file is auto-loaded by Claude Code. It records hard invariants and architectural
decisions that MUST be preserved across all future AI-assisted changes.

---

## Project Overview

NewsLingo aggregates bilingual (Chinese + English) news from two sources:
- **联合早报 (Zaobao)** — Singapore newspaper, scraped via monthly sitemaps
- **Astro 本地圈** — Malaysian YouTube channel, fetched via YouTube Data API v3

News is translated to English by Claude Haiku, quality-assessed by Claude Sonnet,
and stored in Supabase. The job runs every 3 hours via GitHub Actions.

---

## CRITICAL INVARIANTS — DO NOT VIOLATE

### 1. Zaobao: Category is ALWAYS set from the source URL section

**Never** classify Zaobao articles with an LLM.

| URL section | Category |
|---|---|
| `/news/singapore/` | `Singapore` |
| `/news/world/` | `International` |

`/news/china/` and `/news/sea/` are out of scope — not scraped, not stored.

**Why:** The URL unambiguously signals the editorial section. LLM classification
introduced errors and added unnecessary API cost. This is enforced by:
- `scrapers/zaobao.py` → `_category_from_url(url)` sets category at scrape time
- `job.py` → `translate_zaobao()` calls `_translate_batch(..., classify=False)`
- `job.py` → `_validate_zaobao_categories()` hard-crashes if any row has `category=None`
- `tests/test_invariants.py` → CI tests verify this in code

If you see `classify=True` in `translate_zaobao()` — that's a bug. Fix it.

### 2. Zaobao: Two sections are scraped — singapore and world only

`china` and `sea` are **out of scope** and intentionally excluded.

The sitemap regex must match only: `singapore`, `world`. NOT `china`, `sea`, `sports`.

```python
r"<url>\s*<loc>(https://www\.zaobao\.com\.sg/news/(?:singapore|world)/story[^<]+)</loc>"
```

The frontend also filters out any china/sea rows that may exist in the DB from earlier runs.

### 3. Astro: No sitemap — uses YouTube Data API v3 PlaylistItems

Astro 本地圈 is a YouTube channel, not a website, so there is no sitemap.

The scraper (`scrapers/astro.py`) uses the **YouTube Data API v3 PlaylistItems endpoint**
(uploads playlist), which returns videos in **reverse-chronological order** (newest first).
It paginates until it hits a video published before the cutoff, then stops — the same
"scan until out of range" logic that Zaobao uses against its sitemap.

Key implementation notes:
- Upload playlist ID is derived by replacing `UC` prefix with `UU` (no extra API call).
- Uses PlaylistItems, not the Search API — Search has a several-hour indexing delay
  that silently misses recent videos. PlaylistItems reflects uploads immediately.
- `DEFAULT_LOOKBACK_HOURS = 120` (5 days) ensures first-run repull has enough coverage.

### 4. Astro: Category IS set by the LLM — three valid values

Astro is a YouTube channel — there's no URL section to classify from.
`translate_astro()` uses `classify=True`. The scraper returns `category=None`.

Valid categories: `Malaysia`, `Singapore`, `International`.

**Sequential classification rules (apply in order, stop at first match):**
1. `Malaysia` — news about Malaysian politics, people, places, companies, courts, or events
2. `Singapore` — news **exclusively** about Singapore with no material Malaysian angle (rare on this channel)
3. `International` — everything else

Tie-breaking:
- Malaysia-Singapore bilateral stories → `Malaysia` (Astro is a Malaysian channel)
- SEA regional news (Thailand, Indonesia, etc.) → `International`
- Any doubt between Malaysia and Singapore → `Malaysia`

### 5. Assistant prefill — model-specific support

`_call_claude(use_prefill=True)` — adds `{"role": "assistant", "content": "["}` to force
JSON output. **Only Haiku supports this.** Use it for translation calls.

`_call_claude(use_prefill=False)` — ends with the user message only. **Required for
Sonnet 4.6+**, which returns HTTP 400 if the conversation ends with an assistant turn.
Use it for assessment and distillation calls. The system prompts for these are
sufficiently strict ("Return ONLY a JSON array … must START with '['") to avoid prose.

**Never** change `translate_zaobao` / `translate_astro` to `use_prefill=False`.
**Never** change `assess_translations` / `_distill_rules` to `use_prefill=True`.

### 6. Defensive batch iteration — never iterate `results` directly

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

## Frontend Features

| Feature | Where | Notes |
|---|---|---|
| Vocab tap | `HeadlineCard` + `useWordDefinition` + `WordSheet` | Tap English word → bottom sheet definition; Free Dictionary API; module-level cache |
| Read aloud | `SpeechContext` + speaker icon in `HeadlineCard` | Web Speech API; one active at a time via shared context |
| Share | `HeadlineCard.shareHeadline()` | Web Share API (text + URL) on mobile; clipboard copy + toast on desktop |
| Font size | `FontSizeContext` + Preferences menu | Three levels (S/M/L); persisted in localStorage |
| Dark mode | `theme.ts` semantic tokens + toggle in header + Preferences menu | Chakra color mode; stored in localStorage; warm dark palette |

### Theme tokens
`brand.red` is static (`#c8102e`). All others (`brand.paper/ink/muted/rule/card`) are **semantic tokens** that switch between light and dark values. Always use these tokens in components — never hardcode hex. `brand.card` is the surface token for white cards/sheets/menu backgrounds.

---

## Architecture

```
GitHub Actions (cron: every 3h)
  └── job.py
       ├── scrapers/zaobao.py  → scrape sitemap → rows with category from URL
       ├── scrapers/astro.py   → YouTube API    → rows with category=None
       ├── _translate_batch()  → Claude Haiku   → fills title_en (+ category for Astro)
       ├── assess_translations() → Claude Sonnet → scores 1–5, retry if <3
       ├── _distill_rules()    → Claude Sonnet  → every successful run, improves prompt_rules
       └── upsert_rows()       → Supabase       → headlines table

GitHub Actions (cron: daily 08:00 SGT)
  └── digest.py
       ├── loads previous learning_digest + digest_at watermark
       ├── pulls delta assessment_logs failures + prompt_rules since watermark
       ├── _call_digest()      → Claude Sonnet  → updated bullet-points JSON per region
       └── rotates learning_digest table (deactivates old, inserts new)

GitHub Actions (cron: Monday 08:00 SGT)
  └── weekly_summary.py
       ├── pulls last 7 days of translated headlines
       ├── _call_summary()     → Claude Sonnet  → 5-8 topic clusters with summaries
       └── rotates weekly_summary table (deactivates old, inserts new)
```

## Supabase Tables

| Table | Reset on repull? | Notes |
|---|---|---|
| `headlines` | YES | All article rows |
| `assessment_logs` | YES | Per-run quality scores |
| `prompt_rules` | YES | Distilled LLM rules |
| `learning_digest` | YES | Inside AI digest; rotated by digest.py |
| `weekly_summary` | YES | This Week topic clusters; rotated by weekly_summary.py |
| `job_runs` | NO | Audit log — preserve |
| `visits` | NO | Frontend analytics — preserve; includes `ip`, `country`, `is_mobile` |

---

## Models

| Task | Model | Notes |
|---|---|---|
| Translation | `claude-haiku-4-5-20251001` | Fast, cheap — high volume |
| Assessment | `claude-sonnet-4-6` | Structured output; runs every 3h |
| Distillation | `claude-sonnet-4-6` | Rule extraction from failures |
| Inside AI digest | `claude-sonnet-4-6` | Daily; structured summarisation, Sonnet is sufficient |
| Weekly summary | `claude-sonnet-4-6` | Weekly; editorial judgement, Sonnet is sufficient |

**ASSESS_BATCH_SIZE = 20** — Sonnet drops/duplicates items at higher counts. Do not raise.  
**CLAUDE_BATCH_SIZE = 50** — Translation batch size.

---

## Common Pitfalls

- **"Expecting value: line 1 column 1"** — Claude returned prose instead of JSON.
  The prefill `[` in `_call_claude` prevents this. If it recurs, check that the
  `messages` list in `claude.messages.create()` ends with `{"role": "assistant", "content": "["}`.

- **IndexError: list index out of range** — `results` has more items than `batch`.
  Always iterate `enumerate(batch)` and guard with `j < len(results)`.

- **All Zaobao rows showing `category=Singapore`** — regex is only matching `/news/singapore/`.
  Check that the sitemap regex includes `(?:singapore|world)`.

- **GitHub Actions running stale code** — a `workflow_dispatch` queued before a push
  runs the old version. The startup banner `[job] NewsLingo job starting — build: ...`
  confirms which code version is running.

---

## Testing

```bash
uv run pytest            # run all tests
uv run pytest -v         # verbose
uv run pytest tests/test_invariants.py  # invariant checks only
```

Tests run on every push to `main` via `.github/workflows/test.yml`.
The `Aggregate` workflow is gated on `test` passing — no broken code reaches production.

---

## Data Reset Procedure

1. Ensure code changes are committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`, `learning_digest`.
3. Trigger `workflow_dispatch` on the job workflow.
4. Verify classification distribution: `SELECT category, COUNT(*) FROM headlines GROUP BY category`.
