"""Action allow-list (FR-46, NFR-4): the single authoritative gate for writes and exec.

Checked inside `src/tools/filesystem_server.write_file` and
`src/tools/runcode_server.exec_command` — the pure functions `ToolBelt` calls
directly — not inside the `@mcp.tool()` wrappers, so both the in-process agent
path and the MCP stdio transport are covered by one check.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass

import yaml

from src.errors import GuardrailError

DEFAULT_CONFIG_PATH = "config/allowlist.yaml"


@dataclass(frozen=True)
class Decision:
    """The allow-list's verdict on one write or exec attempt."""

    allowed: bool
    code: str = ""
    message: str = ""


@dataclass(frozen=True)
class AllowlistConfig:
    """Parsed `config/allowlist.yaml`: denied write patterns and exec rules."""

    denied_path_patterns: tuple[str, ...]
    allowed_command_prefixes: tuple[str, ...]
    denied_substrings: tuple[str, ...]


def load_allowlist_config(path: str = DEFAULT_CONFIG_PATH) -> AllowlistConfig:
    """Parse the YAML allow-list at `path`, raising `GuardrailError` on any failure.

    Unlike the budget config, there is no silent fallback: an unreadable or
    malformed allow-list must fail closed rather than default to permissive.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except OSError as exc:
        raise GuardrailError(f"Could not read allow-list config at {path!r}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise GuardrailError(f"Invalid YAML in allow-list config at {path!r}: {exc}") from exc

    if not isinstance(raw, dict):
        raise GuardrailError(f"Allow-list config at {path!r} must be a mapping")

    write_raw = raw.get("write") or {}
    exec_raw = raw.get("exec") or {}
    if not isinstance(write_raw, dict) or not isinstance(exec_raw, dict):
        raise GuardrailError(f"Allow-list config at {path!r} has malformed 'write'/'exec' sections")

    return AllowlistConfig(
        denied_path_patterns=tuple(write_raw.get("denied_path_patterns") or ()),
        allowed_command_prefixes=tuple(exec_raw.get("allowed_command_prefixes") or ()),
        denied_substrings=tuple(exec_raw.get("denied_substrings") or ()),
    )


def check_write(rel_path: str, config: AllowlistConfig) -> Decision:
    """Deny `rel_path` if it matches any `denied_path_patterns` glob, else allow it."""
    for pattern in config.denied_path_patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return Decision(
                allowed=False,
                code="denied",
                message=f"Write to {rel_path!r} denied: matches pattern {pattern!r}",
            )
    return Decision(allowed=True)


def check_exec(command: str, config: AllowlistConfig) -> Decision:
    """Deny `command` unless its first token is an allowed prefix and it has no denied substring.

    Defense in depth: a command carrying a denied substring is rejected even
    if its first token is an allowed prefix (e.g. `pytest; rm -rf /`).
    """
    for substring in config.denied_substrings:
        if substring in command:
            return Decision(
                allowed=False,
                code="denied",
                message=f"Command denied: contains {substring!r}",
            )

    first_token = command.strip().split(" ", 1)[0] if command.strip() else ""
    if first_token not in config.allowed_command_prefixes:
        return Decision(
            allowed=False,
            code="denied",
            message=f"Command {first_token!r} is not in the allowed command prefixes",
        )
    return Decision(allowed=True)
