# Implementation Plan — Spec 00: Foundation

## Overview

Build the project skeleton bottom-up: directory layout first, then Python packaging, then the Makefile that ties everything together, then Postgres + Docker infrastructure, then the sandbox wrapper, and finally the Claude Code hooks and agents. Each layer is independently testable before the next is added. The key constraint is that nothing in this spec makes LLM calls or executes untrusted code — we're building the harness that will do those things later.

## Key Decisions

1. **Docker Compose for Postgres**: We use Docker Compose (not a system Postgres) so that `make setup` is fully reproducible across developer machines. The compose file is in `config/docker/docker-compose.yml` and `make setup` calls `docker compose up -d`.

2. **Virtual environment with `uv` or `pip`**: Use `pip` with `pyproject.toml` for simplicity (no extra toolchain). `make setup` creates `.venv/` if it doesn't exist, then runs `pip install -e ".[dev]"`. This keeps the toolchain minimal for now; uv can be introduced later.

3. **Sandbox via `docker run` (not compose)**: The sandbox for code execution uses a one-shot `docker run --rm` call (not a long-running container). This is simpler for Spec 00 and matches how SWE-bench evaluation works per-task. `scripts/sandbox_exec.py` wraps this.

4. **Ruff + Black for linting**: Ruff handles all static analysis (replaces flake8, isort, pyupgrade). Black handles formatting. Both are configured in `pyproject.toml`. `make lint` runs both in check mode; the PostToolUse hook runs both in fix mode.

5. **Postgres schema designed for the full system**: Even though no data is inserted in Spec 00, we design the schema for the full benchmark now (3 tables) to avoid schema migrations across specs. The schema is in `scripts/db_init.sql` and `make setup` runs it idempotently (`CREATE TABLE IF NOT EXISTS`).

6. **`make sandbox-run` uses a marker script**: `scripts/hello_sandbox.py` is a trivial script that prints "Hello from sandbox". It exists solely to verify the Docker execution path works end-to-end without requiring any agent code.

## File Structure

Files and directories created in this spec:

```
.
├── pyproject.toml                          # project metadata + deps
├── Makefile                                # all make targets
├── .env.example                            # env var template (DATABASE_URL, etc.)
├── .gitignore                              # Python + project-specific ignores
├── CLAUDE.md                               # already exists (created separately)
├── src/
│   └── __init__.py                         # package root
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # shared pytest fixtures
│   └── unit/
│       ├── __init__.py
│       └── test_foundation/
│           ├── __init__.py
│           └── test_sandbox_exec.py        # tests for sandbox_exec.py
├── config/
│   └── docker/
│       ├── Dockerfile                      # sandbox image
│       └── docker-compose.yml             # Postgres service
├── scripts/
│   ├── db_init.sql                         # schema creation
│   ├── sandbox_exec.py                     # Docker wrapper script
│   └── hello_sandbox.py                   # smoke-test script for sandbox
├── specs/                                  # already exists
├── reports/                                # empty; .gitkeep
├── logs/                                   # empty; .gitkeep
└── dashboard/                              # empty; .gitkeep
```

## Implementation Order

1. **Directory skeleton + .gitignore**: Create all directories with `.gitkeep` files. Set up `.gitignore` (Python standard + `.env`, `reports/`, `logs/`, `.venv/`). This is the commit point for the empty skeleton.

2. **`pyproject.toml`**: Define package metadata, dependencies, and tool configs (ruff, black, pytest, mypy). Pin versions carefully to avoid conflicts. After this, `pip install -e ".[dev]"` must succeed.

3. **`Makefile`**: Write all make targets. At this point, `make lint` and `make test` will work (on empty source). `make benchmark` is a stub. `make setup` will partially work (deps only; Docker targets come next).

4. **Docker Compose + Postgres** (`config/docker/docker-compose.yml` + `scripts/db_init.sql`): Write the compose file and schema. Update `make setup` to call `docker compose up -d` and `psql` to run `db_init.sql`. Verify `make db-shell` works.

5. **Docker sandbox image** (`config/docker/Dockerfile`): Write the Dockerfile. Build and verify it. Update `make setup` to build the image.

6. **`scripts/sandbox_exec.py`** + **`scripts/hello_sandbox.py`**: Write the Docker wrapper and the hello-world test script. Verify `make sandbox-run SCRIPT=scripts/hello_sandbox.py` works. Write unit tests in `tests/unit/test_foundation/test_sandbox_exec.py`.

7. **Claude Code infrastructure** (hooks, agents, skills — all in `.claude/`): These files already exist (created separately as part of the Claude Code setup). Verify the block-host-exec hook works by running a test bash command through Claude Code.

8. **Final verification**: Run the full done-when checklist. Fix any remaining issues.

## Integration Points

- **Makefile → docker compose**: `make setup` calls `docker compose -f config/docker/docker-compose.yml up -d`.
- **Makefile → sandbox_exec.py**: `make sandbox-run` calls `python scripts/sandbox_exec.py --script $(SCRIPT)`.
- **sandbox_exec.py → Docker**: Uses `subprocess.run(["docker", "run", "--rm", ...])`.
- **db_init.sql → Postgres**: Run via `psql $DATABASE_URL -f scripts/db_init.sql` in `make setup`.

## Risk Areas

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Docker not installed on dev machine | Low | Check at top of `make setup`; print helpful error |
| Python version < 3.11 | Low | Check in `pyproject.toml` `requires-python = ">=3.11"` |
| Port 5432 already in use | Medium | Document in README; allow `POSTGRES_PORT` override in `.env` |
| `sb-cli` install fails in Dockerfile | Medium | Pin to a known-good version; test in CI |
| `pip install` conflict between LangGraph + LiteLLM | Medium | Test on clean venv before finalising pins |

## Testing Strategy

- **Unit tests** (`tests/unit/test_foundation/test_sandbox_exec.py`):
  - Mock `subprocess.run` to test `sandbox_exec.py` argument construction without Docker.
  - Test that `--script` and `--args` are passed correctly to `docker run`.
  - Test that the script's exit code is forwarded correctly.

- **Integration tests** (skipped if Docker not running):
  - `test_sandbox_runs_hello_world`: runs `make sandbox-run SCRIPT=scripts/hello_sandbox.py` and checks stdout.
  - `test_postgres_connection`: connects to `benchmark_db` and verifies tables exist.
  - Both tests check for `SKIP_INTEGRATION=1` env var and skip if set.

- **Manual verification**:
  - `make setup && make lint && make test && make sandbox-run SCRIPT=scripts/hello_sandbox.py`
  - Should produce zero errors and print "Hello from sandbox".
