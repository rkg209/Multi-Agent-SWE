# Spec 01: Model Router

## Goal

Provide a single model-router abstraction, implemented via LiteLLM, through which **every** agent LLM call in the system is made. The router is the only place in the codebase that talks to a model provider: it selects a back-end (hosted via OpenRouter/Together/Groq/etc. or a local Ollama endpoint) from configuration, invokes the model, and records the provider, model, prompt/completion tokens, and computed USD cost to Postgres **before** returning the response to the caller. It also implements the two-tier model policy (strong tier for Architect/Reviewer, small/fast tier for Developer/Tester) so that later specs assign a tier by role, not by hard-coded model name. This is the foundation of the project's cost-measurement discipline: no LLM call may be "silent."

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-9 | Single model-router abstraction (LiteLLM); no agent/app code imports a provider SDK directly. |
| FR-10 | Router supports ≥2 provider back-ends simultaneously, selectable via config without code changes. |
| FR-11 | Two-tier model config — **strong tier** (Architect, Reviewer) and **small/fast tier** (Developer, Tester) — defined in a single config file. |
| FR-12 | Per LLM call, record provider, model, prompt tokens, completion tokens, and USD cost; write to Postgres **before** returning. |
| FR-13 | Support local Ollama endpoints as a zero-cost provider, selectable via env var / config entry. |
| NFR-8 | No silent LLM calls — every call produces a trace record before the response is returned. |
| NFR-13 | Cost recorded in USD per call using published per-token prices from config, not estimated retroactively. |
| NFR-21 | The two model layers stay separated — nothing in router code imports Claude Code tooling. |

## Non-Goals

- No response cache — the `(model, prompt)` cache and `cache_hit` accounting are Spec 07 (`src/router/cache.py`).
- No token-budget cap / halt-on-cap — that is Spec 07 (`src/guardrails/budget.py`).
- No agent logic — the router exposes a `complete()` function; who calls it (Architect, Developer, single-agent) comes in Specs 04/06.
- No retry/fallback routing policy beyond what LiteLLM provides out of the box; advanced routing is deferred.
- No LangGraph integration — the router is a standalone callable in this spec.

## Done-When

All of the following are true and verifiable:

- [x] `config/litellm_config.yaml` defines a strong tier and a small/fast tier, each mapping a role to a model + provider + per-token price, with at least two distinct providers configured.
- [x] A single function (e.g. `src/router/router.py::complete(request)`) returns a completion from a hosted open provider **and** from a local Ollama endpoint, selected purely by config/env — no code change to switch.
- [x] Every call writes one `trace_events` row (provider, model, prompt_tokens, completion_tokens, cost_usd) to Postgres **before** the response is returned to the caller.
- [x] Cost is computed from the per-token prices in config; a unit test asserts the computed `cost_usd` matches the expected value for known token counts.
- [x] Requesting a tier (`strong` / `small`) resolves to the configured model for that tier without the caller naming a model.
- [x] `grep -rE 'import openai|from openai|google.generativeai|anthropic|mistralai|cohere' src/` returns nothing — all calls go through LiteLLM.
- [x] `make lint` exits 0.
- [x] `make test` exits 0 (unit tests mock LiteLLM + the DB; integration test that hits a live/local model skips cleanly when no provider is configured).
- [x] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/00-foundation` — Postgres (`trace_events`, `llm_cache` tables), Makefile, `.env`, pyproject deps (LiteLLM already pinned).

## Status

Complete.
