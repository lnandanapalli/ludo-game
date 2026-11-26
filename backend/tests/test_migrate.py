import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from app import migrate as migrations

FILES = sorted(p.name for p in migrations.FOLDER.glob("*.sql"))


@pytest.fixture
def empty_database(monkeypatch):
    """A throwaway database, with DATABASE_URL pointing at it."""
    base = os.environ["DATABASE_URL"]
    name = "ludo_migrate_" + secrets.token_hex(4)
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    parts = urlsplit(base)
    url = urlunsplit(parts._replace(path="/" + name))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("LUDO_AUTO_MIGRATE", raising=False)
    yield url
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


def tables(url):
    with psycopg.connect(url) as db:
        return {row[0] for row in db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='ludo'")}


def test_fresh_database_is_built_once(empty_database):
    assert migrations.migrate() == FILES
    assert {"rooms", "accounts", "signups", "password_resets", "sessions", "room_players",
            "schema_migrations"} <= tables(empty_database)
    assert migrations.migrate() == []


def test_database_set_up_by_hand_keeps_its_rooms(empty_database):
    with psycopg.connect(empty_database) as db:
        db.execute((migrations.FOLDER / FILES[0]).read_text())
        db.execute("""INSERT INTO ludo.rooms(id, mode, seats, state) VALUES ('abcdef0123', 'local', '[]', '{}')""")
    assert migrations.migrate() == FILES  # Files are safe to run again on a hand-made schema.
    with psycopg.connect(empty_database) as db:
        assert db.execute("SELECT updated_at IS NOT NULL FROM ludo.rooms WHERE id='abcdef0123'").fetchone() == (True,)


def test_instances_starting_together_apply_each_file_once(empty_database):
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: migrations.migrate(), range(4)))
    assert sorted(name for result in results for name in result) == FILES


def test_failed_file_is_not_recorded(empty_database, monkeypatch, tmp_path):
    (tmp_path / "1_good.sql").write_text("CREATE TABLE ludo.good(x int);")
    (tmp_path / "2_bad.sql").write_text("CREATE TABLE ludo.half(x int); SELECT broken syntax here;")
    monkeypatch.setattr(migrations, "FOLDER", tmp_path)
    with pytest.raises(psycopg.Error):
        migrations.migrate()
    assert "good" in tables(empty_database) and "half" not in tables(empty_database)
    with psycopg.connect(empty_database) as db:
        assert [r[0] for r in db.execute("SELECT name FROM ludo.schema_migrations")] == ["1_good.sql"]


def test_can_be_turned_off(empty_database, monkeypatch):
    monkeypatch.setenv("LUDO_AUTO_MIGRATE", "0")
    assert migrations.migrate() == [] and tables(empty_database) == set()
