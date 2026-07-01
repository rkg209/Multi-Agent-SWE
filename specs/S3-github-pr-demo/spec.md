# Spec S3 (Stretch): Real GitHub PR Demo

> **Stretch** — implement only if time remains after Spec 09 (constraints C-8, C-10, D.3). **Demo-only; never part of a scored run.**

## Goal

Show the best-multi solver opening a **real** pull request on a designated throwaway GitHub repository — for the demo video only, clearly labelled and strictly outside any scored benchmark run. This proves the system can produce a real, mergeable contribution end-to-end while keeping the hard rule intact: scored runs stay sandbox-only, and real PR creation never touches the measured results.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-S3 | Real GitHub PR mode (demo only, outside scored runs): best-multi opens a PR on a throwaway repo via the GitHub MCP server. |

## Non-Goals

- **Never** part of a scored/benchmark run (C-10) — a hard guard must prevent it.
- No change to the sandbox rule — generated code is still produced/executed in the sandbox; only the final patch is pushed as a PR in demo mode.
- Not run against arbitrary/production repos — a single designated throwaway repo only.
- No auto-merge — the demo opens the PR; a human reviews/merges.

## Done-When

- [ ] A clearly-labelled demo mode (e.g. `make demo-pr` / a `--demo-pr` flag) runs the best-multi solver on a task and opens a real PR on the designated throwaway repo via the GitHub MCP server.
- [ ] A hard guard makes it impossible to trigger PR creation from a scored `make benchmark` run (C-10) — enforced in code and covered by a test.
- [ ] The PR contains the solver's patch and a generated description; the run is not written to `run_records` as a scored result (or is written with an explicit `demo=true` marker, never counted in the headline).
- [ ] The demo video shows the real PR being opened end-to-end (feeds Spec 09 FR-60).
- [ ] `make lint` exits 0; `make test` exits 0.
- [ ] No agent-generated code runs on the host (sandbox rule intact) — code exec stays in the sandbox; only the git PR push crosses out, in demo mode only.

## Depends-On

- `specs/06-multi-agent-system` — the best-multi solver that produces the patch.
- `specs/09-writeup-reproducibility` — the demo video this feeds.
