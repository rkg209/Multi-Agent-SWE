"""The Architect node: reads the issue + repo snapshot, produces a plan for the Developer."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import cast

from src.agents.developer import build_context
from src.graph.contracts import Plan
from src.graph.state import GraphState
from src.metrics.turn_tracer import RecordingToolBelt, trace_turn
from src.router.router import LLMRequest, complete
from src.tools.toolbelt import ToolBelt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a software architect planning a fix for a bug in a small repository.\n"
    "Reply in exactly this format:\n\n"
    "FILES: <comma-separated list of relative filenames to modify>\n"
    "APPROACH:\n<a short paragraph describing the approach>\n"
    "CONSTRAINTS:\n<any constraints the Developer must respect, or 'None'>\n"
)

_FILES_RE = re.compile(r"^FILES:\s*(?P<files>.*)$", re.MULTILINE)
_APPROACH_RE = re.compile(
    r"^APPROACH:\s*\n(?P<approach>.*?)(?=^CONSTRAINTS:|\Z)", re.MULTILINE | re.DOTALL
)
_CONSTRAINTS_RE = re.compile(r"^CONSTRAINTS:\s*\n(?P<constraints>.*)\Z", re.MULTILINE | re.DOTALL)


def parse_plan(content: str) -> Plan:
    """Parse the Architect's `FILES:`/`APPROACH:`/`CONSTRAINTS:` reply into a `Plan`.

    Missing sections degrade to empty values rather than raising — a malformed
    reply should not crash the graph; the Developer still gets the issue text.
    """
    files_match = _FILES_RE.search(content)
    files = (
        tuple(f.strip() for f in files_match.group("files").split(",") if f.strip())
        if files_match
        else ()
    )

    approach_match = _APPROACH_RE.search(content)
    approach = approach_match.group("approach").strip() if approach_match else ""

    constraints_match = _CONSTRAINTS_RE.search(content)
    constraints = constraints_match.group("constraints").strip() if constraints_match else ""

    return Plan(files=files, approach=approach, constraints=constraints)


def build_messages(context: str, state: GraphState) -> list[dict[str, str]]:
    """Build chat messages: system prompt pinning the output contract, user = issue + context."""
    user_content = f"Issue:\n{state.get('issue_text', '')}\n\nRepository contents:\n{context}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def architect_node(state: GraphState) -> GraphState:
    """Read the repo, get a plan from the model, write it into state. Runs once at entry."""
    root = Path(state["workspace"])
    run_id = uuid.UUID(state["run_id"])
    iteration = state.get("iteration", 0)

    with trace_turn(
        run_id=run_id, task_id=state["task_id"], agent_role="architect", turn_index=iteration
    ) as recorder:
        belt = RecordingToolBelt(ToolBelt(root), recorder)

        context = build_context(belt, state)
        messages = build_messages(context, state)
        response = complete(
            LLMRequest(
                messages=messages,
                role="architect",
                run_id=run_id,
                task_id=state["task_id"],
                turn_index=iteration,
                temperature=0.0,
            )
        )
        recorder.model = response.model
        recorder.prompt_tokens = response.prompt_tokens
        recorder.completion_tokens = response.completion_tokens
        recorder.cost_usd = response.cost_usd

        plan = parse_plan(response.content)
        if not plan.files:
            logger.warning("Architect reply for %s named no files", state["task_id"])

    new_state = cast("GraphState", dict(state))
    new_state["plan"] = plan.approach
    new_state["plan_files"] = list(plan.files)
    new_state["plan_constraints"] = plan.constraints
    new_state["cost_usd"] = state.get("cost_usd", 0.0) + response.cost_usd
    new_state["total_tokens"] = (
        state.get("total_tokens", 0) + response.prompt_tokens + response.completion_tokens
    )
    return new_state
