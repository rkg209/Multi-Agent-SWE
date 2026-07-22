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
        graph_module.build_graph({"mode": "multi"})
