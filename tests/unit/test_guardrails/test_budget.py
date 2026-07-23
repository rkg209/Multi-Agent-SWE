"""Unit tests for `src.guardrails.budget` — the FR-43/NFR-11 per-task token cap."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.errors import GuardrailError
from src.guardrails.budget import (
    DEFAULT_TOKEN_BUDGET,
    is_budget_exceeded,
    load_budget_config,
)


def test_is_budget_exceeded_under_cap() -> None:
    assert is_budget_exceeded(50_000, 100_000) is False


def test_is_budget_exceeded_at_cap() -> None:
    assert is_budget_exceeded(100_000, 100_000) is True


def test_is_budget_exceeded_over_cap() -> None:
    assert is_budget_exceeded(150_000, 100_000) is True


def test_load_budget_config_reads_real_file() -> None:
    config = load_budget_config("config/budget.yaml")
    assert config.token_cap_per_task == 100_000


def test_load_budget_config_missing_file_falls_back_to_default() -> None:
    config = load_budget_config("config/does-not-exist.yaml")
    assert config.token_cap_per_task == DEFAULT_TOKEN_BUDGET


def test_load_budget_config_malformed_yaml_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "budget.yaml"
    bad_file.write_text("token_cap_per_task: [not, an, int")
    with pytest.raises(GuardrailError):
        load_budget_config(str(bad_file))


def test_load_budget_config_missing_key_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "budget.yaml"
    bad_file.write_text("something_else: 5\n")
    with pytest.raises(GuardrailError):
        load_budget_config(str(bad_file))
