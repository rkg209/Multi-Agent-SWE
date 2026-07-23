"""The Developer node: reads the repo, asks the model for full-file rewrites, tests them.

Full-file rewrites rather than diffs: small models cannot reliably emit valid
unified diffs, so the model returns complete file contents per fenced block
and `git_diff` (via `ToolBelt.diff`) generates the actual patch afterwards.

`test_passed` is the agent's own signal from whatever tests it wrote or found
in the workspace — the hidden test is only copied in at score time
(`benchmark/scorer.py`), so this is not the scorer's verdict.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import cast

from src.graph.state import GraphState
from src.metrics.turn_tracer import RecordingToolBelt, trace_turn
from src.router.router import LLMRequest, complete
from src.tools.toolbelt import ToolBelt, ToolError

logger = logging.getLogger(__name__)

CONTEXT_CHAR_CAP = 8000
SKIP_ENTRIES = {".git", "hidden_test.py"}

_FILE_BLOCK_RE = re.compile(r"```path=(?P<path>\S+)\n(?P<content>.*?)```", re.DOTALL)

SYSTEM_PROMPT = (
    "You are a software engineer fixing a bug in a small repository.\n"
    "Reply with one fenced code block per file you create or modify, using exactly this "
    "format (the full new contents of the file, not a diff):\n\n"
    "```path=<relative/path/to/file>\n"
    "<the complete new file contents>\n"
    "```\n\n"
    "The `path=` value MUST be exactly one of the filenames listed under 'Repository "
    "contents' below (e.g. `path=calculator.py`), never a longer path mentioned "
    "elsewhere in the issue text.\n"
    "Do not include any explanation outside the code blocks."
)


def build_context(belt: ToolBelt, state: GraphState) -> str:
    """Concatenate `list_dir(".")` entries' contents, skipping fixtures, capped at ~8000 chars."""
    parts: list[str] = []
    total = 0
    for entry in sorted(belt.list_dir(".")):
        if entry in SKIP_ENTRIES:
            continue
        try:
            content = belt.read_file(entry)
        except ToolError:
            continue
        block = f"--- {entry} ---\n{content}\n"
        if total + len(block) > CONTEXT_CHAR_CAP:
            break
        parts.append(block)
        total += len(block)
    return "".join(parts)


def build_messages(context: str, state: GraphState) -> list[dict[str, str]]:
    """Build chat messages: system prompt pinning the output contract, user = issue + context."""
    user_parts = [
        f"Issue:\n{state.get('issue_text', '')}",
        f"Repository contents:\n{context}",
    ]
    previous_stdout = state.get("test_stdout")
    if state.get("iteration", 0) > 0 and previous_stdout:
        user_parts.append(f"The previous attempt's test run failed:\n{previous_stdout}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def parse_file_blocks(content: str) -> dict[str, str]:
    """Extract ```path=<file>``` fenced blocks from a model reply into `{path: contents}`."""
    blocks: dict[str, str] = {}
    for match in _FILE_BLOCK_RE.finditer(content):
        path = match.group("path").strip()
        body = match.group("content")
        if body.endswith("\n"):
            body = body[:-1]
        blocks[path] = body
    return blocks


def _normalize_path(path: str, known_entries: set[str]) -> str:
    """Fold a hallucinated longer path down to a known top-level filename, if one matches.

    Small models sometimes echo a longer path mentioned in the issue text
    (e.g. a dataset-relative path) instead of the workspace-relative filename
    listed under 'Repository contents'. If `path`'s basename is a known
    existing file, prefer that; otherwise leave `path` untouched (it may
    legitimately be a new file).
    """
    if path in known_entries:
        return path
    basename = Path(path).name
    if basename in known_entries:
        return basename
    return path


def developer_node(state: GraphState) -> GraphState:
    """Read the repo, get file rewrites from the model, write them, run tests, update state."""
    root = Path(state["workspace"])
    run_id = uuid.UUID(state["run_id"])
    iteration = state.get("iteration", 0)

    with trace_turn(
        run_id=run_id, task_id=state["task_id"], agent_role="developer", turn_index=iteration
    ) as recorder:
        belt = RecordingToolBelt(ToolBelt(root), recorder)

        known_entries = {e for e in belt.list_dir(".") if e not in SKIP_ENTRIES}
        context = build_context(belt, state)
        messages = build_messages(context, state)
        response = complete(
            LLMRequest(
                messages=messages,
                role="developer",
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

        blocks = parse_file_blocks(response.content)
        if not blocks:
            logger.warning("Developer reply for %s contained no file blocks", state["task_id"])
        for raw_path, file_content in blocks.items():
            path = _normalize_path(raw_path, known_entries)
            try:
                belt.write_file(path, file_content)
            except ToolError as exc:
                logger.warning("Could not write %r: %s", path, exc.message)

        try:
            exec_result = belt.exec("pytest -q")
            test_stdout = exec_result.stdout + exec_result.stderr
            test_passed = exec_result.exit_code == 0
        except ToolError as exc:
            test_stdout = exc.message
            test_passed = False

        patch = belt.diff()

    new_state = cast("GraphState", dict(state))
    new_state["test_stdout"] = test_stdout
    new_state["test_passed"] = test_passed
    new_state["patch"] = patch
    new_state["cost_usd"] = state.get("cost_usd", 0.0) + response.cost_usd
    new_state["total_tokens"] = (
        state.get("total_tokens", 0) + response.prompt_tokens + response.completion_tokens
    )
    new_state["iteration"] = iteration + 1
    return new_state
