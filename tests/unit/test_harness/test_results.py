"""Unit tests for `benchmark.results` — Postgres is mocked, never a real connection."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from benchmark.errors import HarnessError
from benchmark.results import write_run_record


def test_write_run_record_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(HarnessError, match="DATABASE_URL is not set"):
        write_run_record(
            run_id=uuid.uuid4(),
            task_id="repo__x-1",
            solver_name="noop",
            outcome="FAIL",
            duration_seconds=0.1,
        )


def test_write_run_record_inserts_expected_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    run_id = uuid.uuid4()

    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    with patch("benchmark.results.psycopg2.connect", return_value=mock_conn) as mock_connect:
        write_run_record(
            run_id=run_id,
            task_id="repo__x-1",
            solver_name="noop",
            outcome="FAIL",
            duration_seconds=0.25,
            patch_size_bytes=0,
        )

    mock_connect.assert_called_once_with("postgresql://fake", connect_timeout=5)
    mock_cursor.execute.assert_called_once()
    sql, params = mock_cursor.execute.call_args.args
    assert "INSERT INTO benchmark.run_records" in sql
    assert "ON CONFLICT (run_id, task_id) DO NOTHING" in sql
    assert params["run_id"] == str(run_id)
    assert params["task_id"] == "repo__x-1"
    assert params["outcome"] == "FAIL"
    assert params["duration_seconds"] == 0.25
    assert params["patch_size_bytes"] == 0
    mock_conn.close.assert_called_once()


def test_write_run_record_connection_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    with patch("benchmark.results.psycopg2.connect", side_effect=psycopg2.Error("boom")):
        with pytest.raises(HarnessError, match="Could not connect to Postgres"):
            write_run_record(
                run_id=uuid.uuid4(),
                task_id="repo__x-1",
                solver_name="noop",
                outcome="FAIL",
                duration_seconds=0.1,
            )


def test_write_run_record_insert_failure_raises_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")

    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.execute.side_effect = psycopg2.Error("insert failed")
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    with patch("benchmark.results.psycopg2.connect", return_value=mock_conn):
        with pytest.raises(HarnessError, match="Failed to write run_records row"):
            write_run_record(
                run_id=uuid.uuid4(),
                task_id="repo__x-1",
                solver_name="noop",
                outcome="FAIL",
                duration_seconds=0.1,
            )

    mock_conn.close.assert_called_once()
