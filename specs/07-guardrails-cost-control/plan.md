# Implementation Plan — Spec 07: Guardrails & Cost Control

## Overview

Insert three interception points without touching agent logic: (1) an allow-list + safety pre-check at the tool-layer boundary so disallowed writes/execs return structured rejections; (2) a budget guard threaded through the router/graph that halts a run on the token cap; (3) a Postgres-backed response cache in the router so repeat `(model, prompt)` pairs skip the LLM. All three read from single config files and record their effects in the trace / run record.

## Key Decisions

1. **Allow-list at the boundary, config-driven (FR-46, NFR-4).** `config/allowlist.yaml` lists permitted actions (e.g. `write_file`, `exec` with constraints). `allowlist.py` is called by the MCP servers (Spec 02) before executing. It is the single gate; agents cannot bypass it because tools always consult it.
2. **Structured rejection, not exception (FR-45).** A denied action returns `{"error": {"code": "denied", "reason": ...}}` to the agent, matching the tool-boundary contract from Spec 02. Internal misuse (bypassing the gate) is the defect NFR-4 forbids.
3. **Budget guard in the router path (FR-43).** The router increments a per-`run_id` token counter on each call; when cumulative tokens ≥ cap, it signals halt. The graph catches the halt, keeps the best patch, and the harness writes `budget_exceeded=true`. Default cap documented in config and sized for < ~$5 / 50 tasks (NFR-11).
4. **Persistent cache keyed by hash(model, prompt) (FR-44, NFR-12).** Reuse the Spec 00 `llm_cache` table. Before calling LiteLLM, the router looks up the key; on hit, return cached content with `cache_hit=true`, cost 0, and still write a trace event (so cache hits are observable). On miss, call, then store.
5. **Cache correctness.** Key includes model + normalised messages (+ relevant params like temperature) so different prompts don't collide. Deterministic hashing (sha256) → the `CHAR(64)` `cache_key`.
6. **Guardrails are opt-out-safe.** Defaults on; all thresholds in config so a demo can raise them without code change.

## Implementation Order

1. **`config/allowlist.yaml`** + **`src/guardrails/allowlist.py`** — load, validate, `check(action) -> Decision`.
2. **Wire allow-list + safety pre-check into the Spec 02 MCP servers** — deny returns structured error.
3. **`src/router/cache.py`** — key builder, `get`/`put` against `llm_cache`; integrate into `router.complete` (lookup before call, store after).
4. **Trace cache hits** — set `cache_hit=true`, cost 0 on cached-path trace events.
5. **`src/guardrails/budget.py`** — per-run token counter; cap check; halt signal.
6. **Wire budget into router + graph** — catch halt, keep best patch, record `budget_exceeded=true`.
7. **Tests** — allow-list allow/deny, cache hit/miss + persistence, budget halt + flag; a runaway-task integration test.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Cache key collisions / stale hits | Include model + normalised messages + params in the hash; unit-test distinct prompts → distinct keys. |
| Budget halt leaves inconsistent state | Halt at a node boundary; always retain best patch; write the run record in a `finally` path. |
| Allow-list bypass via direct function calls (NFR-4) | Only the MCP servers touch the filesystem/exec; a test asserts no agent code calls tools around the gate. |
| Cache masking real cost changes across model swaps | Key on model; changing model → cache miss (correct). |
| Over-aggressive denial breaks legit writes | Start permissive-but-explicit; unit-test the intended Developer actions are allowed. |

## Testing Strategy

- Unit tests: `tests/unit/test_guardrails/` — allow-list allows intended actions, denies others with a structured error; budget counter halts at cap and flags `budget_exceeded`; `tests/unit/test_router/` — cache miss then hit returns identical content with `cache_hit=true`, cost 0.
- Integration tests: `tests/integration/test_guardrails/` — a runaway task halts at the cap with a recorded stop point; re-running a completed benchmark shows near-zero LLM cost (cache persistence across restart). Skip without Postgres/provider.
- Manual check: run a benchmark twice; `make db-shell` → second run's `trace_events` show `cache_hit=true` and cost 0; confirm any capped run shows `budget_exceeded=true`.
