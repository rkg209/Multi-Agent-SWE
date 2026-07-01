# Spec 07: Guardrails & Cost Control

## Goal

Make runs safe to leave running and cheap to repeat. This spec adds the four cost/safety mechanisms that turn the multi-agent system from "works" into "works within a budget": an **action allow-list** checked at the tool-layer boundary (not in prompts), a **safety pre-check** before any file write or code run that returns a structured rejection instead of raising, a **per-task token-budget cap** that halts a runaway run and records `budget_exceeded=true` with the best patch, and a **persistent response cache** so identical `(model, prompt)` pairs return the cached response at zero cost with `cache_hit=true`. Together these satisfy the project's cost target (a full 50-task run under ~$5) and close NFR-1 layer via the allow-list as the single authoritative gate.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-43 | Per-task token-budget cap: on reaching the cap, halt immediately, record `budget_exceeded=true`, return best patch. |
| FR-44 | Response cache: identical (model, prompt) → cached response, no new call; `cache_hit=true`, zero cost in trace. |
| FR-45 | Safety pre-check before any file write / code run; disallowed actions rejected with a **structured error** (not an exception). |
| FR-46 | Allowed-action list in a single config file, checked at the tool-layer boundary (not inside agent prompts). |
| NFR-4 | The allow-list is the single authoritative gate for all agent tool calls; bypassing via direct calls is a defect. |
| NFR-11 | Token-budget default keeps an expected full 50-task run under ~$5; default documented in config. |
| NFR-12 | Response cache persistent across process restarts (Postgres `llm_cache`), so re-runs don't re-incur cost. |

## Non-Goals

- No new agent behaviour or graph topology — this wraps existing Spec 06 nodes/tools.
- No dashboard — Spec 08 will surface `cap_hit` / `budget_exceeded` / cache-hit rate.
- No provider-side rate limiting or retry policy beyond LiteLLM defaults.
- No change to the sandbox hard boundary (Spec 02) — the allow-list is an additional, structured gate above it, not a replacement.

## Done-When

All of the following are true and verifiable:

- [ ] `config/allowlist.yaml` (single file) defines the allowed tool actions; `src/guardrails/allowlist.py` enforces it at the tool-layer boundary (FR-46, NFR-4).
- [ ] Before any file write or code exec, the safety pre-check runs; a disallowed action returns a **structured error** object to the agent, and is **not** raised as an exception (FR-45).
- [ ] `src/guardrails/budget.py` tracks cumulative tokens per run; on reaching the configured cap the run halts immediately, `budget_exceeded=true` is recorded on `run_records`, and the best available patch is returned (FR-43).
- [ ] The budget default is set so an expected full 50-task run stays under ~$5, and the default is documented in config (NFR-11).
- [ ] `src/router/cache.py` implements a Postgres-backed `(model, prompt)` cache; a repeat call returns the cached response with **no** new LLM call, `cache_hit=true`, and zero cost in the trace (FR-44).
- [ ] The cache persists across process restarts — re-running a benchmark after a restart incurs no LLM cost for already-seen calls (NFR-12).
- [ ] A "runaway" test task halts at the cap and the run record shows where it stopped; a re-run of a completed benchmark shows near-zero LLM cost due to cache hits.
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (unit tests cover allow-list decisions, budget halt, cache hit/miss; DB-backed cache tests skip without Postgres).
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/06-multi-agent-system` — the multi-agent run these guardrails wrap.
- `specs/01-model-router` — router is where the cache and cost accounting live.
- `specs/02-tool-layer` — the tool boundary where the allow-list + safety pre-check are enforced.
