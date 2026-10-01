"""Visible test for custom-002-str-reverse: weaker than `hidden_test.py`, shown to the agents."""

from strutils import reverse_words


def test_reverse_two_words() -> None:
    assert reverse_words("a b") == "b a"
