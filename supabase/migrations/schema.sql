-- NewsLingo — complete current schema
-- Last updated: 2026-05-12
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

-- ── weekly_summary ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.weekly_summary (
    id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at  TIMESTAMPTZ DEFAULT now() NOT NULL,
    week_start  DATE        NOT NULL,
    week_end    DATE        NOT NULL,
    payload     JSONB       NOT NULL,   -- {topics:[{title,summary,region},...]}
    active      BOOLEAN     DEFAULT true NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_weekly_summary_active ON public.weekly_summary (active, created_at DESC);

-- ── visits ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.visits (
    id         BIGSERIAL   PRIMARY KEY,
    visited_at TIMESTAMPTZ DEFAULT now(),
    ip         TEXT,
    country    TEXT,
    user_agent TEXT,
    is_mobile  BOOLEAN
);

-- ── Row Level Security ────────────────────────────────────────────────────────
-- The anon key is exposed in the frontend bundle. RLS ensures it can only read
-- data — never write/delete — except visits where INSERT is intentional.
-- The service_role key (backend job) bypasses RLS entirely, so no policies
-- are needed for write operations.

ALTER TABLE public.headlines       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_runs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assessment_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_rules    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_digest ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.weekly_summary  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.visits          ENABLE ROW LEVEL SECURITY;

-- headlines — public read
CREATE POLICY "headlines_anon_select"
  ON public.headlines FOR SELECT TO anon USING (true);

-- job_runs — public read (frontend reads latest job timestamp)
CREATE POLICY "job_runs_anon_select"
  ON public.job_runs FOR SELECT TO anon USING (true);

-- assessment_logs — public read (Stats drawer)
CREATE POLICY "assessment_logs_anon_select"
  ON public.assessment_logs FOR SELECT TO anon USING (true);

-- prompt_rules — public read (Learning Digest drawer)
CREATE POLICY "prompt_rules_anon_select"
  ON public.prompt_rules FOR SELECT TO anon USING (true);

-- learning_digest — public read (Inside AI drawer)
CREATE POLICY "learning_digest_anon_select"
  ON public.learning_digest FOR SELECT TO anon USING (true);

-- weekly_summary — public read (This Week drawer)
CREATE POLICY "weekly_summary_anon_select"
  ON public.weekly_summary FOR SELECT TO anon USING (true);

-- visits — anon may insert (visit tracking) and select (Traffic drawer)
-- Note: raw IPs are readable via anon key — acceptable for a personal project.
CREATE POLICY "visits_anon_insert"
  ON public.visits FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "visits_anon_select"
  ON public.visits FOR SELECT TO anon USING (true);

-- ── token_usage ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.token_usage (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at   TIMESTAMPTZ DEFAULT now(),
    task          TEXT        NOT NULL,    -- 'translation' | 'feedback' | 'insights'
    model         TEXT        NOT NULL,
    input_tokens  BIGINT      NOT NULL DEFAULT 0,
    output_tokens BIGINT      NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(10,6) NOT NULL DEFAULT 0
);

ALTER TABLE public.token_usage ENABLE ROW LEVEL SECURITY;

-- token_usage — public read (Costs drawer)
CREATE POLICY "token_usage_anon_select"
  ON public.token_usage FOR SELECT TO anon USING (true);
