"""Unit tests for `src.router.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.router.config import RouterConfigError, load_router_config

VALID_YAML = """
tiers:
  strong:
    provider: openrouter
    model: openrouter/qwen/qwen-2.5-72b-instruct
    input_price_per_1k: 0.00035
    output_price_per_1k: 0.0004
  small:
    provider: groq
    model: groq/llama-3.1-8b-instant
    input_price_per_1k: 0.00005
    output_price_per_1k: 0.00008
roles:
  architect: strong
  reviewer: strong
  developer: small
  tester: small
"""


def _write(tmp_path: Path, content: str) -> str:
    config_path = tmp_path / "litellm_config.yaml"
    config_path.write_text(content)
    return str(config_path)


def test_resolve_by_role(tmp_path: Path) -> None:
    config = load_router_config(_write(tmp_path, VALID_YAML))
    spec = config.resolve("developer")
    assert spec.tier == "small"
    assert spec.model == "groq/llama-3.1-8b-instant"


def test_resolve_by_explicit_tier(tmp_path: Path) -> None:
    config = load_router_config(_write(tmp_path, VALID_YAML))
    spec = config.resolve("strong")
    assert spec.tier == "strong"
    assert spec.provider == "openrouter"


def test_resolve_unknown_role_or_tier_raises(tmp_path: Path) -> None:
    config = load_router_config(_write(tmp_path, VALID_YAML))
    with pytest.raises(RouterConfigError):
        config.resolve("nonexistent")


def test_missing_price_raises(tmp_path: Path) -> None:
    bad_yaml = """
tiers:
  strong:
    provider: openrouter
    model: openrouter/qwen/qwen-2.5-72b-instruct
    input_price_per_1k: 0.00035
"""
    with pytest.raises(RouterConfigError):
        load_router_config(_write(tmp_path, bad_yaml))


def test_role_pointing_to_unknown_tier_raises(tmp_path: Path) -> None:
    bad_yaml = """
tiers:
  strong:
    provider: openrouter
    model: openrouter/qwen/qwen-2.5-72b-instruct
    input_price_per_1k: 0.00035
    output_price_per_1k: 0.0004
roles:
  architect: nonexistent_tier
"""
    with pytest.raises(RouterConfigError):
        load_router_config(_write(tmp_path, bad_yaml))


def test_missing_file_raises() -> None:
    with pytest.raises(RouterConfigError):
        load_router_config("/nonexistent/path/config.yaml")


def test_env_var_expansion_in_api_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    yaml_with_env = """
tiers:
  local:
    provider: ollama
    model: ollama/llama3.1
    input_price_per_1k: 0.0
    output_price_per_1k: 0.0
    api_base: ${OLLAMA_BASE_URL}
"""
    config = load_router_config(_write(tmp_path, yaml_with_env))
    spec = config.resolve("local")
    assert spec.api_base == "http://localhost:11434"
