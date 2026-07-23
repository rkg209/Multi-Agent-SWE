"""Unit tests for `src.metrics.trace_store`, with Postgres mocked."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from src.errors import RouterError
from src.metrics.trace_store import TurnRow, fetch_task_durations, fetch_turns, record_agent_turn


def _mock_conn_cursor() -> tuple[MagicMock, MagicMock]:
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


def test_record_agent_turn_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RouterError, match="DATABASE_URL is not set"):
        record_agent_turn(
            run_id=uuid.uuid4(),
            task_id="repo__x-1",
            agent_role="developer",
            turn_index=0,
            model="groq/llama",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.001,
            duration_ms=250,
            tool_calls=["read_file", "write_file"],
        )


def test_record_agent_turn_inserts_expected_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    run_id = uuid.uuid4()
    mock_conn, mock_cursor = _mock_conn_cursor()

    with patch("src.metrics.trace_store.psycopg2.connect", return_value=mock_conn):
        record_agent_turn(
            run_id=run_id,
            task_id="repo__x-1",
            agent_role="developer",
            turn_index=2,
            model="groq/llama",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.001,
            duration_ms=250,
            tool_calls=["read_file", "write_file"],
        )

    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args.args
    assert "agent_turn" in sql
    assert params["run_id"] == str(run_id)
    assert params["turn_index"] == 2
    assert params["duration_ms"] == 250
    assert params["payload"].adapted == {
        "tool_calls": ["read_file", "write_file"],
        "tool_call_count": 2,
    }
    mock_conn.close.assert_called_once()


def test_record_agent_turn_insert_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    mock_conn, mock_cursor = _mock_conn_cursor()
    mock_cursor.execute.side_effect = psycopg2.Error("boom")

    with patch("src.metrics.trace_store.psycopg2.connect", return_value=mock_conn):
        with pytest.raises(RouterError, match="Failed to write trace_events row"):
            record_agent_turn(
                run_id=uuid.uuid4(),
                task_id="repo__x-1",
                agent_role="developer",
                turn_index=0,
                model=None,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                duration_ms=1,
                tool_calls=[],
            )
    mock_conn.close.assert_called_once()


def test_fetch_turns_parses_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    run_id = uuid.uuid4()
    mock_conn, mock_cursor = _mock_conn_cursor()
    mock_cursor.fetchall.return_value = [
        ("developer", 0, 100, {"tool_calls": ["read_file"], "tool_call_count": 1}),
    ]

    with patch("src.metrics.trace_store.psycopg2.connect", return_value=mock_conn):
        turns = fetch_turns(run_id, "repo__x-1")

    assert turns == [
        TurnRow(agent_role="developer", turn_index=0, duration_ms=100, tool_calls=["read_file"])
    ]


def test_fetch_task_durations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    run_id = uuid.uuid4()
    mock_conn, mock_cursor = _mock_conn_cursor()
    mock_cursor.fetchall.return_value = [(1.5,), (2.5,)]

    with patch("src.metrics.trace_store.psycopg2.connect", return_value=mock_conn):
        durations = fetch_task_durations(run_id)

    assert durations == [1.5, 2.5]
