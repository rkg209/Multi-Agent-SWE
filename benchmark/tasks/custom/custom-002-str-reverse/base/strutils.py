"""A tiny string-utility module used as a fixture for the custom-ticket scorer."""


def reverse_words(sentence: str) -> str:
    """Buggy: reverses the characters of `sentence` instead of the word order."""
    return sentence[::-1]
