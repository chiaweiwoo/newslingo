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
- `claude-sonnet-4-6` - Top Stories generation and fact-check
- `claude-haiku-4-5` - AI summary web search and summarisation
- `gemini-*` - kept configured for future experiments; not used by the current summary runtime path

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
- `feed_ingest.py` -> `translate_zaobao(...)` routes URL-classified rows with `classify=False`
- `feed_ingest.py` -> sea rows go through `_translate_batch(..., classify=True)`
- `feed_ingest.py` -> `_validate_zaobao_categories()` checks post-scrape and post-translate states

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

### 7. Job observability: never fail silently

All job scripts (`feed_ingest.py`, `summary_ai.py`, `summary_top_stories.py`) MUST exit with a non-zero status (typically `sys.exit(1)`) if a fatal error occurs.
- **Never** catch an exception and exit with 0.
- **Never** assume that printing an error is sufficient for GitHub Actions.
- Ensure the Action fails so it is visible in the GitHub UI.

---

## Workflow Layout

Workflow names and filenames are standardized by product surface:

| Workflow name | YAML file | Scope |
|---|---|---|
| `Feed - Ingest` | `.github/workflows/feed_ingest.yml` | Raw feed pipeline |
| `Summary - Top Stories` | `.github/workflows/summary_top_stories.yml` | Runs the General Top Stories payload |
| `Summary - AI` | `.github/workflows/summary_ai.yml` | Runs the AI summary payload |
| `CI - Test` | `.github/workflows/ci_test.yml` | Ruff, pytest, frontend build |
| `Ops - Keep Alive` | `.github/workflows/ops_keep_alive.yml` | Keep scheduled Actions alive |

Guideline:
- keep feed and summary workflows separate
- keep CI separate from scheduled content jobs
- use `workflow_dispatch` on all content workflows

---

## Runtime Architecture

### Feed - Ingest (`feed_ingest.py`)

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

### Summary - Top Stories (`summary_top_stories.py`)

- loads recent headlines from Supabase
- skips when fewer than `MIN_NEW_HEADLINES = 30` new translated headlines arrived
- pass 1 uses `claude-sonnet-4-6` to generate `8-10` must-know topics
- pass 2 uses `claude-sonnet-4-6` to fact-check and tense-correct against the same headline block
- pass 3 uses `deepseek-v4-flash` for EN->ZH translation
- rotates `weekly_summary`

Important behavior:
- use the same cached headline block in pass 1 and pass 2
- frontend payload shape must stay unchanged
- keep count logs for loaded headlines and pass outputs

### Summary - AI (`summary_ai.py`)

- calls Claude web search once per category:
  - `governance`
  - `product`
  - `infrastructure`
- primary model: `claude-haiku-4-5`
- fallback model: `claude-sonnet-4-6` only when Haiku is unavailable
- pass 2 uses `deepseek-v4-flash` for EN->ZH translation
- rotates `ai_radar`

Important behavior:
- output must keep the `categories -> items[]` shape
- items include `title`, `description`, `title_zh`, `description_zh`
- items may include `sources` internally even if the UI does not show them
- keep per-category count logs and total final item count

### Gemini status

- `GEMINI_API_KEY` remains in config and workflows for future experiments
- current runtime summary jobs should not require Gemini to succeed

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
- `summary:generate`
- `summary:factcheck`
- `summary:translate-zh`
- `ai-radar:generate`

Always flush Langfuse before process exit.

---

## Common Pitfalls

- **All Zaobao rows same category** -> sitemap regex lost one of `singapore|world|sea`
- **Zaobao sea rows left with `category=None`** -> sea path lost `classify=True`
- **IndexError during batch merge** -> someone iterated model results directly
- **Top Stories fails immediately** -> check `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, and Supabase headline availability
- **AI summary fails immediately** -> check `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, and Anthropic web search tool behavior
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
- `tests/test_feed_ingest.py`
- `tests/test_summary_top_stories.py`
- `tests/test_summary_ai.py`
- scraper tests

`CI - Test` is the single workflow whose job is to run validation. Content workflows should stay focused on content generation.

---

## Data Reset Procedure

1. Confirm code is committed and CI is green.
2. Delete rows from: `headlines`, `assessment_logs`, `prompt_rules`, `learning_digest`, `weekly_summary`, `ai_radar`.
3. Trigger `workflow_dispatch` on `Feed - Ingest`, then on `Summary - Top Stories` and `Summary - AI`.
4. Verify with:

```sql
SELECT category, COUNT(*) FROM headlines GROUP BY category;
```
