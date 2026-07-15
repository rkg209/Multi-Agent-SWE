"""Model-router package: the sole LiteLLM entry point for all agent LLM calls."""

from __future__ import annotations

from src.errors import RouterError
from src.router.router import LLMRequest, LLMResponse, complete

__all__ = ["complete", "LLMRequest", "LLMResponse", "RouterError"]
