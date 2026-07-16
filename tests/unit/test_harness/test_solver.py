"""Unit tests for `benchmark.solver`."""

from __future__ import annotations

from benchmark.loader import Task
from benchmark.solver import NoopSolver


def test_noop_solver_returns_empty_patch() -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    patch = NoopSolver().solve(task)
    assert patch.diff == ""
