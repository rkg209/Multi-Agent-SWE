#!/usr/bin/env python3
"""Run a script or ad-hoc command inside the Docker sandbox container.

`--script` mounts the project root read-only. `--cmd` runs the hardened
`docker_sandbox.run()` against a throwaway scratch dir (never the project
root, which that path mounts read-write). Both disable networking and
forward the container's exit code. This is the only sanctioned way to
execute agent-generated code (see CLAUDE.md's sandbox safety rule).
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sandbox.docker_sandbox import run as run_in_sandbox  # noqa: E402
from src.sandbox.image import SANDBOX_IMAGE  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments for the sandbox wrapper."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--script",
        help="Path to the script to run, relative to the project root or absolute.",
    )
    group.add_argument(
        "--cmd",
        help="A raw shell command to run inside the sandbox (via docker_sandbox.run).",
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
    """Build the `docker run` command to execute `script_path` inside the sandbox.

    Args:
        script_path: Absolute path (under `PROJECT_ROOT`) of the script to run.
        extra_args: A single shell-quoted string of extra CLI args for the script.

    Returns:
        The full `docker run` argv, ready for `subprocess.run`.
    """
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
    """Entry point: run the requested script or command in the sandbox and return its exit code."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.cmd is not None:
        # A scratch dir, not PROJECT_ROOT: docker_sandbox.run always mounts
        # its task_dir read-write, and CMD= must never get write access to
        # the host repo (the --script path below stays read-only).
        with tempfile.TemporaryDirectory() as scratch_dir:
            result = run_in_sandbox(args.cmd, Path(scratch_dir))
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.exit_code
    script_path = resolve_script_path(args.script)
    cmd = build_docker_command(script_path, args.args)
    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
