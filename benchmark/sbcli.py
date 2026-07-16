"""Thin wrapper around the real `sb-cli` binary (FR-21) — never reimplement SWE-bench scoring.

`sb-cli` is a hosted-API CLI (confirmed against the installed `0.1.5` package): it requires
`SWEBENCH_API_KEY`, uploads a predictions file via `sb-cli submit <subset> <split>
--predictions_path ... --run_id ... --instance_ids ... -o <dir>`, and writes a report JSON to
`<dir>/<subset>__<split>__<run_id>.json`. This module builds the one-line predictions file, shells
out, and parses that report — it never talks to the API directly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from benchmark.errors import HarnessError

DEFAULT_SUBSET = "swe-bench_lite"
DEFAULT_SPLIT = "test"
DEFAULT_TIMEOUT_SECONDS = 600


def sb_cli_available() -> bool:
    """Return True if the `sb-cli` binary is on PATH and `SWEBENCH_API_KEY` is set."""
    return shutil.which("sb-cli") is not None and bool(os.environ.get("SWEBENCH_API_KEY"))


def _write_predictions_file(path: Path, task_id: str, patch: str) -> None:
    """Write a one-instance predictions JSON file in the shape `sb-cli submit` expects."""
    predictions = [
        {
            "instance_id": task_id,
            "model_patch": patch,
            "model_name_or_path": "swe-agent-harness",
        }
    ]
    path.write_text(json.dumps(predictions), encoding="utf-8")


def _report_path(output_dir: Path, subset: str, split: str, run_id: str) -> Path:
    return output_dir / f"{subset}__{split}__{run_id}.json"


def run_sbcli_eval(
    task_id: str,
    patch: str,
    *,
    run_id: str,
    output_dir: Path,
    subset: str = DEFAULT_SUBSET,
    split: str = DEFAULT_SPLIT,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Submit `patch` for `task_id` to the SWE-bench API via `sb-cli`; return whether it resolved.

    Args:
        task_id: SWE-bench instance ID.
        patch: Unified diff to evaluate (may be empty).
        run_id: Run identifier passed to `sb-cli --run_id`.
        output_dir: Directory `sb-cli` writes its report JSON into.
        subset: SWE-bench subset name (`sb-cli`'s `Subset` enum value).
        split: Dataset split.
        timeout: Seconds allowed for the `sb-cli submit` subprocess.

    Returns:
        True if `task_id` resolved (PASS), False otherwise.

    Raises:
        HarnessError: `sb-cli` is unavailable (missing binary or `SWEBENCH_API_KEY`), the subprocess
            fails or times out, or the report is missing/unparseable.
    """
    if not sb_cli_available():
        raise HarnessError(
            "sb-cli unavailable: SWEBENCH_API_KEY is not set or the sb-cli binary is not on PATH"
        )

    # sb-cli's own `get_report` only overwrites an existing report file when `--overwrite 1`
    # (default 0); calling it twice for the same subset/split/run_id silently diverts the second
    # report to a `-1`-suffixed file instead. We call `sb-cli submit` once per task, so the run_id
    # passed to sb-cli must be scoped per-task (not the shared benchmark run_id) or every task
    # after the first would read back the first task's stale report.
    sbcli_run_id = f"{run_id}-{task_id}"

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / f"{sbcli_run_id}-predictions.json"
    _write_predictions_file(predictions_path, task_id, patch)

    cmd = [
        "sb-cli",
        "submit",
        subset,
        split,
        "--predictions_path",
        str(predictions_path),
        "--run_id",
        sbcli_run_id,
        "--instance_ids",
        task_id,
        "-o",
        str(output_dir),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"sb-cli submit timed out for {task_id}") from exc
    except subprocess.CalledProcessError as exc:
        raise HarnessError(f"sb-cli submit failed for {task_id}: {exc.stderr}") from exc

    report_path = _report_path(output_dir, subset, split, sbcli_run_id)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HarnessError(f"sb-cli did not write a report at {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessError(f"sb-cli report at {report_path} is not valid JSON: {exc}") from exc

    resolved_ids = report.get("resolved_ids")
    if resolved_ids is not None:
        return task_id in resolved_ids
    # Defensive fallback if the API's report schema omits per-instance IDs: for a
    # single-instance submission, resolved_instances >= 1 means that instance resolved.
    return int(report.get("resolved_instances", 0)) >= 1
