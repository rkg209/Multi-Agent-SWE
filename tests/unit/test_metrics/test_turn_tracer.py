"""Unit tests for `src.metrics.turn_tracer`."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from src.metrics.turn_tracer import RecordingToolBelt, trace_turn
from src.tools.toolbelt import ToolBelt


def test_trace_turn_records_row_with_recorder_fields(tmp_path: Path) -> None:
    run_id = uuid.uuid4()
    recorded: dict[str, object] = {}

    def fake_record_agent_turn(**kwargs: object) -> None:
        recorded.update(kwargs)

    with patch("src.metrics.turn_tracer.record_agent_turn", side_effect=fake_record_agent_turn):
        with trace_turn(
            run_id=run_id, task_id="repo__x-1", agent_role="developer", turn_index=1
        ) as recorder:
            recorder.model = "groq/llama"
            recorder.prompt_tokens = 10
            recorder.completion_tokens = 5
            recorder.cost_usd = 0.002
            recorder.record_tool_call("read_file")

    assert recorded["run_id"] == run_id
    assert recorded["task_id"] == "repo__x-1"
    assert recorded["agent_role"] == "developer"
    assert recorded["turn_index"] == 1
    assert recorded["model"] == "groq/llama"
    assert recorded["tool_calls"] == ["read_file"]
    assert isinstance(recorded["duration_ms"], int)
    assert recorded["duration_ms"] >= 0


def test_trace_turn_records_row_even_when_body_raises() -> None:
    run_id = uuid.uuid4()
    recorded: dict[str, object] = {}

    def fake_record_agent_turn(**kwargs: object) -> None:
        recorded.update(kwargs)

    with patch("src.metrics.turn_tracer.record_agent_turn", side_effect=fake_record_agent_turn):
        with pytest.raises(ValueError, match="boom"):
            with trace_turn(
                run_id=run_id, task_id="repo__x-1", agent_role="developer", turn_index=0
            ):
                raise ValueError("boom")

    assert recorded["task_id"] == "repo__x-1"


def test_recording_tool_belt_logs_tool_names(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    belt = ToolBelt(tmp_path)
    run_id = uuid.uuid4()

    with patch("src.metrics.turn_tracer.record_agent_turn"):
        with trace_turn(
            run_id=run_id, task_id="repo__x-1", agent_role="developer", turn_index=0
        ) as recorder:
            recording_belt = RecordingToolBelt(belt, recorder)
            recording_belt.list_dir(".")
            recording_belt.read_file("a.txt")
            recording_belt.write_file("b.txt", "world")

    assert recorder.tool_calls == ["list_dir", "read_file", "write_file"]
