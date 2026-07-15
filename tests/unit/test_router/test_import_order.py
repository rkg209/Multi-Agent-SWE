"""Regression test: `src.metrics.trace_store` must import cleanly on its own.

A prior version defined `RouterError` inside `src/router/errors.py`, which
made importing `src.metrics.trace_store` *before* `src.router` had been
loaded raise an `ImportError` from a partially-initialized module. Run in a
subprocess so the import order isn't already primed by other test modules.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def test_metrics_trace_store_imports_without_router_preloaded() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-c", "import src.metrics.trace_store"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
