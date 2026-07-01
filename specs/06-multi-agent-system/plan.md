# Implementation Plan — Spec 06: Multi-Agent System

## Overview

Enable the three dormant nodes and the routing edges on the Spec 04 graph. Add Architect (plan), Tester (structured PASS/FAIL + route-back), and Reviewer (quality/security + route-back) nodes, each calling the router by role for tier assignment and the tool layer for sandboxed I/O. Add conditional edges and two capped feedback loops, and turn on LangGraph checkpointing. `SOLVER=multi` selects this configuration through the same harness seam as `single`.

## Key Decisions

1. **Reuse the graph, don't fork it (FR-28 continuity).** Spec 04 built the graph with `solver_config` gating. `multi` enables all four nodes + edges; `single` stays as-is. Shared state, tracing, router, tools.
2. **Structured inter-node contracts.** Architect → `Plan(files, approach, constraints)`; Tester → `TestResult(passed, failures)`; Reviewer → `Review(approved, issues)`. Nodes read/write these on `GraphState` (per architecture §4.2).
3. **Conditional routing.** Tester FAIL → Developer; Reviewer issues → Developer; success paths advance. Routing lives in graph edges, not inside prompts.
4. **Two independent capped loops (FR-39/40).** Separate counters for Dev↔Test (default 3) and Dev↔Review (default 2). On cap: stop, keep best patch, set `cap_hit=true` on the run record. Caps are config values.
5. **Tier by role (FR-42).** Nodes pass `agent_role` to the router; tier map from Spec 01 config (Architect/Reviewer=strong, Developer/Tester=small). No model names in node code.
6. **Checkpointing (FR-41).** Use LangGraph's checkpointer (e.g. Postgres/SQLite saver) keyed by `run_id`; a resumed run continues from the last completed node.
7. **"Best available patch" defined.** Track the last patch that most recently passed the Tester; on cap or termination, return that, else the latest attempt.

## Implementation Order

1. **`src/agents/architect.py`** — issue+snapshot → `Plan`; strong tier.
2. **Extend `src/agents/developer.py`** — consume Architect `Plan` and Tester/Reviewer feedback (not just self-loop).
3. **`src/agents/tester.py`** — run suite via run-code tool → `TestResult`; small tier.
4. **`src/agents/reviewer.py`** — evaluate patch → `Review`; strong tier.
5. **`src/graph/graph.py`** — add nodes + conditional edges + two capped loops for `multi`.
6. **Checkpointing** — configure the saver; add resume support keyed by `run_id`.
7. **`benchmark/solver.py`** — `MultiAgentSolver` at the `Solver` seam; register `SOLVER=multi`.
8. **Tests + E2E** — unit for each node + routing/cap logic; live multi run for comparability with single.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Loops thrash without converging | Hard iteration caps (FR-39/40) + best-patch retention; token budget guard arrives in Spec 07. |
| Multi-agent doesn't beat single | Expected/acceptable — the honest finding is the result; ensure comparability, not a win. |
| Checkpoint state grows / serialization issues | Keep `GraphState` small + serialisable; test interrupt-and-resume explicitly. |
| Tier misassignment silently uses wrong model | Assert `trace_events.model` per role in a test; caps + role passed explicitly. |
| Reviewer/Tester routing bugs create infinite loops | Cap counters are the backstop; unit-test each conditional edge. |

## Testing Strategy

- Unit tests: `tests/unit/test_agents/` + `tests/unit/test_graph/` — each node's I/O contract (mocked router/tools); Tester-FAIL routes to Developer; Reviewer-issues routes to Developer; Dev↔Test cap=3 and Dev↔Review cap=2 set `cap_hit`; role→tier passed to router.
- Integration tests: `tests/integration/test_multi_agent/` — `SOLVER=multi` end-to-end on a fixture; checkpoint interrupt→resume continues from last node; per-agent turns present in trace. Skip without provider + Docker.
- Manual check: run `single` then `multi` on the same subset; `make db-shell` → compare `run_records` for both `solver_config`s.
