"""Cached, shallow checkout of a SWE-bench repository at a specific commit.

Only fixed VCS operations (`git init/fetch/checkout`) run on the host, the same reasoning
`benchmark/scorer.py` documents for `git apply`. The checked-out code is untrusted: nothing in
this module executes it, and tests/setup scripts must only ever run in the Docker sandbox.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from benchmark.errors import HarnessError

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
SWEBENCH_CACHE_DIR = REPO_ROOT / ".swebench_cache"
GIT_TIMEOUT_SECONDS = 900

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _git(cwd: Path, args: list[str]) -> None:
    """Run one fixed git command, raising `HarnessError` on any failure."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise HarnessError(f"git {' '.join(args[:2])} failed: {detail.strip()[-500:]}") from exc


def ensure_checkout(repo: str, base_commit: str, cache_dir: Path | None = None) -> Path:
    """Return a cached source tree (no `.git`) of `repo` at `base_commit`, cloning on first use.

    Args:
        repo: GitHub `owner/name`, e.g. `django/django`.
        base_commit: The instance's `base_commit` SHA.
        cache_dir: Cache root; defaults to the gitignored `.swebench_cache/`.

    Returns:
        A directory the solvers can `copytree` into their per-task workspace.

    Raises:
        HarnessError: Malformed `repo`/`base_commit`, or a git operation failed.
    """
    if not _REPO_RE.match(repo) or not _COMMIT_RE.match(base_commit):
        raise HarnessError(f"Refusing malformed repo/commit: {repo!r} @ {base_commit!r}")

    root = cache_dir or SWEBENCH_CACHE_DIR
    final = root / f"{repo.replace('/', '__')}__{base_commit[:12]}"
    if final.is_dir():
        return final

    root.mkdir(parents=True, exist_ok=True)
    work = root / f".tmp-{final.name}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    try:
        logger.info("Cloning %s @ %s (first use; cached afterwards)", repo, base_commit[:12])
        _git(work, ["init", "-q"])
        _git(work, ["remote", "add", "origin", f"https://github.com/{repo}.git"])
        _git(work, ["fetch", "-q", "--depth", "1", "origin", base_commit])
        _git(work, ["checkout", "-q", "--detach", "FETCH_HEAD"])
        staged = root / f".stage-{final.name}"
        shutil.rmtree(staged, ignore_errors=True)
        shutil.copytree(work, staged, ignore=shutil.ignore_patterns(".git"))
        staged.rename(final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return final
