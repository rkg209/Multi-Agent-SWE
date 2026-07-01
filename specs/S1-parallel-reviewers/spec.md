# Spec S1 (Stretch): Parallel Specialist Reviewers

> **Stretch** — implement only if time remains after Spec 09 (constraint C-8, D.3). Depends on the full comparison being in place.

## Goal

Test the hypothesis that multi-agent coordination pays off specifically in **parallel review**. After the Tester passes, run three independent specialist reviewers — **Security**, **Performance**, **Style** — concurrently (rather than one sequential Reviewer), aggregate their findings, and route back to the Developer on blocking issues. The benchmark records this configuration **separately** so its success/cost can be isolated from the sequential-Reviewer multi-agent baseline, answering "is *parallel review* where coordination wins?"

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-S1 | Parallel Security/Performance/Style reviewers run concurrently after Tester passes; benchmark records this config separately to isolate parallel-review gains. |

## Non-Goals

- No change to Architect/Developer/Tester nodes — this only replaces the single Reviewer stage.
- No new metric definitions — reuse Spec 05; add a new `solver_config` label only.
- Not part of the core comparison — reported as an additional axis.

## Done-When

- [ ] Three reviewer nodes (Security, Performance, Style) run concurrently in the graph after Tester PASS, using LangGraph parallel/fan-out.
- [ ] Their findings are aggregated; blocking issues route back to the Developer (respecting the Dev↔Review cap).
- [ ] The configuration runs under a distinct `solver_config` label so its records are comparable-but-separate from sequential multi.
- [ ] The dashboard/headline query shows the parallel-reviewer row alongside single and multi.
- [ ] `make lint` exits 0; `make test` exits 0.
- [ ] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/06-multi-agent-system` — graph, Reviewer stage, capped loops, tiers.
- `specs/08-comparison-dashboard` — comparison + dashboard to add the new row to.
