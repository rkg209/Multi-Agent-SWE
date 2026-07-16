"""Unit tests for `benchmark.scorer`. Sandbox and sb-cli are mocked; no Docker/network required."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from benchmark.errors import HarnessError
from benchmark.loader import Task
from benchmark.scorer import ScoreResult, score
from benchmark.solver import Patch
from src.sandbox.docker_sandbox import SandboxResult


def _custom_task(tmp_path: Path) -> Task:
    base_dir = tmp_path / "ticket" / "base"
    base_dir.mkdir(parents=True)
    (base_dir / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "ticket" / "hidden_test.py").write_text(
        "from mod import f\ndef test_f():\n    assert f() == 1\n", encoding="utf-8"
    )
    return Task(
        id="custom-fixture",
        source="custom",
        issue_text="fix f",
        hidden_tests=("hidden_test.py",),
        base_dir=base_dir,
    )


def test_score_custom_pass_when_sandbox_exits_zero(tmp_path: Path) -> None:
    task = _custom_task(tmp_path)
    with patch(
        "benchmark.scorer.run_in_sandbox",
        return_value=SandboxResult(stdout="1 passed", stderr="", exit_code=0),
    ) as mock_run:
        result = score(task, Patch(diff=""), run_id="r1")

    assert result == ScoreResult(outcome="PASS")
    mock_run.assert_called_once()
    assert "pytest hidden_test.py" in mock_run.call_args.args[0]


def test_score_custom_fail_when_sandbox_exits_nonzero(tmp_path: Path) -> None:
    task = _custom_task(tmp_path)
    with patch(
        "benchmark.scorer.run_in_sandbox",
        return_value=SandboxResult(stdout="", stderr="1 failed", exit_code=1),
    ):
        result = score(task, Patch(diff=""), run_id="r1")

    assert result.outcome == "FAIL"
    assert result.reason is not None


def test_score_custom_fail_on_harness_error(tmp_path: Path) -> None:
    task = _custom_task(tmp_path)
    with patch(
        "benchmark.scorer.run_in_sandbox",
        return_value=SandboxResult(stdout="", stderr="", exit_code=-1, timed_out=True),
    ):
        result = score(task, Patch(diff=""), run_id="r1")

    assert result.outcome == "FAIL"
    assert "harness error" in (result.reason or "")


def test_score_custom_bad_patch_fails_without_running_sandbox(tmp_path: Path) -> None:
    task = _custom_task(tmp_path)
    with patch("benchmark.scorer.run_in_sandbox") as mock_run:
        result = score(task, Patch(diff="not a real diff"), run_id="r1")

    assert result.outcome == "FAIL"
    assert "did not apply" in (result.reason or "")
    mock_run.assert_not_called()


def test_score_custom_determinism(tmp_path: Path) -> None:
    task = _custom_task(tmp_path)
    with patch(
        "benchmark.scorer.run_in_sandbox",
        return_value=SandboxResult(stdout="1 passed", stderr="", exit_code=0),
    ):
        first = score(task, Patch(diff=""), run_id="r1")
        second = score(task, Patch(diff=""), run_id="r2")

    assert first == second == ScoreResult(outcome="PASS")


def test_score_custom_missing_base_dir_raises() -> None:
    task = Task(id="broken", source="custom", issue_text="", hidden_tests=(), base_dir=None)
    with pytest.raises(HarnessError, match="no base_dir"):
        score(task, Patch(diff=""), run_id="r1")


def test_score_swebench_delegates_to_sbcli(tmp_path: Path) -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    with patch("benchmark.scorer.run_sbcli_eval", return_value=True) as mock_eval:
        result = score(task, Patch(diff=""), run_id="r1", sbcli_output_dir=tmp_path)

    assert result == ScoreResult(outcome="PASS")
    mock_eval.assert_called_once_with("repo__x-1", "", run_id="r1", output_dir=tmp_path)


def test_score_swebench_harness_error_becomes_fail(tmp_path: Path) -> None:
    task = Task(id="repo__x-1", source="swebench", issue_text="")
    with patch("benchmark.scorer.run_sbcli_eval", side_effect=HarnessError("sb-cli unavailable")):
        result = score(task, Patch(diff=""), run_id="r1", sbcli_output_dir=tmp_path)

    assert result.outcome == "FAIL"
    assert "sb-cli unavailable" in (result.reason or "")


def test_score_unknown_source_raises() -> None:
    task = Task(id="x", source="bogus", issue_text="")
    with pytest.raises(HarnessError, match="Unknown task source"):
        score(task, Patch(diff=""), run_id="r1")
