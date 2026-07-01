# Tasks — Spec 05: Instrumentation & Metrics

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Ensure `src/metrics/` package exists (from Spec 01); create `tests/unit/test_metrics/` and `tests/integration/test_metrics/` with `__init__.py`

## Full trace store

- [ ] Extend `src/metrics/trace_store.py` to record complete turn rows (role, turn_index, model, tokens, cost, duration, tool_calls) linked by `run_id`
- [ ] Keep `record_llm_call` (Spec 01) compatible; add read helpers for metric queries
- [ ] Turn-tracing wrapper (decorator/context manager) around node execution; apply to Developer node

## Hallucination checker

- [ ] `src/metrics/hallucination.py`: build snapshot file tree + AST symbol table
- [ ] Extract path/symbol references from agent outputs; flag run if any absent from snapshot
- [ ] Store the flag on the `run_records` row (conservative — minimise false positives)

## Iteration count

- [ ] Compute Developer↔Tester (single: Developer self-loop) cycles from the trace; store on `run_records`

## Latency aggregation

- [ ] Compute p50 + p99 end-to-end latency across a run at run-close; store aggregates
- [ ] Verify/extend the `run_summary` view to expose them

## Headline query + indexes

- [ ] Confirm indexes on `run_id`, `task_id`, `solver_config`
- [ ] Write the single headline query (or extend views) returning success rate, mean cost/solved task, p50/p99 latency, hallucination rate, mean iterations for a named `solver_config`
- [ ] Assert headline query runs < 2 s on the full subset

## Tests

- [ ] Unit: hallucination flags bogus path/symbol, not real ones (both directions)
- [ ] Unit: iteration counter on synthetic traces; p50/p99 on known distributions incl. N=1
- [ ] Integration: single-agent run → headline query returns all five metrics; latency < 2 s — skip without Postgres
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md` (esp. FR-33 single-query headline)
- [ ] Add `## Status` → `Complete.` to `spec.md`
