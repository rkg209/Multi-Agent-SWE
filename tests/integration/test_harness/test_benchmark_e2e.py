"""Integration test: `make benchmark TASKS=lite-5 SOLVER=noop` end-to-end (Docker+Postgres)."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/benchmark_db"
)
RUN_ID_RE = re.compile(r"Benchmark run ([0-9a-f-]{36})")


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    except psycopg2.OperationalError:
        return False
    conn.close()
    return True


pytestmark = pytest.mark.skipif(
    not _docker_available() or not _postgres_available(),
    reason="Docker or Postgres not available",
)


def _run_benchmark(tasks: str, solver: str) -> tuple[int, str]:
    result = subprocess.run(
        ["make", "benchmark", f"TASKS={tasks}", f"SOLVER={solver}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def _fetch_outcomes(run_id: str) -> list[tuple[str, str]]:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT task_id, outcome FROM benchmark.run_records WHERE run_id = %s",
                (run_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


@pytest.mark.integration
def test_noop_benchmark_writes_fail_rows_and_reruns_are_immutable() -> None:
    exit_code_1, output_1 = _run_benchmark("lite-5", "noop")
    assert exit_code_1 == 0, output_1
    match_1 = RUN_ID_RE.search(output_1)
    assert match_1, output_1
    run_id_1 = match_1.group(1)

    rows_1 = _fetch_outcomes(run_id_1)
    assert len(rows_1) == 7  # 5 SWE-bench + 2 custom
    assert all(outcome == "FAIL" for _, outcome in rows_1)

    exit_code_2, output_2 = _run_benchmark("lite-5", "noop")
    assert exit_code_2 == 0, output_2
    match_2 = RUN_ID_RE.search(output_2)
    assert match_2, output_2
    run_id_2 = match_2.group(1)

    assert run_id_2 != run_id_1
    rows_2 = _fetch_outcomes(run_id_2)
    assert len(rows_2) == 7


@pytest.mark.integration
def test_over_cap_refused_without_override(tmp_path: Path) -> None:
    big_subset = PROJECT_ROOT / "config" / "tasks" / "lite-51-itest.txt"
    big_subset.write_text("\n".join(f"repo__x-{i}" for i in range(51)), encoding="utf-8")
    try:
        exit_code, output = _run_benchmark("lite-51-itest", "noop")
        assert exit_code != 0
        assert "exceeding the cap" in output
    finally:
        big_subset.unlink()
