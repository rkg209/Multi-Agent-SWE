# Spec S2 (Stretch): Multi-Model Cost-Per-Success Sweep

> **Stretch** — implement only if time remains after Spec 09 (constraint C-8, D.3). "A second result axis with near-zero new code."

## Goal

Add a sweep mode that re-runs the fixed task subset across 2–3 distinct open models (swapping the model per tier via config only, no code change) and produces a cost-per-solved-task comparison plot per model. This turns the router's config-driven design (Spec 01) into a second measurement axis: which open model gives the best success-per-dollar on this task set?

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-S2 | Multi-model sweep mode: re-run the fixed subset across 2–3 open models; produce a cost-per-solved-task plot per model. |

## Non-Goals

- No new agent logic — models change via `config/litellm_config.yaml` only.
- No new metric definitions — reuse Spec 05; add a `model` dimension to the records/labels.
- Not part of the core single-vs-multi headline — a supplementary axis.

## Done-When

- [ ] A sweep runner iterates a configured list of models, running the chosen solver over the fixed subset once per model, purely via config swaps (no code change per model).
- [ ] Each run's model is recorded so records are attributable per model (existing `trace_events.model` + a run-level label).
- [ ] A cost-per-solved-task plot per model is produced (dashboard and/or exported figure).
- [ ] The task subset is identical across models (comparability); the sweep respects the task cap + budget guard.
- [ ] `make lint` exits 0; `make test` exits 0.
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/01-model-router` — config-driven model/tier swapping.
- `specs/05-instrumentation-metrics` — per-model cost/success data.
- `specs/08-comparison-dashboard` — where the per-model plot is rendered.
