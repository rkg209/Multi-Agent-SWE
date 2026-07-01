# Tasks — Spec 06: Multi-Agent System

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Ensure `src/agents/` and `src/graph/` exist (Spec 04); create `tests/integration/test_multi_agent/` with `__init__.py`
- [ ] Add typed contracts `Plan`, `TestResult`, `Review` (in `src/graph/state.py` or a `contracts.py`)

## Nodes

- [ ] `src/agents/architect.py`: issue + snapshot → `Plan(files, approach, constraints)`; strong tier
- [ ] Extend `src/agents/developer.py`: consume Architect `Plan` + Tester/Reviewer feedback
- [ ] `src/agents/tester.py`: run suite via run-code tool → `TestResult(passed, failures)`; small tier
- [ ] `src/agents/reviewer.py`: evaluate patch → `Review(approved, issues)`; strong tier
- [ ] Every node passes `agent_role` to the router (tier assignment, FR-42); all I/O via tools (sandbox)

## Graph wiring

- [ ] `src/graph/graph.py`: default order Architect→Developer→Tester→Reviewer for `multi`
- [ ] Conditional edges: Tester FAIL → Developer; Reviewer issues → Developer
- [ ] Dev↔Test loop cap (default 3) + Dev↔Review loop cap (default 2); on cap set `cap_hit=true`, keep best patch
- [ ] Caps read from config, not hard-coded

## Checkpointing

- [ ] Configure a LangGraph checkpointer keyed by `run_id`
- [ ] Support resume from last completed node without re-running prior nodes

## Harness integration

- [ ] `benchmark/solver.py`: `MultiAgentSolver.solve(task)`; register `SOLVER=multi`

## Tests + E2E

- [ ] Unit: each node's I/O contract (mocked); routing (Tester FAIL→Dev, Reviewer issues→Dev)
- [ ] Unit: both caps set `cap_hit`; role→tier passed to router
- [ ] Integration: `SOLVER=multi` end-to-end on a fixture; checkpoint interrupt→resume — skip without provider + Docker
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Run `single` and `multi` on one subset; confirm comparable `run_records`
- [ ] Add `## Status` → `Complete.` to `spec.md`
