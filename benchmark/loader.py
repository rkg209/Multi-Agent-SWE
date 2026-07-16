"""Task loader: resolves a subset id + the in-repo custom tickets into a uniform `Task` list.

Two sources (FR-20), one shape:
- SWE-bench: instance IDs listed in a version-locked `config/tasks/<subset_id>.txt` (NFR-7). Full
  issue text/repo state is resolved by `sb-cli` itself at scoring time (Spec 03 doesn't reimplement
  dataset fetching); only the instance ID matters here.
- Custom: tickets under `benchmark/tasks/custom/<id>/` (`issue.md`, `base/`, `hidden_test.py`,
  `meta.json`), fully self-contained in-repo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from benchmark.errors import HarnessError

MAX_SWEBENCH_TASKS = 50
MAX_CUSTOM_TASKS = 5

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_TASKS_DIR = REPO_ROOT / "config" / "tasks"
CUSTOM_TASKS_DIR = Path(__file__).resolve().parent / "tasks" / "custom"


@dataclass(frozen=True)
class Task:
    """A uniform task shape covering both SWE-bench and custom tickets."""

    id: str
    source: str  # "swebench" | "custom"
    issue_text: str
    hidden_tests: tuple[str, ...] = ()
    base_dir: Path | None = None  # only set for source="custom"


def _load_swebench_ids(subset_id: str) -> list[str]:
    """Read the version-locked instance-ID list for `subset_id` from `config/tasks/`."""
    config_path = CONFIG_TASKS_DIR / f"{subset_id}.txt"
    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"Unknown task subset {subset_id!r}: {config_path} not found") from exc

    return [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")]


def _load_custom_tickets() -> list[Task]:
    """Load every custom ticket under `benchmark/tasks/custom/` into a `Task`."""
    tickets: list[Task] = []
    if not CUSTOM_TASKS_DIR.is_dir():
        return tickets

    for ticket_dir in sorted(p for p in CUSTOM_TASKS_DIR.iterdir() if p.is_dir()):
        meta_path = ticket_dir / "meta.json"
        issue_path = ticket_dir / "issue.md"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            issue_text = issue_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HarnessError(f"Malformed custom ticket at {ticket_dir}: {exc}") from exc

        entry_point_test = meta["entry_point_test"]
        tickets.append(
            Task(
                id=meta["id"],
                source="custom",
                issue_text=issue_text,
                hidden_tests=(entry_point_test,),
                base_dir=ticket_dir / "base",
            )
        )
    return tickets


def load_tasks(
    subset_id: str, *, include_custom: bool = True, override: bool = False
) -> list[Task]:
    """Load and normalise the SWE-bench subset `subset_id` plus every custom ticket.

    Refuses to exceed 50 SWE-bench + 5 custom tasks unless `override=True` (C-2).

    Args:
        subset_id: Name of a `config/tasks/<subset_id>.txt` file (without extension).
        include_custom: Whether to also load the in-repo custom tickets.
        override: Bypass the task-count cap.

    Returns:
        A combined list of SWE-bench tasks followed by custom tasks.

    Raises:
        HarnessError: Unknown subset, malformed custom ticket, or over-cap without `override`.
    """
    swebench_ids = _load_swebench_ids(subset_id)
    if len(swebench_ids) > MAX_SWEBENCH_TASKS and not override:
        raise HarnessError(
            f"Subset {subset_id!r} has {len(swebench_ids)} tasks, exceeding the cap of "
            f"{MAX_SWEBENCH_TASKS}; pass override=True to bypass (C-2)"
        )
    swebench_tasks = [
        Task(id=instance_id, source="swebench", issue_text="") for instance_id in swebench_ids
    ]

    custom_tasks: list[Task] = []
    if include_custom:
        custom_tasks = _load_custom_tickets()
        if len(custom_tasks) > MAX_CUSTOM_TASKS and not override:
            raise HarnessError(
                f"{len(custom_tasks)} custom tickets exceed the cap of {MAX_CUSTOM_TASKS}; "
                "pass override=True to bypass (C-2)"
            )

    return swebench_tasks + custom_tasks
