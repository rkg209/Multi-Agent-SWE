"""Unit tests for `benchmark.cli` per-task error handling."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from benchmark import cli
from benchmark.loader import Task
from benchmark.scorer import ScoreResult
from benchmark.solver import Patch, SolveStats
from src.errors import RouterError


def test_router_error_on_one_task_is_recorded_and_run_continues() -> None:
    tasks = [
        Task(id="a", source="custom", issue_text=""),
        Task(id="b", source="custom", issue_text=""),
    ]
    solver = MagicMock()
    solver.solve.side_effect = [RouterError("context too long"), Patch(diff="d")]
    solver.stats.return_value = SolveStats(total_tokens=5)

    with (
        mock_patch.object(cli, "load_tasks", return_value=tasks),
        mock_patch.dict(cli.SOLVERS, {"fake": lambda run_id: solver}),
        mock_patch.object(cli, "score", return_value=ScoreResult(outcome="FAIL")),
        mock_patch.object(cli, "write_run_record") as write,
    ):
        code = cli.run(["--tasks", "x", "--solver", "fake"])

    assert code == 0
    recorded = {c.kwargs["task_id"]: c.kwargs for c in write.call_args_list}
    assert recorded["a"]["total_tokens"] == 0 and recorded["a"]["patch_size_bytes"] == 0
    assert recorded["b"]["total_tokens"] == 5  # stats are not stale from the failed task
