"""Persistent `(model, prompt)` response cache backed by `benchmark.llm_cache` (FR-44, NFR-12).

Mirrors `src/metrics/trace_store.py`'s connection pattern: one `psycopg2`
connection per call, `RouterError` on any Postgres failure. The cache key is
`SHA-256(model || canonical_json(messages))`, exactly as documented on the
`llm_cache` table in `scripts/db_init.sql`.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

import psycopg2
import psycopg2.extras

from src.errors import RouterError


def _connect() -> psycopg2.extensions.connection:
    """Open a fresh Postgres connection from `DATABASE_URL`, raising `RouterError` on failure."""
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise RouterError("DATABASE_URL is not set; cannot access llm_cache") from exc

    try:
        return psycopg2.connect(database_url, connect_timeout=5)
    except psycopg2.Error as exc:
        raise RouterError(f"Could not connect to Postgres at DATABASE_URL: {exc}") from exc


@dataclass(frozen=True)
class CachedEntry:
    """A cached LLM response, read back from `llm_cache`."""

    content: str
    prompt_tokens: int
    completion_tokens: int


def build_cache_key(model: str, messages: list[dict[str, str]]) -> str:
    """Compute `SHA-256(model || canonical_json(messages))` as a 64-char hex digest."""
    canonical = model + json.dumps(messages, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_cached_response(cache_key: str) -> CachedEntry | None:
    """Return the cached entry for `cache_key`, or `None` on a miss.

    Raises `RouterError` on any Postgres failure.
    """
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, usage FROM benchmark.llm_cache
                    WHERE cache_key = %(cache_key)s
                    """,
                    {"cache_key": cache_key},
                )
                row = cur.fetchone()
    except psycopg2.Error as exc:
        raise RouterError(f"Failed to read llm_cache row: {exc}") from exc
    finally:
        conn.close()

    if row is None:
        return None
    content, usage = row
    return CachedEntry(
        content=content,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
    )


def store_response(
    cache_key: str,
    model: str,
    content: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
) -> None:
    """Insert `cache_key`'s response into `llm_cache`; first write wins (`ON CONFLICT DO NOTHING`).

    Raises `RouterError` on any Postgres failure.
    """
    usage = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO benchmark.llm_cache (
                        cache_key, model, content, usage, cost_usd
                    ) VALUES (
                        %(cache_key)s, %(model)s, %(content)s, %(usage)s, %(cost_usd)s
                    )
                    ON CONFLICT (cache_key) DO NOTHING
                    """,
                    {
                        "cache_key": cache_key,
                        "model": model,
                        "content": content,
                        "usage": psycopg2.extras.Json(usage),
                        "cost_usd": cost_usd,
                    },
                )
    except psycopg2.Error as exc:
        raise RouterError(f"Failed to write llm_cache row: {exc}") from exc
    finally:
        conn.close()
