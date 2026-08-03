"""Single source of truth for the sandbox container image tag (NFR-23).

`docker_sandbox.py`, `scripts/sandbox_exec.py`, and the `Makefile` all need
the same tag; importing it here instead of redeclaring it in each place is
what keeps them from drifting.
"""

from __future__ import annotations

SANDBOX_IMAGE: str = "swe-sandbox:0.1.0"
