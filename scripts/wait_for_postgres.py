#!/usr/bin/env python3
"""Poll DATABASE_URL until Postgres accepts connections, or fail after a timeout."""

from __future__ import annotations

import os
import sys
import time

import psycopg2

DEFAULT_DATABASE_URL = "postgresql://postgres:password@localhost:5432/benchmark_db"
MAX_WAIT_SECONDS = 30
POLL_INTERVAL_SECONDS = 1


def wait_for_postgres(database_url: str, max_wait_seconds: int) -> bool:
    """Poll `database_url` until a connection succeeds or the timeout elapses."""
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        try:
            conn = psycopg2.connect(database_url, connect_timeout=3)
            conn.close()
            return True
        except psycopg2.OperationalError:
            time.sleep(POLL_INTERVAL_SECONDS)
    return False


def main() -> int:
    """Entry point: wait for Postgres readiness and return a process exit code."""
    database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    if wait_for_postgres(database_url, MAX_WAIT_SECONDS):
        print("Postgres is ready.")
        return 0
    print(f"Postgres did not become ready within {MAX_WAIT_SECONDS}s.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
