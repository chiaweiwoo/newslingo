# NewsLingo

> 中英双语时事 · Chinese & English bilingual news

A personal learning tool that aggregates Chinese-language news from Malaysian and Singaporean media, translates headlines into English, and classifies them by region — so you can read news you already understand while picking up the proper English terminology used in journalism.

<img src="docs/screenshot.jpeg" alt="NewsLingo mobile screenshot" width="320" />

---

## Features

- **Bilingual headlines** — Chinese original alongside English translation
- **Category tabs** — International, Malaysia, and Singapore feeds
- **Date-grouped feed** — chronological, latest first, grouped by date
- **Infinite scroll** — loads more as you scroll, no button needed
- **Mobile-first** — designed for phone reading
- **Auto-updated** — job runs every 3 hours SGT, fetches only new content since last run
- **Self-improving translation** — quality scores, retry on failure, and dynamic prompts that learn from past mistakes
- **Learning Digest** — daily AI-generated summary of what the translation pipeline has learned, grouped by region

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| Frontend | React, TypeScript, Chakra UI, React Query, Vite |
| Backend | Python, Claude Haiku (translate + classify), Claude Sonnet (assess + distill + digest) |
| Database | Supabase (Postgres) |
| Sources | YouTube Data API v3, Zaobao sitemap scraper |
| Hosting | Vercel (frontend), GitHub Actions (scheduled jobs) |

---

## Architecture

```
 Astro 本地圈 (YouTube API)         联合早报 (Zaobao sitemap)
        │  incremental, since               │  incremental, since
        │  last published_at                │  last published_at
        │                                   │  parallel fetch (10 workers)
        └──────────────────┬────────────────┘
                           ▼
                        job.py  (every 3h)
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
    translate (Haiku)           translate (Haiku)
    + classify                  category from URL
    MY / SG / Intl              SG or Intl only
             └─────────────┬─────────────┘
                           ▼
                  assess (Sonnet)
                  quality score 1–5
                  + correction suggestion
                           │
                 score < 3 → retry once
                 still failing → insert anyway
                           │
                      Supabase
              (headlines, assessment_logs,
               prompt_rules, job_runs)
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
  distill rules (Sonnet)        React Frontend → Vercel
  every successful run
  → updates prompt_rules

digest.py  (daily 08:00 SGT)
  reads assessment_logs + prompt_rules
  → incremental summary by region
  → learning_digest table
```

---

## Self-Improving Translation Pipeline

Translation quality improves automatically through three layers:

```
Static prompt (job.py)
  — foundational rules: agency names, political titles, style
  — version-controlled, rarely changes

Distilled rules (prompt_rules table)
  — patterns extracted from failure history by Sonnet
  — regenerated on every successful run, replaces previous

Few-shot corrections (assessment_logs)
  — concrete (ZH → correct EN) examples from recent failures
  — automatically rotates, always reflects the last 5 runs
```

Every run, Haiku translates using all three layers combined. After each successful run, Sonnet reads the accumulated failure history and distills new rules — so systematic mistakes get permanently fixed without manual prompt editing.

The **Learning Digest** (daily job) incrementally summarises what the pipeline has learned, grouped by International / Malaysia / Singapore. It uses a watermark (`digest_at`) so each run only processes new data since the last digest.

---

## Database Tables

| Table | Purpose | Reset on repull? |
|-------|---------|-----------------|
| `headlines` | Translated articles, unique on `source_url` | YES |
| `job_runs` | Per-run audit log: status, duration, item counts | NO |
| `assessment_logs` | Per-source quality stats: scores, retry counts, failure samples | YES |
| `prompt_rules` | Distilled translation rules per source, updated every run | YES |
| `learning_digest` | Daily AI digest of learned patterns, grouped by region | YES |
| `visits` | Anonymous visit tracking | NO |

---

## Sources

| Channel | Country | Categories | Classification |
|---------|---------|------------|----------------|
| Astro 本地圈 | Malaysia | Malaysia / Singapore / International | LLM (Haiku) — sequential: Malaysia → Singapore → International |
| 联合早报 | Singapore | Singapore / International | URL-based, deterministic — see [CLAUDE.md](./CLAUDE.md) |

**Zaobao scope:** only `/news/singapore/` and `/news/world/` sections are scraped. China and SEA sections are out of scope.

**Astro scope:** Singapore classification is rare (Astro is a Malaysian channel). Malaysia-Singapore bilateral stories classify as Malaysia. SEA regional news (Thailand, Indonesia, etc.) classifies as International.

---

## GitHub Actions Workflows

| Workflow | Schedule | What it does |
|----------|----------|--------------|
| `Aggregate` | Every 3h SGT | Scrape → translate → assess → distill → upsert |
| `Learning Digest` | Daily 08:00 SGT | Incremental digest from assessment history |
| `test` | Every push to main | Ruff lint + pytest (gates the Aggregate job) |
| `keep-alive` | Weekly Monday | Keeps GitHub Actions active |

---

## Testing

The project has a pytest suite that runs on every push to `main`. The Aggregate job is **gated on tests passing** — broken code never reaches production.

```bash
uv sync --group dev
uv run pytest -v
uv run pytest tests/test_invariants.py  # invariant checks only
```

| Test file | What it covers |
|---|---|
| `test_zaobao_scraper.py` | URL→category mapping, sitemap regex (2 sections: singapore + world), audio-brief filter |
| `test_astro_scraper.py` | YouTube JSON → row schema, title cleaning, lookback window |
| `test_call_claude.py` | `_call_claude` with mocked responses: clean JSON, code-fenced, truncated, prose-wrapped, length mismatch, prefill on/off |
| `test_invariants.py` | Architectural invariants: Zaobao classification is URL-based, Astro classification is LLM-based, prefill respects per-model support |

---

## Hard Invariants

See [CLAUDE.md](./CLAUDE.md) for the full list. Key ones:

1. Zaobao category is set from URL — never from the LLM
2. Zaobao scrapes only `singapore` and `world` sections — china and sea are out of scope
3. Astro category is filled by the LLM with three options: Malaysia / Singapore / International
4. `use_prefill=True` for Haiku translation; `use_prefill=False` for Sonnet assessment/distillation
5. Batch iteration is defensive — never index `batch[j]` from a `results` loop
