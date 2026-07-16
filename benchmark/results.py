"""Writes immutable `run_records` rows (FR-24). Never `UPDATE`s; each run `INSERT`s (NFR-6)."""

from __future__ import annotations

import logging
import os
import uuid

import psycopg2
import psycopg2.extras

from benchmark.errors import HarnessError

logger = logging.getLogger(__name__)


def write_run_record(
    *,
    run_id: uuid.UUID,
    task_id: str,
    solver_name: str,
    outcome: str,
    duration_seconds: float,
    patch_size_bytes: int | None = None,
    total_cost_usd: float = 0,
    total_tokens: int = 0,
    iteration_count: int = 0,
    hallucination_score: float = 0,
    cap_hit: bool = False,
    budget_exceeded: bool = False,
) -> None:
    """Insert one immutable `(run_id, task_id)` row into `benchmark.run_records`.

    `ON CONFLICT (run_id, task_id) DO NOTHING` enforces immutability at the database level:
    re-running the same `run_id`/`task_id` pair (which shouldn't happen in practice, since `run_id`
    is fresh per CLI invocation) never overwrites an existing row (NFR-6).

    Raises `HarnessError` on any Postgres failure — callers must not treat a failed write as a
    silently successful run.
    """
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise HarnessError("DATABASE_URL is not set; cannot write run_records row") from exc

    solver_config = {"solver": solver_name}
    try:
        conn = psycopg2.connect(database_url, connect_timeout=5)
    except psycopg2.Error as exc:
        raise HarnessError(f"Could not connect to Postgres at DATABASE_URL: {exc}") from exc

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO benchmark.run_records (
                        run_id, task_id, solver_config, outcome, total_cost_usd,
                        total_tokens, iteration_count, hallucination_score,
                        duration_seconds, cap_hit, budget_exceeded, patch_size_bytes
                    ) VALUES (
                        %(run_id)s, %(task_id)s, %(solver_config)s, %(outcome)s, %(total_cost_usd)s,
                        %(total_tokens)s, %(iteration_count)s, %(hallucination_score)s,
                        %(duration_seconds)s, %(cap_hit)s, %(budget_exceeded)s, %(patch_size_bytes)s
                    )
                    ON CONFLICT (run_id, task_id) DO NOTHING
                    """,
                    {
                        "run_id": str(run_id),
                        "task_id": task_id,
                        "solver_config": psycopg2.extras.Json(solver_config),
                        "outcome": outcome,
                        "total_cost_usd": total_cost_usd,
                        "total_tokens": total_tokens,
                        "iteration_count": iteration_count,
                        "hallucination_score": hallucination_score,
                        "duration_seconds": duration_seconds,
                        "cap_hit": cap_hit,
                        "budget_exceeded": budget_exceeded,
                        "patch_size_bytes": patch_size_bytes,
                    },
                )
    except psycopg2.Error as exc:
        raise HarnessError(f"Failed to write run_records row: {exc}") from exc
    finally:
        conn.close()
