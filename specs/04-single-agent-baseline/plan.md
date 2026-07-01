# Implementation Plan — Spec 04: Single-Agent Baseline

## Overview

Stand up the minimal LangGraph graph and a single Developer node, then wire it into the harness as `SOLVER=single`. The Developer node runs the full inner loop for one agent: read repo → plan → edit → run tests → return patch, using the router for reasoning and the tool layer for all I/O and execution. Because the graph and state are introduced here (single active node), Spec 06 later just enables the other three nodes and the routing edges — no rewrite.

## Key Decisions

1. **Graph-first, even for one node (FR-28).** Introduce `GraphState` + `graph.py` now. Single mode = graph with Architect/Tester/Reviewer disabled via `solver_config`. This guarantees single and multi share instrumentation.
2. **Developer node owns the inner loop for the baseline.** It plans (one strong-ish call or the small tier per config), writes files, runs tests, and decides done/continue with a self-loop capped (default 3) to avoid runaway.
3. **All LLM calls via the Spec 01 router.** The node passes `agent_role="developer"` so the router applies the configured tier and logs `trace_events`.
4. **All file/exec via the Spec 02 tool layer.** No direct filesystem writes or subprocess in agent code — reads via filesystem server, execution via run-code server (sandbox).
5. **Harness seam reuse.** `SingleAgentSolver.solve(task)` builds initial `GraphState` from the `Task`, runs the graph, returns the final patch to the Spec 03 scorer/results writer.
6. **Stop at first honest PASS (FR-27).** Success criterion for the spec is one real end-to-end PASS with real cost/latency; prompt/quality iteration is deferred.

## Implementation Order

1. **`src/graph/state.py`** — `GraphState` TypedDict: task, plan, patch, test_result, iteration, solver_config, run_id.
2. **`src/agents/developer.py`** — Developer node function: read → plan (router) → write (tools) → run tests (tools) → update state; self-loop decision.
3. **`src/graph/graph.py`** — build graph; conditional inclusion of nodes by `solver_config`; single mode wires only Developer (+ self-loop edge).
4. **`benchmark/solver.py`** — add `SingleAgentSolver` implementing the `Solver` seam; register `SOLVER=single`.
5. **End-to-end run** — pick an easy custom ticket first, get a real PASS, then try a SWE-bench lite task.
6. **Tests** — unit (mock router + tools) for node logic and state transitions; integration for the live slice.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Model can't solve any task → no PASS | Start with the easiest hand-authored custom ticket; only then attempt SWE-bench lite. |
| Self-loop runs away on cost | Hard-cap iterations (default 3) now; full budget guard is Spec 07. |
| Tool-call plumbing between node and MCP servers is brittle | Reuse the Spec 02 test driver pattern; assert the node only touches the sandbox. |
| Graph abstraction over-built for one node | Keep `graph.py` minimal but node-pluggable; resist adding routing not needed until Spec 06. |
| Non-deterministic model output flakes tests | Unit tests mock the model; the live PASS is an integration test, not a gate for `make test`. |

## Testing Strategy

- Unit tests: `tests/unit/test_graph/` and `tests/unit/test_agents/` — state transitions, Developer node calls router with `role=developer`, writes/executes only via tools (mocked), self-loop cap respected.
- Integration tests: `tests/integration/test_single_agent/` — `SOLVER=single` on one fixture task end-to-end, asserting a `run_records` row with real cost/latency and `trace_events` rows. Skip without a model provider (or Ollama) + Docker.
- Manual check: `make benchmark TASKS=lite-5 SOLVER=single`; `make db-shell` → confirm ≥1 PASS row with non-zero cost and latency, and matching trace events.
