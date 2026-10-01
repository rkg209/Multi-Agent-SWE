"""Unit tests for `benchmark.solver`."""

from __future__ import annotations

import uuid
from unittest.mock import patch as mock_patch

from benchmark.loader import Task
from benchmark.solver import MultiAgentSolver, NoopSolver, SingleAgentSolver, SolveStats


def test_noop_solver_returns_empty_patch() -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    patch = NoopSolver().solve(task)
    assert patch.diff == ""


def test_noop_solver_stats_are_zero() -> None:
    assert NoopSolver().stats() == SolveStats()


def _hydrated_swebench_task(tmp_path: object) -> Task:
    base_dir = tmp_path / "checkout"  # type: ignore[operator]
    base_dir.mkdir()
    (base_dir / "mod.py").write_text("x = 1\n")
    return Task(
        id="repo__x-1",
        source="swebench",
        issue_text="real problem statement",
        base_dir=base_dir,
        repo="o/r",
        base_commit="abc1234",
    )


def test_single_agent_solver_hydrates_swebench_task_and_runs_graph(tmp_path: object) -> None:
    hydrated = _hydrated_swebench_task(tmp_path)
    bare = Task(id="repo__x-1", source="swebench", issue_text="")
    solver = SingleAgentSolver(run_id=uuid.uuid4())

    with (
        mock_patch("benchmark.solver.hydrate_task", return_value=hydrated) as hydrate,
        mock_patch("benchmark.solver.build_graph") as mock_build_graph,
    ):
        mock_build_graph.return_value.invoke.return_value = {"patch": "diff", "total_tokens": 7}
        patch = solver.solve(bare)

    hydrate.assert_called_once_with(bare)
    state = mock_build_graph.return_value.invoke.call_args.args[0]
    assert state["issue_text"] == "real problem statement"
    assert state["run_tests"] is False
    assert state["max_iterations"] == 1
    assert patch.diff == "diff"
    assert solver.stats().total_tokens == 7


def test_single_agent_solver_unresolvable_task_returns_empty_patch() -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    solver = SingleAgentSolver(run_id=uuid.uuid4())
    with mock_patch("benchmark.solver.hydrate_task", return_value=task):
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


def test_multi_agent_solver_hydrates_swebench_task_and_runs_graph(tmp_path: object) -> None:
    hydrated = _hydrated_swebench_task(tmp_path)
    bare = Task(id="repo__x-1", source="swebench", issue_text="")
    solver = MultiAgentSolver(run_id=uuid.uuid4())

    with (
        mock_patch("benchmark.solver.hydrate_task", return_value=hydrated),
        mock_patch("benchmark.solver.build_graph") as mock_build_graph,
        mock_patch("benchmark.solver.CHECKPOINT_DIR", tmp_path),
    ):
        mock_build_graph.return_value.invoke.return_value = {"patch": "diff", "total_tokens": 9}
        patch = solver.solve(bare)

    state = mock_build_graph.return_value.invoke.call_args.args[0]
    assert state["issue_text"] == "real problem statement"
    assert patch.diff == "diff"


def test_multi_agent_solver_uses_best_patch_and_reports_no_cap_hit(tmp_path: object) -> None:
    base_dir = tmp_path / "base"  # type: ignore[operator]
    base_dir.mkdir()
    (base_dir / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    task = Task(id="custom-999", source="custom", issue_text="add is missing", base_dir=base_dir)
    solver = MultiAgentSolver(run_id=uuid.uuid4())

    fake_final_state = {
        "patch": "diff --git a/calculator.py b/calculator.py (latest)",
        "best_patch": "diff --git a/calculator.py b/calculator.py (best)",
        "cost_usd": 0.01,
        "total_tokens": 100,
        "iteration": 0,
        "test_iteration": 1,
        "review_iteration": 1,
        "max_test_iterations": 3,
        "max_review_iterations": 2,
        "test_passed": True,
        "review_approved": True,
    }
    with mock_patch("benchmark.solver.build_graph") as mock_build_graph:
        mock_build_graph.return_value.invoke.return_value = fake_final_state
        patch = solver.solve(task)

    assert patch.diff == "diff --git a/calculator.py b/calculator.py (best)"
    stats = solver.stats()
    assert stats.total_tokens == 100
    assert stats.cap_hit is False


def test_multi_agent_solver_scopes_thread_id_per_task_to_avoid_state_leakage(
    tmp_path: object,
) -> None:
    base_dir = tmp_path / "base"  # type: ignore[operator]
    base_dir.mkdir()
    (base_dir / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    run_id = uuid.uuid4()
    solver = MultiAgentSolver(run_id=run_id)

    fake_final_state = {"patch": "diff", "cost_usd": 0.0, "total_tokens": 1, "iteration": 0}
    seen_thread_ids: list[str] = []

    def _record_invoke(_state: object, config: dict) -> dict:
        seen_thread_ids.append(config["configurable"]["thread_id"])
        return fake_final_state

    with mock_patch("benchmark.solver.build_graph") as mock_build_graph:
        mock_build_graph.return_value.invoke.side_effect = _record_invoke
        solver.solve(Task(id="custom-a", source="custom", issue_text="", base_dir=base_dir))
        solver.solve(Task(id="custom-b", source="custom", issue_text="", base_dir=base_dir))

    assert len(seen_thread_ids) == 2
    assert seen_thread_ids[0] != seen_thread_ids[1]
    assert all(str(run_id) in tid for tid in seen_thread_ids)
    assert "custom-a" in seen_thread_ids[0]
    assert "custom-b" in seen_thread_ids[1]


def test_multi_agent_solver_derives_cap_hit_on_test_cap(tmp_path: object) -> None:
    base_dir = tmp_path / "base"  # type: ignore[operator]
    base_dir.mkdir()
    (base_dir / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    task = Task(id="custom-999", source="custom", issue_text="add is missing", base_dir=base_dir)
    solver = MultiAgentSolver(run_id=uuid.uuid4())

    fake_final_state = {
        "patch": "diff --git a/calculator.py b/calculator.py",
        "cost_usd": 0.01,
        "total_tokens": 100,
        "iteration": 0,
        "test_iteration": 3,
        "review_iteration": 0,
        "max_test_iterations": 3,
        "max_review_iterations": 2,
        "test_passed": False,
        "review_approved": False,
    }
    with mock_patch("benchmark.solver.build_graph") as mock_build_graph:
        mock_build_graph.return_value.invoke.return_value = fake_final_state
        solver.solve(task)

    assert solver.stats().cap_hit is True
