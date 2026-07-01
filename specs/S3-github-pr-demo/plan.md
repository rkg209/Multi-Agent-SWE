# Implementation Plan — Spec S3 (Stretch): Real GitHub PR Demo

## Overview

Add a separate, clearly-labelled demo entrypoint that runs the best-multi solver and, instead of just scoring, pushes the resulting patch as a real PR to a designated throwaway repo via the GitHub MCP server. A hard guard keeps this path unreachable from any scored run.

## Key Decisions

1. **Separate entrypoint, never the scored path (C-10).** `make demo-pr` / a `--demo-pr` flag is the only way to open a PR. The scored `make benchmark` path has no branch that can create a PR — enforced by a guard and a test.
2. **Sandbox rule preserved.** The solver still generates and runs code in the sandbox; demo mode only takes the final patch and opens a PR (git push), it does not run untrusted code on the host.
3. **Designated throwaway repo only.** Target repo is fixed via config; refuse any other target. No auto-merge — human reviews.
4. **GitHub MCP for the PR.** Reuse the GitHub MCP server; branch → commit patch → open PR with a generated description.
5. **Demo runs excluded from headline.** Either not written to `run_records` or marked `demo=true` and always filtered out of the headline query.

## Implementation Order

1. `benchmark/demo_pr.py` — demo runner: best-multi solve → take patch → GitHub MCP branch/commit/PR on the configured throwaway repo.
2. Hard guard — assert PR creation is impossible from a scored run; add a test that proves it.
3. Config — designated throwaway repo + credentials via env (`.gitignore`d).
4. `make demo-pr` target.
5. Record the demo video (feeds Spec 09).

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| PR creation leaks into a scored run (C-10) | Single guarded entrypoint; test asserts scored path can't reach it. |
| Pushing to the wrong repo | Fixed throwaway repo in config; refuse other targets. |
| Credentials in code | Env/`.env` only (NFR-3); never committed. |
| Confusing demo results with measured results | Exclude from headline (`demo=true` / not recorded). |

## Testing Strategy

- Unit: scored `make benchmark` path cannot reach PR creation (guard test); demo runner builds a PR request against only the configured repo (mocked GitHub MCP).
- Integration/manual: `make demo-pr` opens a real PR on the throwaway repo; verify no scored record is counted in the headline.
