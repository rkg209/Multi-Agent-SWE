"""Builds the LangGraph agent graph. `mode="single"` is Developer-only; `mode="multi"` is
the full Architect -> Developer -> Tester -> Reviewer team (Spec 06).
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.architect import architect_node
from src.agents.developer import developer_node
from src.agents.reviewer import reviewer_node
from src.agents.tester import tester_node
from src.graph.state import GraphState
from src.guardrails.budget import DEFAULT_TOKEN_BUDGET, is_budget_exceeded

DEFAULT_MAX_ITERATIONS = 3
DEFAULT_MAX_TEST_ITERATIONS = 3
DEFAULT_MAX_REVIEW_ITERATIONS = 2


def _budget_ok(state: GraphState) -> bool:
    """Return whether the run is still under its per-task token budget (FR-43)."""
    return not is_budget_exceeded(
        state.get("total_tokens", 0), state.get("token_budget", DEFAULT_TOKEN_BUDGET)
    )


def _should_continue(state: GraphState) -> str:
    """Loop back to `developer` unless tests passed, the budget is exhausted, or the cap is hit."""
    if not _budget_ok(state):
        return END
    if state.get("test_passed"):
        return END
    if not state.get("run_tests", True) and state.get("patch", "").strip():
        return END  # no test signal exists; a non-empty patch is all there is to wait for
    if state.get("iteration", 0) >= state.get("max_iterations", DEFAULT_MAX_ITERATIONS):
        return END
    return "developer"


def _after_architect(state: GraphState) -> str:
    """Route to `developer` unless the budget is already exhausted (FR-43)."""
    if not _budget_ok(state):
        return END
    return "developer"


def _after_developer_multi(state: GraphState) -> str:
    """Route to `tester` unless the budget is already exhausted (FR-43)."""
    if not _budget_ok(state):
        return END
    return "tester"


def _after_tester(state: GraphState) -> str:
    """Route to `reviewer` on PASS, back to `developer` on FAIL under cap, else `END`."""
    if not _budget_ok(state):
        return END
    if state.get("test_passed"):
        return "reviewer"
    if state.get("test_iteration", 0) >= state.get(
        "max_test_iterations", DEFAULT_MAX_TEST_ITERATIONS
    ):
        return END
    return "developer"


def _after_reviewer(state: GraphState) -> str:
    """Route to `END` on approval, back to `developer` on issues under cap, else `END`."""
    if not _budget_ok(state):
        return END
    if state.get("review_approved"):
        return END
    if state.get("review_iteration", 0) >= state.get(
        "max_review_iterations", DEFAULT_MAX_REVIEW_ITERATIONS
    ):
        return END
    return "developer"


def build_graph(
    solver_config: dict[str, object],
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the agent graph; `mode="single"` activates only the Developer node.

    `mode="multi"` (Spec 06) registers all four nodes with the default order
    Architect -> Developer -> Tester -> Reviewer and two capped feedback loops.
    """
    mode = solver_config.get("mode", "single")
    graph = StateGraph(GraphState)

    if mode == "single":
        graph.add_node("developer", developer_node)
        graph.set_entry_point("developer")
        graph.add_conditional_edges(
            "developer", _should_continue, {"developer": "developer", END: END}
        )
    elif mode == "multi":
        graph.add_node("architect", architect_node)
        graph.add_node("developer", developer_node)
        graph.add_node("tester", tester_node)
        graph.add_node("reviewer", reviewer_node)
        graph.set_entry_point("architect")
        graph.add_conditional_edges(
            "architect", _after_architect, {"developer": "developer", END: END}
        )
        graph.add_conditional_edges(
            "developer", _after_developer_multi, {"tester": "tester", END: END}
        )
        graph.add_conditional_edges(
            "tester", _after_tester, {"reviewer": "reviewer", "developer": "developer", END: END}
        )
        graph.add_conditional_edges(
            "reviewer", _after_reviewer, {"developer": "developer", END: END}
        )
    else:
        raise ValueError(f"Unsupported solver mode: {mode!r}")

    return graph.compile(checkpointer=checkpointer)
