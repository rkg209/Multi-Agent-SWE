# Spec 09: Writeup, Demo & Reproducibility

## Goal

Ship the project as a credible, reproducible portfolio artifact. This spec produces the public-facing deliverables: a `README.md` whose first visible section is the headline single-vs-multi metric table with real numbers, an architecture diagram matching the data flow, a CI workflow that runs `make lint && make test` on every push, verified reproducibility of the headline results from a clean clone (within documented stochastic tolerance), a short writeup whose opening sentence answers "does multi-agent coding pay for itself?", and a demo video showing the system resolving a task end-to-end. When this spec is done, the repo is public, reproducible, and leads with the measured number — the résumé bullet.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-56 | Public GitHub repo; `README.md`'s first visible section is the headline single-vs-multi metric table with real numbers. |
| FR-57 | README includes an architecture diagram (image or ASCII) matching the data flow. |
| FR-58 | `make benchmark` on a clean clone reproduces the headline results within documented stochastic tolerance. |
| FR-59 | Short writeup whose opening sentence states the measured answer; reports success-rate delta, cost multiple, and qualitative where-it-helped analysis. |
| FR-60 | Demo video of an end-to-end task resolution, linked from the README. |
| FR-61 | GitHub Actions CI runs `make lint && make test` on every push to main and reports status. |
| NFR-22 | Dependencies pinned; `make setup` installs exactly those versions. |
| NFR-23 | Sandbox image built from committed Dockerfile; benchmark image tag pinned to a digest/explicit version, not `latest`. |
| NFR-24 | README documents the exact hardware/software environment the headline results were produced on. |
| DR-6 | CI runs `make lint && make test` without Docker/Postgres (unit tests stub infra); Docker integration tests in a separate manual workflow. |

## Non-Goals

- No new system capability — this spec is documentation, packaging, CI, and reproducibility only.
- No stretch features (parallel reviewers, model sweep, real PR demo) — S1–S3.
- No hosted deployment (C-4) — reproducibility is from a clean clone, run locally/on-demand.
- No change to metric definitions — the README table renders Spec 05/08 numbers verbatim.

## Done-When

All of the following are true and verifiable:

- [ ] `README.md` opens with the headline single-vs-multi metric table populated with **real** numbers from an actual benchmark run.
- [ ] `README.md` includes an architecture diagram matching the data flow, and documents the exact hardware/software environment the results were produced on (NFR-24).
- [ ] `.github/workflows/ci.yml` runs `make lint && make test` on every push to main **without** requiring Docker/Postgres (unit tests stub infra); a separate manually-triggered workflow runs the Docker integration tests (DR-6, FR-61).
- [ ] Dependencies are pinned and the benchmark sandbox image tag is pinned to a digest/explicit version (not `latest`) in the code path that runs it (NFR-22, NFR-23).
- [ ] A clean clone → `make setup && make benchmark TASKS=lite-5` reproduces the headline results within the tolerance documented in the README (FR-58).
- [ ] A short writeup (`WRITEUP.md` or linked post) opens with the measured answer to "does multi-agent coding pay for itself?" and reports the success-rate delta, cost multiple, and a qualitative analysis of where multi-agent helped and where it did not (FR-59).
- [ ] A demo video shows an end-to-end task resolution and is linked from the README (FR-60).
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0.
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/08-comparison-dashboard` — the real single-vs-multi numbers the README/writeup report.
