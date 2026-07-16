"""Git MCP server (FR-16): diff/stage/commit against the sandboxed task clone.

Runs `git` on the host, path-scoped to `SANDBOX_TASK_DIR` — a confirmed
design decision (see specs/02-tool-layer plan): diff/stage/commit are fixed
VCS operations on files, not untrusted-code execution, so the Docker
sandbox boundary doesn't apply here. Any file paths passed in are still
validated with the same `resolve_within_root` guard as the other servers.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.tools._errors import ToolError, resolve_within_root, task_root

logger = logging.getLogger(__name__)

mcp = FastMCP("git-server")

COMMIT_AUTHOR_NAME = "swe-agent"
COMMIT_AUTHOR_EMAIL = "swe-agent@localhost"


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a git subcommand with a deterministic commit identity, cwd-scoped to `root`."""
    return subprocess.run(
        [
            "git",
            "-c",
            f"user.name={COMMIT_AUTHOR_NAME}",
            "-c",
            f"user.email={COMMIT_AUTHOR_EMAIL}",
            "-c",
            "color.ui=never",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def git_diff(root: Path) -> str:
    """Return the working-tree diff for `root`."""
    result = _run_git(root, ["diff"])
    if result.returncode != 0:
        raise ToolError("git_error", result.stderr)
    return result.stdout


def git_stage(root: Path, paths: list[str]) -> None:
    """Stage `paths`, each validated to stay within `root`.

    Args:
        root: The task repo root.
        paths: Paths relative to `root` to `git add`.

    Raises:
        ToolError: `code="path_escape"` if any path escapes `root`, or
            `code="git_error"` if `git add` itself fails.
    """
    resolved_rel_paths = [str(resolve_within_root(root, p).relative_to(root)) for p in paths]
    result = _run_git(root, ["add", "--", *resolved_rel_paths])
    if result.returncode != 0:
        raise ToolError("git_error", result.stderr)


def git_commit(root: Path, message: str) -> str:
    """Create a commit with `message` and return the new commit SHA."""
    result = _run_git(root, ["commit", "-m", message])
    if result.returncode != 0:
        raise ToolError("git_error", result.stderr or result.stdout)
    sha = _run_git(root, ["rev-parse", "HEAD"])
    return sha.stdout.strip()


@mcp.tool()
def diff() -> dict[str, object]:
    """Return the working-tree diff for the task repo."""
    try:
        output = git_diff(task_root())
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True, "diff": output}


@mcp.tool()
def stage(paths: list[str]) -> dict[str, object]:
    """Stage the given paths, scoped to the task repo."""
    try:
        git_stage(task_root(), paths)
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True}


@mcp.tool()
def commit(message: str) -> dict[str, object]:
    """Create a commit with `message` in the task repo and return its SHA."""
    try:
        sha = git_commit(task_root(), message)
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True, "sha": sha}


if __name__ == "__main__":
    mcp.run()
