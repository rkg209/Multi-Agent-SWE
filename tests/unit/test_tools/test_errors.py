"""Unit tests for src/tools/_errors.py path-scoping guard — no Docker required."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools._errors import ToolError, resolve_within_root


def test_resolve_within_root_accepts_nested_path(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    resolved = resolve_within_root(tmp_path, "sub/file.txt")
    assert resolved == tmp_path / "sub" / "file.txt"


def test_resolve_within_root_rejects_dotdot_escape(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as exc_info:
        resolve_within_root(tmp_path, "../escape.txt")
    assert exc_info.value.code == "path_escape"


def test_resolve_within_root_rejects_absolute_escape(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as exc_info:
        resolve_within_root(tmp_path, "/etc/passwd")
    assert exc_info.value.code == "path_escape"


def test_resolve_within_root_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_target.txt"
    outside.write_text("secret")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(ToolError) as exc_info:
        resolve_within_root(tmp_path, "link.txt")
    assert exc_info.value.code == "path_escape"
    outside.unlink()


def test_tool_error_to_dict_shape() -> None:
    err = ToolError("path_escape", "nope")
    assert err.to_dict() == {"ok": False, "error": {"code": "path_escape", "message": "nope"}}
