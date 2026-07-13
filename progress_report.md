# Progress Report

A running, append-only narrative of how this project was built: **what** changed, **why** it changed, and **how** it was done — plus every issue hit along the way and how it was resolved.

**Rules for this file** (see also the "Progress Report" section in `CLAUDE.md`):

- One `## Sequence NN — <title>` section per meaningful change. Never renumber or rewrite past sequences; only append.
- Every sequence has: **What**, **Why**, **How**, **Issues & Resolutions**, **Verification**, **Files touched**.
- If a past decision is reversed, do not edit the old sequence — write a new one that says so and links back.

---

## Sequence 00 — Project definition and design docs

**Date:** 2026-07 (pre-implementation)
**Commit:** `9870022` — *Initialize repo skeleton for Spec 00 foundation*

### What
Wrote the project brief (`multi-agent-swe-benchmark.md`) and the full design set under `planning/`:
requirements, architecture, system design, database design (`04-database-schema.sql`), and API design
(`05-api-design.md` + `05-openapi.yaml`).

### Why
The research question — *does a multi-agent SWE system beat a single agent on SWE-bench, and at what
cost?* — only produces a defensible answer if the metrics, the schema that stores them, and the agent
topology are pinned down **before** any code exists. Designing the Postgres schema up front also meant
later specs could write to a stable table contract instead of migrating as they went.

### How
Top-down: brief → requirements (FR-*) → architecture → system design → DB schema → API surface.
Every functional requirement got an FR number so that individual specs could later claim a subset of them
(e.g. Spec 00 claims FR-1…FR-8 and FR-47…FR-52). `planning/04-database-schema.sql` was written as the
implementation-ready schema, to be ported into `scripts/db_init.sql` rather than re-invented.

### Issues & Resolutions
None — design-only phase.

### Verification
Design docs reviewed for internal consistency; every FR referenced by at least one spec.

### Files touched
`multi-agent-swe-benchmark.md`, `planning/01-project-summary.md`, `planning/01-requirements.md`,
`planning/02-architecture.md`, `planning/03-system-design.md`, `planning/04-database-design.md`,
`planning/04-database-schema.sql`, `planning/05-api-design.md`, `planning/05-openapi.yaml`

---

## Sequence 01 — Claude Code development harness

**Date:** 2026-07
**Commit:** `9870022` — *Initialize repo skeleton for Spec 00 foundation*

### What
Set up the `.claude/` development harness alongside the repo skeleton: `CLAUDE.md`, three hooks
(`block-host-exec.sh`, `fast-tests.sh`, `format-python.sh`), six subagents (code-reviewer, explorer,
harness-debugger, planner, spec-writer, test-runner), five skills (eval-conventions, new-spec, run-bench,
score-patch, trace), `.mcp.json`, `.gitignore`, and `.env.example`.

### Why
The single most dangerous failure mode in this project is **agent-generated code executing on the host**.
Making that a written rule in `CLAUDE.md` is not enough — a rule that isn't enforced is a rule that gets
violated under time pressure. So the sandbox rule is backed by a `PreToolUse` hook that hard-blocks
(exit code 2) any Bash call trying to run `src/agents/`, `src/tools/`, or `benchmark/` code directly.

The subagents and skills exist to keep context small and the workflow repeatable: benchmark runs and
patch scoring are long, noisy operations that belong in an isolated subagent context, not the main thread.

### How
- `CLAUDE.md` states the two-model-layer distinction (Claude Code vs. LiteLLM-routed system agents), the
  sandbox hard rule, the make targets, coding conventions, and the spec-driven workflow.
- `.claude/settings.json` registers the hooks; hook scripts are pattern-matchers over the proposed Bash
  command, returning exit code 2 to block.
- Skills are `SKILL.md` files with a description that lets the model select them by intent.

### Issues & Resolutions
- **Issue:** A blanket "no python execution" hook would also block legitimate host commands like
  `make lint` and `pytest tests/`.
  **Resolution:** Scoped the block to the three untrusted-code paths (`src/agents/`, `src/tools/`,
  `benchmark/`) instead of blocking Python wholesale.

### Verification
`python -m json.tool .claude/settings.json` and `.mcp.json` parse; all three hook scripts are `-rwxr-xr-x`;
a deliberate `python src/agents/test.py` attempt was blocked by the hook.

### Files touched
`CLAUDE.md`, `.claude/**`, `.mcp.json`, `.gitignore`, `.env.example`

---

## Sequence 02 — Spec 00: Foundation (implementation)

**Date:** 2026-07
**Commit:** `ac700d2` — *Implement Spec 00: Foundation*
**Spec:** `specs/00-foundation/` — **Status: Complete**

### What
Built everything every later spec depends on:

| Piece | File(s) |
|-------|---------|
| Python packaging + tool config | `pyproject.toml`, `requirements.txt` |
| Make targets | `Makefile` (`setup`, `lint`, `test`, `benchmark` stub, `sandbox-run`, `dashboard`, `db-shell`, `clean`) |
| Postgres metrics DB | `config/docker/docker-compose.yml`, `scripts/db_init.sql`, `scripts/wait_for_postgres.py` |
| Docker sandbox image | `config/docker/Dockerfile` |
| Sandbox wrapper | `scripts/sandbox_exec.py`, `scripts/hello_sandbox.py` |
| Tests | `tests/unit/test_foundation/`, `tests/integration/test_foundation/` |

### Why
`make setup` on a fresh clone must produce a working environment — Postgres healthy with the schema
loaded, sandbox image built, deps installed — or every subsequent spec starts by debugging infrastructure
instead of writing agents. The DB schema (`llm_cache`, `trace_events`, `run_records`, plus the
`run_summary` and `task_cost_breakdown` views) was created now, empty, so that Spec 05's instrumentation
has a stable target to write into.

### How
- **Schema** ported from `planning/04-database-schema.sql` with `CREATE ... IF NOT EXISTS` guards so
  `make setup` is idempotent and safe to re-run.
- **Sandbox wrapper** (`scripts/sandbox_exec.py`) builds a `docker run` command with the two properties
  that make it a sandbox: `--network none` (no egress) and `-v $PROJECT_ROOT:/workspace:ro` (read-only
  mount). It forwards the container's exit code so callers see real failures. Command construction is
  split into a pure `build_docker_command()` function specifically so it can be unit-tested without
  Docker.
- **Tests** are split by dependency: unit tests assert on the constructed docker command (no Docker
  needed); integration tests are marked `@pytest.mark.integration` and skip cleanly when Postgres or
  Docker isn't running, keeping `make test` green on a bare machine.

### Issues & Resolutions
- **Issue:** The planned `setup` target called `psql "$(DATABASE_URL)" -f scripts/db_init.sql` from the
  host — which requires a host `psql` client that most machines don't have.
  **Resolution:** Piped the SQL into the container's own client instead:
  `docker compose exec -T postgres psql -U postgres -d benchmark_db < scripts/db_init.sql`. Zero host
  dependencies beyond Docker. `make db-shell` was changed the same way, for the same reason.
- **Issue:** The planned `sleep 3` before loading the schema is a race — Postgres is sometimes slower,
  and a fixed sleep either flakes or wastes time.
  **Resolution:** Replaced it with `scripts/wait_for_postgres.py`, which polls the connection until ready
  (30s cap) and then exits.
- **Issue:** Strict ruff (`ANN` = annotations) flagged the test files, where annotating every fixture and
  test function is noise.
  **Resolution:** Added `[tool.ruff.lint.per-file-ignores]` with `"tests/**" = ["ANN"]` — strict typing
  where it buys correctness, relaxed where it doesn't.

### Verification
- `make lint` → 0 (ruff + black clean)
- `make test` → 0 (unit tests pass; integration tests skip without infra)
- `docker compose ps` → `benchmark-db` **healthy**
- `make db-shell` → `\dt` shows `llm_cache`, `trace_events`, `run_records`; `\dv` shows `run_summary`,
  `task_cost_breakdown`
- `make sandbox-run SCRIPT=scripts/hello_sandbox.py` → prints `Hello from sandbox`, exit 0
- block-host-exec hook confirmed blocking; **no agent-generated code ran on the host**

### Files touched
`Makefile`, `pyproject.toml`, `requirements.txt`, `config/docker/Dockerfile`,
`config/docker/docker-compose.yml`, `scripts/db_init.sql`, `scripts/sandbox_exec.py`,
`scripts/hello_sandbox.py`, `scripts/wait_for_postgres.py`, `tests/unit/test_foundation/*`,
`tests/integration/test_foundation/*`, `specs/00-foundation/{spec,tasks}.md`

---

## Sequence 03 — Full spec backlog authored (01–09 + stretch S1–S3)

**Date:** 2026-07
**Commit:** `8aa9b34` — *specs added*

### What
Wrote `spec.md` + `plan.md` + `tasks.md` for every remaining spec:

| Spec | Delivers |
|------|----------|
| 01-model-router | LiteLLM router, tier config, LLM response caching |
| 02-tool-layer | Tools the agents can call (file read/write, run tests, git diff) |
| 03-benchmark-harness | SWE-bench task loading + `sb-cli` scoring |
| 04-single-agent-baseline | The single-agent solver — the control arm |
| 05-instrumentation-metrics | Trace events + run records written to Postgres |
| 06-multi-agent-system | Architect → Developer → Tester → Reviewer LangGraph |
| 07-guardrails-cost-control | Iteration caps, budget caps, timeouts |
| 08-comparison-dashboard | Streamlit single-vs-multi comparison |
| 09-writeup-reproducibility | Final results write-up + reproduction steps |
| S1–S3 (stretch) | Parallel reviewers, multi-model sweep, GitHub PR demo |

### Why
Sequencing is the whole game here. The baseline (04) must land **before** the multi-agent system (06),
because a multi-agent result with no control arm answers nothing. Instrumentation (05) must sit between
them so both arms are measured by identical code paths — otherwise any cost/success difference could be a
measurement artifact rather than a real effect. Writing all specs up front makes that dependency order
explicit and hard to drift from.

### How
Used the `spec-writer` and `planner` subagents to draft each spec from the `planning/` docs, then reviewed
each for a clear goal, explicit non-goals, and verifiable *done-when* criteria. Each spec's `tasks.md`
is a checkbox list, checked off only after `make lint && make test` pass. Also added the git commit policy
to `CLAUDE.md` (no `Co-Authored-By` trailers).

### Issues & Resolutions
None — documentation-only change.

### Verification
Every spec has all three files; dependency chain (`Depends-On`) forms a valid order with no cycles.

### Files touched
`specs/01-*` … `specs/09-*`, `specs/S1-*` … `specs/S3-*`, `CLAUDE.md`

---

## Sequence 04 — Progress report established

**Date:** 2026-07-13

### What
Created this file (`progress_report.md`) and added a **Progress Report** section to `CLAUDE.md` requiring
it to be appended to after every meaningful change.

### Why
The spec files describe the *intended* state and git log records the *mechanical* state, but neither
captures the reasoning — why the schema load moved inside the container, why the sandbox mount is
read-only, why the baseline must precede the multi-agent system. That reasoning is exactly what a reader
(or a future maintainer, or the write-up in Spec 09) needs, and it's the first thing lost to time. One
append-only narrative file keeps it.

### How
Reconstructed sequences 00–03 from the git history, the spec files, and the delta between what `tasks.md`
prescribed and what the code actually does (that delta is where the interesting issues live). Added the
maintenance instruction to `CLAUDE.md` so it applies to every future change.

### Issues & Resolutions
None.

### Verification
Report reflects the three existing commits and the current working tree.

### Files touched
`progress_report.md` (new), `CLAUDE.md`

---

## Sequence 05 — Purge `Co-Authored-By` trailers from git history

**Date:** 2026-07-13

### What
Rewrote the messages of the two commits that carried
`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (the original `9870022` and `ac700d2`), and
hardened the git commit policy in `CLAUDE.md` into an explicit hard rule listing the exact banned strings.

### Why
The trailer breaks `git push` to GitHub. That makes it a shipping blocker, not a style nit — so it had to
come out of history *before* a remote was ever added, and the policy had to be stated strongly enough
that it doesn't get re-added by a default behaviour on the next commit.

### How
The repo has **no remote and no other branches**, and nothing had been pushed, so rewriting history was
free of the usual collaborator hazards. Stashed the in-flight working changes, then:

```
git filter-branch -f --msg-filter 'grep -v -i "Co-Authored-By:.*anthropic\|Co-Authored-By: Claude"' -- --all
```

then restored the stash. Message-only rewrite — trees and file contents are untouched.

In `CLAUDE.md`, the one-line policy was replaced with a Hard Rule block that spells out the literal banned
trailers, states the *why* (GitHub push failure), says it overrides any built-in default, and requires a
self-check of the message before every commit.

### Issues & Resolutions
- **Issue:** All commit SHAs below the rewrite point changed (`9870022`→`485e09f`, `ac700d2`→`a1fbbb7`,
  `8aa9b34`→`0647057`). Earlier sequences in this report cite the old SHAs.
  **Resolution:** Left the old SHAs in Sequences 00–03 as written (this file is append-only) and record
  the mapping here instead. The old SHAs are dead; use the new ones.
- **Issue:** After the rewrite, a repo-wide grep still found 2 hits. These were in `filter-branch`'s
  `refs/original/*` backup refs and a leftover `refs/stash` entry whose parents are the old commits.
  **Resolution:** Deleted the `refs/original/*` backups. The dangling `refs/stash` entry was left in
  place — `refs/stash` is a local-only ref that is **never pushed**, so it cannot cause the GitHub
  failure. `main`, the only thing that will be pushed, is verified clean.

### Verification
- `git log main --format='%B' | grep -ci "co-authored\|anthropic"` → **0**
- All three commits still present with their bodies intact, trailers removed
- Working tree unaffected: `CLAUDE.md` modified, `progress_report.md` untracked, no file content lost

### Files touched
`CLAUDE.md`; commit messages of `485e09f`, `a1fbbb7`, `0647057` (rewritten)

---
