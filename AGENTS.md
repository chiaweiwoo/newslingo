# NewsLingo - AI Session Memory

Auto-loaded by Codex. Records hard invariants and current architecture that
must stay aligned with the repo.

**Scope:** this session is NewsLingo only (`chiaweiwoo/newslingo`). Do not edit,
commit, or push any other repository from this thread.

---

## Project Overview

NewsLingo aggregates bilingual Chinese + English news from two sources:
- **Zaobao** - Singapore newspaper, scraped from monthly sitemaps
- **Astro Ben Di Quan** - Malaysian YouTube channel, fetched via YouTube Data API v3

Current provider split:
- `deepseek-v4-flash` - headline translation and EN->ZH summary translation
- `deepseek-v4-pro` - translation assessment and rule distillation
- `gemini-3.5-flash` - Top Stories and AI Radar discovery / selection

Storage is in Supabase. LLM observability is handled by Langfuse Cloud.

---

## Critical Invariants

### 1. Zaobao category source depends on section

| URL section | Category source | Values |
|---|---|---|
| `/news/singapore/` | URL | `Singapore` |
| `/news/world/` | URL | `International` |
| `/news/sea/` | LLM | `International` / `Singapore` / `Malaysia` |

`/news/china/` is out of scope.

Enforced by:
- `scrapers/zaobao.py` -> `_category_from_url(url)` returns `None` for sea
- `job.py` -> `translate_zaobao(...)` routes URL-classified rows with `classify=False`
- `job.py` -> sea rows go through `_translate_batch(..., classify=True)`
- `job.py` -> `_validate_zaobao_categories()` checks post-scrape and post-translate states

Do not remove `classify=True` for sea rows.

### 2. Zaobao scraper scope is singapore + world + sea

The sitemap regex must keep matching these sections:

```python
r"<url>\s*<loc>(https://www\.zaobao\.com\.sg/news/(?:singapore|world|sea)/story[^<]+)</loc>"
```

`china` and `sports` stay excluded.

### 3. Astro uses YouTube PlaylistItems, not Search API

`scrapers/astro.py` uses the uploads playlist because Search API has indexing delay.

Keep:
- uploads playlist ID derived by replacing `UC` with `UU`
- scan-until-cutoff behavior
- `DEFAULT_LOOKBACK_HOURS = 120`

### 4. Astro category is set by the LLM

Valid Astro categories:
- `Malaysia`
- `Singapore`
- `International`

Tie-breaking:
- Malaysia-Singapore bilateral -> `Malaysia`
- wider SEA regional -> `International`

Shorts are excluded before rows are built via `_is_short(item)`.

### 5. Defensive batch iteration

Never iterate raw model results and index into the batch from result length.

Correct:

```python
for j, row in enumerate(batch):
    if j < len(results) and isinstance(results[j], dict):
        ...
```

Wrong:

```python
for j, result in enumerate(results):
    row = batch[j]
```

### 6. JSON reliability comes from prompt contract + tolerant parsing

Do not rely on assistant-prefill tricks.

Current code uses:
- strict JSON-only prompts
- schema examples inline
- self-check instructions
- best-effort JSON extraction helpers such as `_extract_json_object()` / `_extract_json_array()`

Do not assume raw `json.loads(response_text)` is sufficient for provider responses.

### 7. Summary jobs stay small and selective

Top Stories and AI Radar are concise overlays, not long analyst memos.

Keep:
- `LOOKBACK_DAYS = 7`
- short titles
- short summaries / descriptions
- fewer items rather than weak filler

Do not silently expand scope or verbosity without checking the UX impact.

---

## Workflow Layout

Workflow names and filenames are standardized by product surface:

| Workflow name | YAML file | Scope |
|---|---|---|
| `Feed - Ingest` | `.github/workflows/feed_ingest.yml` | Raw feed pipeline |
| `Summary - Overlay` | `.github/workflows/summary_overlay.yml` | Runs both General Top Stories and AI summary payloads |
| `CI - Test` | `.github/workflows/ci_test.yml` | Ruff, pytest, frontend build |
| `Ops - Keep Alive` | `.github/workflows/ops_keep_alive.yml` | Keep scheduled Actions alive |

Guideline:
- keep feed and summary workflows separate
- keep CI separate from scheduled content jobs
- use `workflow_dispatch` on all content workflows

---

## Runtime Architecture

### Feed - Ingest (`job.py`)

- scrape Zaobao sitemap
- scrape Astro YouTube uploads playlist
- translate with `deepseek-v4-flash`
- classify Astro and Zaobao sea rows during translation
- assess with `deepseek-v4-pro`
- distill prompt rules with `deepseek-v4-pro`
- write to `headlines`, `assessment_logs`, `prompt_rules`, `job_runs`

Key constants:
- `CLAUDE_BATCH_SIZE = 50` (legacy constant name, still translation batch size)
- `ASSESS_BATCH_SIZE = 20`
- `TRANSLATE_MODEL = "deepseek-v4-flash"`
- `ASSESS_MODEL = "deepseek-v4-pro"`
- `DISTILL_MODEL = "deepseek-v4-pro"`

### Summary - Overlay (`summary_overlay.yml`)

The overlay workflow runs both summary scripts sequentially:
- `weekly_summary.py`
- `ai_radar.py`

This keeps the UI-aligned summaries under one workflow while avoiding extra quota burst from parallel summary runs.

### Top Stories engine (`weekly_summary.py`)

- uses `gemini-3.5-flash` for 3 grounded discovery calls:
  - `International`
  - `Singapore`
  - `Malaysia`
- uses `gemini-3.5-flash` again for final topic selection
- uses `deepseek-v4-flash` for EN->ZH translation
- rotates `weekly_summary`

Important behavior:
- frontend payload shape must stay unchanged
- no dependency on `headlines` prompt-caching design anymore
- return fewer topics rather than padding weak ones

### AI engine (`ai_radar.py`)

- uses `gemini-3.5-flash` for grounded discovery in:
  - `governance`
  - `product`
  - `infrastructure`
- uses `deepseek-v4-flash` for EN->ZH translation
- rotates `ai_radar`

Important behavior:
- output must keep the `categories -> items[]` shape
- items include `title`, `description`, `title_zh`, `description_zh`
- source links may exist in payload even if the UI chooses not to show them

---

## Supabase Tables

| Table | Reset on repull? | Notes |
|---|---|---|
| `headlines` | YES | Feed rows |
| `assessment_logs` | YES | Translation quality runs |
| `prompt_rules` | YES | Distilled translation rules |
| `learning_digest` | YES | Legacy / safe to clear |
| `weekly_summary` | YES | Top Stories payload, rotated |
| `ai_radar` | YES | AI Radar payload, rotated |
| `job_runs` | NO | Audit log |
| `visits` | NO | Frontend analytics |

---

## Frontend Product Shape

- Main feed: `International / Singapore / Malaysia`
- Sparkle drawer: shared summary surface
  - title stays `Top Stories`
  - first-level switch: `General / AI`
  - second-level switch:
    - `World / Singapore / Malaysia` for General
    - `Governance / Product / Infra` for AI
  - shared `EN / 中` toggle

Do not split AI Radar back into a separate drawer unless explicitly requested.

---

## Observability

Use Langfuse only. Do not add custom token accounting.

Current named observations:
- `translate:zaobao`
- `translate:astro`
- `assess:zaobao`
- `assess:astro`
- `distill:zaobao`
- `distill:astro`
- `summary:discover-international`
- `summary:discover-singapore`
- `summary:discover-malaysia`
- `summary:select`
- `summary:translate-zh`
- `ai-radar:generate`

Always flush Langfuse before process exit.

---

## Common Pitfalls

- **All Zaobao rows same category** -> sitemap regex lost one of `singapore|world|sea`
- **Zaobao sea rows left with `category=None`** -> sea path lost `classify=True`
- **IndexError during batch merge** -> someone iterated model results directly
- **Gemini summary job fails immediately** -> check `GEMINI_API_KEY` and model name
- **DeepSeek call fails immediately** -> check `DEEPSEEK_API_KEY` and Anthropic-compatible endpoint
- **Scheduled workflow runs stale code** -> dispatch happened before push reached `main`

---

## Testing

```bash
uv run python -m pytest -q
uv run ruff check .
```

Key tests:
- `tests/test_invariants.py`
- `tests/test_call_claude.py` (legacy filename, still covers shared LLM-call helpers)
- `tests/test_weekly_summary.py`
- `tests/test_ai_radar.py`
- scraper tests

`CI - Test` is the single workflow whose job is to run validation. Content workflows should stay focused on content generation.

---

## Data Reset Procedure

1. Confirm code is committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`, `learning_digest`, `weekly_summary`, `ai_radar`.
3. Trigger `workflow_dispatch` on `Feed - Ingest`, then on `Summary - Overlay`.
4. Verify with:

```sql
SELECT category, COUNT(*) FROM headlines GROUP BY category;
```
