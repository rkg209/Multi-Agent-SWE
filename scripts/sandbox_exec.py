#!/usr/bin/env python3
"""Run a script inside the Docker sandbox container.

Mounts the project root read-only, disables networking, and forwards the
container's exit code. This is the only sanctioned way to execute
agent-generated code (see CLAUDE.md's sandbox safety rule).
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_IMAGE = "swe-sandbox:latest"


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for the sandbox wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--script",
        required=True,
        help="Path to the script to run, relative to the project root or absolute.",
    )
    parser.add_argument(
        "--args",
        default="",
        help="Extra arguments to pass to the script, as a single shell-quoted string.",
    )
    return parser.parse_args(argv)


def resolve_script_path(script: str) -> Path:
    """Resolve `script` to an absolute path under the project root, raising if it doesn't exist."""
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = PROJECT_ROOT / script_path
    script_path = script_path.resolve()
    if not script_path.is_file():
        raise FileNotFoundError(f"Script not found: {script_path}")
    return script_path


def build_docker_command(script_path: Path, extra_args: str) -> list[str]:
    """Build the `docker run` command to execute `script_path` inside the sandbox."""
    script_rel_path = script_path.relative_to(PROJECT_ROOT)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",  # no network access from sandbox
        "-v",
        f"{PROJECT_ROOT}:/workspace:ro",  # read-only project mount
        "-w",
        "/workspace",
        SANDBOX_IMAGE,
        f"/workspace/{script_rel_path}",
        *shlex.split(extra_args),
    ]
    return cmd


def main(argv: list[str] | None = None) -> int:
    """Entry point: run the requested script in the sandbox and return its exit code."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    script_path = resolve_script_path(args.script)
    cmd = build_docker_command(script_path, args.args)
    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
