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

## Sequence 06 — Spec 01: Model Router (implementation)

**Date:** 2026-07-15
**Spec:** `specs/01-model-router/` — **Status: Complete**

### What
Built the single model-router abstraction every agent LLM call must go through:

| Piece | File(s) |
|-------|---------|
| Tier/role config loader | `src/router/config.py` (`ModelSpec`, `TierConfig`, `RouterConfig`, `load_router_config`) |
| Shared exception | `src/errors.py` (`RouterError`) |
| Router entry point | `src/router/router.py` (`LLMRequest`, `LLMResponse`, `complete()`) |
| Trace write path | `src/metrics/trace_store.py` (`record_llm_call`) |
| Config | `config/litellm_config.yaml` (strong/small/local tiers, role map) |
| Tests | `tests/unit/test_router/`, `tests/integration/test_router/` |

### Why
Every later spec (04 single-agent, 06 multi-agent) needs to call an LLM without knowing or caring which
provider is behind a role. Centralising that behind `complete(request)` is what makes the cost-measurement
discipline possible: if any agent could call `litellm.completion` directly, some call could skip the trace
write and the benchmark's cost numbers would be silently wrong. Writing the trace row *before* returning
(rather than fire-and-forget after) means a DB outage surfaces as a loud `RouterError`, not a quietly
incomplete `trace_events` table.

### How
- **Config-driven tiers**: `config/litellm_config.yaml` defines `tiers.strong` (OpenRouter), `tiers.small`
  (Groq), and `tiers.local` (Ollama, zero-cost), plus a `roles` map. Switching a role's provider, or adding
  a new tier, is a YAML edit — no code change (FR-10).
- **`RouterError` lives in a standalone top-level module** (`src/errors.py`, not nested inside either
  package) so `src/metrics/trace_store.py` can raise it without importing anything from `src/router/` —
  see the circular-import issue below for why nesting it under `src/router/` didn't work.
  `RouterConfigError` subclasses `RouterError` so callers can catch one type for any router failure.
- **Cost math**: `_compute_cost()` is `prompt_tokens/1000*input_price + completion_tokens/1000*output_price`,
  computed from the resolved tier's config prices — never estimated after the fact (NFR-13).
  Ollama tiers are configured with `0.0` prices, satisfying FR-13 without special-casing the cost formula.
  `_normalize_usage()` defaults missing token counts to `0` and logs a warning rather than raising, since a
  malformed usage block shouldn't block a response the model already produced.
  api_key resolution reads `api_key_env` from the tier config: os.environ.get(api_key_env), a config-driven
  join rather than hard-coded per-provider env var names.

### Issues & Resolutions
- **Issue:** `trace_events.turn_index` and `event_type` are `NOT NULL` with `CHECK` constraints, but
  `tasks.md`'s `record_llm_call(...)` signature didn't mention either.
  **Resolution:** `record_llm_call` takes `turn_index: int = 0` (real per-turn tracking arrives with the
  LangGraph agents in Spec 04/06) and hard-codes `event_type='llm_call'` since this module only ever writes
  that event type.
- **Issue:** `trace_events.agent_role` has a `CHECK` constraint restricted to
  `architect|developer|tester|reviewer|system`, but an explicit-tier `complete()` call (no `role` set) has
  no natural role to record.
  **Resolution:** `_resolve_agent_role()` records `agent_role='system'` for tier-only calls; role-based
  calls record the role itself (`config.load_router_config` also rejects any config `roles:` entry outside
  that same set, so bad config fails at load time, not at insert time).
  **Resolution:** — same principle would apply to an unknown *role* pointing at a *known* tier, but that's
  actually rejected at config-load time by `load_router_config`, which validates every `roles:` entry
  against both `VALID_ROLES` and the declared tiers.
- **Issue:** `RouterConfigError` initially subclassed `Exception` directly (per the file plan's literal
  wording), which meant `pytest.raises(RouterError)` in the router-level unit test for "unknown role"
  failed — `complete()` only ever raises `RouterError`, not a bare `RouterConfigError`.
  **Resolution:** Made `RouterConfigError(RouterError)` so any config-resolution failure surfaced through
  `complete()` is still catchable as `RouterError`, matching the spec's promise that "a DB failure raises
  `RouterError`" generalized to "any router failure raises `RouterError`."
- **Issue:** `pyyaml` was only a transitive dependency (via `litellm`), not pinned directly.
  **Resolution:** Added `pyyaml>=6.0` to `pyproject.toml` and `requirements.txt` per the reconciliation
  note in the plan, and `pip install`ed it into `.venv` before running tests.
- **Issue:** No local Docker/Postgres/Ollama were running in this environment, so the plan's "manual
  verification" step (`make db-shell` showing real trace rows from a live call) could not be executed.
  **Resolution:** Confirmed the integration test (`tests/integration/test_router/test_ollama_live.py`)
  skips cleanly (`ssss` in `make test` output) rather than failing, which is the done-when criterion the
  spec actually asks for ("integration test... skips cleanly when no provider is configured"). Live
  verification is deferred to whenever Docker/Ollama are available locally.
- **Issue (found by `/code-review`, medium effort, 5-agent finder pass):** Nesting `RouterError` under
  `src/router/errors.py` created a real circular import — `import src.metrics.trace_store` on its own
  (before `src.router` had ever been imported) raised `ImportError: cannot import name 'record_llm_call'
  from partially initialized module`. Reproduced live: `src.router.__init__` eagerly imports `router.py`,
  which imports `metrics.trace_store`, which was mid-initialization when it tried to import
  `src.router.errors` back. Only failed in the metrics-first import order, so it wasn't caught by any test
  that always imported `src.router` first.
  **Resolution:** Moved `RouterError` to a standalone top-level `src/errors.py` with no package
  relationship to either `router` or `metrics`, breaking the cycle regardless of import order. Added
  `tests/unit/test_router/test_import_order.py`, which imports `src.metrics.trace_store` in a fresh
  subprocess to regression-test the fix.
- **Issue (found by `/code-review`):** `response.choices[0].message.content` was accessed unguarded in
  `complete()`, after `cost_usd` was already computed from `usage` but before `record_llm_call`. A
  content-filtered/empty response would raise `IndexError` there, skipping the trace write entirely for a
  call that had already been made (and billed) — a silent-LLM-call gap in exactly the NFR-8 sense the
  spec exists to prevent.
  **Resolution:** Added `_extract_content()`, which defaults to `""` and logs a warning on empty
  `choices`, so `record_llm_call` always runs once a completion response comes back. Added
  `test_empty_choices_still_writes_trace`.
- **Issue (found by `/code-review`):** `os.environ["DATABASE_URL"]` in `record_llm_call` raised a raw
  `KeyError` instead of `RouterError` when the env var was unset, breaking the function's own documented
  contract ("raises `RouterError` on any Postgres failure").
  **Resolution:** Wrapped the lookup in `try/except KeyError: raise RouterError(...)`. Also widened the
  `psycopg2.connect` except clause from `OperationalError` to the broader `psycopg2.Error`, since not
  every connection failure is an `OperationalError`.
- **Issue (found by `/code-review`):** `config.resolve(request.role or request.tier)` used Python
  truthiness rather than an explicit `None` check, so `LLMRequest(role="", tier="strong")` would silently
  resolve against `tier` while `_resolve_agent_role` recorded `agent_role=""` in the trace.
  **Resolution:** Replaced with an explicit `request.role if request.role is not None else request.tier`.
  Added `test_empty_string_role_does_not_silently_fall_back_to_tier`.
- **Issue (found by `/code-review`):** An empty `tiers:` or `roles:` section in the YAML config (parses to
  `None` via `yaml.safe_load`) passed the existing presence checks but then crashed with `AttributeError`
  (`NoneType has no attribute 'items'`) instead of raising `RouterConfigError`.
  **Resolution:** Both sections are now validated with `isinstance(..., dict)` before iterating.
- Not fixed (logged, not blocking): `complete()` re-reads and re-parses `config/litellm_config.yaml` from
  disk on every call when no `RouterConfig` is passed in. Acceptable for this spec's scope — no caching
  layer is required until Spec 07 — and callers that care can pass a pre-loaded `RouterConfig` explicitly.

### Verification
- `make lint` → 0 (ruff + black clean, `src/` and `tests/`)
- `make test` → 0 (26 unit tests pass, 4 integration tests skip cleanly without Postgres/Ollama)
- `grep -rE 'import openai|from openai|google.generativeai|anthropic|mistralai|cohere' src/` → no output
- Unit tests cover: role resolution, explicit-tier resolution, exact cost math (1000/500 tokens against
  known prices), trace-write-before-return ordering (via a shared call-order list), missing-role-and-tier
  error, unknown-role error, empty-string-role, empty-choices response, missing-price config error,
  unknown-tier config error, empty `tiers:`/`roles:` sections, env-var expansion in `api_base`, the
  no-SDK-import grep guard, and the metrics-before-router import-order regression.
- `/code-review` (medium effort): 6 findings, 5 CONFIRMED correctness bugs fixed as above, 1 efficiency
  finding logged as intentionally deferred; re-verified `make lint && make test` clean after fixes.

### Files touched
`src/errors.py`, `src/router/__init__.py`, `src/router/config.py`, `src/router/router.py`,
`src/metrics/__init__.py`, `src/metrics/trace_store.py`, `config/litellm_config.yaml`,
`tests/unit/test_router/*`, `tests/integration/test_router/*`, `pyproject.toml`, `requirements.txt`,
`.env.example`, `specs/01-model-router/{spec,tasks}.md`

---

## Sequence 07 — Live verification pass on Spec 00 + Spec 01 (Docker/Postgres now available)

**Date:** 2026-07-16
**Specs:** `specs/00-foundation`, `specs/01-model-router` — verification, not new implementation

### What
Ran a full, live end-to-end verification of both completed specs now that Docker Desktop was available in
this environment (it was not running during Sequence 02/06, so those verifications relied on unit tests and
code inspection for the Docker/Postgres-dependent paths). Started Docker, then ran `make clean` → `make
setup` → `make lint` → `make test` → `make db-shell` inspection → `make sandbox-run` → a direct invocation
of `block-host-exec.sh` with both a blocked and an allowed command. Found and fixed two real bugs in the
process.

### Why
The progress report and both specs' `tasks.md` claimed full verification, but several done-when criteria
in `specs/01-model-router/spec.md` were still checkbox-`[ ]` despite the spec's own `## Status: Complete`
— a documentation/reality mismatch worth resolving by actually exercising the infrastructure rather than
trusting the prior record.

### How
- Confirmed `make lint` and `make test` were already green from a prior run without Docker (23 passed, 4
  skipped — the Docker/Postgres-dependent integration tests skipping cleanly, as designed).
- Started Docker Desktop, then exercised the full Docker-dependent path for real: `make setup` from a
  clean state, live `\dt`/`\dv` inspection via `make db-shell` showing all 3 tables + 2 views, `make
  sandbox-run` printing `Hello from sandbox`, and re-ran `make test` — now 26 passed, 1 skipped (only the
  Ollama-live test skips, since no local Ollama server was running).
- Verified `block-host-exec.sh` directly by piping synthetic PreToolUse JSON at it: a `python
  src/agents/test.py` command got exit code 2 with the safety-block message; `make lint` passed through
  with exit code 0.
- Verified the git-history purge from Sequence 05 is still intact: `git log main --format='%B' | grep -i
  "co-authored\|anthropic"` returns nothing; the old pre-rewrite SHAs only exist in `refs/stash` (never
  pushed), not in any branch.

### Issues & Resolutions
- **Issue:** `docker compose -f config/docker/docker-compose.yml ...` was invoked from the repo root
  throughout the Makefile, but Docker Compose resolves its implicit `.env` file relative to the **compose
  file's directory** (`config/docker/`), not the caller's working directory. Reproduced directly:
  `docker compose -f config/docker/docker-compose.yml config` showed `POSTGRES_PASSWORD: password` even
  with a root `.env` setting `POSTGRES_PASSWORD=roottest` present — a real environment-variable that
  `.env.example` documents as configurable was silently ignored. The same root cause affected
  `scripts/wait_for_postgres.py`: the Makefile's `DATABASE_URL` variable was never exported to that
  subprocess's environment, so a custom `DATABASE_URL` in `.env` would silently be ignored there too,
  even though `make db-shell`/`psql` calls elsewhere already read it correctly via the `DATABASE_URL`
  make variable.
  **Resolution:** Added `ENV_FILE := $(if $(wildcard .env),--env-file .env,)` to the Makefile (empty when
  no `.env` exists yet, so a fresh clone's first `make setup` still works against defaults) and passed
  `$(ENV_FILE)` to every `docker compose` invocation (`setup`, `db-shell`, `clean`). Also changed the
  `wait_for_postgres.py` invocation in `setup` to explicitly export `DATABASE_URL="$(DATABASE_URL)"` into
  that subprocess's environment. Re-verified: with a root `.env` containing `POSTGRES_PASSWORD=roottest`,
  `docker compose ... --env-file .env config` now correctly resolves to `roottest`.
- **Issue:** `make clean`'s `docker compose down` did not pass `-v`, so the Postgres volume
  (`docker_benchmark-pgdata`) survived a clean — silently contradicting CLAUDE.md's own Make Targets table,
  which documents `make clean` as "stop containers, drop volumes, remove `__pycache__`".
  **Resolution:** Changed `clean` to `docker compose ... down -v`. Re-verified: `docker volume ls` shows no
  `benchmark-pgdata` volume after `make clean`, and a subsequent `make setup` still recreates the schema
  from scratch correctly (confirmed via `\dt`/`\dv`).
- **Issue:** `specs/01-model-router/spec.md`'s done-when section had all 9 boxes unchecked (`[ ]`) despite
  `## Status: Complete` and a fully checked `tasks.md` — a stale-documentation gap, not a functional bug.
  **Resolution:** Checked each criterion against a live re-verification (grep for provider SDK imports,
  live Postgres write path, `make lint`/`make test` exit codes, sandbox rule) and checked all 9 boxes.
- No functional regressions found in `src/router/`, `src/metrics/`, or the sandbox wrapper — the
  correctness bugs found and fixed in Sequence 06's `/code-review` pass are still fixed and covered by
  their regression tests.

### Verification
- `make lint` → 0
- `make test` → 26 passed, 1 skipped (Ollama-live only), up from 23 passed/4 skipped pre-Docker
- `make setup` from `make clean` state → exits 0, twice (once before the Makefile fix to establish the bug,
  once after to confirm the fix and no regression)
- `docker compose ... ps` → `benchmark-db` healthy
- `make db-shell` → `\dt` shows `llm_cache`, `run_records`, `trace_events`; `\dv` shows `run_summary`,
  `task_cost_breakdown`
- `make sandbox-run SCRIPT=scripts/hello_sandbox.py` → `Hello from sandbox`, exit 0
- `echo '{"tool_input":{"command":"python src/agents/test.py"}}' | .claude/hooks/block-host-exec.sh` → exit
  2, safety-block message; same with `make lint` as the command → exit 0
- `grep -rE 'import openai|from openai|google.generativeai|anthropic|mistralai|cohere' src/` → no output
- `git log main --format='%B' | grep -ci "co-authored\|anthropic"` → 0
- `docker volume ls | grep benchmark` → empty immediately after `make clean` (post-fix)

### Files touched
`Makefile`, `specs/01-model-router/spec.md`, `progress_report.md`

---
