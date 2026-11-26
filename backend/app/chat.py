"""In-game chat and emotes for online rooms."""
import re
import unicodedata

# Reactions appear over the sender; throws fly from the sender to the chosen player.
REACTIONS = ("ooo", "howzat", "haha", "clap", "cool", "cry", "thinking", "goodluck")
THROWS = ("snake", "rocket", "tomato", "rose", "heart", "party")
EMOTES = REACTIONS + THROWS
MAX_LENGTH = 200


def clean(text):
    """Drop control and invisible formatting characters and collapse whitespace."""
    text = "".join(" " if ch in "\t\n\r" else ch for ch in text
                   if ch in "\t\n\r" or unicodedata.category(ch) not in ("Cc", "Cf"))
    return re.sub(r"\s+", " ", text).strip()


def event(row):
    return dict(id=row["id"], kind=row["kind"], seat=row["seat"], target=row["target"], body=row["body"],
                at=row["created_at"].timestamp())


def recent(db, room, after):
    """Events newer than `after`; on the first poll (after < 1), the latest 50 as history."""
    if after < 1:
        rows = db.execute("SELECT * FROM ludo.room_events WHERE room_id=%s ORDER BY id DESC LIMIT 50",
                          (room,)).fetchall()[::-1]
    else:
        rows = db.execute("SELECT * FROM ludo.room_events WHERE room_id=%s AND id>%s ORDER BY id LIMIT 100",
                          (room, after)).fetchall()
    return [event(row) for row in rows]


def add(db, room, kind, seat, body, target=None):
    row = db.execute("INSERT INTO ludo.room_events(room_id, kind, seat, target, body) VALUES (%s,%s,%s,%s,%s) "
                     "RETURNING *", (room, kind, seat, target, body)).fetchone()
    return event(row)
