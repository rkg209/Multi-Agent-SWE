"""Unit tests for `dashboard.format` — pure functions, no I/O."""

from __future__ import annotations

import decimal

import pandas as pd

from dashboard.format import order_solvers, to_display_table, to_markdown_table


def test_order_solvers_puts_single_before_multi() -> None:
    frame = pd.DataFrame({"solver": ["multi", "single", "noop"]})
    ordered = order_solvers(frame)
    assert list(ordered["solver"]) == ["single", "multi", "noop"]


def test_order_solvers_appends_unknown_solvers_alphabetically() -> None:
    frame = pd.DataFrame({"solver": ["zeta", "single", "alpha"]})
    ordered = order_solvers(frame)
    assert list(ordered["solver"]) == ["single", "alpha", "zeta"]


def test_order_solvers_empty_frame_is_noop() -> None:
    frame = pd.DataFrame({"solver": []})
    assert order_solvers(frame).empty


def test_to_display_table_converts_decimal_to_float() -> None:
    frame = pd.DataFrame({"pass_rate_pct": [decimal.Decimal("66.67")]})
    display = to_display_table(frame)
    assert isinstance(display["Success rate (%)"].iloc[0], float)
    assert display["Success rate (%)"].iloc[0] == 66.67


def test_to_display_table_renames_and_truncates_run_id() -> None:
    frame = pd.DataFrame(
        {
            "solver": ["single"],
            "run_id": ["abcdefgh-1234-5678-9999-000000000000"],
            "mean_cost_per_solved_task": [decimal.Decimal("0.01")],
            "hallucination_rate": [decimal.Decimal("0.0")],
        }
    )
    display = to_display_table(frame)
    assert display["Run ID"].iloc[0] == "abcdefgh"
    assert "Mean cost / solved ($)" in display.columns
    assert "Hallucination rate (0-1)" in display.columns


def test_to_markdown_table_renders_pipe_table() -> None:
    frame = pd.DataFrame({"Solver": ["single", "multi"], "Success rate (%)": [60.0, 80.0]})
    markdown = to_markdown_table(frame)
    assert markdown.startswith("|")
    assert "single" in markdown
    assert "multi" in markdown
