"""Unit tests for src/agents/reviewer.py — router and ToolBelt are mocked, no LLM/Docker."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents import reviewer
from src.graph.state import GraphState
from src.router.router import LLMResponse
from src.tools.toolbelt import ToolBelt


@pytest.fixture(autouse=True)
def _no_real_trace_writes() -> Iterator[None]:
    """`reviewer_node` records an `agent_turn` trace row; keep these tests DB-free."""
    with patch("src.metrics.turn_tracer.record_agent_turn"):
        yield


def test_parse_review_approved() -> None:
    review = reviewer.parse_review("APPROVED\n")
    assert review.approved is True
    assert review.issues == ""


def test_parse_review_changes_requested() -> None:
    review = reviewer.parse_review("CHANGES\n- missing type hints\n- no docstring\n")
    assert review.approved is False
    assert "missing type hints" in review.issues


def _state(tmp_path: Path, run_id: uuid.UUID) -> GraphState:
    return {
        "run_id": str(run_id),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "review_iteration": 0,
        "cost_usd": 0.0,
        "total_tokens": 0,
    }


def test_reviewer_node_calls_router_with_role_and_writes_verdict(tmp_path: Path) -> None:
    run_id = uuid.uuid4()
    state = _state(tmp_path, run_id)
    fake_response = LLMResponse(
        content="APPROVED\n",
        model="qwen-2.5-72b-instruct",
        provider="openrouter",
        prompt_tokens=8,
        completion_tokens=1,
        cost_usd=0.0005,
    )
    with patch.object(reviewer, "complete", return_value=fake_response) as mock_complete:
        with patch.object(ToolBelt, "diff", return_value="diff --git a/calculator.py ..."):
            new_state = reviewer.reviewer_node(state)

    request = mock_complete.call_args.args[0]
    assert request.role == "reviewer"
    assert request.run_id == run_id
    assert new_state["review_approved"] is True
    assert new_state["review_issues"] == ""
    assert new_state["review_iteration"] == 1
