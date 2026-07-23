"""Integration test for the `headline_metrics` view (FR-33). Skips without Postgres."""

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
def test_headline_metrics_returns_all_five_metrics_under_2s() -> None:
    run_id = uuid.uuid4()
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for i, (outcome, duration, cost, halluc, iters) in enumerate(
                    [
                        ("PASS", 1.0, 0.01, 0.0, 1),
                        ("PASS", 2.0, 0.02, 0.5, 2),
                        ("FAIL", 3.0, 0.03, 0.0, 3),
                    ]
                ):
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
                            f"task-{i}",
                            psycopg2.extras.Json({"solver": "single"}),
                            outcome,
                            cost,
                            10,
                            iters,
                            halluc,
                            duration,
                        ),
                    )

        start = time.monotonic()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM benchmark.headline_metrics WHERE solver = 'single' "
                "AND run_id = %s",
                (str(run_id),),
            )
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
        elapsed = time.monotonic() - start

        assert row is not None
        result = dict(zip(columns, row, strict=True))
        for key in (
            "pass_rate_pct",
            "mean_cost_per_solved_task",
            "p50_duration_seconds",
            "p99_duration_seconds",
            "hallucination_rate",
            "avg_iterations",
        ):
            assert result[key] is not None

        assert elapsed < 2.0
    finally:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM benchmark.run_records WHERE run_id = %s", (str(run_id),))
        conn.close()
