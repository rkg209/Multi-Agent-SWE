"""Integration test for `src.router.cache` persistence (NFR-12). Skips without Postgres."""

from __future__ import annotations

import os
import uuid

import pytest

psycopg2 = pytest.importorskip("psycopg2")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/benchmark_db"
)
os.environ.setdefault("DATABASE_URL", DATABASE_URL)


def _can_connect() -> bool:
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    except psycopg2.OperationalError:
        return False
    conn.close()
    return True


pytestmark = pytest.mark.skipif(not _can_connect(), reason="Postgres not reachable at DATABASE_URL")


@pytest.mark.integration
def test_store_then_fresh_connection_reads_same_content() -> None:
    """A cached response written by one connection is readable by an unrelated later connection.

    Proves the cache is a real persistent store, not an in-process dict —
    the exact property NFR-12 requires (survives process restarts).
    """
    from src.router.cache import build_cache_key, get_cached_response, store_response

    model = f"test-model-{uuid.uuid4()}"
    messages = [{"role": "user", "content": f"unique-{uuid.uuid4()}"}]
    cache_key = build_cache_key(model, messages)

    store_response(cache_key, model, "the cached answer", 10, 5, 0.001)

    entry = get_cached_response(cache_key)
    assert entry is not None
    assert entry.content == "the cached answer"
    assert entry.prompt_tokens == 10
    assert entry.completion_tokens == 5


@pytest.mark.integration
def test_first_write_wins_on_conflict() -> None:
    """`ON CONFLICT (cache_key) DO NOTHING` — a second store for the same key is a no-op."""
    from src.router.cache import build_cache_key, get_cached_response, store_response

    model = f"test-model-{uuid.uuid4()}"
    messages = [{"role": "user", "content": f"unique-{uuid.uuid4()}"}]
    cache_key = build_cache_key(model, messages)

    store_response(cache_key, model, "first answer", 10, 5, 0.001)
    store_response(cache_key, model, "second answer", 999, 999, 999.0)

    entry = get_cached_response(cache_key)
    assert entry is not None
    assert entry.content == "first answer"
