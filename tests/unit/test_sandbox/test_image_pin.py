"""Guards against the sandbox image tag drifting apart again (NFR-23).

Before `src/sandbox/image.py` existed, the tag was a duplicated string
literal in three places; this test only needs to check the two that are
still separate sources (the Makefile default and the Python constant) since
`docker_sandbox.py` and `scripts/sandbox_exec.py` now both import the
constant instead of redeclaring it.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.sandbox.image import SANDBOX_IMAGE

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def test_python_constant_is_not_latest() -> None:
    assert not SANDBOX_IMAGE.endswith(":latest")


def test_makefile_default_matches_python_constant() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text()
    match = re.search(r"^SANDBOX_IMAGE \?= (\S+)$", makefile, re.MULTILINE)
    assert match is not None, "Makefile must declare a SANDBOX_IMAGE ?= default"
    assert match.group(1) == SANDBOX_IMAGE
    assert not match.group(1).endswith(":latest")
