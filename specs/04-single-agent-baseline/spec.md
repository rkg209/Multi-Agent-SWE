# Spec 04: Single-Agent Baseline (Thin End-to-End Slice)

## Goal

Produce the project's first **real** end-to-end result: one agent that takes a ticket (issue text + repo snapshot), makes a plan, writes code changes through the tool layer (sandbox only), runs the task's tests, and returns a patch the harness scores. This is the thin slice that connects the router (Spec 01), tool layer (Spec 02), and harness (Spec 03) into a working system that records a genuine success/fail with real cost and latency. Critically, the single-agent solver is implemented as a **degenerate case of the LangGraph graph** — a graph whose only active node is the Developer — so that when the multi-agent system arrives (Spec 06) both configurations share the exact same instrumentation, router, tool layer, and metrics writer with no separate code path.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-26 | Single-agent solver: ticket → plan → write code (sandbox) → run tests → return patch. |
| FR-27 | The solver resolves ≥1 task end-to-end (real PASS in `run_records` with real cost + latency) before multi-agent work begins. |
| FR-28 | Implemented as a degenerate LangGraph graph (one active node), **not** a separate code path — shared instrumentation. |

## Non-Goals

- No Architect / Tester / Reviewer nodes and no multi-node routing — that is Spec 06. The graph exists but only the Developer node is active.
- No full metric suite (hallucination check, p50/p99 aggregation) — Spec 05. Basic cost/latency come free via the router + harness.
- No guardrails (token budget cap, action allow-list, cache) — Spec 07.
- No new tools or scoring — reuse Specs 02 and 03 as-is.
- No prompt-tuning marathon — get one honest PASS, then stop; quality work is later.

## Done-When

All of the following are true and verifiable:

- [ ] `src/graph/state.py` defines the typed `GraphState` (`TypedDict`) shared by all nodes.
- [ ] `src/graph/graph.py` builds a LangGraph graph; a `solver_config` selects **single** mode → only the Developer node is active (Architect/Tester/Reviewer disabled), with an optional self-loop.
- [ ] `src/agents/developer.py` implements the Developer node: reads the repo via the filesystem tool, plans, writes changes and runs tests via the run-code tool (sandbox only), and emits a patch.
- [ ] The solver plugs into the Spec 03 harness at the `Solver` seam as `SOLVER=single`.
- [ ] `make benchmark TASKS=<subset> SOLVER=single` runs at least one task **end-to-end** and records a **real** outcome (≥1 PASS) in `run_records` with real cost (from the router) and latency.
- [ ] Every LLM call the Developer makes is logged to `trace_events` via the Spec 01 router (no silent calls).
- [ ] All code execution happens in the sandbox — verified by the run-code server boundary (no host exec).
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (unit tests mock the router + tools; the live end-to-end run is an integration test that skips without a model provider + Docker).
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/01-model-router` — LLM calls + cost logging.
- `specs/02-tool-layer` — filesystem/run-code/git tools + sandbox.
- `specs/03-benchmark-harness` — `Solver` seam, loader, scorer, results writer.
