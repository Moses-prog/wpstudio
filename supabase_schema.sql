-- ==============================================================================
-- WP STUDIO | SUPABASE CLOUD DATABASE SCHEMA
-- Run this script in your Supabase SQL Editor (https://supabase.com/dashboard)
-- ==============================================================================

-- 1. Create wp_studio_users table
CREATE TABLE IF NOT EXISTS public.wp_studio_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    credits INTEGER DEFAULT 20,
    tier TEXT DEFAULT 'Builder',
    custom_gemini_key TEXT,
    selected_model TEXT DEFAULT 'gemini-3.8-flash',
    stories_created INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Create wp_studio_jobs table
CREATE TABLE IF NOT EXISTS public.wp_studio_jobs (
    job_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    source_input TEXT,
    source_title TEXT,
    transcript TEXT,
    culture TEXT DEFAULT 'Universal',
    style TEXT DEFAULT 'Stylised 3D',
    genre TEXT DEFAULT 'Action Thriller',
    timezone TEXT DEFAULT 'Africa/Lagos',
    length_tier TEXT DEFAULT 'Short',
    concepts_json JSONB,
    selected_concept_idx INTEGER,
    full_story_json JSONB,
    story_bible_pdf TEXT,
    scene_prompts_pdf TEXT,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Create wp_studio_story_history table
CREATE TABLE IF NOT EXISTS public.wp_studio_story_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    title TEXT,
    topic TEXT,
    style TEXT,
    genre TEXT,
    duration TEXT,
    pdf_path TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Enable Row Level Security (RLS) but allow anon access for Bot/Service
ALTER TABLE public.wp_studio_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wp_studio_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wp_studio_story_history ENABLE ROW LEVEL SECURITY;

-- 5. Policies to allow read/write from anon key
CREATE POLICY "Allow public read/write to wp_studio_users" ON public.wp_studio_users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow public read/write to wp_studio_jobs" ON public.wp_studio_jobs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow public read/write to wp_studio_story_history" ON public.wp_studio_story_history FOR ALL USING (true) WITH CHECK (true);
