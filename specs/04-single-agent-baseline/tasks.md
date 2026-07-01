# Tasks — Spec 04: Single-Agent Baseline

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `src/graph/` and `src/agents/` packages with `__init__.py`
- [ ] Confirm `langgraph` is pinned (Spec 00); add anything missing to `pyproject.toml`/`requirements.txt`
- [ ] Create `tests/unit/test_graph/`, `tests/unit/test_agents/`, `tests/integration/test_single_agent/` with `__init__.py`

## Graph state

- [ ] `src/graph/state.py`: `GraphState` TypedDict (task, plan, patch, test_result, iteration, solver_config, run_id)

## Developer node

- [ ] `src/agents/developer.py`: node fn — read repo (filesystem tool) → plan (router, `role=developer`) → write changes (tools) → run tests (run-code tool) → update state
- [ ] Self-loop decision with a hard iteration cap (default 3)
- [ ] All LLM calls via Spec 01 router; all I/O via Spec 02 tools; no host exec

## Graph

- [ ] `src/graph/graph.py`: build LangGraph graph; include nodes by `solver_config`
- [ ] Single mode: only Developer active (+ self-loop edge); Architect/Tester/Reviewer disabled

## Harness integration

- [ ] `benchmark/solver.py`: add `SingleAgentSolver.solve(task)`; register `SOLVER=single`
- [ ] Build initial `GraphState` from `Task`; return final patch to the scorer

## End-to-end

- [ ] Get ≥1 real PASS on an easy custom ticket (real cost + latency in `run_records`)
- [ ] Attempt one SWE-bench lite task end-to-end

## Tests

- [ ] Unit: state transitions; Developer calls router with `role=developer`; writes/execs only via tools (mocked); self-loop cap respected
- [ ] Integration: `SOLVER=single` end-to-end on a fixture — skip without provider + Docker
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md` (esp. FR-27 real PASS)
- [ ] Add `## Status` → `Complete.` to `spec.md`
