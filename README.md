# NewsLingo

> 中英双语时事 · Chinese & English bilingual news

A personal learning tool that aggregates Chinese-language news from Malaysian and Singaporean media, translates headlines into English, and classifies them by category — so you can read news you already understand while picking up the proper English terminology used in journalism.

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

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| Frontend | React, TypeScript, Chakra UI, React Query, Vite |
| Backend | Python, Anthropic Claude Haiku (translate + classify), Claude Sonnet (assess + distill) |
| Database | Supabase (Postgres) |
| Sources | YouTube Data API v3, Zaobao sitemap scraper |
| Hosting | Vercel (frontend), GitHub Actions (scheduled job) |

---

## Architecture

```
 Astro 本地圈 (YouTube API)       联合早报 (Zaobao sitemap)
        │  incremental, since           │  incremental, since
        │  last published_at            │  last published_at
        │                               │  parallel fetch (10 workers)
        └──────────────┬────────────────┘
                       ▼
                    job.py
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
    translate (Haiku)       translate (Haiku)
    + classify MY/Intl      + classify SG/Intl
           └───────────┬───────────┘
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
              prompt_rules tables)
                       │
              React Frontend ──► Vercel
```

---

## Self-Improving Translation Pipeline

Translation quality improves automatically over time through three layers:

```
Static prompt (job.py)
  — foundational rules: agency names, political titles, style
  — version-controlled, rarely changes

Distilled rules (prompt_rules table)
  — patterns extracted from failure history by Sonnet
  — regenerated every 10 runs per source, replaces previous

Few-shot corrections (assessment_logs)
  — concrete (ZH → correct EN) examples from recent failures
  — automatically rotates, always reflects the last 5 runs
```

Every run, Claude Haiku translates using all three layers combined. Every 10 runs, Claude Sonnet reads the accumulated failure history and distills new rules — so systematic mistakes get permanently fixed without manual prompt editing.

Assessment results are logged to `assessment_logs` with avg quality score per run, enabling quality trend monitoring over time.

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `headlines` | Translated articles, unique on `source_url` |
| `job_runs` | Per-run audit log: status, duration, item counts |
| `assessment_logs` | Per-source quality stats: scores, retry counts, failure samples |
| `prompt_rules` | Distilled translation rules per source, auto-updated every 10 runs |
| `visits` | Anonymous visit tracking |

---

## Sources

| Channel | Country | Categories | Classification |
|---------|---------|------------|----------------|
| Astro 本地圈 | Malaysia | Malaysia / International | LLM (Haiku) |
| 联合早报 | Singapore | Singapore / International | URL-based, deterministic — see [CLAUDE.md](./CLAUDE.md) |

Zaobao categories come from the source URL section (`/news/singapore/`, `/news/world/`, `/news/china/`, `/news/sea/`) — never from the LLM. This is a hard invariant enforced by runtime assertions and CI tests.

---

## Testing

The project has a pytest suite that runs on every push to `main` via GitHub Actions. The scheduled job is **gated on tests passing** — broken code never reaches production.

```bash
uv sync --group dev
uv run pytest -v             # all 56 tests
uv run pytest tests/test_invariants.py  # invariant checks only
```

| Test file | What it covers |
|---|---|
| `test_zaobao_scraper.py` | URL→category mapping, sitemap regex (4 sections, excludes sports), audio-brief filter |
| `test_astro_scraper.py` | YouTube JSON → row schema, title cleaning, lookback window |
| `test_call_claude.py` | `_call_claude` with mocked Anthropic responses: clean JSON, code-fenced, truncated, prose-wrapped, length mismatch, prefill on/off |
| `test_invariants.py` | Architectural invariants: Zaobao classification is URL-based, Astro classification is LLM-based, prefill respects per-model support |

### CI gating

`.github/workflows/job.yml` runs `test` before `run-job` (`needs: test`). If pytest fails, the scheduled job is skipped — you only get a notification when something is actually broken in test-land.

### Hard invariants (see [CLAUDE.md](./CLAUDE.md))

The pipeline asserts these at runtime AND in CI tests:

1. Zaobao category is set from URL, never from the LLM
2. The Zaobao sitemap regex matches `singapore`, `world`, `china`, `sea` — never `sports`
3. Astro category is filled by the LLM (the scraper returns `category=None`)
4. `_call_claude(use_prefill=True)` for Haiku translation; `use_prefill=False` for Sonnet assessment/distillation
5. Batch iteration is defensive — never index `batch[j]` from a `results` loop
