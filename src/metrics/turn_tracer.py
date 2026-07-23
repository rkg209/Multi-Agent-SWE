"""Turn-tracing context manager: wraps one agent-node execution and records it.

Framed as a context manager (not a decorator) so future nodes get tracing "for
free" by wrapping their body — no dependency on node signatures. Exceptions
inside the body still emit the turn row before re-raising: a crashed turn is
data, not a gap in the trace.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Iterator

from src.metrics.trace_store import record_agent_turn
from src.tools.toolbelt import ToolBelt


class TurnRecorder:
    """Accumulates one agent turn's metrics; written to `trace_events` on context exit."""

    def __init__(self) -> None:
        self.model: str | None = None
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.cost_usd: float = 0.0
        self.tool_calls: list[str] = []

    def record_tool_call(self, name: str) -> None:
        """Append `name` to this turn's tool-call log."""
        self.tool_calls.append(name)


class RecordingToolBelt:
    """Thin `ToolBelt` wrapper that logs each call's method name onto a `TurnRecorder`.

    Delegates every call to a real `ToolBelt` — `src/tools/` is untouched.
    """

    def __init__(self, belt: ToolBelt, recorder: TurnRecorder) -> None:
        self._belt = belt
        self._recorder = recorder

    def read_file(self, path: str) -> str:
        """Read `path` via the wrapped `ToolBelt`, logging the call."""
        self._recorder.record_tool_call("read_file")
        return self._belt.read_file(path)

    def write_file(self, path: str, content: str) -> None:
        """Write `content` to `path` via the wrapped `ToolBelt`, logging the call."""
        self._recorder.record_tool_call("write_file")
        self._belt.write_file(path, content)

    def list_dir(self, path: str = ".") -> list[str]:
        """List `path` via the wrapped `ToolBelt`, logging the call."""
        self._recorder.record_tool_call("list_dir")
        return self._belt.list_dir(path)

    def exec(self, command: str, timeout: int = 120) -> object:
        """Run `command` via the wrapped `ToolBelt`, logging the call."""
        self._recorder.record_tool_call("exec")
        return self._belt.exec(command, timeout=timeout)

    def diff(self) -> str:
        """Return the working-tree diff via the wrapped `ToolBelt`, logging the call."""
        self._recorder.record_tool_call("diff")
        return self._belt.diff()


@contextlib.contextmanager
def trace_turn(
    *, run_id: uuid.UUID, task_id: str, agent_role: str, turn_index: int
) -> Iterator[TurnRecorder]:
    """Time a node's body and record one `agent_turn` trace row on exit.

    The caller sets `recorder.model`, token counts, and `cost_usd` from the
    `LLMResponse` it already has, and reads/writes files through a
    `RecordingToolBelt(belt, recorder)` so tool calls are captured too.
    """
    recorder = TurnRecorder()
    start = time.monotonic()
    try:
        yield recorder
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        record_agent_turn(
            run_id=run_id,
            task_id=task_id,
            agent_role=agent_role,
            turn_index=turn_index,
            model=recorder.model,
            prompt_tokens=recorder.prompt_tokens,
            completion_tokens=recorder.completion_tokens,
            cost_usd=recorder.cost_usd,
            duration_ms=duration_ms,
            tool_calls=recorder.tool_calls,
        )
