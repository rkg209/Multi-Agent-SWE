# Implementation Plan — Spec 01: Model Router

## Context

Spec 00 (foundation) is complete: repo skeleton, Postgres with the `benchmark` schema
(`trace_events`, `llm_cache`, `run_records` + two views), Docker sandbox, Makefile, and Claude Code
setup are all in place. `litellm`, `psycopg2-binary`, and `python-dotenv` are already pinned.

Spec 01 builds **the single model-router abstraction** that every agent LLM call in the system must go
through. It is the foundation of the project's cost-measurement discipline: the router is the *only*
place that talks to a model provider, and **no LLM call may be silent** — every call writes a
`trace_events` row (provider, model, tokens, USD cost) to Postgres **before** the response is returned.
It also encodes the two-tier policy (strong tier → Architect/Reviewer, small tier → Developer/Tester)
so later specs assign models by *role*, not by hard-coded name.

This spec is standalone and callable (`complete(request)`); LangGraph wiring, caching, and budget caps
are explicitly out of scope (Specs 04/06/07).

## Scope Reconciliation (differences from spec/plan/tasks — record these in `progress_report.md`)

1. **`trace_events` requires `turn_index` (NOT NULL, ≥0) and `event_type` (NOT NULL, CHECK IN
   'llm_call'…).** The tasks.md `record_llm_call(...)` signature omits both. Resolution:
   `record_llm_call` takes a `turn_index: int = 0` parameter and hard-codes `event_type='llm_call'`.
   Callers in this spec pass `turn_index=0` (real turn tracking arrives with the agents in later specs).
2. **`agent_role` has a CHECK constraint** (`architect|developer|tester|reviewer|system`). Role
   resolution must reject/normalise anything outside this set; an explicit-tier call with no role
   records `agent_role='system'`.
3. **Config path is `config/litellm_config.yaml`** (per `.env.example` `LITELLM_CONFIG`). The
   `llm_cache` table comment mentioning `config/models.yaml` is stale; ignore it.
4. **`pyyaml` is not explicitly pinned** (only transitively via litellm). Add it to `pyproject.toml`
   and `requirements.txt` per tasks.md.

## Key Decisions

- **LiteLLM is the sole provider interface.** All calls go through `litellm.completion(...)`. No
  provider SDK imported anywhere in `src/` (enforced by a grep-style unit test).
- **Config-driven tiers.** `config/litellm_config.yaml` maps `strong`/`small` tiers to a
  `{provider, model, input_price_per_1k, output_price_per_1k, api_base?}` block; a `roles` map assigns
  each role to a tier. Callers ask for a role or an explicit tier; the router resolves the model.
- **Cost computed from config prices at call time** (NFR-13):
  `cost_usd = prompt_tokens/1000*input_price + completion_tokens/1000*output_price`. Ollama = `0.0`.
- **Trace write before return** (NFR-8): `complete()` calls `record_llm_call(...)` before returning;
  a DB failure raises `RouterError` (no silent success).
- **Ollama = zero-cost path** (FR-13): provider `ollama` sets `api_base=OLLAMA_BASE_URL`, model
  `ollama/<name>`, price `0.0`. Switching providers is config/env only — no code change.
- **Typed contract:** `LLMRequest(messages, role?, tier?, max_tokens?, temperature?, run_id?, task_id?,
  turn_index?)` → `LLMResponse(content, model, provider, prompt_tokens, completion_tokens, cost_usd,
  cache_hit=False)`. `cache_hit` is always `False` here (Spec 07 fills it).

## Files to Create

| Path | Purpose |
|------|---------|
| `src/router/__init__.py` | package init; export `complete`, `LLMRequest`, `LLMResponse`, `RouterError` |
| `src/router/config.py` | `ModelSpec`, `TierConfig`, `RouterConfig` dataclasses; `load_router_config(path)` (YAML parse + `os.path.expandvars` env expansion + price validation); `resolve(role_or_tier)` → `ModelSpec` |
| `src/router/router.py` | `LLMRequest`/`LLMResponse` dataclasses, `RouterError`, `complete(request)`, usage-normalisation helper, `_compute_cost(...)` |
| `src/metrics/__init__.py` | package init |
| `src/metrics/trace_store.py` | `record_llm_call(...)` — one INSERT into `benchmark.trace_events`; raises `RouterError` on DB failure |
| `config/litellm_config.yaml` | `tiers.strong` + `tiers.small`, `roles` map, ≥2 hosted providers (OpenRouter + Groq) + one `ollama` entry; secrets via `${ENV_VAR}` |
| `tests/unit/test_router/__init__.py` + tests | resolution, cost math, ordering, config validation, no-SDK-import |
| `tests/integration/test_router/__init__.py` + test | live Ollama call, skips if `OLLAMA_BASE_URL` unset |

## Files to Modify

- `pyproject.toml` — add `pyyaml>=6.0` to `dependencies`.
- `requirements.txt` — add `pyyaml>=6.0`.
- `.env.example` — add `OPENROUTER_API_KEY=`, `GROQ_API_KEY=`, `OLLAMA_BASE_URL=http://localhost:11434`.
- `specs/01-model-router/tasks.md` — check off tasks as completed.
- `specs/01-model-router/spec.md` — append `## Status → Complete.` at the end.
- `progress_report.md` — append a new `## Sequence NN — Spec 01: Model Router` section (What/Why/How/
  Issues & Resolutions/Verification/Files touched), including the reconciliation points above.

## Implementation Order

1. **Deps + env**: add `pyyaml` to `pyproject.toml` + `requirements.txt`; add the three env vars to
   `.env.example`. `pip install -e ".[dev]"` (or `pip install pyyaml`).
2. **`config/litellm_config.yaml`**: define tiers, roles, providers (see shape below).
3. **`src/router/config.py`**: dataclasses + loader (env expansion via `os.path.expandvars`, fail
   loudly on missing prices / unknown tier / unknown role) + `resolve()`.
4. **`src/metrics/trace_store.py`**: `record_llm_call(...)` using `psycopg2` against `DATABASE_URL`,
   `INSERT INTO benchmark.trace_events (...)` with `event_type='llm_call'`; wrap DB errors (catch
   `psycopg2.Error`, no bare except) and re-raise `RouterError`.
5. **`src/router/router.py`**: `complete()` — resolve tier→model, build LiteLLM kwargs (inc. `api_base`
   for ollama), call `litellm.completion`, normalise usage in one helper (default missing counts to 0,
   log a warning), compute cost, `record_llm_call(...)`, return `LLMResponse`.
6. **Unit tests** (mock `litellm.completion` and `record_llm_call`).
7. **Integration test** (live Ollama, skip-clean).
8. `make lint && make test`; then update tasks.md/spec.md/progress_report.md.

## Config Shape (`config/litellm_config.yaml`)

```yaml
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
# Optional local override tier (zero cost), selectable via config only:
  local:
    provider: ollama
    model: ollama/llama3.1
    input_price_per_1k: 0.0
    output_price_per_1k: 0.0
    api_base: ${OLLAMA_BASE_URL}
roles:
  architect: strong
  reviewer:  strong
  developer: small
  tester:    small
```
(Prices are placeholders flagged "verify before commit"; secrets stay as `${OPENROUTER_API_KEY}` /
`${GROQ_API_KEY}` env references — never literal keys.)

## Reused Existing Patterns

- **DB connect pattern** — mirror `scripts/wait_for_postgres.py` / `tests/integration/test_foundation/
  test_postgres.py`: `psycopg2.connect(os.environ["DATABASE_URL"])`, `with conn.cursor()`, `try/finally
  conn.close()`, catch `psycopg2.OperationalError`/`psycopg2.Error` specifically.
- **Integration skip pattern** — reuse the `_can_connect()` + `pytest.mark.skipif` / `importorskip`
  idiom from `test_postgres.py` for the Ollama skip.
- **Env loading** — `python-dotenv` is already a dependency and `DATABASE_URL` already lives in
  `.env.example`.
- **Coding conventions (CLAUDE.md):** `from __future__ import annotations`, type hints on all
  signatures, docstrings on public funcs, no bare `except`, no `print` (use
  `logging.getLogger(__name__)`), no direct provider SDK imports.

## Testing Strategy

Unit (`tests/unit/test_router/`), all with `litellm.completion` and `record_llm_call` mocked:
- resolution by role (`developer`→small model) and by explicit tier (`strong`→strong model);
- unknown role/tier raises a clear error;
- cost math: known token counts (e.g. 1000 prompt / 500 completion at the configured prices) → assert
  exact `cost_usd`;
- ordering: assert `record_llm_call` is invoked **before** `complete()` returns (via mock call-order /
  side-effect list);
- config validation: missing price or unknown tier raises;
- no-SDK-import guard: `grep -rE 'import openai|from openai|google.generativeai|anthropic|mistralai|
  cohere' src/` returns nothing (subprocess or path-walk assertion).

Integration (`tests/integration/test_router/`):
- one live `complete()` against local Ollama (`role`/tier resolving to the `ollama/` model); skips if
  `OLLAMA_BASE_URL` unset **or** Postgres unreachable; asserts a `trace_events` row was written with
  `cost_usd = 0`.

## Verification (Done-When mapping)

Run from repo root:
- `make lint` → exits 0.
- `make test` → exits 0 (unit pass; integration skips cleanly without Ollama/Postgres).
- `grep -rE 'import openai|from openai|google.generativeai|anthropic|mistralai|cohere' src/` → no
  output (FR-9 / no silent SDK).
- Manual (optional, needs local Ollama + Postgres up): set `OLLAMA_BASE_URL`, run a one-off
  `complete(LLMRequest(role="developer", messages=[...]))` for a small tier and a strong tier, then
  `make db-shell` → `SELECT provider, model, prompt_tokens, completion_tokens, cost_usd FROM
  benchmark.trace_events ORDER BY created_at DESC LIMIT 5;` shows the calls with correct cost.
- Confirm each `spec.md` Done-When checkbox is satisfied; append the Spec 01 sequence to
  `progress_report.md`; run `/code-review` for a blocking-issue pass.
