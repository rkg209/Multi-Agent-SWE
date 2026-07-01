# Tasks — Spec S3 (Stretch): Real GitHub PR Demo

> Stretch — only after Spec 09. Demo-only; never in a scored run. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create `tests/unit/test_demo_pr/` with `__init__.py`
- [ ] Configure the designated throwaway repo + GitHub token via env (`.gitignore`d)

## Demo runner

- [ ] `benchmark/demo_pr.py`: run best-multi solver → take final patch → GitHub MCP branch/commit/PR on the throwaway repo
- [ ] Generate a PR description; no auto-merge
- [ ] Exclude from headline: not written to `run_records` (or `demo=true`, always filtered out)

## Hard guard (C-10)

- [ ] Make PR creation unreachable from any scored `make benchmark` run
- [ ] Refuse any target repo other than the configured throwaway repo

## Makefile

- [ ] `make demo-pr` target (the only PR-creating entrypoint)

## Tests

- [ ] Unit: scored path cannot reach PR creation (guard test)
- [ ] Unit: demo runner targets only the configured repo (mocked GitHub MCP)
- [ ] Integration/manual: `make demo-pr` opens a real PR; no scored record counted in the headline
- [ ] `make lint` exits 0; `make test` exits 0

## Acceptance

- [ ] Verify each done-when criterion in `spec.md`
- [ ] Add `## Status` → `Complete.` to `spec.md`
