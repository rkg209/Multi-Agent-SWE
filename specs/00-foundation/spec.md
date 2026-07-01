# Spec 00: Foundation

## Goal

Establish the complete repository skeleton and development infrastructure for the Multi-Agent SWE System + Benchmark project. This spec creates everything that every subsequent spec will depend on: the `Makefile` with all standard targets, a running Postgres instance for metrics, a Docker sandbox wrapper skeleton for safe code execution, and the full Claude Code setup (CLAUDE.md, hooks, agents, skills). When this spec is done, a developer can clone the repo, run `make setup`, and immediately start implementing Spec 01 in a correctly configured environment.

## Scope

Functional requirements addressed by this spec:

| ID     | Requirement |
|--------|-------------|
| FR-1   | The repository has a standard Python project layout: `src/`, `tests/`, `config/`, `scripts/`, `specs/`, `reports/`, `logs/`, `dashboard/` directories. |
| FR-2   | `pyproject.toml` defines all project metadata, dependencies (LangGraph, LiteLLM, psycopg2, Streamlit, swebench), and dev dependencies (pytest, ruff, black, mypy). |
| FR-3   | A `.venv/` virtual environment is created and all dependencies install without conflict on Python 3.11+. |
| FR-4   | `make setup` idempotently installs deps, starts Postgres via Docker Compose, runs `db_init.sql` to create the metrics schema, and builds the Docker sandbox image. |
| FR-5   | `make lint` runs `ruff check src/ tests/` and `black --check src/ tests/` and exits 0 on a clean codebase. |
| FR-6   | `make test` runs `pytest tests/unit/ tests/integration/ -q` and exits 0 (or with skips for tests requiring infrastructure). |
| FR-7   | `make benchmark` exists in the Makefile (with a stub that prints "not yet implemented") — it will be wired up in later specs. |
| FR-8   | `make clean` stops Docker Compose services, removes `__pycache__` directories, removes `.pytest_cache`, and removes `reports/` and `logs/` content (but not the directories). |
| FR-47  | A `docker-compose.yml` runs a Postgres 15 container named `benchmark-db` on port 5432, with persistent volume `benchmark-pgdata`, and health check. |
| FR-48  | `scripts/db_init.sql` creates the `benchmark_db` database and the initial schema: `benchmark_runs`, `task_results`, and `agent_events` tables with correct column types and indices. |
| FR-49  | A Docker sandbox image is defined in `config/docker/Dockerfile`. It installs Python 3.11, the project's requirements, and `sb-cli`. The image builds successfully (`docker build` exits 0). |
| FR-50  | `scripts/sandbox_exec.py` is a Python script that runs a given script inside the Docker sandbox container. It accepts `--script` and `--args` parameters, mounts the project root as read-only, and returns the container's exit code. |
| FR-51  | The `.claude/hooks/block-host-exec.sh` PreToolUse hook is installed and working: attempting to run `python src/agents/` directly in a Bash tool call causes Claude Code to hard-block with exit code 2. |
| FR-52  | `make sandbox-run SCRIPT=scripts/hello_sandbox.py` executes `hello_sandbox.py` inside the Docker container and prints "Hello from sandbox" to stdout. |

## Non-Goals

- No agent logic (Architect, Developer, Tester, Reviewer) — that starts in Spec 02+.
- No LLM calls of any kind — no LiteLLM config, no model routing.
- No SWE-bench task execution — the sandbox wrapper is a skeleton only.
- No Streamlit dashboard — that is Spec 08 or later.
- No benchmark scoring or metrics analysis — Postgres schema is created, but no data is inserted.
- No CI/CD pipeline (GitHub Actions etc.) — out of scope for now.

## Done-When

All of the following are true and verifiable:

- [ ] `git clone <repo> && cd <repo> && make setup` exits 0 on a fresh macOS or Ubuntu machine with Docker and Python 3.11 installed.
- [ ] `make lint` exits 0 on the initial codebase (no lint errors in skeleton files).
- [ ] `make test` exits 0 (skeleton unit tests pass; integration tests that require Postgres skip gracefully if not running).
- [ ] `docker compose ps` shows `benchmark-db` container in `healthy` state after `make setup`.
- [ ] `make db-shell` opens a `psql` prompt connected to `benchmark_db` and `\dt` shows the three tables: `benchmark_runs`, `task_results`, `agent_events`.
- [ ] `docker build -f config/docker/Dockerfile .` exits 0 (sandbox image builds).
- [ ] `make sandbox-run SCRIPT=scripts/hello_sandbox.py` prints `Hello from sandbox` and exits 0.
- [ ] The block-host-exec hook blocks a direct host run: simulating `python src/agents/test.py` in Claude Code's Bash tool triggers the hook and shows the safety block message.
- [ ] `make clean` exits 0 and leaves the repo in a clean state (no containers running, no cache dirs).
- [ ] No agent-generated code runs on the host at any point during this spec's implementation.

## Depends-On

_(none)_ — This is the foundation spec. It has no dependencies on other specs.

## Status

In progress.
