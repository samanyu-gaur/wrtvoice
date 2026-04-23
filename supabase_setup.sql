-- =============================================================
-- Socratic Oracle LLM - Supabase Table Setup
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- =============================================================

-- Sessions table: stores PDF context and session metadata
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    pdf_context TEXT,
    pdf_metadata JSONB DEFAULT '{}'::jsonb
);

-- Messages table: stores the full conversation history
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Vision logs: stores Deliverable 3 architectural critique history
CREATE TABLE IF NOT EXISTS vision_logs (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE,
    image_prompt TEXT,
    response TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_vision_logs_session ON vision_logs(session_id);

-- Verify tables were created
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name IN ('sessions', 'messages', 'vision_logs')
ORDER BY table_name;
