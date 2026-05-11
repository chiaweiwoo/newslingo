# NewsLingo

> 中英双语时事 · Chinese & English bilingual news

Read Chinese news with English translations side by side — follow current events you already understand while picking up natural English phrasing.

Headlines from **联合早报 (Zaobao)** and **Astro 本地圈** are scraped every 3 hours, translated by Claude, and organised into International / Singapore / Malaysia tabs. The translation pipeline self-improves: a second AI scores each run, distils rules from mistakes, and publishes observations via **Inside AI** (··· menu). **This Week** (··· menu) summarises the past week into topic clusters every Monday.

Tap any English word for a definition · speaker icon reads aloud · share button sends both titles + URL · font size and dark mode in ··· → Preferences.

<table>
  <tr>
    <td><img src="docs/screenshot-feed.jpeg" alt="News feed" width="200"/></td>
    <td><img src="docs/screenshot-about.jpeg" alt="About drawer" width="200"/></td>
    <td><img src="docs/screenshot-inside-ai.jpeg" alt="Inside AI drawer" width="200"/></td>
  </tr>
  <tr>
    <td align="center"><sub>News feed</sub></td>
    <td align="center"><sub>About</sub></td>
    <td align="center"><sub>Inside AI</sub></td>
  </tr>
</table>

---

## How it works

```mermaid
flowchart LR
    subgraph src["Sources"]
        ZB["🗞️ 联合早报\nSitemap"]
        YT["📺 Astro 本地圈\nYouTube API"]
    end

    subgraph agg["Aggregate · every 3 hours"]
        TR["Translate\nClaude Haiku"]
        AS["Assess\nClaude Sonnet"]
        DR["Distil rules\nClaude Sonnet"]
        TR --> AS --> DR
    end

    DB[("Supabase")]

    subgraph scheduled["Scheduled jobs"]
        DG["Inside AI\nSonnet · daily"]
        WS["This Week\nSonnet · Monday"]
    end

    FE["🌐 Frontend\nVercel"]

    ZB & YT --> TR
    AS --> DB
    DR --> DB
    DB <--> DG
    DB <--> WS
    DB --> FE
```

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript, Chakra UI, Vite — deployed on Vercel |
| Backend | Python, Claude Haiku (translate), Claude Sonnet (assess + improve) |
| Database | Supabase (Postgres) |
| Jobs | GitHub Actions — aggregation every 3h, digest daily, weekly summary Monday |

---

## APIs & Services

| API | Purpose | Cost |
|---|---|---|
| [Anthropic Claude](https://anthropic.com) | Translation (Haiku), assessment + distillation + digest (Sonnet) | Pay per token |
| [YouTube Data API v3](https://developers.google.com/youtube/v3) | Fetch Astro 本地圈 videos | Free quota |
| [Supabase](https://supabase.com) | Database, REST API | Free tier |
| [ipapi.co](https://ipapi.co) | Visitor geolocation for traffic analytics | Free tier |
| [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) | Headline pronunciation (read-aloud) | Browser built-in |
| [Free Dictionary API](https://dictionaryapi.dev) | Vocab tap — word definitions and phonetics | Free, no key |

---

## Running locally

**Prerequisites:** Python 3.12+, Node 18+, `uv` ([install](https://docs.astral.sh/uv/))

```bash
# Backend deps
uv sync

# Frontend deps
cd frontend && npm install
```

Copy `.env.example` to `.env` and fill in:
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
ANTHROPIC_API_KEY=
YOUTUBE_API_KEY=
```

Copy `frontend/.env.example` to `frontend/.env` and fill in:
```
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

```bash
# Run the aggregation job once
uv run job.py

# Run the daily digest
uv run digest.py

# Start the frontend dev server
cd frontend && npm run dev
```

---

## Tests

```bash
uv run pytest -v
```

Tests cover URL→category mapping, scraper output schema, Claude JSON parsing, and architectural invariants. The aggregation job is gated on tests passing — broken code never reaches production.
