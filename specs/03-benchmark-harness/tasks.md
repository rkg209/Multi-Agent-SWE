# Tasks — Spec 03: Benchmark Harness

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [x] Create `benchmark/` package with `__init__.py`; create `benchmark/tasks/custom/`
- [x] Add `sb-cli` to `pyproject.toml` dependencies (host-only CLI; not needed in the sandbox image,
      so not added to `requirements.txt` — see progress_report.md Sequence for the reasoning)
- [x] Create `tests/unit/test_harness/` and `tests/integration/test_harness/` with `__init__.py`

## Task config + fixtures

- [x] `config/tasks/lite-5.txt` and `config/tasks/lite-30.txt` — version-locked SWE-bench task IDs
- [x] 2 custom tickets under `benchmark/tasks/custom/<id>/` with issue text + hidden test files

## Loader

- [x] `benchmark/loader.py`: `Task` dataclass + `load_tasks(subset_id, override=False)`
- [x] Normalise SWE-bench + custom into one `Task` shape
- [x] Enforce cap (50 SWE-bench + 5 custom); refuse over-cap without `--override` (C-2)

## Solver interface

- [x] `benchmark/solver.py`: `Solver` protocol (`solve(task) -> Patch`) + `NoopSolver` (empty patch)

## Scorer

- [x] `benchmark/scorer.py`: dispatch by `task.source`
- [x] Custom scorer: apply patch in Spec 02 sandbox → run hidden tests → deterministic PASS/FAIL
- [x] SWE-bench scorer: wrap `sb-cli` / official harness; parse PASS/FAIL report (no reimplementation)

## Results writer

- [x] `benchmark/results.py`: `write_run_record(...)` inserts an immutable `run_records` row with a fresh UUID `run_id`
- [x] Never `UPDATE`/overwrite — re-runs INSERT new rows (NFR-6)

## CLI + Makefile

- [x] `benchmark/cli.py`: parse `TASKS` + `SOLVER`, run loop, print summary table
- [x] Wire `make benchmark` to `benchmark/cli.py` (replace the Spec 00 stub)

## Tests

- [x] Unit: loader normalisation + cap enforcement
- [x] Unit: no-op solver, results-writer row shape, scorer dispatch (mocked)
- [x] Unit: custom scorer determinism given fixed inputs
- [x] Integration: `make benchmark TASKS=lite-5 SOLVER=noop` writes 5 FAIL rows — skip without Docker/`sb-cli`
- [x] Integration: custom scorer on a real fixture in the sandbox
- [x] `make lint` exits 0
- [x] `make test` exits 0

## Acceptance

- [x] Verify each done-when criterion in `spec.md`
- [x] Add `## Status` → `Complete.` to `spec.md`
