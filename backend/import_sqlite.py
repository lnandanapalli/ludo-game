"""Copy legacy rooms into Postgres without modifying the source or overwriting rooms."""
import argparse
import json
import sqlite3
from pathlib import Path

from psycopg.types.json import Jsonb

from app.db import database


def migrate(path):
    copied = 0
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as source, database() as target:
        for room, mode, seats, state, revision in source.execute(
            "SELECT id, mode, seats, state, revision FROM rooms"
        ):
            record = dict(mode=mode, seats=json.loads(seats), state=json.loads(state), revision=revision)
            inserted = target.execute(
                "INSERT INTO ludo.rooms (id, mode, seats, state, revision) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (room, mode, Jsonb(record["seats"]), Jsonb(record["state"]), revision),
            ).rowcount
            if not inserted:
                existing = target.execute(
                    "SELECT mode, seats, state, revision FROM ludo.rooms WHERE id=%s", (room,)
                ).fetchone()
                if existing != record:
                    raise ValueError(f"Room {room} differs in Postgres; import rolled back.")
            copied += inserted
    return copied


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    print(f"Imported {migrate(parser.parse_args().source)} rooms.")
