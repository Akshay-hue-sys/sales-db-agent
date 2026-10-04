"""Separate explicit maintenance writes from read-only runtime access."""

import os


def _connect(*, read_only, connector=None):
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is not configured.")
    if connector is None:
        import psycopg

        connector = psycopg.connect
    conn = connector(
        url,
        connect_timeout=5,
        options="-c statement_timeout=5000 -c lock_timeout=2000 -c search_path=pg_catalog,public",
    )
    try:
        conn.read_only = read_only
    except Exception:
        conn.close()
        raise
    return conn


def get_conn():
    """Writable connection for explicit maintenance scripts only."""
    return _connect(read_only=False)


def get_read_conn():
    """Production tools start read-only transactions."""
    return _connect(read_only=True)
