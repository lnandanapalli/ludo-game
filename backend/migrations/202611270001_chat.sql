-- In-game chat messages and emotes for online rooms; removed with their room.
CREATE TABLE IF NOT EXISTS ludo.room_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id text NOT NULL REFERENCES ludo.rooms(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('chat', 'emote')),
    seat text NOT NULL,
    target text,
    body text NOT NULL CHECK (length(body) <= 200),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS room_events_room ON ludo.room_events (room_id, id);
REVOKE ALL ON ludo.room_events FROM PUBLIC;
ALTER TABLE ludo.room_events ENABLE ROW LEVEL SECURITY;
