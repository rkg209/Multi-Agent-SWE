# Implementation Plan — Spec 09: Writeup, Demo & Reproducibility

## Overview

Wrap the finished system for a public audience: write the README (headline table first), add CI, pin everything for reproducibility, do a clean-clone reproduction pass, write the short answer-first writeup, and record the demo video. No system code changes beyond pinning and any small fixes surfaced by the clean-clone run.

## Key Decisions

1. **README leads with the number (FR-56, BG-4).** First visible section = the single-vs-multi headline table with real numbers, generated from an actual run (ideally exported from the Spec 08 query so it can't drift).
2. **CI without infra (DR-6, FR-61).** `ci.yml` runs `make lint && make test`; unit tests already stub Docker/Postgres, so CI needs neither. A second, manually-triggered workflow runs the Docker/Postgres integration tests.
3. **Pin for reproducibility (NFR-22/23).** Confirm deps are pinned; change the benchmark run path to reference the sandbox image by digest/explicit tag, not `latest`.
4. **Clean-clone reproduction is the real test (FR-58).** Fresh clone → `make setup && make benchmark TASKS=lite-5`; record results; document the tolerance (temperature > 0 non-determinism, ±pp).
5. **Answer-first writeup (FR-59, D.4).** Opening sentence states the measured answer; body reports success-rate delta, cost multiple, and where coordination helped vs. burned tokens — honest either way.
6. **Environment documented (NFR-24).** Capture OS, Python, Docker versions, model/provider used, and wall-clock for the subset.

## Implementation Order

1. **Pin the benchmark image tag** (digest/explicit) in the run path; confirm dep pins (NFR-22/23).
2. **`.github/workflows/ci.yml`** — lint + test on push to main (no Docker/Postgres); separate manual integration workflow.
3. **Clean-clone reproduction run** — fresh checkout → `make setup && make benchmark TASKS=lite-5`; capture numbers + environment.
4. **`README.md`** — headline table first, architecture diagram, environment + reproduction instructions, demo link placeholder.
5. **`WRITEUP.md`** — answer-first short writeup (delta, cost multiple, qualitative analysis).
6. **Demo video** — record an end-to-end task resolution; link from README.
7. **Final pass** — `make lint && make test`; verify CI is green on main.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Headline numbers drift between README and DB | Generate the table from the Spec 08 query; note the source run + date. |
| Clean-clone run fails on a fresh machine | This is the point — fix setup gaps found; keep instructions to the README only (NFR-25 < 15 min). |
| CI needs Docker/Postgres and fails | Ensure unit tests stub infra; integration tests behind a manual workflow (DR-6). |
| Non-determinism makes reproduction look "wrong" | Document tolerance explicitly (±pp at temperature > 0). |
| Demo video scope creep | Keep it short: one task, end-to-end, sandbox-only. |

## Testing Strategy

- Unit/CI: `make lint && make test` green in `ci.yml` on push to main, no infra required.
- Reproduction: clean-clone `make setup && make benchmark TASKS=lite-5` reproduces the headline within documented tolerance.
- Manual check: open the README — headline table + diagram render; follow the reproduction steps end-to-end; the writeup's first sentence states the measured answer; demo link resolves.
