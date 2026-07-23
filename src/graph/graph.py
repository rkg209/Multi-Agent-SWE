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

DEFAULT_MAX_ITERATIONS = 3
DEFAULT_MAX_TEST_ITERATIONS = 3
DEFAULT_MAX_REVIEW_ITERATIONS = 2


def _should_continue(state: GraphState) -> str:
    """Loop back to `developer` unless tests passed or the iteration cap is hit."""
    if state.get("test_passed"):
        return END
    if state.get("iteration", 0) >= state.get("max_iterations", DEFAULT_MAX_ITERATIONS):
        return END
    return "developer"


def _after_tester(state: GraphState) -> str:
    """Route to `reviewer` on PASS, back to `developer` on FAIL under cap, else `END`."""
    if state.get("test_passed"):
        return "reviewer"
    if state.get("test_iteration", 0) >= state.get(
        "max_test_iterations", DEFAULT_MAX_TEST_ITERATIONS
    ):
        return END
    return "developer"


def _after_reviewer(state: GraphState) -> str:
    """Route to `END` on approval, back to `developer` on issues under cap, else `END`."""
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
        graph.add_edge("architect", "developer")
        graph.add_edge("developer", "tester")
        graph.add_conditional_edges(
            "tester", _after_tester, {"reviewer": "reviewer", "developer": "developer", END: END}
        )
        graph.add_conditional_edges(
            "reviewer", _after_reviewer, {"developer": "developer", END: END}
        )
    else:
        raise ValueError(f"Unsupported solver mode: {mode!r}")

    return graph.compile(checkpointer=checkpointer)
