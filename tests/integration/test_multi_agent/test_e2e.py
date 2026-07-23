"""Integration test: `make benchmark TASKS=lite-5 SOLVER=multi` end-to-end.

Requires Docker, Postgres, `DATABASE_URL`, and a reachable model provider
(`LITELLM_CONFIG=config/litellm_config.local.yaml` + `OLLAMA_BASE_URL`) — skipped otherwise.
"""

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


def _provider_configured() -> bool:
    return bool(os.environ.get("OLLAMA_BASE_URL"))


pytestmark = pytest.mark.skipif(
    not _docker_available() or not _postgres_available() or not _provider_configured(),
    reason="Docker, Postgres, or a model provider (OLLAMA_BASE_URL) not available",
)


def _run_benchmark(tasks: str, solver: str) -> tuple[int, str]:
    env = dict(os.environ)
    env["LITELLM_CONFIG"] = "config/litellm_config.local.yaml"
    result = subprocess.run(
        ["make", "benchmark", f"TASKS={tasks}", f"SOLVER={solver}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
        env=env,
    )
    return result.returncode, result.stdout + result.stderr


def _fetch_run_records(run_id: str) -> list[tuple[str, str]]:
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


def _fetch_trace_roles_and_models(run_id: str) -> list[tuple[str, str]]:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent_role, model FROM benchmark.trace_events "
                "WHERE run_id = %s AND event_type = 'agent_turn'",
                (run_id,),
            )
            return cur.fetchall()
    finally:
        conn.close()


@pytest.mark.integration
def test_multi_agent_benchmark_writes_run_record_and_per_agent_traces() -> None:
    exit_code, output = _run_benchmark("lite-5", "multi")
    assert exit_code == 0, output
    match = RUN_ID_RE.search(output)
    assert match, output
    run_id = match.group(1)

    rows = _fetch_run_records(run_id)
    assert len(rows) == 7  # 5 SWE-bench + 2 custom

    traced_roles = {role for role, _ in _fetch_trace_roles_and_models(run_id)}
    assert {"architect", "developer", "tester", "reviewer"} <= traced_roles
