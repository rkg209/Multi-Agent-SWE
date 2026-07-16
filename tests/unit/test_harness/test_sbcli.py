"""Unit tests for `benchmark.sbcli` — the real `sb-cli` binary is never invoked here."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmark.errors import HarnessError
from benchmark.sbcli import run_sbcli_eval, sb_cli_available


def _fake_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchmark.sbcli.shutil.which", lambda _: "/usr/local/bin/sb-cli")
    monkeypatch.setenv("SWEBENCH_API_KEY", "fake-key")


def test_sb_cli_available_false_without_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchmark.sbcli.shutil.which", lambda _: None)
    monkeypatch.setenv("SWEBENCH_API_KEY", "fake-key")
    assert sb_cli_available() is False


def test_sb_cli_available_false_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchmark.sbcli.shutil.which", lambda _: "/usr/local/bin/sb-cli")
    monkeypatch.delenv("SWEBENCH_API_KEY", raising=False)
    assert sb_cli_available() is False


def test_run_sbcli_eval_raises_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("benchmark.sbcli.shutil.which", lambda _: None)
    monkeypatch.delenv("SWEBENCH_API_KEY", raising=False)

    with pytest.raises(HarnessError, match="sb-cli unavailable"):
        run_sbcli_eval("repo__x-1", "", run_id="r1", output_dir=tmp_path)


def test_run_sbcli_eval_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_available(monkeypatch)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        report_path = tmp_path / "swe-bench_lite__test__r1-repo__x-1.json"
        report_path.write_text(
            json.dumps({"resolved_ids": ["repo__x-1"], "resolved_instances": 1}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("benchmark.sbcli.subprocess.run", side_effect=fake_run) as mock_run:
        result = run_sbcli_eval("repo__x-1", "diff --git a b", run_id="r1", output_dir=tmp_path)

    assert result is True
    mock_run.assert_called_once()
    called_cmd = mock_run.call_args.args[0]
    assert called_cmd[:3] == ["sb-cli", "submit", "swe-bench_lite"]
    assert "--instance_ids" in called_cmd


def test_run_sbcli_eval_unresolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_available(monkeypatch)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        report_path = tmp_path / "swe-bench_lite__test__r1-repo__x-1.json"
        report_path.write_text(
            json.dumps({"resolved_ids": [], "resolved_instances": 0}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("benchmark.sbcli.subprocess.run", side_effect=fake_run):
        result = run_sbcli_eval("repo__x-1", "", run_id="r1", output_dir=tmp_path)

    assert result is False


def test_run_sbcli_eval_fallback_without_resolved_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_available(monkeypatch)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        report_path = tmp_path / "swe-bench_lite__test__r1-repo__x-1.json"
        report_path.write_text(json.dumps({"resolved_instances": 1}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("benchmark.sbcli.subprocess.run", side_effect=fake_run):
        result = run_sbcli_eval("repo__x-1", "", run_id="r1", output_dir=tmp_path)

    assert result is True


def test_run_sbcli_eval_scopes_run_id_per_task_to_avoid_report_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two tasks sharing one benchmark run_id must not read back each other's report.

    Regression test: sb-cli's own `get_report` only overwrites an existing report file when
    `--overwrite 1` (default 0) — calling `sb-cli submit` twice for the same subset/split/run_id
    would otherwise silently divert the second report to a `-1`-suffixed file, leaving
    `run_sbcli_eval` reading the first task's stale report for every task after it.
    """
    _fake_available(monkeypatch)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        run_id_arg = cmd[cmd.index("--run_id") + 1]
        instance_id_arg = cmd[cmd.index("--instance_ids") + 1]
        resolved = instance_id_arg == "repo__x-1"
        report_path = tmp_path / f"swe-bench_lite__test__{run_id_arg}.json"
        report_path.write_text(
            json.dumps({"resolved_ids": [instance_id_arg] if resolved else []}), encoding="utf-8"
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("benchmark.sbcli.subprocess.run", side_effect=fake_run):
        first = run_sbcli_eval("repo__x-1", "", run_id="shared-run", output_dir=tmp_path)
        second = run_sbcli_eval("repo__x-2", "", run_id="shared-run", output_dir=tmp_path)

    assert first is True
    assert second is False


def test_run_sbcli_eval_process_error_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_available(monkeypatch)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, cmd, stderr="boom")

    with patch("benchmark.sbcli.subprocess.run", side_effect=fake_run):
        with pytest.raises(HarnessError, match="sb-cli submit failed"):
            run_sbcli_eval("repo__x-1", "", run_id="r1", output_dir=tmp_path)


def test_run_sbcli_eval_missing_report_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_available(monkeypatch)

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("benchmark.sbcli.subprocess.run", side_effect=fake_run):
        with pytest.raises(HarnessError, match="did not write a report"):
            run_sbcli_eval("repo__x-1", "", run_id="r1", output_dir=tmp_path)
