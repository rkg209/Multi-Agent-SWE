"""Builds the LangGraph agent graph. Spec 04 activates only the Developer node."""

from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.developer import developer_node
from src.graph.state import GraphState

DEFAULT_MAX_ITERATIONS = 3


def _should_continue(state: GraphState) -> str:
    """Loop back to `developer` unless tests passed or the iteration cap is hit."""
    if state.get("test_passed"):
        return END
    if state.get("iteration", 0) >= state.get("max_iterations", DEFAULT_MAX_ITERATIONS):
        return END
    return "developer"


def build_graph(solver_config: dict[str, object]) -> CompiledStateGraph:
    """Build the agent graph; `mode="single"` activates only the Developer node.

    Architect/Tester/Reviewer are added by Spec 06 for `mode="multi"`; they are
    simply not registered here.
    """
    mode = solver_config.get("mode", "single")
    graph = StateGraph(GraphState)

    if mode == "single":
        graph.add_node("developer", developer_node)
        graph.set_entry_point("developer")
        graph.add_conditional_edges(
            "developer", _should_continue, {"developer": "developer", END: END}
        )
    else:
        raise ValueError(f"Unsupported solver mode: {mode!r}")

    return graph.compile()
