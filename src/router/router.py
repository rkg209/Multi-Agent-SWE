"""The single model-router abstraction: every agent LLM call goes through `complete()`."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field

import litellm

from src.errors import RouterError
from src.metrics.trace_store import record_llm_call
from src.router.config import RouterConfig, load_router_config

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config/litellm_config.yaml"


@dataclass(frozen=True)
class LLMRequest:
    """A request to the router: either a `role` or an explicit `tier` must be set."""

    messages: list[dict[str, str]]
    role: str | None = None
    tier: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    task_id: str = "adhoc"
    turn_index: int = 0


@dataclass(frozen=True)
class LLMResponse:
    """The normalised result of a completed LLM call, already recorded to Postgres."""

    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cache_hit: bool = False


def _compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    input_price_per_1k: float,
    output_price_per_1k: float,
) -> float:
    """Compute USD cost from token counts and per-1k-token prices."""
    return (prompt_tokens / 1000) * input_price_per_1k + (
        completion_tokens / 1000
    ) * output_price_per_1k


def _normalize_usage(response: object) -> tuple[int, int]:
    """Extract (prompt_tokens, completion_tokens) from a LiteLLM response, defaulting to 0."""
    usage = getattr(response, "usage", None)
    if usage is None:
        logger.warning("LiteLLM response has no usage data; defaulting token counts to 0")
        return 0, 0
    prompt_tokens = getattr(usage, "prompt_tokens", None) or 0
    completion_tokens = getattr(usage, "completion_tokens", None) or 0
    return int(prompt_tokens), int(completion_tokens)


def _extract_content(response: object) -> str:
    """Extract the assistant message text from a LiteLLM response, defaulting to `""`.

    A malformed/empty `choices` list must not prevent the trace row from
    being written — the provider call already happened (and was billed)
    by the time this runs, so the response is degraded but still traced.
    """
    choices = getattr(response, "choices", None) or []
    if not choices:
        logger.warning("LiteLLM response has no choices; recording empty content")
        return ""
    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None) or ""


def _resolve_agent_role(request: LLMRequest) -> str:
    """Map a request's `role` to the `trace_events.agent_role` value.

    Explicit-tier calls with no role are recorded as `system` (see
    `specs/01-model-router` scope reconciliation note 2).
    """
    return request.role if request.role is not None else "system"


def complete(request: LLMRequest, config: RouterConfig | None = None) -> LLMResponse:
    """Resolve a role/tier to a model, call it via LiteLLM, and record the trace.

    The trace row is written to Postgres *before* this function returns
    (NFR-8): a DB write failure raises `RouterError` rather than returning a
    response the caller would believe was silently recorded.
    """
    if request.role is None and request.tier is None:
        raise RouterError("LLMRequest must set either `role` or `tier`")

    if config is None:
        config = load_router_config(os.environ.get("LITELLM_CONFIG", DEFAULT_CONFIG_PATH))

    role_or_tier = request.role if request.role is not None else request.tier
    model_spec = config.resolve(role_or_tier)

    completion_kwargs: dict[str, object] = {
        "model": model_spec.model,
        "messages": request.messages,
    }
    if request.max_tokens is not None:
        completion_kwargs["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        completion_kwargs["temperature"] = request.temperature
    if model_spec.api_base is not None:
        completion_kwargs["api_base"] = model_spec.api_base
    if model_spec.api_key_env is not None:
        api_key = os.environ.get(model_spec.api_key_env)
        if api_key:
            completion_kwargs["api_key"] = api_key

    try:
        response = litellm.completion(**completion_kwargs)
    except Exception as exc:  # noqa: BLE001 - LiteLLM raises provider-specific exceptions
        raise RouterError(
            f"LiteLLM completion call failed for model {model_spec.model!r}: {exc}"
        ) from exc

    prompt_tokens, completion_tokens = _normalize_usage(response)
    cost_usd = _compute_cost(
        prompt_tokens,
        completion_tokens,
        model_spec.input_price_per_1k,
        model_spec.output_price_per_1k,
    )
    content = _extract_content(response)

    record_llm_call(
        run_id=request.run_id,
        task_id=request.task_id,
        agent_role=_resolve_agent_role(request),
        provider=model_spec.provider,
        model=model_spec.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        cache_hit=False,
        turn_index=request.turn_index,
    )

    return LLMResponse(
        content=content,
        model=model_spec.model,
        provider=model_spec.provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        cache_hit=False,
    )
