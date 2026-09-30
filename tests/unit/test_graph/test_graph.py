"""Unit tests for src/graph/graph.py — no LLM/Docker, developer_node is mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.graph import graph as graph_module
from src.graph.state import GraphState


def test_single_mode_registers_exactly_one_node() -> None:
    compiled = graph_module.build_graph({"mode": "single"})
    nodes = compiled.get_graph().nodes
    node_names = {n for n in nodes if n not in {"__start__", "__end__"}}
    assert node_names == {"developer"}


def test_loop_stops_on_test_passed() -> None:
    def fake_node(state: GraphState) -> GraphState:
        new_state = dict(state)
        new_state["iteration"] = state.get("iteration", 0) + 1
        new_state["test_passed"] = True
        return new_state

    with patch.object(graph_module, "developer_node", side_effect=fake_node):
        compiled = graph_module.build_graph({"mode": "single"})
        final = compiled.invoke({"iteration": 0, "max_iterations": 3})

    assert final["test_passed"] is True
    assert final["iteration"] == 1


def test_loop_stops_at_max_iterations() -> None:
    calls = {"count": 0}

    def fake_node(state: GraphState) -> GraphState:
        calls["count"] += 1
        new_state = dict(state)
        new_state["iteration"] = state.get("iteration", 0) + 1
        new_state["test_passed"] = False
        return new_state

    with patch.object(graph_module, "developer_node", side_effect=fake_node):
        compiled = graph_module.build_graph({"mode": "single"})
        final = compiled.invoke({"iteration": 0, "max_iterations": 3})

    assert calls["count"] == 3
    assert final["iteration"] == 3


def test_unsupported_mode_raises() -> None:
    with pytest.raises(ValueError):
        graph_module.build_graph({"mode": "unsupported"})


def test_multi_mode_registers_exactly_four_nodes() -> None:
    compiled = graph_module.build_graph({"mode": "multi"})
    nodes = compiled.get_graph().nodes
    node_names = {n for n in nodes if n not in {"__start__", "__end__"}}
    assert node_names == {"architect", "developer", "tester", "reviewer"}


def test_after_tester_routes_to_reviewer_on_pass() -> None:
    assert graph_module._after_tester({"test_passed": True}) == "reviewer"


def test_after_tester_routes_to_developer_on_fail_under_cap() -> None:
    state = {"test_passed": False, "test_iteration": 1, "max_test_iterations": 3}
    assert graph_module._after_tester(state) == "developer"


def test_after_tester_ends_at_cap() -> None:
    state = {"test_passed": False, "test_iteration": 3, "max_test_iterations": 3}
    assert graph_module._after_tester(state) == graph_module.END


def test_after_reviewer_ends_on_approval() -> None:
    assert graph_module._after_reviewer({"review_approved": True}) == graph_module.END


def test_after_reviewer_routes_to_developer_on_issues_under_cap() -> None:
    state = {"review_approved": False, "review_iteration": 1, "max_review_iterations": 2}
    assert graph_module._after_reviewer(state) == "developer"


def test_after_reviewer_ends_at_cap() -> None:
    state = {"review_approved": False, "review_iteration": 2, "max_review_iterations": 2}
    assert graph_module._after_reviewer(state) == graph_module.END


def test_multi_mode_drives_dev_test_loop_to_cap_and_derives_cap_hit() -> None:
    calls = {"architect": 0, "developer": 0, "tester": 0, "reviewer": 0}

    def fake_architect(state: GraphState) -> GraphState:
        calls["architect"] += 1
        return dict(state)

    def fake_developer(state: GraphState) -> GraphState:
        calls["developer"] += 1
        new_state = dict(state)
        new_state["patch"] = f"patch-{calls['developer']}"
        return new_state

    def fake_tester(state: GraphState) -> GraphState:
        calls["tester"] += 1
        new_state = dict(state)
        new_state["test_passed"] = False
        new_state["test_iteration"] = state.get("test_iteration", 0) + 1
        return new_state

    def fake_reviewer(state: GraphState) -> GraphState:
        calls["reviewer"] += 1
        return dict(state)

    with (
        patch.object(graph_module, "architect_node", side_effect=fake_architect),
        patch.object(graph_module, "developer_node", side_effect=fake_developer),
        patch.object(graph_module, "tester_node", side_effect=fake_tester),
        patch.object(graph_module, "reviewer_node", side_effect=fake_reviewer),
    ):
        compiled = graph_module.build_graph({"mode": "multi"})
        final = compiled.invoke(
            {
                "test_iteration": 0,
                "review_iteration": 0,
                "max_test_iterations": 3,
                "max_review_iterations": 2,
            }
        )

    assert calls["architect"] == 1
    assert calls["developer"] == 3
    assert calls["tester"] == 3
    assert calls["reviewer"] == 0
    assert final["test_iteration"] == 3
    cap_hit = not final.get("test_passed") and final.get("test_iteration", 0) >= final.get(
        "max_test_iterations", 0
    )
    assert cap_hit is True


def test_should_continue_ends_when_budget_exceeded_even_under_iteration_cap() -> None:
    state = {"total_tokens": 200_000, "token_budget": 100_000, "iteration": 0, "max_iterations": 3}
    assert graph_module._should_continue(state) == graph_module.END


def test_after_tester_ends_when_budget_exceeded_even_on_pass() -> None:
    state = {"total_tokens": 200_000, "token_budget": 100_000, "test_passed": True}
    assert graph_module._after_tester(state) == graph_module.END


def test_after_reviewer_ends_when_budget_exceeded_even_under_cap() -> None:
    state = {
        "total_tokens": 200_000,
        "token_budget": 100_000,
        "review_approved": False,
        "review_iteration": 0,
        "max_review_iterations": 2,
    }
    assert graph_module._after_reviewer(state) == graph_module.END


def test_after_architect_routes_to_developer_under_budget() -> None:
    state = {"total_tokens": 0, "token_budget": 100_000}
    assert graph_module._after_architect(state) == "developer"


def test_after_architect_ends_when_budget_exceeded() -> None:
    state = {"total_tokens": 200_000, "token_budget": 100_000}
    assert graph_module._after_architect(state) == graph_module.END


def test_after_developer_multi_routes_to_tester_under_budget() -> None:
    state = {"total_tokens": 0, "token_budget": 100_000}
    assert graph_module._after_developer_multi(state) == "tester"


def test_after_developer_multi_ends_when_budget_exceeded() -> None:
    state = {"total_tokens": 200_000, "token_budget": 100_000}
    assert graph_module._after_developer_multi(state) == graph_module.END


def test_multi_mode_drives_dev_review_loop_to_cap_and_derives_cap_hit() -> None:
    calls = {"developer": 0, "tester": 0, "reviewer": 0}

    def fake_architect(state: GraphState) -> GraphState:
        return dict(state)

    def fake_developer(state: GraphState) -> GraphState:
        calls["developer"] += 1
        return dict(state)

    def fake_tester(state: GraphState) -> GraphState:
        calls["tester"] += 1
        new_state = dict(state)
        new_state["test_passed"] = True
        new_state["test_iteration"] = state.get("test_iteration", 0) + 1
        return new_state

    def fake_reviewer(state: GraphState) -> GraphState:
        calls["reviewer"] += 1
        new_state = dict(state)
        new_state["review_approved"] = False
        new_state["review_iteration"] = state.get("review_iteration", 0) + 1
        return new_state

    with (
        patch.object(graph_module, "architect_node", side_effect=fake_architect),
        patch.object(graph_module, "developer_node", side_effect=fake_developer),
        patch.object(graph_module, "tester_node", side_effect=fake_tester),
        patch.object(graph_module, "reviewer_node", side_effect=fake_reviewer),
    ):
        compiled = graph_module.build_graph({"mode": "multi"})
        final = compiled.invoke(
            {
                "test_iteration": 0,
                "review_iteration": 0,
                "max_test_iterations": 3,
                "max_review_iterations": 2,
            }
        )

    assert calls["reviewer"] == 2
    assert final["review_iteration"] == 2
    cap_hit = (
        final.get("test_passed")
        and not final.get("review_approved")
        and final.get("review_iteration", 0) >= final.get("max_review_iterations", 0)
    )
    assert cap_hit is True
