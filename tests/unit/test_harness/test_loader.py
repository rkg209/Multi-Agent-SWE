"""Unit tests for `benchmark.loader`."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.errors import HarnessError
from benchmark.loader import load_tasks


def test_load_tasks_real_lite5_and_custom() -> None:
    tasks = load_tasks("lite-5")
    swebench = [t for t in tasks if t.source == "swebench"]
    custom = [t for t in tasks if t.source == "custom"]

    assert len(swebench) == 5
    assert all(t.base_dir is None for t in swebench)
    assert len(custom) == 2
    assert {t.id for t in custom} == {"custom-001-calc-add", "custom-002-str-reverse"}
    for t in custom:
        assert t.base_dir is not None
        assert t.base_dir.is_dir()
        assert t.hidden_tests == ("hidden_test.py",)
        assert t.issue_text


def test_load_tasks_exclude_custom() -> None:
    tasks = load_tasks("lite-5", include_custom=False)
    assert all(t.source == "swebench" for t in tasks)
    assert len(tasks) == 5


def test_unknown_subset_raises() -> None:
    with pytest.raises(HarnessError, match="Unknown task subset"):
        load_tasks("does-not-exist")


def test_over_cap_swebench_refused_without_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big_subset = tmp_path / "big.txt"
    big_subset.write_text("\n".join(f"repo__x-{i}" for i in range(51)), encoding="utf-8")
    monkeypatch.setattr("benchmark.loader.CONFIG_TASKS_DIR", tmp_path)

    with pytest.raises(HarnessError, match="exceeding the cap"):
        load_tasks("big", include_custom=False)


def test_over_cap_swebench_allowed_with_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big_subset = tmp_path / "big.txt"
    big_subset.write_text("\n".join(f"repo__x-{i}" for i in range(51)), encoding="utf-8")
    monkeypatch.setattr("benchmark.loader.CONFIG_TASKS_DIR", tmp_path)

    tasks = load_tasks("big", include_custom=False, override=True)
    assert len(tasks) == 51


def test_over_cap_custom_refused_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchmark.loader.MAX_CUSTOM_TASKS", 1)
    with pytest.raises(HarnessError, match="exceed the cap"):
        load_tasks("lite-5")


def test_comment_and_blank_lines_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subset = tmp_path / "mini.txt"
    subset.write_text("# a comment\n\nrepo__x-1\n\nrepo__x-2\n", encoding="utf-8")
    monkeypatch.setattr("benchmark.loader.CONFIG_TASKS_DIR", tmp_path)

    tasks = load_tasks("mini", include_custom=False)
    assert [t.id for t in tasks] == ["repo__x-1", "repo__x-2"]


def test_custom_tickets_expose_visible_tests_but_not_hidden_ones() -> None:
    custom = [t for t in load_tasks("lite-5") if t.source == "custom"]
    assert custom
    for task in custom:
        assert [p.name for p in task.visible_tests] == ["visible_test.py"]
        assert task.hidden_tests == ("hidden_test.py",)
        assert not (task.base_dir / "hidden_test.py").exists()  # type: ignore[operator]
