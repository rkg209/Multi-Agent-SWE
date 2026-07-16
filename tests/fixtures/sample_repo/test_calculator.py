"""Trivial passing test for the sample_repo fixture."""

from __future__ import annotations

from calculator import add


def test_add() -> None:
    assert add(2, 3) == 5
