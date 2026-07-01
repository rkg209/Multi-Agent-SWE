# Spec 06: Multi-Agent System

## Goal

Realise the full four-agent LangGraph team — **Architect → Developer → Tester → Reviewer** — on top of the graph scaffold introduced in Spec 04. The Architect plans files-to-touch and approach; the Developer implements via the tool layer; the Tester runs the suite in the sandbox and routes back to the Developer on failure; the Reviewer evaluates the passing patch and routes back on issues. Both feedback loops are capped (Developer↔Tester default 3, Developer↔Reviewer default 2) with a `cap_hit` flag, and the graph uses LangGraph checkpointing so an interrupted run resumes from the last completed node. Each node uses the model tier assigned to its role (Architect/Reviewer → strong; Developer/Tester → small/fast). This is the multi-agent configuration whose cost and success the project exists to measure against the single-agent baseline.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-34 | LangGraph graph with four named nodes (Architect, Developer, Tester, Reviewer) in default order. |
| FR-35 | Architect: from issue + snapshot → files to modify, high-level approach, constraints for Developer. |
| FR-36 | Developer: from Architect's plan → code changes via filesystem + run-code tools (sandbox only). |
| FR-37 | Tester: run the suite in sandbox → structured PASS/FAIL; on FAIL route back to Developer. |
| FR-38 | Reviewer: evaluate passing patch for quality + security → APPROVED or issues; on issues route back to Developer. |
| FR-39 | Developer↔Tester loop capped (default 3); on cap, terminate with best patch + `cap_hit=true`. |
| FR-40 | Developer↔Reviewer loop capped (default 2); on cap, terminate with current patch + `cap_hit=true`. |
| FR-41 | Use LangGraph checkpointing so an interrupted run resumes from the last completed node. |
| FR-42 | Each node uses its role's model tier (Architect/Reviewer → strong; Developer/Tester → small/fast). |

## Non-Goals

- No token-budget cap / action allow-list / response cache — Spec 07 (this spec caps **iterations**, not tokens).
- No parallel specialist reviewers — stretch S1 (this spec is a single sequential Reviewer).
- No dashboard / comparison run — Spec 08.
- No new tools or scorer — reuse Specs 02/03; no new metric definitions — reuse Spec 05 (which already generalised iteration count + tracing for multi).

## Done-When

All of the following are true and verifiable:

- [ ] `src/agents/architect.py`, `developer.py` (extended), `tester.py`, `reviewer.py` implement the four nodes with typed I/O against `GraphState`.
- [ ] `src/graph/graph.py` wires the default order Architect→Developer→Tester→Reviewer with conditional edges: Tester FAIL → Developer; Reviewer issues → Developer.
- [ ] `SOLVER=multi` runs the full team end-to-end and resolves tasks; traces show per-agent turns with correct roles (FR-34, Spec 05 tracing).
- [ ] Developer↔Tester loop stops at the configured cap (default 3) and sets `cap_hit=true` with the best available patch (FR-39).
- [ ] Developer↔Reviewer loop stops at the configured cap (default 2) and sets `cap_hit=true` (FR-40).
- [ ] Each node calls the router with its role so tier assignment holds (Architect/Reviewer → strong, Developer/Tester → small) — verifiable in `trace_events.model` (FR-42).
- [ ] Checkpointing works: an interrupted run resumes from the last completed node without re-executing prior nodes (FR-41).
- [ ] `make benchmark TASKS=<subset> SOLVER=multi` records real outcomes in `run_records`, directly comparable to `SOLVER=single`.
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (unit tests mock router + tools for each node + routing logic; live E2E is an integration test that skips without provider + Docker).
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/04-single-agent-baseline` — graph scaffold, Developer node, `GraphState`, `Solver` seam.
- `specs/05-instrumentation-metrics` — turn tracing + iteration count generalised for multi-node.
