# Implementation Plan — Spec 00: Foundation

## Context

The repo currently contains only planning docs (`planning/`), `CLAUDE.md`, `.mcp.json`, and Claude Code config (`.claude/agents`, `.claude/hooks`, `.claude/skills`) — no source tree, no git repo, no `pyproject.toml`/`Makefile` yet. `specs/00-foundation/{spec.md,plan.md,tasks.md}` already define what "foundation" means: the repo skeleton, Postgres + Docker infra, the sandbox wrapper, and verification that the Claude Code safety hooks work. This plan turns those three docs into an executable build order, resolves one real inconsistency between them, and calls out the couple of gaps the docs left implicit (repo not yet under git).

**Schema decision (confirmed with user):** `scripts/db_init.sql` will implement the fuller, "Implementation-Ready v1.0" schema from `planning/04-database-schema.sql` (`benchmark` schema; tables `llm_cache`, `trace_events`, `run_records`; views `run_summary`, `task_cost_breakdown`) rather than the simpler 3-table sketch (`benchmark_runs`/`task_results`/`agent_events`) that `specs/00-foundation/spec.md`'s done-when list and `tasks.md` currently reference. `spec.md`'s done-when criteria and `tasks.md` section 4/10 will be edited to reference the real table/view names before implementation, so the spec stays internally consistent and verifiable. Alembic (mentioned in the planning doc's migration note) is *not* set up in this spec — `db_init.sql` with `CREATE TABLE IF NOT EXISTS` is enough for Spec 00; migrations tooling can be introduced when a spec actually needs a second migration.

**Repo not yet a git repository.** None of FR-1–FR-52 mention `git init`, but `spec.md`'s first done-when line (`git clone <repo> && cd <repo> && make setup`) presupposes one exists. Step 0 below adds `git init` + initial commit as a prerequisite, since `.gitignore`, hooks relying on `git status`/`git diff`, and `make clean` all assume a git working tree.

## Build Order

### 0. Git init (prerequisite, not in original FR list)
- `git init`, first commit will happen after step 1 (directory skeleton + `.gitignore`) so nothing untracked-but-wanted gets ignored by accident.

### 1. Directory skeleton + `.gitignore` + `.env.example`
Per `tasks.md` §1:
- Create `src/`, `tests/{unit,integration}/`, `config/docker/`, `scripts/`, `reports/`, `logs/`, `dashboard/` (+ `.gitkeep` in empty dirs).
- `__init__.py` in `src/`, `tests/`, `tests/unit/`, `tests/unit/test_foundation/`, `tests/integration/`.
- `.gitignore`: Python standard + `.env`, `reports/*`, `logs/*` (keep `.gitkeep`), `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`, `.venv/`.
- `.env.example` with `DATABASE_URL`, `POSTGRES_PASSWORD`, `LITELLM_CONFIG`, `MAX_TASK_SECONDS`, `MAX_ITERATIONS`.
- First commit here.

### 2. `pyproject.toml`
Per `tasks.md` §2 / `planning/01-requirements.md` §7.1 (confirms LangGraph, LiteLLM, Postgres, Streamlit, ruff+black, pytest+pytest-cov as the stack):
- `[build-system]` = setuptools; `requires-python = ">=3.11"`.
- Runtime deps: `langgraph`, `litellm`, `psycopg2-binary`, `streamlit`, `python-dotenv`, `docker`.
- Dev deps: `pytest`, `pytest-cov`, `ruff`, `black`, `mypy`.
- `[tool.ruff]`, `[tool.black]` (line-length 100), `[tool.pytest.ini_options]` (`markers = ["integration: requires Docker/Postgres"]`).
- `python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"` — must exit 0, `pip check` clean.

### 3. `Makefile`
Per `tasks.md` §3: `setup`, `lint`, `test`, `benchmark` (stub, exits 1 with "not yet implemented"), `sandbox-run`, `dashboard`, `db-shell`, `clean`, plus `check-docker`/`check-python` guards and `DATABASE_URL` loaded from `.env`.
- Verify `make lint` / `make test` succeed against the still-empty `src/`.

### 4. Docker Compose + Postgres schema
- `config/docker/docker-compose.yml`: postgres:15-alpine, container `benchmark-db`, port 5432, volume `benchmark-pgdata`, healthcheck (`tasks.md` §4 body is correct as written).
- `scripts/db_init.sql`: **port the schema from `planning/04-database-schema.sql`** — `CREATE SCHEMA IF NOT EXISTS benchmark`, `CREATE EXTENSION IF NOT EXISTS pgcrypto`, tables `llm_cache`, `trace_events`, `run_records` with their constraints/comments, indexes, and the `run_summary` / `task_cost_breakdown` views. Wrap statements with `IF NOT EXISTS` guards so `make setup` stays idempotent (the source file mostly already uses them; add for schema/extension).
- `scripts/wait_for_postgres.py`: poll `DATABASE_URL` until ready (max 30s).
- Verify: `docker compose ... ps` → `healthy`; `make db-shell` → `\dt` shows `llm_cache`, `trace_events`, `run_records`; `\dv` shows the two views.
- **Edit `specs/00-foundation/spec.md`** FR-48 and the done-when bullet (currently line 45) and **`tasks.md`** §4/§10 to reference `llm_cache`/`trace_events`/`run_records` instead of `benchmark_runs`/`task_results`/`agent_events`.

### 5. Docker sandbox image
Per `tasks.md` §5: `config/docker/Dockerfile` (python:3.11-slim, git/curl/build-essential, `requirements.txt`, `pip install swebench`, `ENTRYPOINT ["python"]`), plus a minimal `requirements.txt` (sandbox subset, not dev deps).
- Verify: `docker build ... -t swe-sandbox:latest .` exits 0; `docker run --rm swe-sandbox:latest -c "print('sandbox ok')"` works.

### 6. Sandbox wrapper + smoke test
Per `tasks.md` §6: `scripts/sandbox_exec.py` (`--script`/`--args` argparse, validates script exists on host, builds `docker run --rm --network none -v <root>:/workspace:ro -w /workspace swe-sandbox:latest ...`, type hints, docstring, no bare except) and `scripts/hello_sandbox.py` (prints `Hello from sandbox`).
- `tests/unit/test_foundation/test_sandbox_exec.py`: mock `subprocess.run`, assert `--network none` and `:ro` mount are present, args pass-through, missing-script error.
- Verify `make sandbox-run SCRIPT=scripts/hello_sandbox.py` prints `Hello from sandbox`.

### 7. Claude Code infra verification (no new files — already exist)
- `.claude/settings.json`, `.mcp.json` valid JSON.
- Hook scripts executable (`chmod +x` if not).
- Manually confirm `block-host-exec.sh` blocks `python src/agents/test.py` (exit 2) and allows `make --version`. (Read `.claude/hooks/block-host-exec.sh` — already confirmed it correctly pattern-matches `src/agents/`, `src/tools/`, `src/harness/`, `benchmark/`.)
- Confirm `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` exist (already do).

### 8. Integration tests
Per `tasks.md` §8: `tests/integration/test_foundation/test_postgres.py` (`@pytest.mark.integration`, `pytest.importorskip("psycopg2")`, connects and checks `information_schema.tables` for the **3 real tables** — update names here too), `tests/integration/test_foundation/test_sandbox.py` (runs `sandbox_exec.py` against `hello_sandbox.py`, skips if Docker unavailable).

### 9. Final lint/format pass
`ruff check --fix src/ tests/ scripts/`, `black src/ tests/ scripts/`, `make lint` and `make test` both exit 0.

### 10. Acceptance checklist
Re-run every done-when bullet in (the now-corrected) `spec.md`; mark `## Status: Complete`.

## Key Files to Create
```
pyproject.toml, Makefile, .gitignore, .env.example
src/__init__.py
tests/{__init__.py,conftest.py}, tests/unit/.../test_sandbox_exec.py
tests/integration/test_foundation/{test_postgres.py,test_sandbox.py}
config/docker/{Dockerfile,docker-compose.yml}
scripts/{db_init.sql,wait_for_postgres.py,sandbox_exec.py,hello_sandbox.py}
requirements.txt   (sandbox image subset)
reports/.gitkeep, logs/.gitkeep, dashboard/.gitkeep
```

## Files to Edit (existing)
- `specs/00-foundation/spec.md` — FR-48 + done-when table names → `llm_cache`/`trace_events`/`run_records`.
- `specs/00-foundation/tasks.md` — §4 and §10 table names/checks updated to match; §1 gets a `git init` line.

## Verification (end-to-end)
```
make clean          # confirm clean-from-nothing works
make setup           # venv, pip install, compose up, db_init.sql, docker build
make lint             # ruff + black clean
make test              # unit tests pass, integration tests run if Docker/PG up else skip
docker compose -f config/docker/docker-compose.yml ps   # benchmark-db healthy
make db-shell  → \dt / \dv                                # llm_cache, trace_events, run_records + 2 views
docker build -f config/docker/Dockerfile -t swe-sandbox:test .
make sandbox-run SCRIPT=scripts/hello_sandbox.py           # prints "Hello from sandbox"
# In a Claude Code Bash call: attempt `python src/agents/test.py` → hook blocks (exit 2)
make clean            # tears back down cleanly
```
