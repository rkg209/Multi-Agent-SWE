"""Unit tests for src/agents/developer.py — router and ToolBelt exec are mocked, no LLM/Docker."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents import developer
from src.graph.state import GraphState
from src.router.router import LLMResponse
from src.sandbox.docker_sandbox import SandboxResult
from src.tools.toolbelt import ToolBelt


@pytest.fixture(autouse=True)
def _no_real_trace_writes() -> Iterator[None]:
    """`developer_node` now records an `agent_turn` trace row; keep these tests DB-free."""
    with patch("src.metrics.turn_tracer.record_agent_turn"):
        yield


def test_parse_file_blocks_well_formed() -> None:
    content = (
        "```path=a.py\n" "def f():\n" "    return 1\n" "```\n" "```path=sub/b.py\n" "x = 2\n" "```"
    )
    blocks = developer.parse_file_blocks(content)
    assert blocks == {"a.py": "def f():\n    return 1", "sub/b.py": "x = 2"}


def test_parse_file_blocks_malformed_returns_empty() -> None:
    content = "Sure, here's the fix:\n```python\ndef f(): pass\n```"
    assert developer.parse_file_blocks(content) == {}


def test_parse_file_blocks_empty_reply() -> None:
    assert developer.parse_file_blocks("") == {}


def test_normalize_path_folds_hallucinated_long_path_to_known_basename() -> None:
    known = {"calculator.py"}
    result = developer._normalize_path(
        "benchmark/tasks/custom/custom-001-calc-add/base/calculator.py", known
    )
    assert result == "calculator.py"


def test_normalize_path_leaves_unknown_path_untouched() -> None:
    known = {"calculator.py"}
    assert developer._normalize_path("new_module.py", known) == "new_module.py"


def test_normalize_path_leaves_known_path_as_is() -> None:
    known = {"sub/b.py"}
    assert developer._normalize_path("sub/b.py", known) == "sub/b.py"


def test_developer_node_normalizes_hallucinated_path_before_writing(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    state: GraphState = {
        "run_id": str(uuid.uuid4()),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "iteration": 0,
    }
    hallucinated_path = "benchmark/tasks/custom/custom-001-calc-add/base/calculator.py"
    fake_response = LLMResponse(
        content=f"```path={hallucinated_path}\ndef add(a, b):\n    return a + b\n```",
        model="ollama/llama3.1",
        provider="ollama",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
    )
    with patch.object(developer, "complete", return_value=fake_response):
        with patch.object(
            ToolBelt, "exec", return_value=SandboxResult(stdout="", stderr="", exit_code=0)
        ):
            with patch.object(ToolBelt, "diff", return_value=""):
                developer.developer_node(state)

    assert "def add" in (tmp_path / "calculator.py").read_text()
    assert not (tmp_path / "benchmark").exists()


def test_build_context_skips_hidden_test_and_git(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    (tmp_path / "hidden_test.py").write_text("def test_x(): assert True\n")
    (tmp_path / ".git").mkdir()
    belt = ToolBelt(tmp_path)
    context = developer.build_context(belt, {})
    assert "calculator.py" in context
    assert "hidden_test.py" not in context
    assert ".git" not in context


def test_build_messages_includes_retry_failure_on_later_iteration() -> None:
    state: GraphState = {
        "issue_text": "add is missing",
        "iteration": 1,
        "test_stdout": "AssertionError: boom",
    }
    messages = developer.build_messages("repo context", state)
    user_content = messages[1]["content"]
    assert "add is missing" in user_content
    assert "repo context" in user_content
    assert "AssertionError: boom" in user_content


def test_build_messages_no_retry_text_on_first_iteration() -> None:
    state: GraphState = {"issue_text": "add is missing", "iteration": 0}
    messages = developer.build_messages("repo context", state)
    assert "AssertionError" not in messages[1]["content"]


def test_developer_node_calls_router_with_role_and_turn_index(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    run_id = uuid.uuid4()
    state: GraphState = {
        "run_id": str(run_id),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "iteration": 0,
    }
    fake_response = LLMResponse(
        content="```path=calculator.py\ndef add(a, b):\n    return a + b\n```",
        model="ollama/llama3.1",
        provider="ollama",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.0,
    )
    with patch.object(developer, "complete", return_value=fake_response) as mock_complete:
        with patch.object(
            ToolBelt,
            "exec",
            return_value=SandboxResult(stdout="1 passed\n", stderr="", exit_code=0),
        ) as mock_exec:
            with patch.object(ToolBelt, "diff", return_value="diff --git a/calculator.py ..."):
                new_state = developer.developer_node(state)

    request = mock_complete.call_args.args[0]
    assert request.role == "developer"
    assert request.run_id == run_id
    assert request.task_id == "custom-001-calc-add"
    assert request.turn_index == 0
    mock_exec.assert_called_once()
    assert new_state["test_passed"] is True
    assert new_state["iteration"] == 1
    assert new_state["total_tokens"] == 15
    assert new_state["patch"] == "diff --git a/calculator.py ..."


def test_developer_node_writes_only_through_belt(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    state: GraphState = {
        "run_id": str(uuid.uuid4()),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "iteration": 0,
    }
    fake_response = LLMResponse(
        content="```path=calculator.py\ndef add(a, b):\n    return a + b\n```",
        model="ollama/llama3.1",
        provider="ollama",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=0.0,
    )
    with patch.object(developer, "complete", return_value=fake_response):
        with patch.object(
            ToolBelt, "exec", return_value=SandboxResult(stdout="", stderr="", exit_code=1)
        ):
            with patch.object(ToolBelt, "diff", return_value=""):
                developer.developer_node(state)

    written = (tmp_path / "calculator.py").read_text()
    assert "def add" in written
