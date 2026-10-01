"""`make benchmark` entry point: loads a task subset, runs a solver, scores, records, summarises.

`TASKS`/`SOLVER` come from the environment (set by the Makefile, mirroring the existing `CMD=`/
`SCRIPT=` pattern) with CLI flags as the direct equivalent for ad-hoc invocation.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from benchmark.errors import HarnessError
from benchmark.loader import load_tasks
from benchmark.results import write_run_record
from benchmark.scorer import score
from benchmark.solver import (
    MultiAgentSolver,
    NoopSolver,
    Patch,
    SingleAgentSolver,
    Solver,
    SolveStats,
)
from src.errors import RouterError
from src.metrics.aggregate import percentile

logger = logging.getLogger(__name__)

SOLVERS: dict[str, Callable[..., Solver]] = {
    "noop": NoopSolver,
    "single": SingleAgentSolver,
    "multi": MultiAgentSolver,
}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SWE-bench benchmark harness.")
    parser.add_argument("--tasks", default=os.environ.get("TASKS", "lite-5"))
    parser.add_argument("--solver", default=os.environ.get("SOLVER", "noop"))
    parser.add_argument(
        "--override",
        action="store_true",
        default=os.environ.get("OVERRIDE", "").lower() in {"1", "true", "yes"},
        help="Bypass the 50-swebench + 5-custom task cap (C-2).",
    )
    return parser.parse_args(argv)


def _print_summary(rows: list[tuple[str, str, float]]) -> None:
    """Print a `task_id | outcome | duration` summary table to stdout."""
    header = f"{'task_id':<40} {'outcome':<8} {'duration_s':>10}"
    print(header)
    print("-" * len(header))
    for task_id, outcome, duration in rows:
        print(f"{task_id:<40} {outcome:<8} {duration:>10.3f}")
    passed = sum(1 for _, outcome, _ in rows if outcome == "PASS")
    print("-" * len(header))
    print(f"{passed}/{len(rows)} passed")


def run(argv: list[str] | None = None) -> int:
    """Run the benchmark harness end-to-end; return a process exit code."""
    args = _parse_args(argv)

    solver_cls = SOLVERS.get(args.solver)
    if solver_cls is None:
        print(f"Unknown solver {args.solver!r}; known solvers: {sorted(SOLVERS)}", file=sys.stderr)
        return 1

    try:
        tasks = load_tasks(args.tasks, override=args.override)
    except HarnessError as exc:
        print(f"Failed to load task subset {args.tasks!r}: {exc}", file=sys.stderr)
        return 1

    run_id = uuid.uuid4()
    solver = solver_cls(run_id=run_id)
    sbcli_output_dir = Path("reports") / "sbcli" / str(run_id)
    rows: list[tuple[str, str, float]] = []

    print(f"Benchmark run {run_id} — {len(tasks)} tasks, solver={args.solver!r}")

    for task in tasks:
        start = time.monotonic()
        try:
            patch = solver.solve(task)
            stats = solver.stats()
        except RouterError as exc:
            # A model call failed (e.g. context overflow); record this task as an empty-patch
            # FAIL and keep going rather than losing the rest of the run.
            logger.error("Solver failed on %s: %s", task.id, exc)
            patch, stats = Patch(diff=""), SolveStats()
        result = score(task, patch, run_id=str(run_id), sbcli_output_dir=sbcli_output_dir)
        duration = time.monotonic() - start

        write_run_record(
            run_id=run_id,
            task_id=task.id,
            solver_name=args.solver,
            outcome=result.outcome,
            duration_seconds=duration,
            patch_size_bytes=len(patch.diff.encode("utf-8")),
            total_cost_usd=stats.cost_usd,
            total_tokens=stats.total_tokens,
            iteration_count=stats.iterations,
            hallucination_score=stats.hallucination_score,
            cap_hit=stats.cap_hit,
            budget_exceeded=stats.budget_exceeded,
        )
        rows.append((task.id, result.outcome, duration))
        if result.reason:
            logger.info("%s -> %s (%s)", task.id, result.outcome, result.reason)

    _print_summary(rows)
    durations = [duration for _, _, duration in rows]
    p50 = percentile(durations, 0.5)
    p99 = percentile(durations, 0.99)
    print(f"p50_duration_s={p50:.3f} p99_duration_s={p99:.3f}")
    return 0


def main() -> None:
    """CLI entry point: `python -m benchmark.cli`."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run())


if __name__ == "__main__":
    main()
