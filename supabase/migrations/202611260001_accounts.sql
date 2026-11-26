-- Optional accounts, their sign-in sessions, and the online seats they hold.
ALTER TABLE ludo.rooms ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS rooms_updated_at ON ludo.rooms (updated_at);

CREATE TABLE IF NOT EXISTS ludo.accounts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_]{3,20}$'),
    password_hash text NOT NULL,
    profile jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ludo.sessions (
    token_hash text PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES ludo.accounts(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_account ON ludo.sessions (account_id);

-- Finished results outlive their room (rooms are cleaned up later) to keep win records.
CREATE TABLE IF NOT EXISTS ludo.room_players (
    room_id text NOT NULL,
    account_id bigint NOT NULL REFERENCES ludo.accounts(id) ON DELETE CASCADE,
    color text NOT NULL,
    result text CHECK (result IN ('won', 'lost')),
    PRIMARY KEY (room_id, color)
);
CREATE INDEX IF NOT EXISTS room_players_account ON ludo.room_players (account_id);

REVOKE ALL ON ludo.accounts, ludo.sessions, ludo.room_players FROM PUBLIC;
ALTER TABLE ludo.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ludo.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ludo.room_players ENABLE ROW LEVEL SECURITY;
