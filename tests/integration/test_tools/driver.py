"""Test driver: spins up the three MCP servers over stdio and calls their tools.

Used by the integration tests to exercise the full read -> write -> run
pytest -> git diff loop against a fixture repo snapshot, the same way a
LangGraph agent node would.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@asynccontextmanager
async def tool_session(server_module: str, task_dir: Path) -> AsyncIterator[ClientSession]:
    """Start `server_module` (e.g. `src.tools.filesystem_server`) as a stdio MCP server."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", server_module],
        cwd=str(PROJECT_ROOT),
        env={"SANDBOX_TASK_DIR": str(task_dir), "PYTHONPATH": str(PROJECT_ROOT)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_tool(session: ClientSession, name: str, arguments: dict[str, object]) -> dict:
    """Call `name` on `session` and return its structured content dict."""
    result = await session.call_tool(name, arguments)
    assert result.structuredContent is not None
    return result.structuredContent
