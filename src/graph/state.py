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
    apply_feedback: str  # why the Developer's last edits did not apply (real repos)
    run_tests: bool  # False for real repos: sandbox lacks their deps (single mode)
    solver_config: dict[str, object]
    cost_usd: float
    total_tokens: int

    # Spec 06 — multi-agent team (Architect/Tester/Reviewer)
    plan_files: list[str]
    plan_constraints: str
    review_approved: bool
    review_issues: str
    test_iteration: int
    review_iteration: int
    max_test_iterations: int
    max_review_iterations: int
    best_patch: str
    cap_hit: bool

    # Spec 07 — guardrails & cost control
    token_budget: int
    budget_exceeded: bool
