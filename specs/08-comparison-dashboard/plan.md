# Implementation Plan — Spec 08: Comparison Run + Dashboard

## Overview

Confirm the `SOLVER=single|multi` selector produces comparable records, run the fixed subset through both, then build a thin Streamlit app that queries Postgres via a small read-only data-access module and renders the headline table + one plot. All aggregation reuses Spec 05's query/views; the dashboard only shapes and displays.

## Key Decisions

1. **Comparability by construction (FR-53).** Both runs use the same `TASKS` subset; `solver_config` distinguishes rows. No schema change — the harness already writes `solver_config` (Spec 03).
2. **Read-only data-access layer.** `dashboard/data.py` wraps the Spec 05 headline query/views into pandas frames. The Streamlit app imports only this module for data — keeps SQL out of the UI and unit-testable.
3. **Reuse metric definitions (single source of truth).** No metric is recomputed in the dashboard; it renders exactly what `run_summary` / the headline query return, so numbers match `/trace` and the README.
4. **Single-command launch (FR-55).** `make dashboard` → `streamlit run dashboard/app.py`. No export step; the app connects to `DATABASE_URL`.
5. **Minimal, legible visuals (C-9).** One table + one plot (success rate vs. cost per solved task). No filters/interactivity beyond selecting the task subset. Performance target < 10 s (NFR-15) is trivial at this data size but validated.
6. **Graceful empty state.** If no runs exist yet, the dashboard shows a clear "run `make benchmark` first" message rather than erroring.

## Implementation Order

1. **Verify `SOLVER=single|multi` selector** end-to-end (mostly wired in Specs 04/06); ensure comparable rows.
2. **Run the comparison** — `make benchmark TASKS=<subset> SOLVER=single` then `SOLVER=multi` to populate real data.
3. **`dashboard/data.py`** — read-only query functions returning DataFrames from the headline query/views.
4. **`dashboard/app.py`** — Streamlit layout: title, headline table, one plot; empty-state handling.
5. **`make dashboard`** — confirm the target (stubbed in Spec 00) launches the app.
6. **Tests** — unit-test `data.py` shaping against a fixture; manually verify the live dashboard renders < 10 s.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Dashboard numbers diverge from `/trace`/README | Single source: only render Spec 05 query/view output; no recompute. |
| Empty DB → dashboard crash | Explicit empty-state message and guarded queries. |
| Streamlit hard to unit-test | Put all logic in `data.py` (testable); keep `app.py` thin/presentational. |
| Comparison not truly comparable | Same `TASKS` subset for both; assert identical task sets per config in a check. |
| Slow render on cold Postgres | Rely on Spec 05 indexes (NFR-10); validate < 10 s (NFR-15). |

## Testing Strategy

- Unit tests: `tests/unit/test_dashboard/` — `data.py` returns the expected columns/shape for a fixture result set; empty-DB path returns an empty frame (no crash).
- Integration tests: `tests/integration/test_dashboard/` — against a populated test DB, the headline query returns both `single` and `multi` rows. Skip without Postgres.
- Manual check: `make benchmark` for both solvers, `make dashboard`, confirm the table (single vs multi) + plot render in < 10 s.
