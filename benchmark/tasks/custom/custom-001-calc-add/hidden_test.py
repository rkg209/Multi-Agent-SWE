"""Hidden test for custom-001-calc-add. Not part of `base/` — copied in only at score time."""

from calculator import add


def test_add() -> None:
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
