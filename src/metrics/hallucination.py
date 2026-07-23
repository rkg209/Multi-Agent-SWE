"""Static hallucination check (FR-30): flags patch references absent from the repo snapshot.

Conservative by design (see `specs/05-instrumentation-metrics/plan.md`): only
`import` targets and `*.py`-suffixed path-shaped tokens count as references,
and standard-library / common third-party module names are never flagged.
Missing a real hallucination is preferable to a false positive here.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.developer import SKIP_ENTRIES

# Common third-party packages this project or its tasks reasonably depend on;
# not exhaustive, just enough to avoid flagging ordinary imports as hallucinated.
_THIRD_PARTY_ALLOWLIST = {"pytest", "numpy", "requests", "setuptools", "pip", "psycopg2"}

_IMPORT_RE = re.compile(
    r"^[+\- ]?\s*(?:import\s+(?P<import_mod>[\w.]+)|from\s+(?P<from_mod>[\w.]+)\s+import)",
    re.MULTILINE,
)
_PY_PATH_RE = re.compile(r"[\w./\-]+\.py\b")

_INDEX_CACHE: dict[tuple[str, float], SnapshotIndex] = {}


@dataclass(frozen=True)
class SnapshotIndex:
    """A repo snapshot's known file paths and top-level symbol names."""

    files: set[str]
    symbols: set[str]


@dataclass(frozen=True)
class References:
    """References extracted from agent-authored text: import targets and path-shaped tokens."""

    modules: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)


def _iter_source_files(root: Path) -> list[Path]:
    files = []
    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        if any(part in SKIP_ENTRIES for part in entry.relative_to(root).parts):
            continue
        files.append(entry)
    return files


def _collect_symbols(path: Path) -> set[str]:
    """Return the module stem plus top-level def/class names for one `.py` file."""
    symbols = {path.stem}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return symbols
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            symbols.add(node.name)
    return symbols


def _snapshot_mtime(root: Path) -> float:
    mtimes = [p.stat().st_mtime for p in _iter_source_files(root)]
    return max(mtimes) if mtimes else 0.0


def build_snapshot_index(root: Path) -> SnapshotIndex:
    """Build (and cache) a `SnapshotIndex` of `root`'s file tree and Python symbol table."""
    cache_key = (str(root), _snapshot_mtime(root))
    cached = _INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached

    files: set[str] = set()
    symbols: set[str] = set()
    for path in _iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        files.add(rel)
        files.add(path.name)
        if path.suffix == ".py":
            symbols |= _collect_symbols(path)

    index = SnapshotIndex(files=files, symbols=symbols)
    _INDEX_CACHE.clear()  # only one root's worth of cache is ever useful at a time
    _INDEX_CACHE[cache_key] = index
    return index


def extract_references(text: str) -> References:
    """Extract import targets and `*.py`-suffixed path tokens from `text`."""
    modules: set[str] = set()
    for match in _IMPORT_RE.finditer(text):
        mod = match.group("import_mod") or match.group("from_mod")
        if mod:
            modules.add(mod.split(".")[0])

    paths = {token for token in _PY_PATH_RE.findall(text)}
    return References(modules=modules, paths=paths)


def score_references(refs: References, index: SnapshotIndex) -> float:
    """Return the fraction of `refs` absent from `index`; `0.0` when there are no references."""
    bad = 0
    total = 0

    for mod in refs.modules:
        if mod in sys.stdlib_module_names or mod in _THIRD_PARTY_ALLOWLIST:
            continue
        total += 1
        if mod not in index.symbols and mod not in index.files:
            bad += 1

    for path in refs.paths:
        total += 1
        if path not in index.files and Path(path).name not in index.files:
            bad += 1

    if total == 0:
        return 0.0
    return bad / total


def check_patch(patch: str, root: Path) -> float:
    """Score `patch`'s references against `root`'s repo snapshot. `[0.0, 1.0]`."""
    index = build_snapshot_index(root)
    refs = extract_references(patch)
    return score_references(refs, index)
