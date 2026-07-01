# Tasks — Spec 01: Model Router

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `src/router/` and `src/metrics/` packages with `__init__.py`
- [ ] Confirm `litellm` and `psycopg2-binary` (or SQLAlchemy) are already pinned in `pyproject.toml` (added in Spec 00); add `pyyaml` if not present, to `pyproject.toml` and `requirements.txt`
- [ ] Create test dirs `tests/unit/test_router/` and `tests/integration/test_router/` with `__init__.py`

## Config

- [ ] Write `config/litellm_config.yaml`:
  - `tiers.strong` and `tiers.small`, each with `provider`, `model`, `input_price_per_1k`, `output_price_per_1k`, and optional `api_base`
  - Role→tier map: `architect: strong`, `reviewer: strong`, `developer: small`, `tester: small`
  - At least two distinct hosted providers configured, plus one `ollama` entry with `price 0.0`
  - Reference secrets via env vars (`${OPENROUTER_API_KEY}`, `${OLLAMA_BASE_URL}`) — no keys in the file
- [ ] Add the new env vars to `.env.example`

## Router config loader

- [ ] `src/router/config.py`: typed dataclasses `ModelSpec`, `TierConfig`, `RouterConfig`
- [ ] `load_router_config(path)` — parse YAML, expand env vars, validate all prices present, raise a clear error on unknown tier/role
- [ ] `resolve(role_or_tier)` — return the `ModelSpec` for a role or an explicit tier

## Trace write path

- [ ] `src/metrics/trace_store.py`: `record_llm_call(...)` inserts one row into `benchmark.trace_events` (provider, model, prompt/completion tokens, cost_usd, cache_hit, run_id, task_id, agent_role)
- [ ] On DB failure raise `RouterError` (no bare except) — never swallow silently

## Router

- [ ] `src/router/router.py`: `LLMRequest` / `LLMResponse` dataclasses
- [ ] `complete(request)` — resolve tier→model, call `litellm.completion`, normalise usage, compute `cost_usd` from config prices, `record_llm_call(...)`, then return `LLMResponse`
- [ ] Ollama path: set `api_base=OLLAMA_BASE_URL`, model `ollama/<name>`, cost `0.0`
- [ ] Type hints + docstrings on all public functions; `logging.getLogger(__name__)` (no `print`)

## Tests

- [ ] Unit: model resolution by role and by explicit tier
- [ ] Unit: cost computation for known token counts (assert exact USD)
- [ ] Unit: trace-write-happens-before-return (assert mock call order)
- [ ] Unit: config validation raises on missing price / unknown tier
- [ ] Unit: no direct provider SDK imports in `src/` (grep-style assertion)
- [ ] Integration: live call to local Ollama; skips if `OLLAMA_BASE_URL` unset; asserts a `trace_events` row exists
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
