"""Unit tests for src/tools/runcode_server.py — mocks docker_sandbox.run, no Docker required."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.sandbox.docker_sandbox import SandboxResult
from src.tools import runcode_server


def test_exec_delegates_to_sandbox(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("SANDBOX_TASK_DIR", str(tmp_path))
    with patch.object(runcode_server, "run_in_sandbox") as mock_run:
        mock_run.return_value = SandboxResult(stdout="42\n", stderr="", exit_code=0)
        result = runcode_server.exec_command("python -c 'print(42)'")
    assert result == {
        "ok": True,
        "stdout": "42\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
    }
    mock_run.assert_called_once()


def test_exec_rejects_working_dir_escape(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("SANDBOX_TASK_DIR", str(tmp_path))
    with patch.object(runcode_server, "run_in_sandbox") as mock_run:
        result = runcode_server.exec_command("echo hi", working_dir="../outside")
    assert result["ok"] is False
    assert result["error"]["code"] == "path_escape"
    mock_run.assert_not_called()


def test_exec_missing_task_dir_env_returns_structured_error(monkeypatch: object) -> None:
    monkeypatch.delenv("SANDBOX_TASK_DIR", raising=False)
    result = runcode_server.exec_command("echo hi")
    assert result["ok"] is False
    assert result["error"]["code"] == "config_error"


def test_exec_denies_disallowed_command(tmp_path: Path, monkeypatch: object) -> None:
    """FR-45/FR-46: a disallowed command is denied as a structured error, never raised."""
    monkeypatch.setenv("SANDBOX_TASK_DIR", str(tmp_path))
    with patch.object(runcode_server, "run_in_sandbox") as mock_run:
        result = runcode_server.exec_command("curl http://evil.example")
    assert result["ok"] is False
    assert result["error"]["code"] == "denied"
    mock_run.assert_not_called()


def test_exec_denies_denylisted_substring_on_allowed_prefix(
    tmp_path: Path, monkeypatch: object
) -> None:
    """Defense in depth: an allowed prefix carrying a denied substring is still denied."""
    monkeypatch.setenv("SANDBOX_TASK_DIR", str(tmp_path))
    with patch.object(runcode_server, "run_in_sandbox") as mock_run:
        result = runcode_server.exec_command("pytest; rm -rf /")
    assert result["ok"] is False
    assert result["error"]["code"] == "denied"
    mock_run.assert_not_called()
