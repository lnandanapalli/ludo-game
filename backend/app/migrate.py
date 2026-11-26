"""Apply the SQL files in backend/migrations when the API starts.

Each file runs once, in name order, and is recorded in ludo.schema_migrations. An advisory
lock makes concurrent instances wait for each other, and each file runs in its own transaction
together with its record, so a failed file leaves nothing half applied.
Set LUDO_AUTO_MIGRATE=0 to apply the files yourself instead.
"""
import logging
import os
from pathlib import Path

from .db import database

log = logging.getLogger("ludo.migrate")
FOLDER = Path(__file__).resolve().parent.parent / "migrations"
LOCK = 7_340_211  # Arbitrary key shared by every instance of this app.


def migrate():
    if os.getenv("LUDO_AUTO_MIGRATE", "1") == "0":
        return []
    applied = []
    with database() as db:
        db.autocommit = True
        db.execute("SELECT pg_advisory_lock(%s)", (LOCK,))
        try:
            db.execute("CREATE SCHEMA IF NOT EXISTS ludo")
            db.execute("CREATE TABLE IF NOT EXISTS ludo.schema_migrations "
                       "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
            db.execute("REVOKE ALL ON ludo.schema_migrations FROM PUBLIC")
            done = {row["name"] for row in db.execute("SELECT name FROM ludo.schema_migrations")}
            for path in sorted(FOLDER.glob("*.sql")):
                if path.name in done:
                    continue
                with db.transaction():
                    db.execute(path.read_text())
                    db.execute("INSERT INTO ludo.schema_migrations(name) VALUES (%s)", (path.name,))
                applied.append(path.name)
                log.warning("Applied migration %s", path.name)
        finally:
            db.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))
    return applied
