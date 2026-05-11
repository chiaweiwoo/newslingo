-- NewsLingo — complete current schema
-- Last updated: 2026-05
-- Run in Supabase SQL Editor for a fresh setup.
-- For existing databases all these changes are already applied.

-- ── headlines ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.headlines (
    id              TEXT        NOT NULL,
    title_zh        TEXT        NOT NULL,
    title_en        TEXT,
    thumbnail_url   TEXT,
    published_at    TIMESTAMPTZ,
    channel         TEXT,
    category        TEXT,
    source_url      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT headlines_pkey         PRIMARY KEY (id),
    CONSTRAINT headlines_source_url_key UNIQUE (source_url)
);

CREATE INDEX IF NOT EXISTS idx_headlines_published_at ON public.headlines (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_headlines_channel       ON public.headlines (channel);
CREATE INDEX IF NOT EXISTS idx_headlines_category      ON public.headlines (category);

-- ── job_runs ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.job_runs (
    id               BIGSERIAL   PRIMARY KEY,
    ran_at           TIMESTAMPTZ DEFAULT now(),
    items_found      INTEGER,
    items_processed  INTEGER,
    status           TEXT,
    error_msg        TEXT,
    duration_seconds NUMERIC
);

-- ── assessment_logs ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.assessment_logs (
    id                  BIGSERIAL   PRIMARY KEY,
    ran_at              TIMESTAMPTZ DEFAULT now(),
    source              TEXT,       -- 'zaobao' | 'astro' | 'zaobao-retry' | 'astro-retry'
    model               TEXT,
    total_assessed      INTEGER,
    passed              INTEGER,
    retried             INTEGER,
    passed_after_retry  INTEGER,
    dropped             INTEGER,
    sample_failures     JSONB,      -- [{zh, en, score, reason, suggestion}, ...]
    avg_score           NUMERIC
);

-- ── prompt_rules ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.prompt_rules (
    id            BIGSERIAL   PRIMARY KEY,
    generated_at  TIMESTAMPTZ DEFAULT now(),
    source        TEXT,       -- 'zaobao' | 'astro'
    rules         TEXT,       -- distilled rules, newline-separated
    run_count_at  INTEGER,    -- job_runs.count when this was generated
    active        BOOLEAN     DEFAULT true
);

-- ── learning_digest ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.learning_digest (
    id          BIGSERIAL   PRIMARY KEY,
    created_at  TIMESTAMPTZ DEFAULT now(),
    digest_at   TIMESTAMPTZ NOT NULL,   -- watermark: all history up to this point is included
    payload     JSONB       NOT NULL,   -- {international:{summary,examples}, malaysia:{...}, singapore:{...}}
    active      BOOLEAN     DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_learning_digest_active ON public.learning_digest (active, created_at DESC);

-- ── visits ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.visits (
    id         BIGSERIAL   PRIMARY KEY,
    visited_at TIMESTAMPTZ DEFAULT now(),
    ip         TEXT,
    country    TEXT,
    user_agent TEXT,
    is_mobile  BOOLEAN
);
