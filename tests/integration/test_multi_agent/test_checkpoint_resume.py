"""Checkpoint interrupt/resume test (FR-41) — no Docker/Postgres required.

Builds the `multi` graph with a real `SqliteSaver` and mocked nodes (no LLM/tool calls),
interrupts before the Tester, then resumes with the same `thread_id` and asserts the nodes
that already completed do not re-execute.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from langgraph.checkpoint.sqlite import SqliteSaver

from src.graph import graph as graph_module
from src.graph.state import GraphState


def test_interrupted_run_resumes_without_rerunning_completed_nodes(tmp_path: Path) -> None:
    calls = {"architect": 0, "developer": 0, "tester": 0, "reviewer": 0}

    def fake_architect(state: GraphState) -> GraphState:
        calls["architect"] += 1
        new_state = dict(state)
        new_state["plan"] = "do the fix"
        return new_state

    def fake_developer(state: GraphState) -> GraphState:
        calls["developer"] += 1
        new_state = dict(state)
        new_state["patch"] = "diff --git a/x.py b/x.py"
        return new_state

    def fake_tester(state: GraphState) -> GraphState:
        calls["tester"] += 1
        new_state = dict(state)
        new_state["test_passed"] = True
        new_state["test_iteration"] = state.get("test_iteration", 0) + 1
        return new_state

    def fake_reviewer(state: GraphState) -> GraphState:
        calls["reviewer"] += 1
        new_state = dict(state)
        new_state["review_approved"] = True
        new_state["review_iteration"] = state.get("review_iteration", 0) + 1
        return new_state

    checkpoint_file = f"{tmp_path}/resume-test.sqlite"

    with (
        patch.object(graph_module, "architect_node", side_effect=fake_architect),
        patch.object(graph_module, "developer_node", side_effect=fake_developer),
        patch.object(graph_module, "tester_node", side_effect=fake_tester),
        patch.object(graph_module, "reviewer_node", side_effect=fake_reviewer),
        SqliteSaver.from_conn_string(checkpoint_file) as saver,
    ):
        compiled = graph_module.build_graph({"mode": "multi"}, checkpointer=saver)
        thread_id = "resume-thread-1"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "run_id": "00000000-0000-0000-0000-000000000000",
            "task_id": "custom-resume",
            "issue_text": "add is missing",
            "workspace": str(tmp_path),
            "test_iteration": 0,
            "review_iteration": 0,
            "max_test_iterations": 3,
            "max_review_iterations": 2,
        }

        compiled.invoke(initial_state, config=config, interrupt_before=["tester"])

        assert calls["architect"] == 1
        assert calls["developer"] == 1
        assert calls["tester"] == 0

        final_state = compiled.invoke(None, config=config)

        assert calls["architect"] == 1
        assert calls["developer"] == 1
        assert calls["tester"] == 1
        assert calls["reviewer"] == 1
        assert final_state["test_passed"] is True
        assert final_state["review_approved"] is True
