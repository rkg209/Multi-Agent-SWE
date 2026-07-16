"""Run-code MCP server (FR-15, NFR-1): the only agent-facing way to execute a shell command.

Every `exec` call is delegated to `src.sandbox.docker_sandbox.run` — this
server never shells out on the host itself. `working_dir` is resolved
against `SANDBOX_TASK_DIR` and rejected with a structured error if it would
escape the task snapshot or otherwise target the host.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.sandbox.docker_sandbox import run as run_in_sandbox
from src.tools._errors import ToolError, resolve_within_root, task_root

logger = logging.getLogger(__name__)

mcp = FastMCP("runcode-server")


def exec_command(command: str, working_dir: str = ".", timeout: int = 120) -> dict[str, object]:
    """Run `command` inside the Docker sandbox, scoped to `working_dir` within the task root.

    Args:
        command: The shell command to execute.
        working_dir: Path relative to the task root to `cd` into first.
        timeout: Seconds allowed for `command`, forwarded to `docker_sandbox.run`.

    Returns:
        `{"ok": True, "stdout", "stderr", "exit_code", "timed_out"}` on a
        completed (possibly non-zero) run, or the structured error shape if
        `working_dir` escapes the task root.
    """
    try:
        root = task_root()
        resolved_dir = resolve_within_root(root, working_dir)
    except ToolError as exc:
        return exc.to_dict()

    rel = resolved_dir.relative_to(root)
    shell_cmd = command if rel == Path(".") else f"cd {shlex.quote(str(rel))} && {command}"
    result = run_in_sandbox(shell_cmd, root, timeout=timeout)
    return {
        "ok": True,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
    }


@mcp.tool()
def exec(
    command: str, working_dir: str = ".", timeout: int = 120
) -> dict[str, object]:  # noqa: A001
    """Execute `command` inside the sandbox, in `working_dir` relative to the task root."""
    return exec_command(command, working_dir, timeout)


if __name__ == "__main__":
    mcp.run()
