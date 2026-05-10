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
| `/news/china/` | `International` |
| `/news/sea/` | `International` |

**Why:** The URL unambiguously signals the editorial section. LLM classification
introduced errors and added unnecessary API cost. This is enforced by:
- `scrapers/zaobao.py` → `_category_from_url(url)` sets category at scrape time
- `job.py` → `translate_zaobao()` calls `_translate_batch(..., classify=False)`
- `job.py` → `_validate_zaobao_categories()` hard-crashes if any row has `category=None`
- `tests/test_invariants.py` → CI tests verify this in code

If you see `classify=True` in `translate_zaobao()` — that's a bug. Fix it.

### 2. Zaobao: Four sections are scraped (not just Singapore)

The sitemap regex must match: `singapore`, `world`, `china`, `sea`. NOT `sports`.

```python
r"<url>\s*<loc>(https://www\.zaobao\.com\.sg/news/(?:singapore|world|china|sea)/story[^<]+)</loc>"
```

### 3. Astro: Category IS set by the LLM

Astro is a YouTube channel — there's no URL section to classify from.
`translate_astro()` uses `classify=True`. The scraper returns `category=None`.

### 4. Assistant prefill — model-specific support

`_call_claude(use_prefill=True)` — adds `{"role": "assistant", "content": "["}` to force
JSON output. **Only Haiku supports this.** Use it for translation calls.

`_call_claude(use_prefill=False)` — ends with the user message only. **Required for
Sonnet 4.6+**, which returns HTTP 400 if the conversation ends with an assistant turn.
Use it for assessment and distillation calls. The system prompts for these are
sufficiently strict ("Return ONLY a JSON array … must START with '['") to avoid prose.

**Never** change `translate_zaobao`/`translate_astro` to `use_prefill=False`.
**Never** change `assess_translations`/`_distill_rules` to `use_prefill=True`.

### 5. Defensive batch iteration — never iterate `results` directly

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
       ├── scrapers/zaobao.py  → scrape sitemap → rows with category from URL
       ├── scrapers/astro.py   → YouTube API    → rows with category=None
       ├── _translate_batch()  → Claude Haiku   → fills title_en (+ category for Astro)
       ├── assess_translations() → Claude Sonnet → scores 1–5, retry if <3
       ├── _distill_rules()    → Claude Sonnet  → every 10 runs, improves prompt_rules
       └── upsert_rows()       → Supabase       → headlines table
```

## Supabase Tables

| Table | Reset on repull? | Notes |
|---|---|---|
| `headlines` | YES | All article rows |
| `assessment_logs` | YES | Per-run quality scores |
| `prompt_rules` | YES | Distilled LLM rules |
| `job_runs` | NO | Audit log — preserve |
| `visits` | NO | Frontend analytics — preserve |

---

## Models

| Task | Model | Notes |
|---|---|---|
| Translation | `claude-haiku-4-5-20251001` | Fast, cheap |
| Assessment | `claude-sonnet-4-6` | More reliable on structured output |
| Distillation | `claude-sonnet-4-6` | Rule extraction from failures |

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
  Check that the sitemap regex includes `(?:singapore|world|china|sea)`.

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
The `run-job` workflow is gated on `test` passing — no broken code reaches production.

---

## Data Reset Procedure

1. Ensure code changes are committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`.
3. Trigger `workflow_dispatch` on the job workflow.
4. Verify classification distribution: `SELECT category, COUNT(*) FROM headlines GROUP BY category`.
