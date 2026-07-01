# Implementation Plan — Spec 03: Benchmark Harness

## Overview

Assemble the harness as: **loader → solver (pluggable) → scorer → results writer**, driven by `benchmark/cli.py`. The loader normalises SWE-bench IDs and custom tickets into one `Task` shape. The solver is an interface with a single `noop` implementation in this spec (real solvers plug in later at the same seam). The scorer dispatches by task source: SWE-bench → `sb-cli`/official harness; custom → in-repo deterministic scorer that applies the patch in the sandbox and runs hidden tests. Each execution writes one immutable `run_records` row.

## Key Decisions

1. **Uniform `Task` abstraction.** `Task(id, source, repo_snapshot, issue_text, hidden_tests, base_commit)` covers both sources so the solver/scorer are source-agnostic.
2. **Solver as a pluggable interface (`Solver.solve(task) -> Patch`).** The no-op solver returns an empty patch. Specs 04/06 add `single` and `multi` at the same interface — the harness never branches on solver internals (supports FR-28's shared-instrumentation goal).
3. **Reuse SWE-bench, don't reimplement (FR-21, C-6).** SWE-bench scoring shells out to `sb-cli` inside/through the sandbox; we only parse its PASS/FAIL report. Custom tickets use our own scorer.
4. **Deterministic custom scorer (NFR-5).** `apply patch → run pinned hidden tests in sandbox → PASS iff all target tests pass`. No timestamps/network/randomness in the decision path; fixed image digest.
5. **Immutable results (NFR-6).** Every run gets a fresh `run_id` (UUID); writer only `INSERT`s into `run_records`. Re-runs accumulate.
6. **Version-locked subsets (NFR-7, C-2).** Subset IDs live in committed `config/tasks/*.txt`. The loader refuses > (50 SWE-bench + 5 custom) unless `--override` is passed.
7. **`run_records` filled with what exists now.** No-op runs write outcome=FAIL, real cost/latency (≈0), hallucination/iteration null-or-0; Spec 05 enriches the trace side.

## Implementation Order

1. **`config/tasks/lite-5.txt` (+ `lite-30.txt`)** and `benchmark/tasks/custom/` fixtures (issue + hidden tests for 1–2 tickets to start).
2. **`benchmark/loader.py`** — resolve a subset id → list of `Task`; enforce the cap + `--override`.
3. **`benchmark/solver.py`** — `Solver` protocol + `NoopSolver`.
4. **`benchmark/scorer.py`** — dispatch by source; custom scorer via Spec 02 sandbox; SWE-bench via `sb-cli` wrapper.
5. **`benchmark/results.py`** — `write_run_record(...)` inserting an immutable `run_records` row; UUID `run_id` per execution.
6. **`benchmark/cli.py`** — parse `TASKS`/`SOLVER`, run the loop, print the summary table; wire `make benchmark` to it.
7. **Tests** — unit (mock `sb-cli` + sandbox), integration (skip without Docker/`sb-cli`).

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| SWE-bench env setup eats time (top project risk) | Get the **custom-ticket** path green first; wire `sb-cli` after; isolate failures with the `harness-debugger` sub-agent. |
| `sb-cli` output format changes | Parse defensively; pin a known-good `sb-cli`/swebench version; snapshot a sample report in tests. |
| Non-determinism leaks into scorer | Pinned image digest, no network in scoring, fixed test selection; assert repeat-run stability in a test. |
| Accidental full-suite run / cost blowup | Hard cap + explicit `--override` (C-2); no-op solver for harness validation. |
| Patch apply fails silently | Treat apply failure as FAIL with a recorded reason, not a crash. |

## Testing Strategy

- Unit tests: `tests/unit/test_harness/` — loader normalisation + cap enforcement, no-op solver returns empty patch, results writer builds a valid immutable row, scorer dispatch by source (mocked sandbox/`sb-cli`), determinism of the custom scorer decision given fixed inputs.
- Integration tests: `tests/integration/test_harness/` — `make benchmark TASKS=lite-5 SOLVER=noop` writes 5 FAIL rows; custom-ticket scorer on a real fixture in the sandbox. Skip without Docker/`sb-cli`.
- Manual check: run the no-op benchmark twice; `make db-shell` → confirm 10 rows with 2 distinct `run_id`s (immutability).
