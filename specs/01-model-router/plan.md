# Implementation Plan — Spec 01: Model Router

## Overview

Build a thin, well-instrumented wrapper around `litellm.completion`. The router reads a YAML config that defines model tiers and per-token prices, resolves a caller's requested tier to a concrete `provider/model`, invokes LiteLLM, computes USD cost from token usage, writes a trace record to Postgres, and only then returns the completion. Providers (hosted vs. local Ollama) are swappable purely through config + environment variables.

## Key Decisions

1. **LiteLLM as the sole provider interface.** All calls go through `litellm.completion(model=..., messages=..., api_base=...)`. No provider SDK is imported anywhere in `src/`. This satisfies FR-9 and the CLAUDE.md "no direct provider SDK imports" rule.
2. **Config-driven tiers, not hard-coded models.** `config/litellm_config.yaml` maps `strong` and `small` tiers to a `{provider, model, input_price_per_1k, output_price_per_1k, api_base}` block. `src/router/config.py` loads and validates it into typed dataclasses. Callers ask for a tier or a role; the router resolves the model.
3. **Cost computed from config prices at call time (NFR-13).** `cost_usd = (prompt_tokens/1000)*input_price + (completion_tokens/1000)*output_price`. Never estimated retroactively. Ollama/local models have price `0.0`.
4. **Trace write happens before return (NFR-8).** The router calls `TraceStore.record_llm_call(...)` inside the same function, before returning, so a crash after the LLM call still leaves a record. A minimal `src/metrics/trace_store.py` (write path only) is introduced here; the full read/aggregate API is Spec 05.
5. **Ollama as zero-cost path (FR-13).** Selecting the Ollama provider sets `api_base` to `OLLAMA_BASE_URL` and uses LiteLLM's `ollama/<model>` prefix. Switching is a config/env change only.
6. **Typed request/response contract.** `LLMRequest(role, messages, tier?, max_tokens?, temperature?)` → `LLMResponse(content, model, provider, usage, cost_usd, cache_hit=False)`. `cache_hit` is always `False` here; Spec 07 fills it.

## Implementation Order

1. **`src/router/config.py`** — dataclasses for tier/model/price; loader + validation for `config/litellm_config.yaml`. Fail loudly on missing prices or unknown tier.
2. **`config/litellm_config.yaml`** — define `strong` and `small` tiers, ≥2 providers, one Ollama entry. Reference env vars for keys/base URLs.
3. **`src/metrics/trace_store.py` (write path)** — `record_llm_call(run_id, task_id, agent_role, model, provider, prompt_tokens, completion_tokens, cost_usd, cache_hit)` inserting into `trace_events`. Uses psycopg2 or SQLAlchemy against `DATABASE_URL`.
4. **`src/router/router.py`** — `complete(request)`: resolve tier→model, call `litellm.completion`, extract usage, compute cost, write trace, return `LLMResponse`.
5. **Unit tests** — mock `litellm.completion` and `TraceStore`; assert model resolution, cost math, and that the trace write is called before return.
6. **Integration test** — hits a local Ollama model if `OLLAMA_BASE_URL` set; otherwise skips.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Provider token-usage fields vary in shape | Normalise usage extraction in one helper; default missing counts to 0 and log a warning. |
| Cost drift vs. published prices | Prices live only in config (NFR-13); document the "verify before committing" note from planning D.1. |
| Trace write failure masks the completion | Write is best-effort-but-required: on DB error, raise a `RouterError` (no silent success) so NFR-8 holds. |
| Accidental provider SDK import creep | A lint/grep check in `make test` (or a unit test) asserts no `import openai`-style lines in `src/`. |
| Two-layer conflation | Router never imports from `.claude/`; enforced by review + NFR-21. |

## Testing Strategy

- Unit tests: `tests/unit/test_router/` — model resolution by tier/role, cost computation for known token counts, trace-written-before-return ordering (via mock call order), config validation errors.
- Integration tests: `tests/integration/test_router/` — one live call against local Ollama (`ollama/<small-model>`) that skips if `OLLAMA_BASE_URL` unset; asserts a `trace_events` row was written.
- Manual check: set `OLLAMA_BASE_URL`, run a one-off `complete()` for each tier, then `make db-shell` → `SELECT model, prompt_tokens, cost_usd FROM benchmark.trace_events;` shows the calls.
