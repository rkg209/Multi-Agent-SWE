"""Integration tests for the tool layer MCP servers — requires Docker.

Exercises the full read -> write -> run pytest -> git diff loop that a
LangGraph agent node would perform, over real MCP stdio transport against
`tests/fixtures/sample_repo`. Also asserts the sandbox has no network access.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.integration.test_tools.driver import call_tool, tool_session

FIXTURE_REPO = Path(__file__).resolve().parents[2] / "fixtures" / "sample_repo"


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "ps"], capture_output=True, check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _docker_available(), reason="Docker not running"),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def task_repo(tmp_path: Path) -> Path:
    """A copy of the fixture repo, committed as a baseline git repo."""
    repo_dir = tmp_path / "task"
    shutil.copytree(FIXTURE_REPO, repo_dir)
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@localhost",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=repo_dir,
        check=True,
    )
    return repo_dir


@pytest.mark.anyio
async def test_read_write_run_diff_loop(task_repo: Path) -> None:
    async with tool_session("src.tools.filesystem_server", task_repo) as fs:
        read_result = await call_tool(fs, "read_file", {"path": "calculator.py"})
        assert read_result["ok"] is True
        assert "def add" in read_result["content"]

        list_result = await call_tool(fs, "list_dir", {"path": "."})
        assert "calculator.py" in list_result["entries"]

        exists_result = await call_tool(fs, "exists", {"path": "calculator.py"})
        assert exists_result["exists"] is True

        new_content = read_result["content"].replace(
            "return a + b", "return a + b  # patched by test"
        )
        write_result = await call_tool(
            fs, "write_file", {"path": "calculator.py", "content": new_content}
        )
        assert write_result["ok"] is True

    async with tool_session("src.tools.runcode_server", task_repo) as run_code:
        exec_result = await call_tool(run_code, "exec", {"command": "pytest -q"})
        assert exec_result["ok"] is True
        assert exec_result["exit_code"] == 0

    async with tool_session("src.tools.git_server", task_repo) as git:
        diff_result = await call_tool(git, "diff", {})
        assert diff_result["ok"] is True
        assert "patched by test" in diff_result["diff"]


@pytest.mark.anyio
async def test_no_network_access_in_sandbox(task_repo: Path) -> None:
    async with tool_session("src.tools.runcode_server", task_repo) as run_code:
        result = await call_tool(
            run_code,
            "exec",
            {
                "command": 'python -c "import urllib.request; '
                "urllib.request.urlopen('https://example.com', timeout=5)\""
            },
        )
    assert result["ok"] is True
    assert result["exit_code"] != 0
