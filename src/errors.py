"""Shared exception types used across packages.

Kept as a standalone top-level module (not nested inside `src/router/`) so
that `src/metrics/trace_store.py` can raise `RouterError` without importing
anything from `src/router/` — nesting it there previously caused an import
cycle (`src.router.__init__` -> `router.py` -> `metrics.trace_store` ->
`src.router.errors`) that broke whenever `src.metrics.trace_store` was
imported before `src.router` had been loaded.
"""

from __future__ import annotations


class RouterError(Exception):
    """Raised for any router failure: config errors, LLM call failures, or trace-write failures."""
