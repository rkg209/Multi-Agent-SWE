"""The deterministic scorer: dispatches by `task.source` (FR-22).

Custom tickets: `git apply` the patch into a fresh copy of the ticket's `base/` snapshot (host-side
— patch application is a fixed VCS operation, not untrusted-code execution, mirroring Spec 02's
git-server decision), then run the pinned hidden test file inside the Docker sandbox — the only exec
path for the test file/patched code themselves (NFR-1). PASS iff pytest exits 0.

SWE-bench tasks: delegate entirely to `benchmark.sbcli` (FR-21) — never reimplemented here.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from benchmark.errors import HarnessError
from benchmark.loader import Task
from benchmark.sbcli import run_sbcli_eval
from benchmark.solver import Patch
from src.sandbox.docker_sandbox import run as run_in_sandbox

logger = logging.getLogger(__name__)

COMMIT_AUTHOR_NAME = "swe-agent"
COMMIT_AUTHOR_EMAIL = "swe-agent@localhost"

Outcome = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class ScoreResult:
    """The deterministic verdict for one (task, patch) pair."""

    outcome: Outcome
    reason: str | None = None


def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a git subcommand with a deterministic identity, cwd-scoped to `root`."""
    return subprocess.run(
        [
            "git",
            "-c",
            f"user.name={COMMIT_AUTHOR_NAME}",
            "-c",
            f"user.email={COMMIT_AUTHOR_EMAIL}",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _init_baseline(repo_dir: Path) -> None:
    """`git init` + a baseline commit so `git apply`/`git diff` have a clean starting point."""
    _run_git(repo_dir, ["init", "-q"])
    _run_git(repo_dir, ["add", "-A"])
    _run_git(repo_dir, ["commit", "-q", "-m", "baseline"])


def _score_custom(task: Task, patch: Patch) -> ScoreResult:
    """Apply `patch` to a fresh copy of `task.base_dir`, run its hidden tests in the sandbox."""
    if task.base_dir is None:
        raise HarnessError(f"Custom task {task.id!r} has no base_dir")

    with tempfile.TemporaryDirectory(prefix=f"score-{task.id}-") as tmp:
        repo_dir = Path(tmp)
        shutil.copytree(task.base_dir, repo_dir, dirs_exist_ok=True)
        _init_baseline(repo_dir)

        if patch.diff.strip():
            apply_result = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                cwd=repo_dir,
                input=patch.diff,
                capture_output=True,
                text=True,
                check=False,
            )
            if apply_result.returncode != 0:
                return ScoreResult(
                    outcome="FAIL", reason=f"patch did not apply: {apply_result.stderr}"
                )

        ticket_dir = task.base_dir.parent
        for hidden_test in task.hidden_tests:
            shutil.copy(ticket_dir / hidden_test, repo_dir / hidden_test)

        test_args = " ".join(task.hidden_tests)
        result = run_in_sandbox(f"pytest {test_args} -q", repo_dir)
        if result.timed_out:
            return ScoreResult(
                outcome="FAIL", reason="sandbox harness error (startup failure or timeout)"
            )
        if result.exit_code == 0:
            return ScoreResult(outcome="PASS")
        return ScoreResult(outcome="FAIL", reason=(result.stdout + result.stderr)[-2000:])


def _score_swebench(task: Task, patch: Patch, *, run_id: str, output_dir: Path) -> ScoreResult:
    """Delegate to `sb-cli`; any harness-level failure (e.g. no API key) becomes a recorded FAIL."""
    try:
        resolved = run_sbcli_eval(task.id, patch.diff, run_id=run_id, output_dir=output_dir)
    except HarnessError as exc:
        logger.warning("sb-cli scoring unavailable for %s: %s", task.id, exc)
        return ScoreResult(outcome="FAIL", reason=str(exc))
    return ScoreResult(outcome="PASS" if resolved else "FAIL")


def score(
    task: Task,
    patch: Patch,
    *,
    run_id: str,
    sbcli_output_dir: Path | None = None,
) -> ScoreResult:
    """Score `patch` against `task`, dispatching on `task.source`.

    Args:
        task: The task being scored.
        patch: The solver's patch (may be empty).
        run_id: The current benchmark run's UUID, forwarded to `sb-cli` as its run ID.
        sbcli_output_dir: Where `sb-cli` writes its report; defaults to `reports/sbcli`.

    Returns:
        A `ScoreResult` with a deterministic PASS/FAIL outcome (NFR-5).
    """
    if task.source == "custom":
        return _score_custom(task, patch)
    if task.source == "swebench":
        return _score_swebench(
            task, patch, run_id=run_id, output_dir=sbcli_output_dir or Path("reports/sbcli")
        )
    raise HarnessError(f"Unknown task source: {task.source!r}")
