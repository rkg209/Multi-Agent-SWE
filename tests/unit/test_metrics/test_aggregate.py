"""Unit tests for `src.metrics.aggregate`."""

from __future__ import annotations

import pytest

from src.metrics.aggregate import count_iterations, percentile
from src.metrics.trace_store import TurnRow


def test_percentile_known_distribution() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 0.5) == pytest.approx(30.0)
    assert percentile(values, 0.0) == pytest.approx(10.0)
    assert percentile(values, 1.0) == pytest.approx(50.0)


def test_percentile_n_equals_one() -> None:
    assert percentile([42.0], 0.5) == 42.0
    assert percentile([42.0], 0.99) == 42.0


def test_percentile_n_equals_zero() -> None:
    assert percentile([], 0.5) == 0.0


def _turn(role: str, index: int) -> TurnRow:
    return TurnRow(agent_role=role, turn_index=index, duration_ms=100, tool_calls=[])


def test_count_iterations_single_agent_self_loop() -> None:
    turns = [_turn("developer", 0), _turn("developer", 1), _turn("developer", 2)]
    assert count_iterations(turns) == 3


def test_count_iterations_developer_tester_alternation() -> None:
    turns = [
        _turn("developer", 0),
        _turn("tester", 1),
        _turn("developer", 2),
        _turn("tester", 3),
    ]
    assert count_iterations(turns) == 2
