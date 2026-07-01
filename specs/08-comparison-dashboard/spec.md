# Spec 08: Comparison Run + Dashboard

## Goal

Produce and present the project's headline output: run the fixed task subset through **single** and **best-multi** solver configurations and render the comparison. This spec makes `make benchmark` accept a `SOLVER=single|multi` selector so that running both in sequence yields directly comparable Postgres records, then builds a Streamlit dashboard that reads straight from Postgres (no manual export) and renders the headline comparison table (success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations — single vs. multi) plus at least one plot (e.g. success rate vs. cost per solved task). This is the artifact interviewers actually look at.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-53 | `make benchmark` accepts `SOLVER=single|multi`; running both in sequence produces directly comparable Postgres records. |
| FR-54 | Streamlit dashboard reads from Postgres and renders the headline comparison table (single vs multi) + ≥1 plot. |
| FR-55 | Dashboard launchable with a single command (`make dashboard`), no manual data-export step. |
| NFR-15 | Dashboard loads and renders the full table + plots in < 10 s on the Postgres host. |

## Non-Goals

- No new solver logic — `single` (Spec 04) and `multi` (Spec 06) already exist; this spec runs and compares them.
- No interactive coding/agent UX (C-9) — the dashboard is results-display only.
- No stretch reviewer/model-sweep axes — S1/S2 add extra dashboard rows later.
- No hosted deployment (C-4) — the dashboard runs locally / on-demand.
- No new metric definitions — reuse Spec 05's headline query/views.

## Done-When

All of the following are true and verifiable:

- [ ] `make benchmark TASKS=<subset> SOLVER=single` and `SOLVER=multi` both run the subset and write comparable `run_records` (same tasks, distinguishable by `solver_config`).
- [ ] `dashboard/app.py` reads directly from Postgres (via the Spec 05 headline query/views) with no manual export.
- [ ] The dashboard renders the headline comparison table: success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations — one row per solver config (single vs multi).
- [ ] The dashboard renders at least one plot (e.g. success rate vs. cost per solved task).
- [ ] `make dashboard` launches Streamlit on :8501 in a single command (FR-55).
- [ ] The full table + plots render in < 10 s on the Postgres host (NFR-15).
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (unit tests cover the data-access + table-shaping functions against a fixture/mock; the live dashboard is verified manually).
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/06-multi-agent-system` — the `multi` solver to compare.
- `specs/07-guardrails-cost-control` — caps/cache so the comparison run is bounded and cheap.
- `specs/05-instrumentation-metrics` — headline query/views the dashboard reads.
