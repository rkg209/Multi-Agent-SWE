# calculator.py is missing an `add` function

`benchmark/tasks/custom/custom-001-calc-add/base/calculator.py` defines `subtract` and `multiply` but no
`add`. Callers expect `add(a, b)` to return `a + b`.

## Expected behavior

```python
>>> from calculator import add
>>> add(2, 3)
5
```

Currently `calculator.py` has no `add` symbol at all, so any import of it raises `ImportError`.
