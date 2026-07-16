"""Integration test: the custom scorer against a real fixture in the sandbox — requires Docker."""

from __future__ import annotations

import subprocess

import pytest

from benchmark.loader import load_tasks
from benchmark.scorer import ScoreResult, score
from benchmark.solver import Patch

GOOD_PATCH = """diff --git a/calculator.py b/calculator.py
index dea5420..cbac53f 100644
--- a/calculator.py
+++ b/calculator.py
@@ -9,3 +9,8 @@ def subtract(a: float, b: float) -> float:
 def multiply(a: float, b: float) -> float:
     \"\"\"Return a * b.\"\"\"
     return a * b
+
+
+def add(a: float, b: float) -> float:
+    \"\"\"Return a + b.\"\"\"
+    return a + b
"""


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not running")


@pytest.mark.integration
def test_correct_patch_passes_and_noop_fails() -> None:
    tasks = load_tasks("lite-5")
    task = next(t for t in tasks if t.id == "custom-001-calc-add")

    noop_result = score(task, Patch(diff=""), run_id="itest-noop")
    assert noop_result.outcome == "FAIL"

    good_result = score(task, Patch(diff=GOOD_PATCH), run_id="itest-good")
    assert good_result == ScoreResult(outcome="PASS")
