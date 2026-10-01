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


def test_build_messages_includes_plan_and_review_issues() -> None:
    state: GraphState = {
        "issue_text": "add is missing",
        "iteration": 0,
        "plan": "Add the add function.",
        "plan_constraints": "Keep API stable.",
        "review_issues": "Missing type hints.",
    }
    messages = developer.build_messages("repo context", state)
    user_content = messages[1]["content"]
    assert "Add the add function." in user_content
    assert "Keep API stable." in user_content
    assert "Missing type hints." in user_content


def test_developer_node_multi_mode_skips_self_test(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def subtract(a, b): return a - b\n")
    state: GraphState = {
        "run_id": str(uuid.uuid4()),
        "task_id": "custom-001-calc-add",
        "issue_text": "add is missing",
        "workspace": str(tmp_path),
        "iteration": 0,
        "solver_config": {"mode": "multi"},
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
        with patch.object(ToolBelt, "exec") as mock_exec:
            with patch.object(ToolBelt, "diff", return_value="diff --git a/calculator.py ..."):
                new_state = developer.developer_node(state)

    mock_exec.assert_not_called()
    assert "test_passed" not in new_state
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


def test_parse_and_apply_search_replace_edits() -> None:
    from src.agents.developer import apply_edits, parse_edit_blocks

    body = (
        "<<<<<<< SEARCH\n    return a - b\n=======\n    return a + b\n>>>>>>> REPLACE\n"
        "<<<<<<< SEARCH\nx = 1\n=======\n>>>>>>> REPLACE"
    )
    edits = parse_edit_blocks(body)
    assert edits == [("    return a - b", "    return a + b"), ("x = 1", "")]
    text, applied, failed = apply_edits("def f(a, b):\n    return a - b\nx = 1\n", edits)
    assert (applied, failed) == (2, 0)
    assert "return a + b" in text and "x = 1" not in text


def test_apply_edits_tolerates_trailing_whitespace_and_skips_misses() -> None:
    from src.agents.developer import apply_edits

    text, applied, failed = apply_edits(
        "a = 1   \nb = 2\nc = 3\n", [("a = 1\nb = 2", "a = 10\nb = 20"), ("missing", "z")]
    )
    assert (applied, failed) == (1, 1)
    assert text == "a = 10\nb = 20\nc = 3\n"


def test_large_repo_rejects_full_file_rewrite_and_applies_edits(tmp_path: Path) -> None:
    from src.agents.developer import _apply_large_repo_edit
    from src.tools.toolbelt import ToolBelt

    (tmp_path / "m.py").write_text("keep = 1\nbug = 1\n")
    belt = ToolBelt(tmp_path)
    assert _apply_large_repo_edit(belt, "m.py", "bug = 2\n") is None  # whole-file rewrite
    edited = _apply_large_repo_edit(
        belt, "m.py", "<<<<<<< SEARCH\nbug = 1\n=======\nbug = 2\n>>>>>>> REPLACE"
    )
    assert edited == "keep = 1\nbug = 2\n"


def test_build_messages_uses_search_replace_prompt_for_large_repos() -> None:
    from src.agents.developer import SEARCH_REPLACE_PROMPT, SYSTEM_PROMPT, build_messages

    assert build_messages("ctx", {}, search_replace=True)[0]["content"] == SEARCH_REPLACE_PROMPT
    assert build_messages("ctx", {})[0]["content"] == SYSTEM_PROMPT


def test_apply_notes_explain_rejected_edits_and_feed_back_into_messages(tmp_path: Path) -> None:
    from src.agents.developer import _apply_large_repo_edit, build_messages
    from src.tools.toolbelt import ToolBelt

    (tmp_path / "m.py").write_text("a = 1\n")
    notes: list[str] = []
    assert _apply_large_repo_edit(ToolBelt(tmp_path), "m.py", "a = 2\n", notes) is None
    assert "m.py" in notes[0]
    user = build_messages("ctx", {"apply_feedback": notes[0]}, search_replace=True)[1]["content"]
    assert "could not be applied" in user and "m.py" in user


def test_edit_parser_tolerates_missing_chevrons() -> None:
    from src.agents.developer import parse_edit_blocks

    body = "SEARCH\nold line\n=======\nnew line\nREPLACE"
    assert parse_edit_blocks(body) == [("old line", "new line")]
