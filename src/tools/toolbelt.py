"""Root-bound sync facade over the Spec 02 tool servers, for in-process agent nodes.

Agent nodes call these methods directly instead of going through the MCP
stdio transport — the `@mcp.tool()` wrappers are thin shells over the same
pure functions this class calls. `exec` still funnels through
`runcode_server.exec_command` -> `docker_sandbox.run`, so the sandbox
boundary (NFR-1) holds.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

from src.sandbox.docker_sandbox import SandboxResult
from src.tools import filesystem_server, git_server, runcode_server
from src.tools._errors import ToolError

__all__ = ["ToolBelt", "ToolError", "sandbox_task_dir"]


@contextlib.contextmanager
def sandbox_task_dir(root: Path) -> Iterator[None]:
    """Set `SANDBOX_TASK_DIR` to `root` for the duration of the context.

    `runcode_server.exec_command` resolves its working directory against this
    env var; callers of `ToolBelt.exec` must be inside this context (the
    solver enters it once per task, not per call).
    """
    previous = os.environ.get("SANDBOX_TASK_DIR")
    os.environ["SANDBOX_TASK_DIR"] = str(root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SANDBOX_TASK_DIR", None)
        else:
            os.environ["SANDBOX_TASK_DIR"] = previous


class ToolBelt:
    """Root-bound sync facade over the Spec 02 tool servers, for in-process agent nodes."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def read_file(self, path: str) -> str:
        """Read and return the text contents of `path`, scoped to the task root."""
        return filesystem_server.read_file(self._root, path)

    def write_file(self, path: str, content: str) -> None:
        """Write `content` to `path`, scoped to the task root."""
        filesystem_server.write_file(self._root, path, content)

    def list_dir(self, path: str = ".") -> list[str]:
        """List entry names of the directory at `path`, scoped to the task root."""
        return filesystem_server.list_dir(self._root, path)

    def exec(self, command: str, timeout: int = 120) -> SandboxResult:
        """Run `command` inside the Docker sandbox, scoped to the task root.

        Requires `SANDBOX_TASK_DIR` to already be set to the task root (see
        `sandbox_task_dir`); `runcode_server.exec_command` resolves against it.
        """
        result = runcode_server.exec_command(command, working_dir=".", timeout=timeout)
        if not result["ok"]:
            error = result["error"]
            raise ToolError(error["code"], error["message"])  # type: ignore[index]
        return SandboxResult(
            stdout=result["stdout"],  # type: ignore[arg-type]
            stderr=result["stderr"],  # type: ignore[arg-type]
            exit_code=result["exit_code"],  # type: ignore[arg-type]
            timed_out=result["timed_out"],  # type: ignore[arg-type]
        )

    def diff(self) -> str:
        """Return the working-tree diff for the task root."""
        return git_server.git_diff(self._root)
