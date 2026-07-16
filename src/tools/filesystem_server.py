"""Filesystem MCP server (FR-14): read/write/list/exists, scoped to the task snapshot root.

Every path argument is resolved through `resolve_within_root` before any
operation touches disk; escapes (`..`, absolute paths outside the root,
symlinks pointing outside it) come back as a structured error, never an
exception across the MCP boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.tools._errors import ToolError, resolve_within_root, task_root

logger = logging.getLogger(__name__)

mcp = FastMCP("filesystem-server")


def read_file(root: Path, rel_path: str) -> str:
    """Read and return the text contents of `rel_path`, scoped to `root`."""
    resolved = resolve_within_root(root, rel_path)
    if not resolved.is_file():
        raise ToolError("not_found", f"No such file: {rel_path!r}")
    try:
        return resolved.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError("read_error", f"Could not read {rel_path!r}: {exc}") from exc


def write_file(root: Path, rel_path: str, content: str) -> None:
    """Write `content` to `rel_path`, scoped to `root`, creating parent dirs as needed."""
    resolved = resolve_within_root(root, rel_path)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
    except OSError as exc:
        raise ToolError("write_error", f"Could not write {rel_path!r}: {exc}") from exc


def list_dir(root: Path, rel_path: str = ".") -> list[str]:
    """List entry names of the directory at `rel_path`, scoped to `root`."""
    resolved = resolve_within_root(root, rel_path)
    if not resolved.is_dir():
        raise ToolError("not_found", f"No such directory: {rel_path!r}")
    return sorted(entry.name for entry in resolved.iterdir())


def path_exists(root: Path, rel_path: str) -> bool:
    """Return whether `rel_path`, scoped to `root`, exists."""
    resolved = resolve_within_root(root, rel_path)
    return resolved.exists()


@mcp.tool(name="read_file")
def read_file_tool(path: str) -> dict[str, object]:
    """Read a file's text contents, scoped to the task root."""
    try:
        content = read_file(task_root(), path)
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True, "content": content}


@mcp.tool(name="write_file")
def write_file_tool(path: str, content: str) -> dict[str, object]:
    """Write text contents to a file, scoped to the task root."""
    try:
        write_file(task_root(), path, content)
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True}


@mcp.tool(name="list_dir")
def list_dir_tool(path: str = ".") -> dict[str, object]:
    """List entry names of a directory, scoped to the task root."""
    try:
        entries = list_dir(task_root(), path)
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True, "entries": entries}


@mcp.tool(name="exists")
def exists_tool(path: str) -> dict[str, object]:
    """Check whether a path exists, scoped to the task root."""
    try:
        found = path_exists(task_root(), path)
    except ToolError as exc:
        return exc.to_dict()
    return {"ok": True, "exists": found}


if __name__ == "__main__":
    mcp.run()
