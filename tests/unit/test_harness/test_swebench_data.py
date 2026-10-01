"""Unit tests for `benchmark.checkout` and `benchmark.swebench_data` (no network, no real git)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch as mock_patch

import pytest

from benchmark import checkout, swebench_data
from benchmark.errors import HarnessError
from benchmark.loader import Task

SHA = "d26b2424437dabeeca94d7900b37d2df4410da0c"


def test_ensure_checkout_rejects_malformed_inputs(tmp_path: Path) -> None:
    with pytest.raises(HarnessError):
        checkout.ensure_checkout("not a repo; rm -rf /", SHA, tmp_path)
    with pytest.raises(HarnessError):
        checkout.ensure_checkout("django/django", "--upload-pack=evil", tmp_path)


def test_ensure_checkout_uses_cache_without_git(tmp_path: Path) -> None:
    cached = tmp_path / f"django__django__{SHA[:12]}"
    cached.mkdir()
    with mock_patch("benchmark.checkout._git") as git:
        assert checkout.ensure_checkout("django/django", SHA, tmp_path) == cached
    git.assert_not_called()


def test_ensure_checkout_strips_dot_git_and_caches(tmp_path: Path) -> None:
    def fake_git(cwd: Path, args: list[str]) -> None:
        if args[0] == "checkout":
            (cwd / "pkg").mkdir()
            (cwd / "pkg" / "a.py").write_text("x = 1\n")
            (cwd / ".git").mkdir()
            (cwd / ".git" / "HEAD").write_text("ref")

    with mock_patch("benchmark.checkout._git", side_effect=fake_git) as git:
        result = checkout.ensure_checkout("django/django", SHA, tmp_path)

    assert (result / "pkg" / "a.py").read_text() == "x = 1\n"
    assert not (result / ".git").exists()
    assert [c.args[1][0] for c in git.call_args_list] == ["init", "remote", "fetch", "checkout"]
    assert not list(tmp_path.glob(".tmp-*")) and not list(tmp_path.glob(".stage-*"))


def test_load_instance_reads_only_needed_fields_and_caches(tmp_path: Path) -> None:
    record = {"repo": "django/django", "base_commit": SHA, "problem_statement": "bug"}
    with mock_patch("benchmark.swebench_data._fetch_from_hub", return_value=record) as fetch:
        first = swebench_data.load_instance("django__django-1", tmp_path)
        second = swebench_data.load_instance("django__django-1", tmp_path)
    assert first == second == record
    fetch.assert_called_once()
    assert set(json.loads((tmp_path / "instances.json").read_text())["django__django-1"]) == {
        "repo",
        "base_commit",
        "problem_statement",
    }


def test_hydrate_task_fills_issue_repo_and_base_dir(tmp_path: Path) -> None:
    record = {"repo": "django/django", "base_commit": SHA, "problem_statement": "bug"}
    with (
        mock_patch("benchmark.swebench_data.load_instance", return_value=record),
        mock_patch("benchmark.swebench_data.ensure_checkout", return_value=tmp_path) as co,
    ):
        task = swebench_data.hydrate_task(
            Task(id="django__django-1", source="swebench", issue_text="")
        )
    assert (task.issue_text, task.repo, task.base_commit, task.base_dir) == (
        "bug",
        "django/django",
        SHA,
        tmp_path,
    )
    co.assert_called_once()


def test_hydrate_task_leaves_custom_tasks_alone() -> None:
    task = Task(id="custom-1", source="custom", issue_text="x")
    assert swebench_data.hydrate_task(task) is task
