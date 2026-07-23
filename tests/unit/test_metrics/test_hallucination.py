"""Unit tests for `src.metrics.hallucination` against `tests/fixtures/sample_repo/`."""

from __future__ import annotations

from pathlib import Path

from src.metrics.hallucination import build_snapshot_index, check_patch, extract_references

SAMPLE_REPO = Path(__file__).resolve().parents[2] / "fixtures" / "sample_repo"


def test_known_module_import_scores_zero() -> None:
    patch = "+import calculator\n+calculator.add(1, 2)\n"
    assert check_patch(patch, SAMPLE_REPO) == 0.0


def test_nonexistent_module_import_scores_above_zero() -> None:
    patch = "+import nonexistent_module\n"
    assert check_patch(patch, SAMPLE_REPO) > 0.0


def test_nonexistent_path_reference_scores_above_zero() -> None:
    patch = "+++ b/does/not/exist.py\n"
    assert check_patch(patch, SAMPLE_REPO) > 0.0


def test_stdlib_import_not_flagged() -> None:
    patch = "+import os\n+import sys\n"
    assert check_patch(patch, SAMPLE_REPO) == 0.0


def test_no_references_scores_zero() -> None:
    patch = "+x = 1 + 1\n"
    assert check_patch(patch, SAMPLE_REPO) == 0.0


def test_unparseable_python_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n")
    (tmp_path / "good.py").write_text("def helper():\n    pass\n")
    index = build_snapshot_index(tmp_path)
    assert "helper" in index.symbols
    assert "broken" in index.symbols  # module stem still indexed even if body can't be parsed


def test_extract_references_picks_up_import_and_path_tokens() -> None:
    refs = extract_references("import foo\nfrom bar import baz\n+++ b/some/path.py\n")
    assert refs.modules == {"foo", "bar"}
    assert "b/some/path.py" in refs.paths
