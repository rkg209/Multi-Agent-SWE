# Spec 05: Instrumentation & Metrics

## Goal

Turn the working single-agent slice into a fully measured system. This spec completes the trace store so **every** agent turn is recorded (role, turn index, model, tokens, cost, wall-clock, tool calls), and adds the computed metrics that make the headline table possible: per-run **hallucination flag** (static check that every referenced file path / symbol exists in the task's repo snapshot), **iteration count** (Developer↔Tester cycles), and **p50/p99 end-to-end latency** aggregated across a run. The acceptance bar is that a single SQL query against the schema reproduces the full headline metric set (success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations) for a named solver configuration.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-29 | Every agent turn recorded as a `trace_events` row (run_id, task_id, agent_role, turn_index, model, prompt/completion tokens, cost, duration, tool calls). |
| FR-30 | Compute + store per-run hallucination flag (referenced path/symbol not in repo snapshot → flagged), via static check against the file tree + symbol table. |
| FR-31 | Compute + store iteration count per run (Developer↔Tester feedback cycles). |
| FR-32 | Compute p50 and p99 end-to-end latency across a benchmark run; store aggregates. |
| FR-33 | A single SQL query reproduces the full headline table for a named solver config. |
| NFR-8 | No silent LLM calls — every call already traced (Spec 01); this spec extends turn/tool coverage. |
| NFR-9 | Every run has a unique `run_id` linking all trace events, tool calls, and the run record. |
| NFR-10 | Indexes on `run_id`, `task_id`, `solver_config` support interactive-latency queries (< 2 s). |

## Non-Goals

- No dashboard rendering — Spec 08 consumes these metrics; here we only guarantee the data + query exist.
- No multi-agent turns yet — the Developer↔Tester loop is fully realised in Spec 06; here iteration-count logic is implemented and exercised on the single-agent self-loop, ready for multi.
- No response cache / budget accounting fields beyond what the trace records — Spec 07 fills `cache_hit`/`budget_exceeded` semantics.
- No new agent behaviour — this is measurement, not capability.

## Done-When

All of the following are true and verifiable:

- [ ] `src/metrics/trace_store.py` records **every** agent turn (not just LLM calls): role, turn_index, model, tokens, cost, duration, and any tool calls, all linked by `run_id` (NFR-9).
- [ ] `src/metrics/hallucination.py` performs a static check: any file path or symbol referenced by an agent that is absent from the task's repo snapshot flags the run; the flag is stored on the `run_records` row.
- [ ] Iteration count (Developer↔Tester cycles) is computed and stored per run.
- [ ] p50 and p99 end-to-end latency are computed across a benchmark run and stored as aggregates (per-run rows + the run-level summary view).
- [ ] A single SQL query (or the `run_summary` / `task_cost_breakdown` views) returns, for a named `solver_config`: success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations (FR-33).
- [ ] Indexes exist on `run_id`, `task_id`, `solver_config`; the headline query runs < 2 s on the full subset (NFR-10).
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (unit tests cover hallucination detection + metric math on fixtures; DB-backed tests skip cleanly without Postgres).
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/04-single-agent-baseline` — a real end-to-end run producing turns to measure.
