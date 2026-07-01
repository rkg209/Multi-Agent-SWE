# Implementation Plan — Spec 05: Instrumentation & Metrics

## Overview

Extend the write-path trace store from Spec 01 into the full trace + metrics layer. Wrap each agent turn so it emits a complete `trace_events` row including tool calls and duration. Add a static hallucination checker that diffs referenced paths/symbols against the repo snapshot. Compute iteration count from the trace and latency percentiles at run-close, writing aggregates so the headline table is a single query.

## Key Decisions

1. **One `run_id` threads everything (NFR-9).** Assigned at run start (harness), carried in `GraphState`, stamped on every trace event, tool call, and the final `run_records` row.
2. **Turn-level tracing via a wrapper, not per-node boilerplate.** A decorator/context manager records `turn_index`, `agent_role`, model, tokens, cost, `duration`, and captured tool calls around each node execution, so future nodes get tracing for free.
3. **Hallucination = static existence check (FR-30).** Build the snapshot's file tree + a lightweight symbol table (module/function/class names via AST for Python repos). Extract path/symbol references from agent outputs; any reference absent from the snapshot flags the run. Conservative: only flag confident references to avoid false positives.
4. **Iteration count from the trace (FR-31).** Count Developer→Tester→(fail)→Developer cycles. In single-agent mode this maps to Developer self-loop passes; the same counter serves multi-agent in Spec 06.
5. **Latency percentiles at run-close (FR-32).** Compute p50/p99 of per-task end-to-end durations across the benchmark execution; store on run rows and expose via the `run_summary` view.
6. **Headline table is one query (FR-33).** Prefer the existing `run_summary` / `task_cost_breakdown` views (created in Spec 00); extend them so a single `SELECT ... WHERE solver_config = ...` yields all five headline metrics. Ensure indexes (NFR-10).

## Implementation Order

1. **`src/metrics/trace_store.py`** — extend to full turn records + tool-call capture + read helpers; keep the Spec 01 `record_llm_call` compatible.
2. **Turn-tracing wrapper** — apply around the Developer node (and ready for all nodes).
3. **`src/metrics/hallucination.py`** — snapshot file tree + AST symbol table; reference extraction; per-run flag; store on `run_records`.
4. **Iteration counter** — derive from trace; store on `run_records`.
5. **Latency aggregation** — compute p50/p99 at run-close; store aggregates; verify/extend `run_summary` view.
6. **Index + query check** — confirm indexes on `run_id`/`task_id`/`solver_config`; write the single headline query; assert < 2 s.
7. **Tests** — hallucination true/false-positive fixtures, iteration math, percentile math, headline query correctness.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Hallucination false positives (string that looks like a path) | Conservative extraction; require a confident reference form; unit-test both directions. |
| Symbol table cost on large repos | Cheap AST pass over Python files only; cache per snapshot; skip non-Python gracefully. |
| Percentile math on tiny N | Define behaviour for N<2 explicitly (p50=p99=only value); test it. |
| Trace write overhead per turn | Batch/one INSERT per turn; keep under the harness overhead budget (NFR-14). |
| View drift from Spec 00 schema | Alter views idempotently; keep `run_records` columns stable (no destructive migration). |

## Testing Strategy

- Unit tests: `tests/unit/test_metrics/` — hallucination flags a bogus path/symbol and does NOT flag a real one; iteration counter on synthetic traces; p50/p99 on known distributions (incl. N=1).
- Integration tests: `tests/integration/test_metrics/` — run the single-agent slice, then assert the headline query returns all five metrics for `solver_config=single`; assert query latency < 2 s. Skip without Postgres.
- Manual check: `make db-shell` → run the headline query for `single`; eyeball success rate / cost / latency / hallucination / iterations.
