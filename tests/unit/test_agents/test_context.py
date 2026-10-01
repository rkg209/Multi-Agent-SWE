"""Unit tests for `src.agents.context` (file selection for real repositories)."""

from __future__ import annotations

from pathlib import Path

from src.agents import context


def _make_repo(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _big_repo(root: Path) -> None:
    files = {f"pkg/filler_{i}.py": f"def filler_{i}(): pass\n" for i in range(25)}
    files["pkg/core/validators.py"] = "class UsernameValidator:\n    regex = r'^[\\w.@+-]+$'\n"
    files["pkg/http/response.py"] = "class HttpResponse:\n    pass\n"
    files["pkg/tests/test_validators.py"] = "UsernameValidator = 1\n"
    _make_repo(root, files)


def test_flat_repo_is_not_large(tmp_path: Path) -> None:
    _make_repo(tmp_path, {"calculator.py": "x = 1\n", "hidden_test.py": "y\n"})
    assert not context.is_large_repo(tmp_path)


def test_large_repo_detected_and_tests_excluded(tmp_path: Path) -> None:
    _big_repo(tmp_path)
    assert context.is_large_repo(tmp_path)
    assert not any("test" in f for f in context.list_source_files(tmp_path))


def test_identifier_in_issue_ranks_defining_file_first(tmp_path: Path) -> None:
    _big_repo(tmp_path)
    ranked = context.rank_files(tmp_path, "UsernameValidator allows a trailing newline")
    assert ranked[0] == "pkg/core/validators.py"


def test_dotted_module_and_explicit_path_in_issue(tmp_path: Path) -> None:
    _big_repo(tmp_path)
    assert context.rank_files(tmp_path, "see pkg.http.response.HttpResponse")[0] == (
        "pkg/http/response.py"
    )
    assert context.rank_files(tmp_path, "edit core/validators.py please")[0] == (
        "pkg/core/validators.py"
    )


def test_plan_files_take_priority_and_resolve_by_basename(tmp_path: Path) -> None:
    _big_repo(tmp_path)
    ranked = context.rank_files(tmp_path, "UsernameValidator bug", plan_files=["response.py"])
    assert ranked[0] == "pkg/http/response.py"


def test_select_respects_file_count_and_char_budget(tmp_path: Path) -> None:
    _big_repo(tmp_path)
    (tmp_path / "pkg" / "huge.py").write_text("# UsernameValidator\n" + "x = 1\n" * 40_000)
    chosen = context.select_context_files(tmp_path, "UsernameValidator huge")
    assert len(chosen) <= context.MAX_CONTEXT_FILES
    assert "pkg/huge.py" not in chosen  # larger than the per-file limit
    assert "pkg/core/validators.py" in chosen


def test_digit_leading_snake_name_matches_migration_filename(tmp_path: Path) -> None:
    _big_repo(tmp_path)
    _make_repo(tmp_path, {"pkg/migrations/0011_update_proxy_permissions.py": "pass\n"})
    ranked = context.rank_files(tmp_path, "Migration auth.0011_update_proxy_permissions fails")
    assert ranked[0] == "pkg/migrations/0011_update_proxy_permissions.py"


def test_clip_diff_caps_runaway_diffs() -> None:
    assert context.clip_diff("small") == "small"
    clipped = context.clip_diff("x" * (context.MAX_DIFF_CHARS + 500))
    assert len(clipped) < context.MAX_DIFF_CHARS + 100
    assert "diff truncated: 500 more chars" in clipped
