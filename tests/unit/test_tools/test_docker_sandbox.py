"""Unit tests for src/sandbox/docker_sandbox.py — no Docker required."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from src.sandbox import docker_sandbox

TASK_DIR = Path("/tmp/some-task-dir")


def test_build_docker_command_hardening_flags() -> None:
    cmd = docker_sandbox.build_docker_command("echo hi", TASK_DIR)
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert "--network" in cmd
    assert cmd[cmd.index("--network") + 1] == "none"
    assert "--cap-drop" in cmd
    assert cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert "--read-only" in cmd
    assert "--user" in cmd
    assert cmd[cmd.index("--user") + 1] == "sandbox"
    assert "--tmpfs" in cmd
    assert cmd[cmd.index("--tmpfs") + 1] == "/tmp"


def test_build_docker_command_mount_and_workdir() -> None:
    cmd = docker_sandbox.build_docker_command("echo hi", TASK_DIR)
    mount_arg = cmd[cmd.index("-v") + 1]
    assert mount_arg == f"{TASK_DIR}:/workspace:rw"
    assert "-w" in cmd
    assert cmd[cmd.index("-w") + 1] == "/workspace"


def test_build_docker_command_runs_via_shell() -> None:
    cmd = docker_sandbox.build_docker_command("echo hi", TASK_DIR)
    assert cmd[-1] == "echo hi"
    assert "-lc" in cmd
    assert docker_sandbox.SANDBOX_IMAGE in cmd


def test_run_maps_timeout_to_harness_error() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=1)
        result = docker_sandbox.run("sleep 999", TASK_DIR, timeout=1)
    assert result.timed_out is True
    assert result.exit_code == -1


def test_run_maps_missing_docker_binary_to_harness_error() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = OSError("docker not found")
        result = docker_sandbox.run("echo hi", TASK_DIR)
    assert result.timed_out is True
    assert result.exit_code == -1


def test_run_returns_normal_result_on_success() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker"], returncode=0, stdout="42\n", stderr=""
        )
        result = docker_sandbox.run("python -c 'print(42)'", TASK_DIR)
    assert result.exit_code == 0
    assert result.stdout == "42\n"
    assert result.timed_out is False
