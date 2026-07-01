# Tasks — Spec 07: Guardrails & Cost Control

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `src/guardrails/` package with `__init__.py`
- [ ] Create `tests/unit/test_guardrails/` and `tests/integration/test_guardrails/` with `__init__.py`

## Action allow-list + safety pre-check

- [ ] `config/allowlist.yaml`: single source of allowed tool actions
- [ ] `src/guardrails/allowlist.py`: load + validate; `check(action) -> Decision`
- [ ] Wire the check into the Spec 02 MCP servers before any write/exec
- [ ] Denied action returns a **structured error** to the agent (no exception across boundary)

## Response cache

- [ ] `src/router/cache.py`: sha256 key over model + normalised messages + params → `CHAR(64)` `cache_key`
- [ ] `get`/`put` against the `llm_cache` table (persistent, NFR-12)
- [ ] Integrate into `router.complete`: lookup before call, store after miss
- [ ] On hit: return cached content, `cache_hit=true`, cost 0, and still write a trace event

## Budget guard

- [ ] `src/guardrails/budget.py`: per-`run_id` cumulative token counter + cap check
- [ ] Default cap sized for < ~$5 / 50-task run; documented in config (NFR-11)
- [ ] Wire into router + graph: on cap, halt, keep best patch, record `budget_exceeded=true`

## Tests

- [ ] Unit: allow-list allows intended Developer actions, denies others (structured error)
- [ ] Unit: cache miss→hit returns identical content, `cache_hit=true`, cost 0; distinct prompts → distinct keys
- [ ] Unit: budget counter halts at cap and sets `budget_exceeded`
- [ ] Integration: runaway task halts at cap with recorded stop point; re-run shows near-zero cost (cache persistence) — skip without Postgres/provider
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
