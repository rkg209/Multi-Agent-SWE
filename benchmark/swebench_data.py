"""Resolve a SWE-bench task's issue text and repository checkout, lazily, at solve time.

Only `problem_statement` is read from the dataset. `patch`, `test_patch`, `hints_text`,
`FAIL_TO_PASS` and `PASS_TO_PASS` are deliberately never loaded here, so the gold solution and
hidden tests cannot leak into an agent's prompt.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from benchmark.checkout import SWEBENCH_CACHE_DIR, ensure_checkout
from benchmark.errors import HarnessError
from benchmark.loader import Task

logger = logging.getLogger(__name__)

DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
DATASET_SPLIT = "test"
_FIELDS = ("repo", "base_commit", "problem_statement")


def _cache_path(cache_dir: Path | None) -> Path:
    return (cache_dir or SWEBENCH_CACHE_DIR) / "instances.json"


def _fetch_from_hub(instance_id: str) -> dict[str, str]:
    """Look `instance_id` up in SWE-bench Lite (network on first use only)."""
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise HarnessError("The `datasets` package is required for SWE-bench tasks") from exc
    try:
        dataset = load_dataset(DATASET_NAME, split=DATASET_SPLIT)
    except (OSError, ValueError) as exc:  # hub, network and parquet errors
        raise HarnessError(f"Could not load {DATASET_NAME}: {exc}") from exc
    for row in dataset:
        if row["instance_id"] == instance_id:
            return {field: row[field] for field in _FIELDS}
    raise HarnessError(f"{instance_id!r} not found in {DATASET_NAME}[{DATASET_SPLIT}]")


def load_instance(instance_id: str, cache_dir: Path | None = None) -> dict[str, str]:
    """Return `{repo, base_commit, problem_statement}` for `instance_id`, cached on disk."""
    path = _cache_path(cache_dir)
    cached: dict[str, dict[str, str]] = {}
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = {}
    if instance_id in cached:
        return cached[instance_id]

    record = _fetch_from_hub(instance_id)
    cached[instance_id] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cached, indent=1), encoding="utf-8")
    return record


def hydrate_task(task: Task, cache_dir: Path | None = None) -> Task:
    """Return `task` with real `issue_text`, `repo`, `base_commit` and a `base_dir` checkout."""
    if task.source != "swebench" or task.base_dir is not None:
        return task
    record = load_instance(task.id, cache_dir)
    base_dir = ensure_checkout(record["repo"], record["base_commit"], cache_dir)
    return replace(
        task,
        issue_text=record["problem_statement"],
        repo=record["repo"],
        base_commit=record["base_commit"],
        base_dir=base_dir,
    )
