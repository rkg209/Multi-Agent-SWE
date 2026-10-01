"""Visible test for custom-001-calc-add: weaker than `hidden_test.py`, shown to the agents."""

from calculator import add


def test_add_basic() -> None:
    assert add(1, 1) == 2
