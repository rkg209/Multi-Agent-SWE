"""Iteration counting and percentile math, computed in Python so unit tests don't need Postgres."""

from __future__ import annotations

import math

from src.metrics.trace_store import TurnRow


def count_iterations(turns: list[TurnRow]) -> int:
    """Count Developer<->Tester cycles from a run's ordered `agent_turn` rows (FR-31).

    A cycle is one `developer` turn (optionally followed by a `tester` turn).
    In single-agent mode (only `developer` rows present) this equals the
    number of developer turns, so Spec 06's multi-agent mode needs no change
    to this function — it counts roles, not modes.
    """
    return sum(1 for turn in turns if turn.agent_role == "developer")


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile matching Postgres `PERCENTILE_CONT`.

    `q` is in `[0, 1]`. `N==0` returns `0.0`; `N==1` returns that single value.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return ordered[0]

    rank = q * (n - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
