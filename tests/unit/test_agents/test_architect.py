"""Unit tests for src/agents/architect.py — router and ToolBelt exec are mocked, no LLM/Docker."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents import architect
from src.graph.state import GraphState
from src.router.router import LLMResponse


@pytest.fixture(autouse=True)
def _no_real_trace_writes() -> Iterator[None]:
    """`architect_node` records an `agent_turn` trace row; keep these tests DB-free."""
    with patch("src.metrics.turn_tracer.record_agent_turn"):
        yield


def test_parse_plan_well_formed() -> None:
    content = (
        "FILES: calculator.py, utils.py\n"
        "APPROACH:\n"
        "Add the missing add function.\n"
        "CONSTRAINTS:\n"
        "Keep the public API stable.\n"
    )
    plan = architect.parse_plan(content)
    assert plan.files == ("calculator.py", "utils.py")
    assert plan.approach == "Add the missing add function."
    assert plan.constraints == "Keep the public API stable."


def test_parse_plan_missing_sections_degrades_to_empty() -> None:
    plan = architect.parse_plan("Sure, I'll fix it.")
    assert plan.files == ()
    assert plan.approach == ""
    assert plan.constraints == ""


def test_architect_node_calls_router_with_role_and_writes_plan(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    run_id = uuid.uuid4()
    state: GraphState = {
        "run_id": str(run_id),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "iteration": 0,
        "cost_usd": 0.0,
        "total_tokens": 0,
    }
    fake_response = LLMResponse(
        content=(
            "FILES: calculator.py\n"
            "APPROACH:\n"
            "Add the add function.\n"
            "CONSTRAINTS:\n"
            "None\n"
        ),
        model="qwen-2.5-72b-instruct",
        provider="openrouter",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
    )
    with patch.object(architect, "complete", return_value=fake_response) as mock_complete:
        new_state = architect.architect_node(state)

    request = mock_complete.call_args.args[0]
    assert request.role == "architect"
    assert request.run_id == run_id
    assert new_state["plan_files"] == ["calculator.py"]
    assert new_state["plan"] == "Add the add function."
    assert new_state["plan_constraints"] == "None"
    assert new_state["total_tokens"] == 15
    assert new_state["cost_usd"] == pytest.approx(0.001)
