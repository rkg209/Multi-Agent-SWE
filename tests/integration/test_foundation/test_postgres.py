"""Integration tests for the Postgres schema created by scripts/db_init.sql."""

from __future__ import annotations

import os

import pytest

psycopg2 = pytest.importorskip("psycopg2")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/benchmark_db"
)
EXPECTED_TABLES = {"llm_cache", "trace_events", "run_records"}


def _can_connect() -> bool:
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    except psycopg2.OperationalError:
        return False
    conn.close()
    return True


pytestmark = pytest.mark.skipif(not _can_connect(), reason="Postgres not reachable at DATABASE_URL")


@pytest.mark.integration
def test_postgres_connection() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


@pytest.mark.integration
def test_tables_exist() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'benchmark'"
            )
            found = {row[0] for row in cur.fetchall()}
        assert EXPECTED_TABLES <= found
    finally:
        conn.close()
