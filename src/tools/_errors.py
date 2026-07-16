"""Shared structured-error shape and path-scoping guard for the MCP tool servers.

Every server (`filesystem_server`, `runcode_server`, `git_server`) resolves
untrusted path/command arguments through `resolve_within_root` and converts
a `ToolError` into the structured `{"ok": false, "error": {...}}` shape at
the tool boundary — never an exception. Internal bugs still raise.
"""

from __future__ import annotations

import os
from pathlib import Path


class ToolError(Exception):
    """Raised for an expected, structured tool-boundary failure (e.g. a path escape)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, object]:
        """Return the structured `{"ok": false, "error": {...}}` response shape."""
        return {"ok": False, "error": {"code": self.code, "message": self.message}}


def structured_error(code: str, message: str) -> dict[str, object]:
    """Build the structured error response shape directly, without raising."""
    return {"ok": False, "error": {"code": code, "message": message}}


def task_root() -> Path:
    """Return the task snapshot root from the `SANDBOX_TASK_DIR` env var, resolved.

    Every MCP tool server is spawned as a subprocess scoped to one task, with
    the snapshot root passed via this env var rather than a constructor arg.
    """
    task_dir = os.environ.get("SANDBOX_TASK_DIR")
    if not task_dir:
        raise ToolError("config_error", "SANDBOX_TASK_DIR is not set")
    return Path(task_dir).resolve()


def resolve_within_root(root: Path, rel_path: str) -> Path:
    """Resolve `rel_path` against `root` and assert the result stays within it.

    Rejects `..` escapes, absolute paths outside `root`, and symlinks that
    resolve outside `root`, all with a `ToolError(code="path_escape", ...)`
    rather than letting the OS error surface directly.

    Args:
        root: The task snapshot root every path must stay within.
        rel_path: A path relative to `root` (or an absolute path, which is
            only accepted if it already lies within `root`).

    Returns:
        The resolved, escape-checked absolute path.
    """
    root = root.resolve()
    candidate = Path(rel_path)
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise ToolError("path_escape", f"Could not resolve path: {rel_path!r} ({exc})") from exc

    if resolved != root and root not in resolved.parents:
        raise ToolError(
            "path_escape",
            f"Path {rel_path!r} escapes the task root {root}",
        )
    return resolved
