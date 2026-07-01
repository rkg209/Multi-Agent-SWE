# Tasks — Spec 03: Benchmark Harness

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `benchmark/` package with `__init__.py`; create `benchmark/tasks/custom/`
- [ ] Add `swebench` / `sb-cli` to `requirements.txt` (sandbox) and dev deps as needed
- [ ] Create `tests/unit/test_harness/` and `tests/integration/test_harness/` with `__init__.py`

## Task config + fixtures

- [ ] `config/tasks/lite-5.txt` and `config/tasks/lite-30.txt` — version-locked SWE-bench task IDs
- [ ] 1–2 custom tickets under `benchmark/tasks/custom/<id>/` with issue text + hidden test files

## Loader

- [ ] `benchmark/loader.py`: `Task` dataclass + `load_tasks(subset_id, override=False)`
- [ ] Normalise SWE-bench + custom into one `Task` shape
- [ ] Enforce cap (50 SWE-bench + 5 custom); refuse over-cap without `--override` (C-2)

## Solver interface

- [ ] `benchmark/solver.py`: `Solver` protocol (`solve(task) -> Patch`) + `NoopSolver` (empty patch)

## Scorer

- [ ] `benchmark/scorer.py`: dispatch by `task.source`
- [ ] Custom scorer: apply patch in Spec 02 sandbox → run hidden tests → deterministic PASS/FAIL
- [ ] SWE-bench scorer: wrap `sb-cli` / official harness; parse PASS/FAIL report (no reimplementation)

## Results writer

- [ ] `benchmark/results.py`: `write_run_record(...)` inserts an immutable `run_records` row with a fresh UUID `run_id`
- [ ] Never `UPDATE`/overwrite — re-runs INSERT new rows (NFR-6)

## CLI + Makefile

- [ ] `benchmark/cli.py`: parse `TASKS` + `SOLVER`, run loop, print summary table
- [ ] Wire `make benchmark` to `benchmark/cli.py` (replace the Spec 00 stub)

## Tests

- [ ] Unit: loader normalisation + cap enforcement
- [ ] Unit: no-op solver, results-writer row shape, scorer dispatch (mocked)
- [ ] Unit: custom scorer determinism given fixed inputs
- [ ] Integration: `make benchmark TASKS=lite-5 SOLVER=noop` writes 5 FAIL rows — skip without Docker/`sb-cli`
- [ ] Integration: custom scorer on a real fixture in the sandbox
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
