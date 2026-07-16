"""The sole choke-point for executing untrusted/generated code (NFR-1 layer (a)).

Every path that runs agent-generated code — the run-code MCP server, `make
sandbox-run CMD=...` — funnels through `run()`. No other module in this
project may call `docker run` or shell out to execute agent code.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SANDBOX_IMAGE = "swe-sandbox:latest"
STARTUP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class SandboxResult:
    """The outcome of running a command inside the sandbox container."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


def build_docker_command(cmd: str, task_dir: Path) -> list[str]:
    """Build the hardened `docker run` invocation for `cmd` against `task_dir`.

    Locks the container down to no network, no capabilities, a read-only
    root filesystem, a non-root user, and a single read-write mount of the
    task snapshot — the only place the command may persist state.

    Args:
        cmd: The shell command to run inside the container (via `sh -lc`).
        task_dir: Host directory mounted read-write at `/workspace`.

    Returns:
        The full `docker run` argv, ready for `subprocess.run`.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--read-only",
        "--user",
        "sandbox",
        "--tmpfs",
        "/tmp",
        "-v",
        f"{task_dir}:/workspace:rw",
        "-w",
        "/workspace",
        "--entrypoint",
        "sh",
        SANDBOX_IMAGE,
        "-lc",
        cmd,
    ]


def run(cmd: str, task_dir: Path, timeout: int = 120) -> SandboxResult:
    """Run `cmd` inside the Docker sandbox, scoped to `task_dir`, and return the result.

    A container-startup failure or hang (rather than a normal non-zero exit
    from `cmd` itself) is reported as a harness error (`exit_code=-1,
    timed_out=True`) so callers don't mistake infrastructure failure for a
    solver FAIL (NFR-16).

    Args:
        cmd: The shell command to run inside the container.
        task_dir: Host directory mounted read-write at `/workspace`.
        timeout: Seconds allowed for `cmd` itself, on top of the fixed
            `STARTUP_TIMEOUT_SECONDS` budget for the container to start.

    Returns:
        A `SandboxResult` with the command's stdout/stderr/exit code, or a
        harness-error result (`exit_code=-1, timed_out=True`) if the
        container failed to start or the combined timeout was exceeded.
    """
    docker_cmd = build_docker_command(cmd, task_dir)
    try:
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=STARTUP_TIMEOUT_SECONDS + timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("Sandbox command timed out: %s", cmd)
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return SandboxResult(stdout=stdout, stderr=stderr, exit_code=-1, timed_out=True)
    except OSError as exc:  # docker binary missing, etc.
        logger.error("Sandbox failed to start: %s", exc)
        return SandboxResult(stdout="", stderr=str(exc), exit_code=-1, timed_out=True)

    return SandboxResult(stdout=result.stdout, stderr=result.stderr, exit_code=result.returncode)
