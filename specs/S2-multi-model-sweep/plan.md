# Implementation Plan — Spec S2 (Stretch): Multi-Model Sweep

## Overview

Add a thin sweep driver that takes a list of model configs, and for each one runs the existing benchmark over the fixed subset, tagging records with the model. Aggregate cost-per-solved-task per model and plot. Almost all leverage comes from Spec 01's config-driven router.

## Key Decisions

1. **Config-only model swaps (FR-S2).** The sweep sets the tier→model mapping per iteration (e.g. overlays on `litellm_config.yaml`); no per-model code.
2. **Attribute records per model.** `trace_events.model` already captures the model; add a run-level `model_label` (in `solver_config` JSON or a dedicated column) so aggregation groups cleanly.
3. **Identical subset for comparability.** Same `TASKS` for every model; sweep respects the cap (C-2) and the Spec 07 budget guard.
4. **Reuse metrics + dashboard.** Cost-per-solved-task = mean cost over solved tasks (Spec 05 definition), grouped by model; plot in the Spec 08 dashboard or exported as a figure.
5. **Small model list.** 2–3 models from the D.1 shortlist; document choices.

## Implementation Order

1. `benchmark/sweep.py` — iterate model configs; run the benchmark per model with the subset; tag records.
2. Record tagging — ensure per-run model label is persisted for grouping.
3. Aggregation — cost-per-solved-task per model (reuse Spec 05 query, grouped by model).
4. Plot — add per-model cost-per-solved-task to the dashboard / export.
5. Tests + a real 2–3 model sweep on a small subset.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Provider availability / rate limits mid-sweep | Prefer local Ollama + one hosted; resumable per-model; budget guard caps spend. |
| Records not attributable to model | Persist a run-level model label; test grouping. |
| Cost blowup across models | Small subset + budget guard (Spec 07); use cache where identical calls recur. |

## Testing Strategy

- Unit: sweep iterates the configured model list and tags records per model (mocked run).
- Integration: 2-model sweep on a tiny subset produces per-model records + aggregation. Skip without providers.
- Manual: view the per-model cost-per-solved-task plot.
