"""Unit tests for `src.guardrails.allowlist` — the FR-45/FR-46/NFR-4 gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.errors import GuardrailError
from src.guardrails.allowlist import (
    AllowlistConfig,
    check_exec,
    check_write,
    load_allowlist_config,
)

TEST_CONFIG = AllowlistConfig(
    denied_path_patterns=(".git/**", "hidden_test.py"),
    allowed_command_prefixes=("pytest", "python", "git"),
    denied_substrings=("rm -rf", "curl "),
)


def test_check_write_allows_ordinary_path() -> None:
    assert check_write("calculator.py", TEST_CONFIG).allowed is True


def test_check_write_denies_git_directory() -> None:
    decision = check_write(".git/config", TEST_CONFIG)
    assert decision.allowed is False
    assert decision.code == "denied"


def test_check_write_denies_hidden_test() -> None:
    assert check_write("hidden_test.py", TEST_CONFIG).allowed is False


def test_check_exec_allows_listed_prefix() -> None:
    assert check_exec("pytest -q", TEST_CONFIG).allowed is True


def test_check_exec_denies_unlisted_command() -> None:
    decision = check_exec("curl http://evil.example", TEST_CONFIG)
    assert decision.allowed is False
    assert decision.code == "denied"


def test_check_exec_denies_rm_rf() -> None:
    assert check_exec("rm -rf /", TEST_CONFIG).allowed is False


def test_check_exec_denies_denied_substring_on_allowed_prefix() -> None:
    """Defense in depth: an allowed prefix carrying a denied substring is still denied."""
    assert check_exec("pytest; rm -rf /", TEST_CONFIG).allowed is False


def test_load_allowlist_config_reads_real_file() -> None:
    config = load_allowlist_config("config/allowlist.yaml")
    assert "pytest" in config.allowed_command_prefixes
    assert ".git/**" in config.denied_path_patterns


def test_load_allowlist_config_missing_file_raises() -> None:
    """Unlike the budget config, a missing allow-list must fail closed, not default-permissive."""
    with pytest.raises(GuardrailError):
        load_allowlist_config("config/does-not-exist.yaml")


def test_load_allowlist_config_malformed_yaml_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "allowlist.yaml"
    bad_file.write_text("write: [this is not a mapping")
    with pytest.raises(GuardrailError):
        load_allowlist_config(str(bad_file))


def test_gate_is_wired_into_both_tool_servers() -> None:
    """NFR-4: the allow-list must guard the pure functions `ToolBelt` actually calls.

    A check added only to the `@mcp.tool()` wrappers would be dead code for
    the in-process agent path (`ToolBelt` never goes through MCP stdio) —
    this structural test (mirrors `test_no_direct_provider_sdk_imports`)
    catches that regression directly.
    """
    repo_root = Path(__file__).resolve().parents[3]
    fs_source = (repo_root / "src" / "tools" / "filesystem_server.py").read_text()
    exec_source = (repo_root / "src" / "tools" / "runcode_server.py").read_text()
    assert "check_write(" in fs_source
    assert "check_exec(" in exec_source
