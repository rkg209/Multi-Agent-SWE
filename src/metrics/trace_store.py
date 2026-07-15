"""Writes `llm_call` trace events to `benchmark.trace_events`."""

from __future__ import annotations

import logging
import os
import uuid

import psycopg2
import psycopg2.extras

from src.errors import RouterError

logger = logging.getLogger(__name__)


def record_llm_call(
    *,
    run_id: uuid.UUID,
    task_id: str,
    agent_role: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    cache_hit: bool = False,
    turn_index: int = 0,
) -> None:
    """Insert one `llm_call` row into `benchmark.trace_events`.

    Raises `RouterError` on any Postgres failure — callers must never swallow
    this, since an LLM call must not be recorded as silently successful when
    its trace row failed to write.
    """
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise RouterError("DATABASE_URL is not set; cannot write trace_events row") from exc

    payload = {"provider": provider}
    try:
        conn = psycopg2.connect(database_url, connect_timeout=5)
    except psycopg2.Error as exc:
        raise RouterError(f"Could not connect to Postgres at DATABASE_URL: {exc}") from exc

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO benchmark.trace_events (
                        run_id, task_id, agent_role, turn_index, event_type,
                        model, prompt_tokens, completion_tokens, cost_usd,
                        cache_hit, payload
                    ) VALUES (
                        %(run_id)s, %(task_id)s, %(agent_role)s, %(turn_index)s, 'llm_call',
                        %(model)s, %(prompt_tokens)s, %(completion_tokens)s, %(cost_usd)s,
                        %(cache_hit)s, %(payload)s
                    )
                    """,
                    {
                        "run_id": str(run_id),
                        "task_id": task_id,
                        "agent_role": agent_role,
                        "turn_index": turn_index,
                        "model": model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cost_usd": cost_usd,
                        "cache_hit": cache_hit,
                        "payload": psycopg2.extras.Json(payload),
                    },
                )
    except psycopg2.Error as exc:
        raise RouterError(f"Failed to write trace_events row: {exc}") from exc
    finally:
        conn.close()
