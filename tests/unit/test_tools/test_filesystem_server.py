"""Unit tests for src/tools/filesystem_server.py pure functions — no Docker required."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools import filesystem_server
from src.tools._errors import ToolError


def test_write_then_read_file(tmp_path: Path) -> None:
    filesystem_server.write_file(tmp_path, "notes.txt", "hello")
    assert filesystem_server.read_file(tmp_path, "notes.txt") == "hello"


def test_write_file_creates_parent_dirs(tmp_path: Path) -> None:
    filesystem_server.write_file(tmp_path, "a/b/c.txt", "nested")
    assert (tmp_path / "a" / "b" / "c.txt").read_text() == "nested"


def test_read_missing_file_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as exc_info:
        filesystem_server.read_file(tmp_path, "missing.txt")
    assert exc_info.value.code == "not_found"


def test_list_dir(tmp_path: Path) -> None:
    (tmp_path / "one.txt").write_text("1")
    (tmp_path / "two.txt").write_text("2")
    assert filesystem_server.list_dir(tmp_path, ".") == ["one.txt", "two.txt"]


def test_exists_true_and_false(tmp_path: Path) -> None:
    (tmp_path / "present.txt").write_text("x")
    assert filesystem_server.path_exists(tmp_path, "present.txt") is True
    assert filesystem_server.path_exists(tmp_path, "absent.txt") is False


def test_read_file_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as exc_info:
        filesystem_server.read_file(tmp_path, "../escape.txt")
    assert exc_info.value.code == "path_escape"


def test_write_file_denies_git_path(tmp_path: Path) -> None:
    """FR-45/FR-46: the allow-list denies writes into `.git/`, before anything touches disk."""
    with pytest.raises(ToolError) as exc_info:
        filesystem_server.write_file(tmp_path, ".git/config", "malicious")
    assert exc_info.value.code == "denied"
    assert not (tmp_path / ".git").exists()


def test_write_file_denies_hidden_test(tmp_path: Path) -> None:
    """FR-45/FR-46: the allow-list denies overwriting the hidden scorer fixture."""
    with pytest.raises(ToolError) as exc_info:
        filesystem_server.write_file(tmp_path, "hidden_test.py", "cheat")
    assert exc_info.value.code == "denied"
    assert not (tmp_path / "hidden_test.py").exists()
