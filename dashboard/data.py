"""Read-only Postgres access for the Streamlit dashboard. The only module that touches SQL."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

import pandas as pd
import psycopg2

logger = logging.getLogger(__name__)

HEADLINE_COLUMNS: tuple[str, ...] = (
    "solver",
    "run_id",
    "total_tasks",
    "pass_rate_pct",
    "mean_cost_per_solved_task",
    "p50_duration_seconds",
    "p99_duration_seconds",
    "hallucination_rate",
    "avg_iterations",
    "run_finished_at",
)

_HEADLINE_SELECT = """
    h.solver, h.run_id, h.total_tasks, h.pass_rate_pct,
    h.mean_cost_per_solved_task, h.p50_duration_seconds,
    h.p99_duration_seconds, h.hallucination_rate, h.avg_iterations,
    s.run_finished_at
"""


class DashboardError(RuntimeError):
    """Raised for a dashboard data-access failure: missing config or a Postgres error."""


def _connect() -> psycopg2.extensions.connection:
    """Open a fresh Postgres connection from `DATABASE_URL`, raising `DashboardError` on failure."""
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise DashboardError("DATABASE_URL is not set; cannot query the dashboard views") from exc

    try:
        return psycopg2.connect(database_url, connect_timeout=5)
    except psycopg2.Error as exc:
        raise DashboardError(f"Could not connect to Postgres at DATABASE_URL: {exc}") from exc


def _query(sql: str, params: tuple[object, ...] = ()) -> pd.DataFrame:
    """Run one read-only SELECT and return a DataFrame named from `cursor.description`.

    Column names always come from `cursor.description`, so an empty result still yields a
    correctly-named empty DataFrame instead of a bare `pd.DataFrame()`.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise DashboardError(f"Query failed: {exc}") from exc
    finally:
        conn.close()

    return pd.DataFrame(rows, columns=columns)


def fetch_runs() -> pd.DataFrame:
    """Return every run (solver, run_id, run_finished_at, total_tasks), newest first."""
    return _query(
        "SELECT solver, run_id, run_finished_at, total_tasks "
        "FROM benchmark.run_summary ORDER BY run_finished_at DESC"
    )


def fetch_headline(run_ids: Sequence[str] | None = None) -> pd.DataFrame:
    """Return headline metrics for the given `run_id`s (sidebar override)."""
    return _query(
        f"""
        SELECT {_HEADLINE_SELECT}
        FROM benchmark.headline_metrics h
        JOIN benchmark.run_summary s ON s.run_id = h.run_id AND s.solver = h.solver
        WHERE h.run_id = ANY(%s)
        ORDER BY h.solver, s.run_finished_at DESC
        """,
        (list(run_ids) if run_ids else [],),
    )


def fetch_latest_headline() -> pd.DataFrame:
    """Return the most recent headline row per solver (the default dashboard view)."""
    return _query(f"""
        SELECT DISTINCT ON (h.solver)
               {_HEADLINE_SELECT}
        FROM benchmark.headline_metrics h
        JOIN benchmark.run_summary s ON s.run_id = h.run_id AND s.solver = h.solver
        ORDER BY h.solver, s.run_finished_at DESC
        """)
