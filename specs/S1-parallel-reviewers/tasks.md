# Tasks — Spec S1 (Stretch): Parallel Specialist Reviewers

> Stretch — only after Spec 09. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `src/agents/reviewers/` with `__init__.py`
- [ ] Create `tests/unit/test_reviewers/` (+ integration dir) with `__init__.py`

## Specialist nodes

- [ ] `security.py`, `performance.py`, `style.py` — specialist reviewer nodes (strong tier, focused prompts)
- [ ] Aggregator node: fan-in the three `Review`s → APPROVED or route-back

## Graph + harness

- [ ] Parallel fan-out after Tester PASS for the new config (keep sequential Reviewer for baseline `multi`)
- [ ] Route-back on any blocking issue, within the Dev↔Review cap
- [ ] Register the new `solver_config` in `benchmark/solver.py`

## Dashboard

- [ ] Add the parallel-review row to the comparison table/plot

## Tests

- [ ] Unit: specialist contracts (mocked); aggregator route-back / APPROVED logic
- [ ] Integration: end-to-end run recorded under its own `solver_config` — skip without provider + Docker
- [ ] `make lint` exits 0; `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
