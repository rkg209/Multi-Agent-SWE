"""The Tester node: runs the suite in the sandbox and produces a structured PASS/FAIL.

The model call (small tier) is used to interpret the diff/failures for the
trace and for the Developer's next-turn feedback; the authoritative verdict
is always the sandbox `pytest -q` exit code, never the model's opinion.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import cast

from src.agents.context import clip_diff
from src.graph.contracts import TestResult
from src.graph.state import GraphState
from src.metrics.turn_tracer import RecordingToolBelt, trace_turn
from src.router.router import LLMRequest, complete
from src.tools.toolbelt import ToolBelt, ToolError

# Output cap per call: unbounded generations from small models ran away to >100k tokens.
TESTER_MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You are a test engineer. You will be shown a diff and the output of running the test "
    "suite against it. Summarise in one short paragraph whether the change looks correct and "
    "what, if anything, is failing. This summary is informational only — the pass/fail verdict "
    "comes from the test run itself, not from you."
)


def build_messages(diff: str, exec_output: str) -> list[dict[str, str]]:
    """Build chat messages: system prompt, user = current diff + sandbox test output."""
    user_content = f"Diff:\n{clip_diff(diff)}\n\nTest run output:\n{exec_output}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def tester_node(state: GraphState) -> GraphState:
    """Run the suite in the sandbox, ask the model to interpret it, update state."""
    root = Path(state["workspace"])
    run_id = uuid.UUID(state["run_id"])
    test_iteration = state.get("test_iteration", 0)

    with trace_turn(
        run_id=run_id,
        task_id=state["task_id"],
        agent_role="tester",
        turn_index=test_iteration,
    ) as recorder:
        belt = RecordingToolBelt(ToolBelt(root), recorder)

        if state.get("run_tests", True):
            try:
                exec_result = belt.exec("pytest -q")
                exec_output = exec_result.stdout + exec_result.stderr
                passed = exec_result.exit_code == 0
            except ToolError as exc:
                exec_output = exc.message
                passed = False
        else:
            # Real repos: the network-less sandbox lacks their dependencies, so there is no test
            # signal. Review the diff statically and hand it to the Reviewer rather than looping
            # on a failure that can never clear.
            exec_output = "Tests were not executed (the repository's dependencies are unavailable)."
            passed = bool(belt.diff().strip())
            if not passed:
                exec_output += " The Developer produced no change, so there is nothing to review."

        diff = belt.diff()
        messages = build_messages(diff, exec_output)
        response = complete(
            LLMRequest(
                messages=messages,
                role="tester",
                max_tokens=TESTER_MAX_TOKENS,
                run_id=run_id,
                task_id=state["task_id"],
                turn_index=test_iteration,
                temperature=0.0,
            )
        )
        recorder.model = response.model
        recorder.prompt_tokens = response.prompt_tokens
        recorder.completion_tokens = response.completion_tokens
        recorder.cost_usd = response.cost_usd

        result = TestResult(passed=passed, failures=exec_output)

    new_state = cast("GraphState", dict(state))
    new_state["test_passed"] = result.passed
    new_state["test_stdout"] = result.failures
    new_state["test_iteration"] = test_iteration + 1
    if result.passed:
        new_state["best_patch"] = state.get("patch", "")
    new_state["cost_usd"] = state.get("cost_usd", 0.0) + response.cost_usd
    new_state["total_tokens"] = (
        state.get("total_tokens", 0) + response.prompt_tokens + response.completion_tokens
    )
    return new_state
