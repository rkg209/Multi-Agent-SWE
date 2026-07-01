# Tasks — Spec 09: Writeup, Demo & Reproducibility

Work through these in order. Check off each task only after `make lint && make test` pass.

## Reproducibility pins

- [ ] Confirm all deps pinned in `pyproject.toml` / `requirements.txt` (NFR-22)
- [ ] Pin the benchmark sandbox image to a digest/explicit tag (not `latest`) in the run path (NFR-23)

## CI

- [ ] `.github/workflows/ci.yml`: run `make lint && make test` on push to main, no Docker/Postgres (DR-6, FR-61)
- [ ] Separate manually-triggered workflow for Docker/Postgres integration tests
- [ ] Confirm CI is green on main

## Clean-clone reproduction

- [ ] Fresh clone → `make setup && make benchmark TASKS=lite-5`; capture headline numbers + environment
- [ ] Document stochastic tolerance (±pp at temperature > 0)

## README

- [ ] `README.md` opens with the headline single-vs-multi table (real numbers, generated from the Spec 08 query)
- [ ] Architecture diagram matching the data flow (FR-57)
- [ ] Document exact hardware/software environment (NFR-24) + reproduction instructions
- [ ] Link the demo video (placeholder until recorded)

## Writeup

- [ ] `WRITEUP.md`: opening sentence answers "does multi-agent coding pay for itself?"
- [ ] Report success-rate delta, cost multiple, and qualitative where-it-helped analysis (FR-59)

## Demo

- [ ] Record a short end-to-end task-resolution video (sandbox-only); link from README (FR-60)

## Final

- [ ] `make lint` exits 0
- [ ] `make test` exits 0
- [ ] Repo is public and reproducible from a clean clone

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
