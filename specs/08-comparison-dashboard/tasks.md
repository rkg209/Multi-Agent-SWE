# Tasks — Spec 08: Comparison Run + Dashboard

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Confirm `streamlit` + `pandas` pinned (Spec 00); add anything missing to `pyproject.toml`/`requirements.txt`
- [ ] Create `tests/unit/test_dashboard/` and `tests/integration/test_dashboard/` with `__init__.py`

## Comparison run

- [ ] Verify `make benchmark` `SOLVER=single|multi` selector produces comparable `run_records` (same subset, distinct `solver_config`)
- [ ] Run `make benchmark TASKS=<subset> SOLVER=single` then `SOLVER=multi` to populate real data

## Data-access layer

- [ ] `dashboard/data.py`: read-only functions returning DataFrames from the Spec 05 headline query/views
- [ ] Headline table function: one row per solver config (success rate, mean cost/solved, p50/p99 latency, hallucination rate, mean iterations)
- [ ] Empty-DB path returns an empty frame (no crash)

## Dashboard

- [ ] `dashboard/app.py`: title, headline comparison table, ≥1 plot (success rate vs cost per solved task)
- [ ] Empty-state message when no runs exist
- [ ] Confirm `make dashboard` launches Streamlit on :8501 (single command, no export)

## Tests

- [ ] Unit: `data.py` returns expected columns/shape for a fixture result set; empty-DB path safe
- [ ] Integration: populated test DB → headline query returns both `single` and `multi` rows — skip without Postgres
- [ ] Manual: dashboard renders table + plot in < 10 s (NFR-15)
- [ ] `make lint` exits 0
- [ ] `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
