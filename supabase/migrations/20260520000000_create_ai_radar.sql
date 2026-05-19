CREATE TABLE IF NOT EXISTS public.ai_radar (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at   TIMESTAMPTZ DEFAULT now() NOT NULL,
    window_start DATE        NOT NULL,
    window_end   DATE        NOT NULL,
    payload      JSONB       NOT NULL,
    active       BOOLEAN     DEFAULT true NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_radar_active ON public.ai_radar (active, created_at DESC);

ALTER TABLE public.ai_radar ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_radar_anon_select"
  ON public.ai_radar FOR SELECT TO anon USING (true);
