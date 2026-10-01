"""Unit tests for src/agents/tester.py — router and ToolBelt are mocked, no LLM/Docker."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents import tester
from src.graph.state import GraphState
from src.router.router import LLMResponse
from src.sandbox.docker_sandbox import SandboxResult
from src.tools.toolbelt import ToolBelt


@pytest.fixture(autouse=True)
def _no_real_trace_writes() -> Iterator[None]:
    """`tester_node` records an `agent_turn` trace row; keep these tests DB-free."""
    with patch("src.metrics.turn_tracer.record_agent_turn"):
        yield


def _fake_response() -> LLMResponse:
    return LLMResponse(
        content="Looks correct.",
        model="llama-3.1-8b-instant",
        provider="groq",
        prompt_tokens=5,
        completion_tokens=2,
        cost_usd=0.0001,
    )


def _state(tmp_path: Path, run_id: uuid.UUID) -> GraphState:
    return {
        "run_id": str(run_id),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "patch": "diff --git a/calculator.py ...",
        "test_iteration": 0,
        "cost_usd": 0.0,
        "total_tokens": 0,
    }


def test_tester_node_records_pass_and_best_patch(tmp_path: Path) -> None:
    run_id = uuid.uuid4()
    state = _state(tmp_path, run_id)
    with patch.object(tester, "complete", return_value=_fake_response()) as mock_complete:
        with patch.object(
            ToolBelt,
            "exec",
            return_value=SandboxResult(stdout="1 passed\n", stderr="", exit_code=0),
        ):
            with patch.object(ToolBelt, "diff", return_value="diff --git a/calculator.py ..."):
                new_state = tester.tester_node(state)

    request = mock_complete.call_args.args[0]
    assert request.role == "tester"
    assert request.run_id == run_id
    assert new_state["test_passed"] is True
    assert new_state["test_iteration"] == 1
    assert new_state["best_patch"] == "diff --git a/calculator.py ..."


def test_tester_node_records_fail_without_best_patch(tmp_path: Path) -> None:
    run_id = uuid.uuid4()
    state = _state(tmp_path, run_id)
    with patch.object(tester, "complete", return_value=_fake_response()):
        with patch.object(
            ToolBelt,
            "exec",
            return_value=SandboxResult(stdout="", stderr="1 failed\n", exit_code=1),
        ):
            with patch.object(ToolBelt, "diff", return_value="diff --git a/calculator.py ..."):
                new_state = tester.tester_node(state)

    assert new_state["test_passed"] is False
    assert new_state["test_iteration"] == 1
    assert "best_patch" not in new_state


def test_tester_skips_execution_and_passes_through_when_run_tests_false(tmp_path: Path) -> None:
    state = _state(tmp_path, uuid.uuid4())
    state["run_tests"] = False
    with patch.object(tester, "complete", return_value=_fake_response()):
        with patch.object(ToolBelt, "exec") as mock_exec:
            with patch.object(ToolBelt, "diff", return_value="diff --git a/x.py ..."):
                new_state = tester.tester_node(state)

    mock_exec.assert_not_called()
    assert new_state["test_passed"] is True
    assert "not executed" in new_state["test_stdout"]
    assert new_state["best_patch"] == state["patch"]


def test_tester_without_runnable_tests_fails_on_empty_diff(tmp_path: Path) -> None:
    state = _state(tmp_path, uuid.uuid4())
    state["run_tests"] = False
    with patch.object(tester, "complete", return_value=_fake_response()):
        with patch.object(ToolBelt, "diff", return_value=""):
            new_state = tester.tester_node(state)

    assert new_state["test_passed"] is False
    assert "no change" in new_state["test_stdout"]
