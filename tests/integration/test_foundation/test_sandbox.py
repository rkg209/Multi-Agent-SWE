"""Integration tests for scripts/sandbox_exec.py — requires Docker."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker not running")


@pytest.mark.integration
def test_hello_sandbox() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "sandbox_exec.py"),
            "--script",
            "scripts/hello_sandbox.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Hello from sandbox" in result.stdout
