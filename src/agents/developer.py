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

from src.agents.context import (
    MAX_CANDIDATE_LISTING,
    fit_to_budget,
    is_large_repo,
    rank_files,
)
from src.graph.state import GraphState
from src.metrics.turn_tracer import RecordingToolBelt, trace_turn
from src.router.router import LLMRequest, complete
from src.tools.toolbelt import ToolBelt, ToolError

logger = logging.getLogger(__name__)

# Output cap per call: unbounded generations from small models ran away to >100k tokens.
DEVELOPER_MAX_TOKENS = 4096

CONTEXT_CHAR_CAP = 8000
SKIP_ENTRIES = {".git", "hidden_test.py", "visible_test.py"}

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


def large_repo_files(state: GraphState) -> tuple[list[str], list[str]] | None:
    """For a non-flat repo return `(files shown, all ranked candidates)`, else None.

    Ranking seeds from the Architect's `plan_files` (multi mode) and the issue text.
    """
    workspace = state.get("workspace")
    if not workspace:
        return None
    root = Path(workspace)
    if not is_large_repo(root):
        return None
    ranked = rank_files(root, state.get("issue_text", ""), state.get("plan_files"))
    return fit_to_budget(root, ranked), ranked


def _build_large_context(belt: ToolBelt, chosen: list[str], ranked: list[str]) -> str:
    """Full contents of the selected files, plus a listing of the other ranked candidates."""
    parts = [f"--- {rel} ---\n{belt.read_file(rel)}\n" for rel in chosen]
    others = [r for r in ranked if r not in chosen][:MAX_CANDIDATE_LISTING]
    if others:
        parts.append("Other candidate files (not shown; do not edit):\n" + "\n".join(others) + "\n")
    return "".join(parts)


# Tolerant of chevron counts and of the chevrons being omitted entirely: 8B models drift on them.
_EDIT_RE = re.compile(
    r"^(?:<{3,} *)?SEARCH *\n(?P<search>.*?)\n={3,} *\n(?P<replace>.*?)\n?^(?:>{3,} *)?REPLACE *$",
    re.DOTALL | re.MULTILINE,
)

SEARCH_REPLACE_PROMPT = (
    "You are a software engineer fixing a bug in a large repository. You are shown a few "
    "relevant files in full. Do NOT rewrite whole files. Reply with search/replace edits, in "
    "exactly this format, one fenced block per file (repeat the SEARCH/REPLACE section for "
    "several edits in the same file):\n\n"
    "```path=<relative/path/to/file>\n"
    "<<<<<<< SEARCH\n"
    "<exact lines copied from the file, including indentation>\n"
    "=======\n"
    "<the replacement lines>\n"
    ">>>>>>> REPLACE\n"
    "```\n\n"
    "Example (changing one line of `pkg/util.py`):\n\n"
    "```path=pkg/util.py\n"
    "<<<<<<< SEARCH\n"
    "    return a - b\n"
    "=======\n"
    "    return a + b\n"
    ">>>>>>> REPLACE\n"
    "```\n\n"
    "Always include all three marker lines (SEARCH, =======, REPLACE) for every edit. "
    "The SEARCH text must match the existing file exactly and be unique enough to locate the "
    "edit; keep it short (a few lines). The `path=` value MUST be one of the files shown under "
    "'Repository contents' with its full relative path. Do not include any explanation outside "
    "the code blocks."
)


def parse_edit_blocks(body: str) -> list[tuple[str, str]]:
    """Extract `(search, replace)` pairs from one file block's SEARCH/REPLACE sections."""
    return [(m.group("search"), m.group("replace")) for m in _EDIT_RE.finditer(body)]


def apply_edits(original: str, edits: list[tuple[str, str]]) -> tuple[str, int, int]:
    """Apply search/replace edits to `original`; return `(new_text, applied, failed)`.

    Matching is exact first, then tolerant of trailing whitespace on each line. An edit whose
    SEARCH text is not found is skipped (counted as failed) rather than guessed at.
    """
    text = original
    applied = failed = 0
    for search, replace in edits:
        if search in text:
            text = text.replace(search, replace, 1)
            applied += 1
            continue
        normalized = "\n".join(line.rstrip() for line in search.split("\n"))
        lines = text.split("\n")
        stripped = [line.rstrip() for line in lines]
        needle = normalized.split("\n")
        span = len(needle)
        for start in range(len(stripped) - span + 1):
            if stripped[start : start + span] == needle:
                lines[start : start + span] = replace.split("\n")
                text = "\n".join(lines)
                applied += 1
                break
        else:
            failed += 1
    return text, applied, failed


def build_context(belt: ToolBelt, state: GraphState) -> str:
    """Show the repo to the model: whole top-level files for toy repos, ranked files otherwise.

    Flat repos: concatenate `list_dir(".")` contents, skipping fixtures, capped at ~8000 chars.
    Real repos: the few files `large_repo_files` selects, uncut (the model rewrites whole files).
    """
    large = large_repo_files(state)
    if large is not None:
        return _build_large_context(belt, *large)
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


def build_messages(
    context: str, state: GraphState, *, search_replace: bool = False
) -> list[dict[str, str]]:
    """Build chat messages: system prompt pinning the output contract, user = issue + context.

    In `multi` mode also includes the Architect's plan/constraints and the
    latest Tester/Reviewer feedback, so the Developer consumes the rest of
    the team's output (FR-36).
    """
    user_parts = [
        f"Issue:\n{state.get('issue_text', '')}",
        f"Repository contents:\n{context}",
    ]
    plan = state.get("plan")
    if plan:
        user_parts.append(f"Architect's plan:\n{plan}")
    plan_constraints = state.get("plan_constraints")
    if plan_constraints:
        user_parts.append(f"Constraints from the Architect:\n{plan_constraints}")
    previous_stdout = state.get("test_stdout")
    if state.get("iteration", 0) > 0 and previous_stdout:
        user_parts.append(f"The previous attempt's test run failed:\n{previous_stdout}")
    apply_feedback = state.get("apply_feedback")
    if apply_feedback:
        user_parts.append(f"Your previous reply could not be applied:\n{apply_feedback}")
    review_issues = state.get("review_issues")
    if review_issues:
        user_parts.append(f"The reviewer requested these changes:\n{review_issues}")
    return [
        {"role": "system", "content": SEARCH_REPLACE_PROMPT if search_replace else SYSTEM_PROMPT},
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


def _apply_large_repo_edit(
    belt: ToolBelt, path: str, body: str, notes: list[str] | None = None
) -> str | None:
    """Turn a model block into the new file text for a real repo, or None to skip the file.

    Whole-file rewrites are rejected here: models return truncated "complete" files for
    hundreds-of-lines modules, which would delete most of the file.
    """
    edits = parse_edit_blocks(body)
    if not edits:
        logger.warning(
            "Rejected full-file rewrite of %r in a large repo (use SEARCH/REPLACE)", path
        )
        if notes is not None:
            notes.append(
                f"{path}: not a valid SEARCH/=======/REPLACE edit (whole-file rewrite rejected)."
            )
        return None
    new_text, applied, failed = apply_edits(belt.read_file(path), edits)
    if failed:
        logger.warning("%d of %d edits to %r did not match the file", failed, len(edits), path)
        if notes is not None:
            notes.append(f"{path}: {failed} SEARCH block(s) did not match the file text exactly.")
    return new_text if applied else None


def developer_node(state: GraphState) -> GraphState:
    """Read the repo, get file rewrites from the model, write them, run tests, update state."""
    root = Path(state["workspace"])
    run_id = uuid.UUID(state["run_id"])
    iteration = state.get("iteration", 0)

    with trace_turn(
        run_id=run_id,
        task_id=state["task_id"],
        agent_role="developer",
        turn_index=iteration,
    ) as recorder:
        belt = RecordingToolBelt(ToolBelt(root), recorder)

        large = large_repo_files(state)
        if large is not None:
            known_entries = set(large[0])
            context = _build_large_context(belt, *large)
        else:
            known_entries = {e for e in belt.list_dir(".") if e not in SKIP_ENTRIES}
            context = build_context(belt, state)
        messages = build_messages(context, state, search_replace=large is not None)
        response = complete(
            LLMRequest(
                messages=messages,
                role="developer",
                max_tokens=DEVELOPER_MAX_TOKENS,
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
        apply_notes: list[str] = []
        if large is not None and not blocks:
            apply_notes.append("No ```path=<file>``` block was found in your reply.")
        if not blocks:
            logger.warning("Developer reply for %s contained no file blocks", state["task_id"])
        for raw_path, file_content in blocks.items():
            path = _normalize_path(raw_path, known_entries)
            try:
                if large is not None:
                    file_content = _apply_large_repo_edit(belt, path, file_content, apply_notes)
                    if file_content is None:
                        continue
                belt.write_file(path, file_content)
            except ToolError as exc:
                logger.warning("Could not write %r: %s", path, exc.message)

        is_multi = state.get("solver_config", {}).get("mode") == "multi"
        test_stdout = state.get("test_stdout", "")
        test_passed = state.get("test_passed", False)
        if not is_multi and state.get("run_tests", True):
            try:
                exec_result = belt.exec("pytest -q")
                test_stdout = exec_result.stdout + exec_result.stderr
                test_passed = exec_result.exit_code == 0
            except ToolError as exc:
                test_stdout = exc.message
                test_passed = False

        patch = belt.diff()

    new_state = cast("GraphState", dict(state))
    if not is_multi:
        new_state["test_stdout"] = test_stdout
        new_state["test_passed"] = test_passed
    new_state["patch"] = patch
    new_state["apply_feedback"] = "\n".join(apply_notes) if not patch.strip() else ""
    new_state["cost_usd"] = state.get("cost_usd", 0.0) + response.cost_usd
    new_state["total_tokens"] = (
        state.get("total_tokens", 0) + response.prompt_tokens + response.completion_tokens
    )
    new_state["iteration"] = iteration + 1
    return new_state
