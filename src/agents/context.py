"""File selection for non-trivial repositories.

Flat toy repos (a handful of top-level files) are fed to the model whole, as before. A real
repository (Django, astropy, ...) cannot be: this module ranks candidate source files from the
issue text and, in multi mode, the Architect's `FILES:` plan, so the Developer sees a few
relevant files instead of an arbitrary alphabetical prefix of the top-level directory.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

FLAT_REPO_MAX_FILES = 20
MAX_CONTEXT_FILES = 3
LARGE_CONTEXT_CHAR_CAP = 60_000
MAX_CANDIDATE_LISTING = 15
MAX_FILE_BYTES = 200_000

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".tox", ".venv", "build", "dist", "docs"}
_TEST_DIR_NAMES = {"tests", "test", "testing"}
_PATH_RE = re.compile(r"[\w./-]+\.py\b")
_DOTTED_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){1,}\b")
_BACKTICK_RE = re.compile(r"`([A-Za-z_][\w.]*)`")
_CAMEL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
_SNAKE_RE = re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b")
_STOPWORDS = {"self", "none", "true", "false", "return", "import", "class", "default"}


def list_source_files(root: Path) -> list[str]:
    """Return workspace-relative `.py` paths, excluding VCS, build, docs and test files."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and d not in _TEST_DIR_NAMES]
        for name in filenames:
            if not name.endswith(".py") or name.startswith("test_") or name == "conftest.py":
                continue
            found.append(str((Path(dirpath) / name).relative_to(root)))
    return sorted(found)


def is_large_repo(root: Path) -> bool:
    """True when the workspace is too big to show whole (more than a few top-level sources)."""
    return len(list_source_files(root)) > FLAT_REPO_MAX_FILES


def _identifiers(issue_text: str) -> list[str]:
    """Distinctive identifiers from the issue, most specific first (backticked > Camel > snake)."""
    ordered: list[str] = []
    for pattern in (_BACKTICK_RE, _CAMEL_RE, _SNAKE_RE):
        for match in pattern.finditer(issue_text):
            token = match.group(1) if pattern is _BACKTICK_RE else match.group(0)
            for part in token.split("."):
                if len(part) >= 4 and part.lower() not in _STOPWORDS and part not in ordered:
                    ordered.append(part)
    return ordered[:15]


def _explicit_matches(files: list[str], issue_text: str) -> list[str]:
    """Files the issue names outright, as a path (`a/b.py`) or dotted module (`a.b.c`)."""
    hits: list[str] = []
    for ref in _PATH_RE.findall(issue_text):
        hits.extend(f for f in files if f.endswith(ref.lstrip("./")))
    for dotted in _DOTTED_RE.findall(issue_text):
        parts = dotted.split(".")
        for end in range(len(parts), 1, -1):  # `a.b.C.method` -> try a/b/C.py, then a/b.py
            suffix = "/".join(parts[:end])
            hits.extend(f for f in files if f.endswith(f"{suffix}.py"))
    return list(dict.fromkeys(hits))


def _score_file(root: Path, rel: str, identifiers: list[str]) -> float:
    """Score one file: identifier in the path, defined here, or merely mentioned here."""
    path = root / rel
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return 0.0
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0.0
    stem = Path(rel).stem.lower()
    score = 0.0
    for ident in identifiers:
        if ident.lower() in stem:
            # A multi-word snake_case name inside a filename (a migration, a module) is a strong
            # signal; a short word in a path is weak.
            score += 12 if "_" in ident and len(ident) >= 12 else 3
        score += 5 * len(re.findall(rf"^\s*(?:class|def)\s+{re.escape(ident)}\b", text, re.M))
        score += min(text.count(ident), 5)
    return score


def _resolve_plan_files(files: list[str], plan_files: list[str]) -> list[str]:
    """Map Architect-named files onto real workspace paths (exact, suffix, unique basename)."""
    resolved: list[str] = []
    for raw in plan_files:
        name = raw.strip().strip("`").lstrip("./")
        if name in files:
            resolved.append(name)
            continue
        suffix_hits = [f for f in files if f.endswith("/" + name)]
        base_hits = [f for f in files if Path(f).name == Path(name).name]
        pick = suffix_hits or (base_hits if len(base_hits) == 1 else [])
        resolved.extend(pick[:1])
    return list(dict.fromkeys(resolved))


def rank_files(root: Path, issue_text: str, plan_files: list[str] | None = None) -> list[str]:
    """Rank candidate files: Architect's plan first, then issue-named files, then keyword score."""
    files = list_source_files(root)
    ranked = _resolve_plan_files(files, plan_files or [])
    ranked += [f for f in _explicit_matches(files, issue_text) if f not in ranked]
    identifiers = _identifiers(issue_text)
    if identifiers:
        scored = sorted(
            ((_score_file(root, f, identifiers), f) for f in files if f not in ranked),
            key=lambda item: (-item[0], item[1]),
        )
        ranked += [f for score, f in scored if score > 0]
    return ranked


def fit_to_budget(root: Path, ranked: list[str]) -> list[str]:
    """Take ranked files in order until `MAX_CONTEXT_FILES` or the character budget is reached."""
    chosen: list[str] = []
    total = 0
    for rel in ranked:
        if len(chosen) >= MAX_CONTEXT_FILES:
            break
        try:
            size = (root / rel).stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES or total + size > LARGE_CONTEXT_CHAR_CAP:
            continue
        chosen.append(rel)
        total += size
    return chosen


def select_context_files(
    root: Path, issue_text: str, plan_files: list[str] | None = None
) -> list[str]:
    """Pick up to `MAX_CONTEXT_FILES` ranked files that fit `LARGE_CONTEXT_CHAR_CAP` in total."""
    return fit_to_budget(root, rank_files(root, issue_text, plan_files))


MAX_DIFF_CHARS = 20_000


def clip_diff(diff: str) -> str:
    """Cap a diff shown to Tester/Reviewer so a runaway patch cannot overflow model context."""
    if len(diff) <= MAX_DIFF_CHARS:
        return diff
    return (
        diff[:MAX_DIFF_CHARS] + f"\n... [diff truncated: {len(diff) - MAX_DIFF_CHARS} more chars]"
    )
