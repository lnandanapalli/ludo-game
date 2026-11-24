import os

import psycopg
from psycopg.rows import dict_row


def database():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL to the backend Postgres connection URI.")
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None)
