-- Backend-only schema outside Supabase's public Data API.
CREATE SCHEMA IF NOT EXISTS ludo;
REVOKE ALL ON SCHEMA ludo FROM PUBLIC;
CREATE TABLE IF NOT EXISTS ludo.rooms (
    id text PRIMARY KEY,
    mode text NOT NULL CHECK (mode IN ('local', 'online')),
    seats jsonb NOT NULL,
    state jsonb NOT NULL,
    revision integer NOT NULL DEFAULT 0
);
REVOKE ALL ON ludo.rooms FROM PUBLIC;
ALTER TABLE ludo.rooms ENABLE ROW LEVEL SECURITY;
