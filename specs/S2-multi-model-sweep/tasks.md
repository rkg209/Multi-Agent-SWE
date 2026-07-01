# Tasks — Spec S2 (Stretch): Multi-Model Sweep

> Stretch — only after Spec 09. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `tests/unit/test_sweep/` (+ integration dir) with `__init__.py`
- [ ] Choose 2–3 open models from the D.1 shortlist; document the choice

## Sweep runner

- [ ] `benchmark/sweep.py`: iterate a list of model configs; run the benchmark over the fixed subset per model
- [ ] Swap models via config overlay on `litellm_config.yaml` only (no per-model code)
- [ ] Respect the task cap (C-2) and the Spec 07 budget guard

## Record attribution

- [ ] Persist a run-level model label so records group per model for aggregation

## Aggregation + plot

- [ ] Cost-per-solved-task per model (reuse Spec 05 query, grouped by model)
- [ ] Add the per-model plot to the dashboard / export a figure

## Tests

- [ ] Unit: sweep iterates the model list and tags records per model (mocked)
- [ ] Integration: 2-model sweep on a tiny subset → per-model records + aggregation — skip without providers
- [ ] `make lint` exits 0; `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
