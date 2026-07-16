"""Hidden test for custom-002-str-reverse. Not part of `base/` — copied in only at score time."""

from strutils import reverse_words


def test_reverse_words() -> None:
    assert reverse_words("the quick brown fox") == "fox brown quick the"
    assert reverse_words("hello") == "hello"
