"""Function-level contracts for node parse/build helpers — never stored as objects in state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    """The Architect's output: files to touch, approach, and constraints for the Developer."""

    files: tuple[str, ...]
    approach: str
    constraints: str


@dataclass(frozen=True)
class TestResult:
    """The Tester's structured PASS/FAIL verdict, from the sandbox suite run."""

    passed: bool
    failures: str


@dataclass(frozen=True)
class Review:
    """The Reviewer's structured verdict on the passing patch."""

    approved: bool
    issues: str
