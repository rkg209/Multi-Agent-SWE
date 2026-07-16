"""Shared exception type for the benchmark harness package."""

from __future__ import annotations


class HarnessError(Exception):
    """Raised for any harness failure: task loading, scoring, or results-writing failures."""
