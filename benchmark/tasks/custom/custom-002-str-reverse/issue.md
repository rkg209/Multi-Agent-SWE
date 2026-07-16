# strutils.py's `reverse_words` reverses characters instead of word order

`benchmark/tasks/custom/custom-002-str-reverse/base/strutils.py` has a `reverse_words` function that is
supposed to reverse the *order of the words* in a sentence, not the characters within it.

## Expected behavior

```python
>>> from strutils import reverse_words
>>> reverse_words("the quick brown fox")
'fox brown quick the'
```

Currently it returns `'xof nworb kciuq eht'` (character-reversed), which is wrong.
