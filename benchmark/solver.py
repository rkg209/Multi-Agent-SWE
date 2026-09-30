"""The pluggable solver interface. `NoopSolver` and `SingleAgentSolver` (Spec 04) live here.

Spec 06 adds a `multi` solver at this same `Solver.solve(task) -> Patch` seam — the harness loop,
scorer, and results writer never branch on solver internals.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from langgraph.checkpoint.sqlite import SqliteSaver

from benchmark.loader import Task
from src.graph.graph import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_REVIEW_ITERATIONS,
    DEFAULT_MAX_TEST_ITERATIONS,
    build_graph,
)
from src.guardrails.budget import is_budget_exceeded, load_budget_config
from src.metrics.hallucination import check_patch
from src.tools.toolbelt import sandbox_task_dir

CHECKPOINT_DIR = Path(".langgraph")

logger = logging.getLogger(__name__)

COMMIT_AUTHOR_NAME = "swe-agent"
COMMIT_AUTHOR_EMAIL = "swe-agent@localhost"


@dataclass(frozen=True)
class Patch:
    """A unified diff produced by a solver. An empty `diff` means no change."""

    diff: str


@dataclass(frozen=True)
class SolveStats:
    """Metrics from a solver's most recent `solve()` call."""

    cost_usd: float = 0.0
    total_tokens: int = 0
    iterations: int = 0
    hallucination_score: float = 0.0
    cap_hit: bool = False
    budget_exceeded: bool = False


class Solver(Protocol):
    """A solver turns a `Task` into a `Patch` and reports metrics for its last solve."""

    def solve(self, task: Task) -> Patch:
        """Produce a patch for `task`."""
        ...

    def stats(self) -> SolveStats:
        """Return metrics for the most recent `solve()` call."""
        ...


class NoopSolver:
    """Always returns an empty patch — proves the harness end-to-end before a real solver exists."""

    def __init__(self, run_id: uuid.UUID | None = None) -> None:
        self._run_id = run_id

    def solve(self, task: Task) -> Patch:
        """Return an empty patch, ignoring `task`."""
        return Patch(diff="")

    def stats(self) -> SolveStats:
        """Return zero-valued stats — `NoopSolver` never calls a model."""
        return SolveStats()


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a git subcommand with a deterministic identity, cwd-scoped to `root`."""
    return subprocess.run(
        [
            "git",
            "-c",
            f"user.name={COMMIT_AUTHOR_NAME}",
            "-c",
            f"user.email={COMMIT_AUTHOR_EMAIL}",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def init_baseline_repo(repo_dir: Path) -> None:
    """`git init` + a baseline commit so `git diff` has a clean starting point.

    Mirrors `benchmark/scorer.py:_init_baseline` — factored here rather than
    copy-pasted a third time.
    """
    _run_git(repo_dir, ["init", "-q"])
    _run_git(repo_dir, ["add", "-A"])
    _run_git(repo_dir, ["commit", "-q", "-m", "baseline"])


class SingleAgentSolver:
    """Runs the degenerate (Developer-only) LangGraph graph against one task."""

    def __init__(self, run_id: uuid.UUID) -> None:
        self._run_id = run_id
        self._stats = SolveStats()

    def solve(self, task: Task) -> Patch:
        """Produce a patch by running the single-agent graph in a fresh workspace copy.

        SWE-bench tasks carry no local repo or issue text (Spec 03 doesn't
        fetch the dataset) — short-circuits to an empty patch, an honest FAIL.
        """
        if task.source != "custom" or task.base_dir is None:
            logger.warning(
                "SingleAgentSolver cannot solve %r (source=%r has no local base_dir); "
                "returning empty patch",
                task.id,
                task.source,
            )
            self._stats = SolveStats()
            return Patch(diff="")

        with tempfile.TemporaryDirectory(prefix=f"solve-{task.id}-") as tmp:
            workspace = Path(tmp)
            shutil.copytree(task.base_dir, workspace, dirs_exist_ok=True)
            init_baseline_repo(workspace)

            initial_state = {
                "run_id": str(self._run_id),
                "task_id": task.id,
                "issue_text": task.issue_text,
                "workspace": str(workspace),
                "iteration": 0,
                "max_iterations": DEFAULT_MAX_ITERATIONS,
                "solver_config": {"mode": "single"},
                "cost_usd": 0.0,
                "total_tokens": 0,
                "token_budget": load_budget_config().token_cap_per_task,
            }

            graph = build_graph({"mode": "single"})
            with sandbox_task_dir(workspace):
                final_state = graph.invoke(initial_state)

            patch_diff = final_state.get("patch", "")
            hallucination_score = check_patch(patch_diff, workspace)

        budget_exceeded = is_budget_exceeded(
            final_state.get("total_tokens", 0), final_state.get("token_budget", 0)
        )
        self._stats = SolveStats(
            cost_usd=final_state.get("cost_usd", 0.0),
            total_tokens=final_state.get("total_tokens", 0),
            iterations=final_state.get("iteration", 0),
            hallucination_score=hallucination_score,
            budget_exceeded=budget_exceeded,
        )
        return Patch(diff=patch_diff)

    def stats(self) -> SolveStats:
        """Return metrics accumulated by the most recent `solve()` call."""
        return self._stats


class MultiAgentSolver:
    """Runs the four-agent (Architect/Developer/Tester/Reviewer) LangGraph team against one task."""

    def __init__(self, run_id: uuid.UUID) -> None:
        self._run_id = run_id
        self._stats = SolveStats()

    def solve(self, task: Task) -> Patch:
        """Produce a patch by running the multi-agent graph in a fresh workspace copy.

        Checkpointed to `.langgraph/<run_id>.sqlite`, keyed by a `thread_id` scoped to both
        the run and the task (`"<run_id>:<task_id>"`) so an interrupted run resumes from the
        last completed node (FR-41) without leaking one task's graph state into another's.
        """
        if task.source != "custom" or task.base_dir is None:
            logger.warning(
                "MultiAgentSolver cannot solve %r (source=%r has no local base_dir); "
                "returning empty patch",
                task.id,
                task.source,
            )
            self._stats = SolveStats()
            return Patch(diff="")

        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint_path = CHECKPOINT_DIR / f"{self._run_id}.sqlite"

        with tempfile.TemporaryDirectory(prefix=f"solve-{task.id}-") as tmp:
            workspace = Path(tmp)
            shutil.copytree(task.base_dir, workspace, dirs_exist_ok=True)
            init_baseline_repo(workspace)

            initial_state = {
                "run_id": str(self._run_id),
                "task_id": task.id,
                "issue_text": task.issue_text,
                "workspace": str(workspace),
                "iteration": 0,
                "test_iteration": 0,
                "review_iteration": 0,
                "max_test_iterations": DEFAULT_MAX_TEST_ITERATIONS,
                "max_review_iterations": DEFAULT_MAX_REVIEW_ITERATIONS,
                "solver_config": {"mode": "multi"},
                "cost_usd": 0.0,
                "total_tokens": 0,
                "token_budget": load_budget_config().token_cap_per_task,
            }

            with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
                graph = build_graph({"mode": "multi"}, checkpointer=saver)
                # thread_id must be scoped per task, not just per run: LangGraph's checkpointer
                # merges each invoke()'s input over the previous checkpoint on the same thread,
                # so a run-wide thread_id would leak one task's state (plan, patch, review_issues,
                # best_patch, ...) into the next task's initial_state on every multi-task run.
                config = {"configurable": {"thread_id": f"{self._run_id}:{task.id}"}}
                with sandbox_task_dir(workspace):
                    final_state = graph.invoke(initial_state, config=config)

            patch_diff = final_state.get("best_patch") or final_state.get("patch", "")
            hallucination_score = check_patch(patch_diff, workspace)

        test_iter = final_state.get("test_iteration", 0)
        review_iter = final_state.get("review_iteration", 0)
        test_passed = final_state.get("test_passed", False)
        review_approved = final_state.get("review_approved", False)
        cap_hit = (not test_passed and test_iter >= final_state.get("max_test_iterations", 0)) or (
            test_passed
            and not review_approved
            and review_iter >= final_state.get("max_review_iterations", 0)
        )
        budget_exceeded = is_budget_exceeded(
            final_state.get("total_tokens", 0), final_state.get("token_budget", 0)
        )

        self._stats = SolveStats(
            cost_usd=final_state.get("cost_usd", 0.0),
            total_tokens=final_state.get("total_tokens", 0),
            iterations=final_state.get("iteration", 0),
            hallucination_score=hallucination_score,
            cap_hit=cap_hit,
            budget_exceeded=budget_exceeded,
        )
        return Patch(diff=patch_diff)

    def stats(self) -> SolveStats:
        """Return metrics accumulated by the most recent `solve()` call."""
        return self._stats
