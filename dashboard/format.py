"""Pure display formatting for the dashboard: no I/O, no metric recomputation."""

from __future__ import annotations

import decimal

import pandas as pd

SOLVER_ORDER: tuple[str, ...] = ("single", "multi", "noop")

_COLUMN_LABELS: dict[str, str] = {
    "solver": "Solver",
    "run_id": "Run ID",
    "total_tasks": "Total tasks",
    "pass_rate_pct": "Success rate (%)",
    "mean_cost_per_solved_task": "Mean cost / solved ($)",
    "p50_duration_seconds": "p50 latency (s)",
    "p99_duration_seconds": "p99 latency (s)",
    "hallucination_rate": "Hallucination rate (0-1)",
    "avg_iterations": "Mean iterations",
    "run_finished_at": "Run finished at",
}


def order_solvers(frame: pd.DataFrame) -> pd.DataFrame:
    """Sort rows by `SOLVER_ORDER`; unknown solvers sort alphabetically after the known ones."""
    if frame.empty:
        return frame

    def _rank(solver: str) -> tuple[int, str]:
        try:
            return (SOLVER_ORDER.index(solver), "")
        except ValueError:
            return (len(SOLVER_ORDER), solver)

    order = frame["solver"].map(_rank)
    return frame.iloc[order.argsort(kind="stable")].reset_index(drop=True)


def to_display_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Render a headline frame for display: human labels, `Decimal` -> `float`, short run IDs."""
    display = frame.copy()

    for column in display.columns:
        display[column] = display[column].map(
            lambda value: float(value) if isinstance(value, decimal.Decimal) else value
        )

    if "run_id" in display.columns:
        display["run_id"] = display["run_id"].map(
            lambda value: str(value)[:8] if pd.notna(value) else value
        )

    return display.rename(columns=_COLUMN_LABELS)
