"""Unit tests for `src.router.router.complete`, with LiteLLM and the trace store mocked."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.errors import RouterError
from src.router.config import RouterConfig, TierConfig
from src.router.router import LLMRequest, complete

TEST_CONFIG = RouterConfig(
    tiers={
        "strong": TierConfig(
            name="strong",
            provider="openrouter",
            model="openrouter/qwen/qwen-2.5-72b-instruct",
            input_price_per_1k=0.001,
            output_price_per_1k=0.002,
        ),
        "small": TierConfig(
            name="small",
            provider="groq",
            model="groq/llama-3.1-8b-instant",
            input_price_per_1k=0.0001,
            output_price_per_1k=0.0002,
        ),
    },
    roles={"architect": "strong", "developer": "small"},
)


def _fake_litellm_response(prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def test_resolves_role_to_configured_model() -> None:
    with (
        patch("src.router.router.litellm.completion", return_value=_fake_litellm_response(10, 5)),
        patch("src.router.router.record_llm_call"),
        patch("src.router.router.get_cached_response", return_value=None),
        patch("src.router.router.store_response"),
    ):
        response = complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="developer"),
            config=TEST_CONFIG,
        )
    assert response.model == "groq/llama-3.1-8b-instant"
    assert response.provider == "groq"


def test_resolves_explicit_tier_to_configured_model() -> None:
    with (
        patch("src.router.router.litellm.completion", return_value=_fake_litellm_response(10, 5)),
        patch("src.router.router.record_llm_call"),
        patch("src.router.router.get_cached_response", return_value=None),
        patch("src.router.router.store_response"),
    ):
        response = complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], tier="strong"),
            config=TEST_CONFIG,
        )
    assert response.model == "openrouter/qwen/qwen-2.5-72b-instruct"


def test_cost_computed_from_config_prices() -> None:
    with (
        patch(
            "src.router.router.litellm.completion",
            return_value=_fake_litellm_response(1000, 500),
        ),
        patch("src.router.router.record_llm_call"),
        patch("src.router.router.get_cached_response", return_value=None),
        patch("src.router.router.store_response"),
    ):
        response = complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="architect"),
            config=TEST_CONFIG,
        )
    # 1000/1000 * 0.001 + 500/1000 * 0.002 = 0.001 + 0.001
    assert response.cost_usd == pytest.approx(0.002)


def test_trace_written_before_response_returned() -> None:
    call_order: list[str] = []

    def fake_completion(**_kwargs: object) -> SimpleNamespace:
        call_order.append("completion")
        return _fake_litellm_response(10, 5)

    def fake_record_llm_call(**_kwargs: object) -> None:
        call_order.append("record_llm_call")

    with (
        patch("src.router.router.litellm.completion", side_effect=fake_completion),
        patch("src.router.router.record_llm_call", side_effect=fake_record_llm_call),
        patch("src.router.router.get_cached_response", return_value=None),
        patch("src.router.router.store_response"),
    ):
        complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="developer"),
            config=TEST_CONFIG,
        )

    assert call_order == ["completion", "record_llm_call"]


def test_missing_role_and_tier_raises() -> None:
    with pytest.raises(RouterError):
        complete(LLMRequest(messages=[{"role": "user", "content": "hi"}]), config=TEST_CONFIG)


def test_unknown_role_raises() -> None:
    with pytest.raises(RouterError):
        complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="nonexistent"),
            config=TEST_CONFIG,
        )


def test_empty_choices_still_writes_trace() -> None:
    """A malformed/empty response must not skip the trace write (NFR-8)."""
    empty_response = SimpleNamespace(
        choices=[], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=0)
    )
    with (
        patch("src.router.router.litellm.completion", return_value=empty_response),
        patch("src.router.router.record_llm_call") as mock_record,
        patch("src.router.router.get_cached_response", return_value=None),
        patch("src.router.router.store_response"),
    ):
        response = complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="developer"),
            config=TEST_CONFIG,
        )
    assert response.content == ""
    mock_record.assert_called_once()


def test_empty_string_role_does_not_silently_fall_back_to_tier() -> None:
    """An empty-string role must not be swallowed by `role or tier` truthiness."""
    with pytest.raises(RouterError):
        complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="", tier="strong"),
            config=TEST_CONFIG,
        )


def test_cache_hit_skips_litellm_and_returns_zero_cost() -> None:
    """FR-44: a cache hit must not call LiteLLM and must report `cache_hit=True`, cost 0."""
    from src.router.cache import CachedEntry

    with (
        patch("src.router.router.litellm.completion") as mock_completion,
        patch("src.router.router.record_llm_call") as mock_record,
        patch(
            "src.router.router.get_cached_response",
            return_value=CachedEntry(content="cached!", prompt_tokens=10, completion_tokens=5),
        ),
        patch("src.router.router.store_response") as mock_store,
    ):
        response = complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="developer"),
            config=TEST_CONFIG,
        )

    assert response.content == "cached!"
    assert response.cache_hit is True
    assert response.cost_usd == 0.0
    mock_completion.assert_not_called()
    mock_store.assert_not_called()
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["cache_hit"] is True
    assert mock_record.call_args.kwargs["cost_usd"] == 0.0


def test_cache_miss_then_stores_response() -> None:
    """FR-44: on a miss, the router calls LiteLLM as usual and stores the result."""
    with (
        patch("src.router.router.litellm.completion", return_value=_fake_litellm_response(10, 5)),
        patch("src.router.router.record_llm_call"),
        patch("src.router.router.get_cached_response", return_value=None),
        patch("src.router.router.store_response") as mock_store,
    ):
        response = complete(
            LLMRequest(messages=[{"role": "user", "content": "hi"}], role="developer"),
            config=TEST_CONFIG,
        )

    assert response.cache_hit is False
    mock_store.assert_called_once()


def test_distinct_prompts_yield_distinct_cache_keys() -> None:
    """Distinct `(model, messages)` pairs must never collide on the same cache key."""
    from src.router.cache import build_cache_key

    key_a = build_cache_key("groq/llama-3.1-8b-instant", [{"role": "user", "content": "hi"}])
    key_b = build_cache_key("groq/llama-3.1-8b-instant", [{"role": "user", "content": "bye"}])
    key_c = build_cache_key(
        "openrouter/qwen/qwen-2.5-72b-instruct", [{"role": "user", "content": "hi"}]
    )

    assert len({key_a, key_b, key_c}) == 3
    assert all(len(key) == 64 for key in (key_a, key_b, key_c))


def test_no_direct_provider_sdk_imports() -> None:
    """FR-9: no agent/app code may import a provider SDK directly."""
    import pathlib
    import subprocess

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            "grep",
            "-rE",
            "import openai|from openai|google.generativeai|anthropic|mistralai|cohere",
            "src/",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
