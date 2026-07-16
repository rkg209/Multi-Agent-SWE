"""Unit tests for src/tools/git_server.py — real host git on a temp repo, no Docker required."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.tools import git_server
from src.tools._errors import ToolError


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "file.txt").write_text("baseline\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    git_server.git_commit(tmp_path, "baseline commit")
    return tmp_path


def test_diff_empty_on_clean_repo(git_repo: Path) -> None:
    assert git_server.git_diff(git_repo) == ""


def test_diff_shows_uncommitted_change(git_repo: Path) -> None:
    (git_repo / "file.txt").write_text("changed\n")
    diff = git_server.git_diff(git_repo)
    assert "changed" in diff


def test_stage_and_commit(git_repo: Path) -> None:
    (git_repo / "file.txt").write_text("changed\n")
    git_server.git_stage(git_repo, ["file.txt"])
    sha = git_server.git_commit(git_repo, "second commit")
    assert len(sha) == 40
    assert git_server.git_diff(git_repo) == ""


def test_stage_rejects_path_escape(git_repo: Path) -> None:
    with pytest.raises(ToolError) as exc_info:
        git_server.git_stage(git_repo, ["../escape.txt"])
    assert exc_info.value.code == "path_escape"


def test_commit_with_nothing_staged_raises_git_error(git_repo: Path) -> None:
    with pytest.raises(ToolError) as exc_info:
        git_server.git_commit(git_repo, "empty commit")
    assert exc_info.value.code == "git_error"
