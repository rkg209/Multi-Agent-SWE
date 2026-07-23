"""Writes `trace_events` rows (LLM calls and agent turns) and reads them back for metrics."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass

import psycopg2
import psycopg2.extras

from src.errors import RouterError

logger = logging.getLogger(__name__)


def _connect() -> psycopg2.extensions.connection:
    """Open a fresh Postgres connection from `DATABASE_URL`, raising `RouterError` on failure."""
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise RouterError("DATABASE_URL is not set; cannot write trace_events row") from exc

    try:
        return psycopg2.connect(database_url, connect_timeout=5)
    except psycopg2.Error as exc:
        raise RouterError(f"Could not connect to Postgres at DATABASE_URL: {exc}") from exc


def _execute(sql: str, params: dict[str, object]) -> None:
    """Run one INSERT against `trace_events` on its own connection; raises `RouterError`."""
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
    except psycopg2.Error as exc:
        raise RouterError(f"Failed to write trace_events row: {exc}") from exc
    finally:
        conn.close()


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
    payload = {"provider": provider}
    _execute(
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


def record_agent_turn(
    *,
    run_id: uuid.UUID,
    task_id: str,
    agent_role: str,
    turn_index: int,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    duration_ms: int,
    tool_calls: list[str],
) -> None:
    """Insert one `agent_turn` row into `benchmark.trace_events` (FR-29).

    `tool_calls` names are recorded in `payload`, not as one row per call
    (satisfies FR-29 without inflating write volume). Raises `RouterError` on
    any Postgres failure, matching `record_llm_call`.
    """
    payload = {"tool_calls": tool_calls, "tool_call_count": len(tool_calls)}
    _execute(
        """
        INSERT INTO benchmark.trace_events (
            run_id, task_id, agent_role, turn_index, event_type,
            model, prompt_tokens, completion_tokens, cost_usd,
            duration_ms, payload
        ) VALUES (
            %(run_id)s, %(task_id)s, %(agent_role)s, %(turn_index)s, 'agent_turn',
            %(model)s, %(prompt_tokens)s, %(completion_tokens)s, %(cost_usd)s,
            %(duration_ms)s, %(payload)s
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
            "duration_ms": duration_ms,
            "payload": psycopg2.extras.Json(payload),
        },
    )


@dataclass(frozen=True)
class TurnRow:
    """One `agent_turn` trace_events row, read back for metric computation."""

    agent_role: str
    turn_index: int
    duration_ms: int | None
    tool_calls: list[str]


def fetch_turns(run_id: uuid.UUID, task_id: str) -> list[TurnRow]:
    """Return all `agent_turn` rows for `(run_id, task_id)`, ordered by `turn_index`.

    Used for iteration counting and by metric unit tests. Raises `RouterError`
    on any Postgres failure.
    """
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_role, turn_index, duration_ms, payload
                    FROM benchmark.trace_events
                    WHERE run_id = %(run_id)s AND task_id = %(task_id)s
                      AND event_type = 'agent_turn'
                    ORDER BY turn_index
                    """,
                    {"run_id": str(run_id), "task_id": task_id},
                )
                rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise RouterError(f"Failed to read trace_events rows: {exc}") from exc
    finally:
        conn.close()

    return [
        TurnRow(
            agent_role=agent_role,
            turn_index=turn_index,
            duration_ms=duration_ms,
            tool_calls=list((payload or {}).get("tool_calls", [])),
        )
        for agent_role, turn_index, duration_ms, payload in rows
    ]


def fetch_task_durations(run_id: uuid.UUID) -> list[float]:
    """Return `run_records.duration_seconds` for every task in `run_id`.

    Used for the Python-side percentile cross-check against the SQL view.
    Raises `RouterError` on any Postgres failure.
    """
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT duration_seconds
                    FROM benchmark.run_records
                    WHERE run_id = %(run_id)s
                    """,
                    {"run_id": str(run_id)},
                )
                rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise RouterError(f"Failed to read run_records rows: {exc}") from exc
    finally:
        conn.close()

    return [float(duration) for (duration,) in rows]
