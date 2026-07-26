"""Integration test for `dashboard.data.fetch_latest_headline`. Skips without Postgres."""

from __future__ import annotations

import os
import time
import uuid

import pytest

psycopg2 = pytest.importorskip("psycopg2")
psycopg2.extras = pytest.importorskip("psycopg2.extras")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/benchmark_db"
)


def _can_connect() -> bool:
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    except psycopg2.OperationalError:
        return False
    conn.close()
    return True


pytestmark = pytest.mark.skipif(not _can_connect(), reason="Postgres not reachable at DATABASE_URL")


@pytest.mark.integration
def test_fetch_latest_headline_returns_one_row_per_solver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)

    from dashboard.data import fetch_latest_headline

    run_ids = {"single": uuid.uuid4(), "multi": uuid.uuid4()}
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for solver, run_id in run_ids.items():
                    cur.execute(
                        """
                        INSERT INTO benchmark.run_records (
                            run_id, task_id, solver_config, outcome, total_cost_usd,
                            total_tokens, iteration_count, hallucination_score,
                            duration_seconds
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(run_id),
                            f"task-{solver}",
                            psycopg2.extras.Json({"solver": solver}),
                            "PASS",
                            0.02,
                            10,
                            1,
                            0.0,
                            1.5,
                        ),
                    )

        start = time.monotonic()
        frame = fetch_latest_headline()
        elapsed = time.monotonic() - start

        result_by_solver = {
            row.solver: row
            for row in frame.itertuples()
            if str(row.run_id) in map(str, run_ids.values())
        }
        for solver, run_id in run_ids.items():
            assert solver in result_by_solver
            row = result_by_solver[solver]
            assert str(row.run_id) == str(run_id)
            assert row.pass_rate_pct is not None
            assert row.mean_cost_per_solved_task is not None

        assert elapsed < 2.0
    finally:
        with conn:
            with conn.cursor() as cur:
                for run_id in run_ids.values():
                    cur.execute(
                        "DELETE FROM benchmark.run_records WHERE run_id = %s", (str(run_id),)
                    )
        conn.close()
