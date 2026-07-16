"""The pluggable solver interface. Only `NoopSolver` exists in this spec.

Specs 04/06 add `single`/`multi` solvers at this same `Solver.solve(task) -> Patch` seam — the
harness loop, scorer, and results writer never branch on solver internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from benchmark.loader import Task


@dataclass(frozen=True)
class Patch:
    """A unified diff produced by a solver. An empty `diff` means no change."""

    diff: str


class Solver(Protocol):
    """A solver turns a `Task` into a `Patch`."""

    def solve(self, task: Task) -> Patch:
        """Produce a patch for `task`."""
        ...


class NoopSolver:
    """Always returns an empty patch — proves the harness end-to-end before a real solver exists."""

    def solve(self, task: Task) -> Patch:
        """Return an empty patch, ignoring `task`."""
        return Patch(diff="")
