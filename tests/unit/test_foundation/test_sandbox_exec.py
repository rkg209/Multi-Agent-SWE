"""Unit tests for scripts/sandbox_exec.py — no Docker required."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sandbox_exec  # noqa: E402


def test_build_docker_command_basic() -> None:
    script_path = SCRIPTS_DIR / "hello_sandbox.py"
    cmd = sandbox_exec.build_docker_command(script_path, "")
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert cmd[-1] == "/workspace/scripts/hello_sandbox.py"


def test_build_docker_command_with_args() -> None:
    script_path = SCRIPTS_DIR / "hello_sandbox.py"
    cmd = sandbox_exec.build_docker_command(script_path, "--foo bar --baz")
    assert cmd[-4:] == ["/workspace/scripts/hello_sandbox.py", "--foo", "bar", "--baz"]


def test_script_not_found_raises() -> None:
    with pytest.raises(FileNotFoundError):
        sandbox_exec.resolve_script_path("scripts/does_not_exist.py")


def test_network_none_in_command() -> None:
    script_path = SCRIPTS_DIR / "hello_sandbox.py"
    cmd = sandbox_exec.build_docker_command(script_path, "")
    assert "--network" in cmd
    assert cmd[cmd.index("--network") + 1] == "none"


def test_readonly_mount_in_command() -> None:
    script_path = SCRIPTS_DIR / "hello_sandbox.py"
    cmd = sandbox_exec.build_docker_command(script_path, "")
    mount_arg = cmd[cmd.index("-v") + 1]
    assert mount_arg.endswith(":ro")


def test_main_forwards_exit_code() -> None:
    with (
        patch.object(
            sandbox_exec, "resolve_script_path", return_value=SCRIPTS_DIR / "hello_sandbox.py"
        ),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 7
        exit_code = sandbox_exec.main(["--script", "scripts/hello_sandbox.py"])
    assert exit_code == 7
