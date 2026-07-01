# Implementation Plan — Spec S1 (Stretch): Parallel Specialist Reviewers

## Overview

Replace the single Reviewer stage (for this config only) with a fan-out of three specialist reviewers running concurrently, then a fan-in aggregator that decides APPROVED vs. route-back. Selected via a new `solver_config` so it is measured as a separate axis, not mixed into the multi baseline.

## Key Decisions

1. **Fan-out/fan-in via LangGraph parallel edges.** Security/Performance/Style are independent nodes reading the same passing patch; an aggregator node collects their `Review` outputs.
2. **Specialists on the strong tier.** Review is quality-critical (matches Reviewer tier from FR-42); each gets a focused prompt (security / performance / style).
3. **Separate `solver_config` label (FR-S1).** e.g. `multi+parallel-review`, so the harness records it distinctly and the dashboard shows it as its own row.
4. **Aggregation policy is explicit.** Any specialist raising a blocking issue → route back to Developer (within the Dev↔Review cap); all-clear → APPROVED.
5. **Reuse everything else.** No changes to Architect/Developer/Tester, tools, router, metrics.

## Implementation Order

1. `src/agents/reviewers/` — `security.py`, `performance.py`, `style.py` specialist nodes.
2. Aggregator node — fan-in of the three `Review`s → decision.
3. Graph wiring — parallel fan-out after Tester PASS for the new config; keep sequential Reviewer for the baseline `multi`.
4. `benchmark/solver.py` — register the new `solver_config`.
5. Dashboard — add the parallel-review row (data layer already generic).
6. Tests + a comparison run.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Concurrency bugs / nondeterministic fan-in | Deterministic aggregation over collected outputs; test with mocked reviewers. |
| Cost jumps (3 strong-tier calls) | Budget guard (Spec 07) applies; report the cost multiple honestly. |
| Config leakage into baseline `multi` | Distinct `solver_config`; assert separation in a test. |

## Testing Strategy

- Unit: each specialist's contract (mocked); aggregator route-back on any blocking issue; APPROVED when all clear.
- Integration: parallel-review config runs end-to-end and records under its own `solver_config`. Skip without provider + Docker.
- Manual: dashboard shows single vs multi vs multi+parallel-review.
