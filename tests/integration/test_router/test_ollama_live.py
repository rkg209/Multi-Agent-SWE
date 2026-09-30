"""Integration test: a live `complete()` call against a local Ollama endpoint."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
import uuid

import pytest

psycopg2 = pytest.importorskip("psycopg2")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/benchmark_db"
)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL")


def _ollama_reachable() -> bool:
    if not OLLAMA_BASE_URL:
        return False
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _can_connect_postgres() -> bool:
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    except psycopg2.OperationalError:
        return False
    conn.close()
    return True


pytestmark = pytest.mark.skipif(
    not _ollama_reachable() or not _can_connect_postgres(),
    reason="Ollama endpoint unreachable (or OLLAMA_BASE_URL unset) or Postgres unreachable",
)


@pytest.mark.integration
def test_live_ollama_call_writes_trace_event() -> None:
    from src.router.config import RouterConfig, TierConfig
    from src.router.router import LLMRequest, complete

    config = RouterConfig(
        tiers={
            "local": TierConfig(
                name="local",
                provider="ollama",
                model="ollama/llama3.1",
                input_price_per_1k=0.0,
                output_price_per_1k=0.0,
                api_base=OLLAMA_BASE_URL,
            )
        },
        roles={},
    )
    run_id = uuid.uuid4()
    response = complete(
        LLMRequest(
            messages=[{"role": "user", "content": "Say hello in one word."}],
            tier="local",
            run_id=run_id,
            task_id="integration-test",
        ),
        config=config,
    )
    assert response.cost_usd == 0.0

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cost_usd FROM benchmark.trace_events "
                "WHERE run_id = %s AND event_type = 'llm_call'",
                (str(run_id),),
            )
            rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 0
    finally:
        conn.close()
