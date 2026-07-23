"""Integration test: a runaway task halts at the token-budget cap, not the iteration cap.

Needs no Docker/Postgres/provider — the developer node is mocked (same
pattern as `tests/integration/test_multi_agent/test_checkpoint_resume.py`),
so this exercises the real graph wiring end-to-end without external services.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.graph import graph as graph_module
from src.graph.state import GraphState


@pytest.mark.integration
def test_single_mode_halts_on_budget_before_iteration_cap() -> None:
    calls = {"count": 0}

    def fake_node(state: GraphState) -> GraphState:
        calls["count"] += 1
        new_state = dict(state)
        new_state["iteration"] = state.get("iteration", 0) + 1
        new_state["total_tokens"] = state.get("total_tokens", 0) + 50_000
        new_state["test_passed"] = False
        return new_state

    with patch.object(graph_module, "developer_node", side_effect=fake_node):
        compiled = graph_module.build_graph({"mode": "single"})
        final = compiled.invoke(
            {
                "iteration": 0,
                "max_iterations": 10,
                "total_tokens": 0,
                "token_budget": 100_000,
            }
        )

    # Budget (100_000 / 50_000-per-turn) is hit after 2 turns, well before the
    # much higher iteration cap of 10 — proves the budget guard, not the
    # iteration cap, stopped the run.
    assert calls["count"] == 2
    assert final["total_tokens"] == 100_000
    assert final["iteration"] < final["max_iterations"]
