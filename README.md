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

| Channel | Country | Categories |
|---------|---------|------------|
| Astro 本地圈 | Malaysia | Malaysia / International |
| 联合早报 | Singapore | Singapore / International |
