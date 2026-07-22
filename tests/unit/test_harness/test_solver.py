"""Unit tests for `benchmark.solver`."""

from __future__ import annotations

import uuid
from unittest.mock import patch as mock_patch

from benchmark.loader import Task
from benchmark.solver import NoopSolver, SingleAgentSolver, SolveStats


def test_noop_solver_returns_empty_patch() -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    patch = NoopSolver().solve(task)
    assert patch.diff == ""


def test_noop_solver_stats_are_zero() -> None:
    assert NoopSolver().stats() == SolveStats()


def test_single_agent_solver_swebench_task_returns_empty_patch_and_zero_stats() -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    solver = SingleAgentSolver(run_id=uuid.uuid4())
    patch = solver.solve(task)
    assert patch.diff == ""
    assert solver.stats() == SolveStats()


def test_single_agent_solver_stats_reflect_graph_output(tmp_path: object) -> None:
    base_dir = tmp_path / "base"  # type: ignore[operator]
    base_dir.mkdir()
    (base_dir / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    task = Task(id="custom-999", source="custom", issue_text="add is missing", base_dir=base_dir)
    solver = SingleAgentSolver(run_id=uuid.uuid4())

    fake_final_state = {
        "patch": "diff --git a/calculator.py b/calculator.py",
        "cost_usd": 0.0,
        "total_tokens": 42,
        "iteration": 1,
    }
    with mock_patch("benchmark.solver.build_graph") as mock_build_graph:
        mock_build_graph.return_value.invoke.return_value = fake_final_state
        patch = solver.solve(task)

    assert patch.diff == "diff --git a/calculator.py b/calculator.py"
    stats = solver.stats()
    assert stats.total_tokens == 42
    assert stats.iterations == 1
