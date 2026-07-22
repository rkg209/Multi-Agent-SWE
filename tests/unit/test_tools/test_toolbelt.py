"""Unit tests for src/tools/toolbelt.py — no Docker required (docker_sandbox.run is mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.sandbox.docker_sandbox import SandboxResult
from src.tools import runcode_server
from src.tools._errors import ToolError
from src.tools.toolbelt import ToolBelt, sandbox_task_dir


def test_read_write_list_delegate_to_filesystem_server(tmp_path: Path) -> None:
    belt = ToolBelt(tmp_path)
    belt.write_file("a.txt", "hello")
    assert belt.read_file("a.txt") == "hello"
    assert "a.txt" in belt.list_dir(".")


def test_write_file_path_escape_raises_tool_error(tmp_path: Path) -> None:
    belt = ToolBelt(tmp_path)
    with pytest.raises(ToolError) as exc_info:
        belt.write_file("../escape.txt", "nope")
    assert exc_info.value.code == "path_escape"


def test_exec_reaches_docker_sandbox_run_not_subprocess(tmp_path: Path) -> None:
    belt = ToolBelt(tmp_path)
    with sandbox_task_dir(tmp_path):
        with patch.object(runcode_server, "run_in_sandbox") as mock_run:
            mock_run.return_value = SandboxResult(stdout="ok\n", stderr="", exit_code=0)
            result = belt.exec("pytest -q")
    assert result.stdout == "ok\n"
    assert result.exit_code == 0
    mock_run.assert_called_once()


def test_exec_raises_tool_error_when_task_dir_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SANDBOX_TASK_DIR", raising=False)
    belt = ToolBelt(Path("/nonexistent"))
    with pytest.raises(ToolError) as exc_info:
        belt.exec("echo hi")
    assert exc_info.value.code == "config_error"


def test_diff_delegates_to_git_server(tmp_path: Path) -> None:
    belt = ToolBelt(tmp_path)
    (tmp_path / "f.txt").write_text("x")
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.com", "commit", "-q", "-m", "baseline"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "f.txt").write_text("y")
    assert "f.txt" in belt.diff()


def test_sandbox_task_dir_restores_previous_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANDBOX_TASK_DIR", "/original")
    with sandbox_task_dir(tmp_path):
        import os

        assert os.environ["SANDBOX_TASK_DIR"] == str(tmp_path)
    import os

    assert os.environ["SANDBOX_TASK_DIR"] == "/original"
