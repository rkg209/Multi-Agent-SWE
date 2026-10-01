"""The Reviewer node: evaluates the passing patch for quality and security."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import cast

from src.agents.context import clip_diff
from src.graph.contracts import Review
from src.graph.state import GraphState
from src.metrics.turn_tracer import RecordingToolBelt, trace_turn
from src.router.router import LLMRequest, complete
from src.tools.toolbelt import ToolBelt

# Output cap per call: unbounded generations from small models ran away to >100k tokens.
REVIEWER_MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You are a senior engineer reviewing a patch for correctness, quality, and security.\n"
    "Reply with exactly one of these two forms:\n\n"
    "APPROVED\n\n"
    "or\n\n"
    "CHANGES\n<a short list of the issues the Developer must fix>\n"
)


def parse_review(content: str) -> Review:
    """Parse the Reviewer's reply: first token `APPROVED`/`CHANGES`, remainder = issues."""
    stripped = content.strip()
    first_line, _, rest = stripped.partition("\n")
    approved = first_line.strip().upper().startswith("APPROVED")
    return Review(approved=approved, issues="" if approved else rest.strip())


def build_messages(issue_text: str, diff: str) -> list[dict[str, str]]:
    """Build chat messages: system prompt pinning the output contract, user = issue + diff."""
    user_content = f"Issue:\n{issue_text}\n\nFinal diff:\n{clip_diff(diff)}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def reviewer_node(state: GraphState) -> GraphState:
    """Review the current diff for quality/security, update state with the verdict."""
    root = Path(state["workspace"])
    run_id = uuid.UUID(state["run_id"])
    review_iteration = state.get("review_iteration", 0)

    with trace_turn(
        run_id=run_id,
        task_id=state["task_id"],
        agent_role="reviewer",
        turn_index=review_iteration,
    ) as recorder:
        belt = RecordingToolBelt(ToolBelt(root), recorder)
        diff = belt.diff()
        messages = build_messages(state.get("issue_text", ""), diff)
        response = complete(
            LLMRequest(
                messages=messages,
                role="reviewer",
                max_tokens=REVIEWER_MAX_TOKENS,
                run_id=run_id,
                task_id=state["task_id"],
                turn_index=review_iteration,
                temperature=0.0,
            )
        )
        recorder.model = response.model
        recorder.prompt_tokens = response.prompt_tokens
        recorder.completion_tokens = response.completion_tokens
        recorder.cost_usd = response.cost_usd

        review = parse_review(response.content)

    new_state = cast("GraphState", dict(state))
    new_state["review_approved"] = review.approved
    new_state["review_issues"] = review.issues
    new_state["review_iteration"] = review_iteration + 1
    new_state["cost_usd"] = state.get("cost_usd", 0.0) + response.cost_usd
    new_state["total_tokens"] = (
        state.get("total_tokens", 0) + response.prompt_tokens + response.completion_tokens
    )
    return new_state
