"""Shared LangGraph state, flat and JSON-serialisable across all agent nodes."""

from __future__ import annotations

from typing import TypedDict


class GraphState(TypedDict, total=False):
    """State threaded through the graph. Spec 06 adds fields; never restructure."""

    run_id: str
    task_id: str
    issue_text: str
    workspace: str
    plan: str
    patch: str
    test_stdout: str
    test_passed: bool
    iteration: int
    max_iterations: int
    solver_config: dict[str, object]
    cost_usd: float
    total_tokens: int
