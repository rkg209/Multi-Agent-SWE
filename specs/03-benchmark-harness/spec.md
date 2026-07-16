# Spec 03: Benchmark Harness

## Goal

Build the reproducible measurement loop that turns "a solver" into "a scored result." This spec implements the task loader (a fixed, version-locked subset of SWE-bench Lite/Verified plus 3–5 hand-authored custom tickets), the deterministic scorer (apply patch in the sandbox → run hidden tests → PASS/FAIL), and the results-writing path that records one immutable `run_records` row per task execution. SWE-bench environment setup and hidden-test scoring reuse the official harness + `sb-cli` (never reimplemented); the custom scorer covers the in-repo tickets. `make benchmark TASKS=lite-5` must load tasks, run a **no-op solver** (empty patch), and record FAIL rows — proving the harness end-to-end before any real solver exists.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-20 | Task loader from two sources: version-locked SWE-bench subset (30–50 IDs) + 3–5 custom tickets in-repo. |
| FR-21 | Reuse official SWE-bench harness + `sb-cli` for env setup and hidden-test scoring; do not reimplement provisioning. |
| FR-22 | Custom scorer for custom tickets: apply patch in sandbox, run hidden tests, deterministic PASS/FAIL. |
| FR-23 | `make benchmark TASKS=<subset-id>` loads the subset, invokes the configured solver, records results, prints a summary table. |
| FR-24 | Write one `run_records` row per task execution (task_id, solver config, outcome, tokens, cost, latency, hallucination flag, iteration count). |
| FR-25 | No-op solver mode (empty patch) — `make benchmark TASKS=lite-5` completes and writes FAIL rows. |
| NFR-5 | Scorer is deterministic — same patch + same hidden tests → same PASS/FAIL. |
| NFR-6 | Run records immutable; re-runs create new rows, never overwrite (preserve history). |
| NFR-7 | Fixed SWE-bench subset (task IDs) committed in a versioned config; unchanged between runs unless the config changes. |
| C-2 | Task set capped at 50 SWE-bench + 5 custom; harness refuses to exceed without an explicit override flag. |

## Non-Goals

- No real solver — the only solver here is the no-op (empty patch). Single-agent is Spec 04.
- No full trace-event instrumentation or metric aggregation (p50/p99, hallucination compute) — that is Spec 05. This spec writes the `run_records` row with the fields available (hallucination/iteration may be null/0 for the no-op).
- No dashboard — Spec 08.
- No multi-model sweep — stretch S2.
- No new sandbox mechanics — reuse Spec 02's run-code/sandbox for patch application and test runs.

## Done-When

All of the following are true and verifiable:

- [x] `benchmark/cli.py` parses `TASKS` and `SOLVER` args and drives the harness loop; `make benchmark` wires to it (replacing the Spec 00 stub).
- [x] A version-locked config (e.g. `config/tasks/lite-5.txt`, `lite-30.txt`) lists SWE-bench task IDs; custom tickets live under `benchmark/tasks/custom/` with issue text + hidden tests.
- [x] The task loader returns a uniform `Task` object for both SWE-bench and custom tickets.
- [x] SWE-bench scoring goes through `sb-cli` / the official harness; custom tickets go through the in-repo deterministic scorer (patch → sandbox → hidden tests → PASS/FAIL).
- [x] `make benchmark TASKS=lite-5 SOLVER=noop` completes without error and writes immutable FAIL rows to `run_records` (7: the 5 `lite-5.txt` SWE-bench IDs + the 2 always-included custom tickets — see progress_report.md for why the row count is 7, not 5), then prints a summary table to stdout.
- [x] Re-running the same command writes **new** rows (different `run_id`), never overwriting (NFR-6).
- [x] Requesting more than the cap (50+5) without `--override` is refused with a clear error (C-2).
- [x] The custom scorer returns identical PASS/FAIL on repeated runs of the same patch (NFR-5).
- [x] `make lint` exits 0.
- [x] `make test` exits 0 (unit tests mock `sb-cli`/sandbox; integration tests that need Docker/`sb-cli` skip cleanly).
- [x] No agent-generated code runs on the host (sandbox rule intact).

## Status

Complete.

## Depends-On

- `specs/00-foundation` — Postgres (`run_records`), Makefile, Docker sandbox image.
- `specs/02-tool-layer` — run-code/sandbox for patch application and test execution.
