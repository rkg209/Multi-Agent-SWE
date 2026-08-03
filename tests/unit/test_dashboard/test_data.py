"""Unit tests for `dashboard.data` — Postgres is mocked, never a real connection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from dashboard.data import (
    HEADLINE_COLUMNS,
    DashboardError,
    _query,
    fetch_latest_headline,
    fetch_latest_totals,
)


def _mock_conn(columns: list[str], rows: list[tuple[object, ...]]) -> MagicMock:
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.description = [(name,) for name in columns]
    mock_cursor.fetchall.return_value = rows

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


def test_query_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(DashboardError, match="DATABASE_URL is not set"):
        _query("SELECT 1")


def test_query_builds_frame_from_cursor_description(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    mock_conn = _mock_conn(["solver", "total_tasks"], [("single", 5)])

    with patch("dashboard.data.psycopg2.connect", return_value=mock_conn):
        frame = _query("SELECT solver, total_tasks FROM benchmark.run_summary")

    assert list(frame.columns) == ["solver", "total_tasks"]
    assert frame.iloc[0]["solver"] == "single"
    mock_conn.close.assert_called_once()


def test_query_empty_result_keeps_column_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    mock_conn = _mock_conn(list(HEADLINE_COLUMNS), [])

    with patch("dashboard.data.psycopg2.connect", return_value=mock_conn):
        frame = _query("SELECT * FROM benchmark.headline_metrics")

    assert list(frame.columns) == list(HEADLINE_COLUMNS)
    assert frame.empty


def test_query_connection_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    with patch("dashboard.data.psycopg2.connect", side_effect=psycopg2.Error("boom")):
        with pytest.raises(DashboardError, match="Could not connect to Postgres"):
            _query("SELECT 1")


def test_fetch_latest_headline_issues_distinct_on_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    mock_conn = _mock_conn(list(HEADLINE_COLUMNS), [])

    with patch("dashboard.data.psycopg2.connect", return_value=mock_conn) as mock_connect:
        fetch_latest_headline()

    mock_connect.assert_called_once()
    executed_sql = mock_conn.cursor.return_value.execute.call_args.args[0]
    assert "DISTINCT ON (h.solver)" in executed_sql
    assert "benchmark.headline_metrics" in executed_sql


def test_fetch_latest_totals_issues_distinct_on_run_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake")
    mock_conn = _mock_conn(
        ["solver", "run_id", "total_cost_usd", "total_tokens", "run_finished_at"], []
    )

    with patch("dashboard.data.psycopg2.connect", return_value=mock_conn) as mock_connect:
        fetch_latest_totals()

    mock_connect.assert_called_once()
    executed_sql = mock_conn.cursor.return_value.execute.call_args.args[0]
    assert "DISTINCT ON (solver)" in executed_sql
    assert "benchmark.run_summary" in executed_sql
