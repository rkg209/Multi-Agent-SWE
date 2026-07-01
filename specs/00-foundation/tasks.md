# Tasks — Spec 00: Foundation

Work through in order. Check off each task only after `make lint && make test` pass (or tests skip cleanly) for that task's code.

---

## 1. Directory Skeleton

- [x] `git init` the repository (not yet a git repo) — required before `.gitignore` and any git-dependent hooks/tooling are meaningful
- [x] Create top-level directories: `src/`, `tests/`, `config/`, `scripts/`, `specs/`, `reports/`, `logs/`, `dashboard/`
- [x] Create subdirectories: `config/docker/`, `tests/unit/`, `tests/unit/test_foundation/`, `tests/integration/`
- [x] Add `.gitkeep` to empty directories: `reports/`, `logs/`, `dashboard/`
- [x] Write `.gitignore`:
  - Python standard: `__pycache__/`, `*.pyc`, `*.pyo`, `*.egg-info/`, `dist/`, `build/`, `.venv/`
  - Project-specific: `.env`, `reports/*`, `logs/*`, `!reports/.gitkeep`, `!logs/.gitkeep`
  - Tools: `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`
- [x] Write `.env.example` with all required env vars:
  ```
  DATABASE_URL=postgresql://postgres:password@localhost:5432/benchmark_db
  POSTGRES_PASSWORD=password
  LITELLM_CONFIG=config/litellm_config.yaml
  MAX_TASK_SECONDS=300
  MAX_ITERATIONS=5
  ```
- [x] Add `__init__.py` to `src/`, `tests/`, `tests/unit/`, `tests/unit/test_foundation/`, `tests/integration/`
- [x] Verify: `find . -name "__init__.py" | grep -v ".venv"` shows all expected locations

---

## 2. Python Packaging (`pyproject.toml`)

- [x] Create `pyproject.toml` with `[build-system]` using `setuptools`
- [x] Add `[project]` section: name, version (0.1.0), description, `requires-python = ">=3.11"`, authors
- [x] Add `[project.dependencies]`:
  ```
  langgraph>=0.2.0
  litellm>=1.40.0
  psycopg2-binary>=2.9.9
  streamlit>=1.35.0
  python-dotenv>=1.0.0
  docker>=7.0.0
  ```
- [x] Add `[project.optional-dependencies]` for `dev`:
  ```
  pytest>=8.0.0
  pytest-cov>=5.0.0
  ruff>=0.4.0
  black>=24.0.0
  mypy>=1.10.0
  ```
- [x] Add `[tool.ruff]` config: `line-length = 100`, `select = ["E", "F", "I", "UP", "B", "ANN"]`, `ignore = ["ANN101", "ANN102"]`
- [x] Add `[tool.ruff.lint.per-file-ignores]`: `"tests/**" = ["ANN"]`
- [x] Add `[tool.black]` config: `line-length = 100`, `target-version = ["py311"]`
- [x] Add `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `addopts = "-q"`, `markers = ["integration: requires Docker/Postgres"]`
- [x] Create `.venv/`: `python3.11 -m venv .venv`
- [x] Activate and install: `.venv/bin/pip install -e ".[dev]"` — exits 0
- [x] Verify: `.venv/bin/pip check` — no conflicts

---

## 3. Makefile

- [x] Create `Makefile` with `.PHONY` declarations for all targets
- [x] Implement `setup` target:
  ```makefile
  setup: check-docker check-python
      python -m venv .venv
      .venv/bin/pip install -e ".[dev]" -q
      docker compose -f config/docker/docker-compose.yml up -d
      sleep 3  # wait for Postgres to be ready
      .venv/bin/python scripts/wait_for_postgres.py
      psql "$(DATABASE_URL)" -f scripts/db_init.sql
      docker build -f config/docker/Dockerfile -t swe-sandbox:latest . -q
      @echo "Setup complete."
  ```
- [x] Implement `lint` target: `ruff check src/ tests/ && black --check src/ tests/`
- [x] Implement `test` target: `pytest tests/unit/ tests/integration/ -q`
- [x] Implement `benchmark` target (stub):
  ```makefile
  benchmark:
      @echo "Benchmark not yet implemented. See specs/01+ for implementation."
      @exit 1
  ```
- [x] Implement `sandbox-run` target:
  ```makefile
  sandbox-run:
      .venv/bin/python scripts/sandbox_exec.py --script $(SCRIPT) $(if $(ARGS),--args "$(ARGS)",)
  ```
- [x] Implement `dashboard` target: `streamlit run dashboard/app.py --server.port 8501`
- [x] Implement `db-shell` target: `psql "$(DATABASE_URL)"`
- [x] Implement `clean` target: stop compose, remove pycache, clean reports/logs
- [x] Add `check-docker` and `check-python` helper targets that exit with error messages if prerequisites are missing
- [x] Add `Makefile` variable: `DATABASE_URL ?= $(shell grep DATABASE_URL .env 2>/dev/null | cut -d= -f2-)` with `.env` loading
- [x] Verify: `make lint` exits 0 on empty `src/__init__.py`
- [x] Verify: `make test` exits 0 (no tests yet, pytest shows "no tests ran")

---

## 4. Docker Compose + Postgres

- [x] Create `config/docker/docker-compose.yml`:
  ```yaml
  services:
    postgres:
      image: postgres:15-alpine
      container_name: benchmark-db
      environment:
        POSTGRES_DB: benchmark_db
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-password}
      ports:
        - "${POSTGRES_PORT:-5432}:5432"
      volumes:
        - benchmark-pgdata:/var/lib/postgresql/data
      healthcheck:
        test: ["CMD-SHELL", "pg_isready -U postgres"]
        interval: 5s
        timeout: 3s
        retries: 5
  volumes:
    benchmark-pgdata:
  ```
- [x] Create `scripts/db_init.sql`, porting the schema from `planning/04-database-schema.sql` (the implementation-ready full-system design) with `CREATE TABLE IF NOT EXISTS` guards:
  - `CREATE SCHEMA IF NOT EXISTS benchmark` + `CREATE EXTENSION IF NOT EXISTS pgcrypto`
  - `llm_cache (cache_key CHAR(64) PRIMARY KEY, model TEXT, content TEXT, tool_calls JSONB, usage JSONB, cost_usd NUMERIC(12,8), created_at TIMESTAMPTZ)` — permanent LLM response cache
  - `trace_events (event_id UUID PRIMARY KEY, run_id UUID, task_id TEXT, agent_role TEXT, turn_index INT, event_type TEXT, model TEXT, prompt_tokens INT, completion_tokens INT, cost_usd NUMERIC(12,8), cache_hit BOOLEAN, payload JSONB, created_at TIMESTAMPTZ)` — append-only event log
  - `run_records (run_id UUID, task_id TEXT, solver_config JSONB, outcome TEXT, total_cost_usd NUMERIC(12,8), total_tokens INT, iteration_count INT, hallucination_score NUMERIC(5,4), duration_seconds NUMERIC(10,3), cap_hit BOOLEAN, budget_exceeded BOOLEAN, patch_size_bytes INT, created_at TIMESTAMPTZ, PRIMARY KEY (run_id, task_id))` — one immutable row per (run, task)
  - Views: `run_summary`, `task_cost_breakdown`
  - Add indices as specified in `planning/04-database-schema.sql` (e.g. `trace_events_run_id_idx`, `run_records_run_id_idx`, and others)
- [x] Create `scripts/wait_for_postgres.py` — polls `DATABASE_URL` until Postgres is ready (max 30s)
- [x] Run: `docker compose -f config/docker/docker-compose.yml up -d`
- [x] Verify: `docker compose -f config/docker/docker-compose.yml ps` shows `benchmark-db` as `healthy`
- [x] Run: `psql "postgresql://postgres:password@localhost:5432/benchmark_db" -f scripts/db_init.sql` — exits 0
- [x] Verify: `make db-shell` opens psql and (with `search_path` including `benchmark`) `\dt` shows 3 tables (`llm_cache`, `trace_events`, `run_records`) and `\dv` shows 2 views (`run_summary`, `task_cost_breakdown`)

---

## 5. Docker Sandbox Image

- [x] Create `config/docker/Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim

  WORKDIR /workspace

  # Install system deps
  RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl build-essential \
      && rm -rf /var/lib/apt/lists/*

  # Install Python deps (copy requirements separately for layer caching)
  COPY requirements.txt /tmp/requirements.txt
  RUN pip install --no-cache-dir -r /tmp/requirements.txt

  # Install sb-cli (SWE-bench CLI)
  RUN pip install --no-cache-dir swebench

  # Default: do nothing (sandbox_exec.py passes the script as CMD)
  ENTRYPOINT ["python"]
  ```
- [x] Create `requirements.txt` (subset of deps needed inside the sandbox — NOT all dev deps)
- [x] Build: `docker build -f config/docker/Dockerfile -t swe-sandbox:latest .` — exits 0
- [x] Verify: `docker run --rm swe-sandbox:latest -c "print('sandbox ok')"` prints `sandbox ok`
- [x] Verify: `docker run --rm swe-sandbox:latest -c "import litellm; print(litellm.__version__)"` prints a version

---

## 6. Sandbox Wrapper + Smoke Test

- [x] Create `scripts/sandbox_exec.py`:
  - `#!/usr/bin/env python3` shebang + module docstring
  - Argument parser: `--script` (required, path to script), `--args` (optional, string of extra args)
  - Validate that `--script` exists on the host
  - Build `docker run` command:
    ```python
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",          # no network access from sandbox
        "-v", f"{project_root}:/workspace:ro",  # read-only project mount
        "-w", "/workspace",
        "swe-sandbox:latest",
        f"/workspace/{script_rel_path}",
        *shlex.split(args or ""),
    ]
    ```
  - Run with `subprocess.run(cmd)`, return its exit code
  - Type hints on all functions, docstrings, no bare excepts
- [x] Create `scripts/hello_sandbox.py`:
  ```python
  #!/usr/bin/env python3
  """Smoke test script for the Docker sandbox. Prints a marker string and exits 0."""
  print("Hello from sandbox")
  ```
- [x] Verify: `make sandbox-run SCRIPT=scripts/hello_sandbox.py` prints `Hello from sandbox` and exits 0
- [x] Write `tests/unit/test_foundation/test_sandbox_exec.py`:
  - Import `sandbox_exec` (may need to adjust `sys.path` or make it importable)
  - `test_build_docker_command_basic` — mock subprocess, verify `docker run` args
  - `test_build_docker_command_with_args` — verify extra args are appended
  - `test_script_not_found_raises` — verify `FileNotFoundError` or `SystemExit` when script missing
  - `test_network_none_in_command` — verify `--network none` is present (sandbox rule)
  - `test_readonly_mount_in_command` — verify `:ro` mount flag is present
- [x] Verify: `make test` exits 0 with these unit tests passing

---

## 7. Claude Code Infrastructure Verification

- [x] Confirm `.claude/settings.json` is valid JSON: `python -m json.tool .claude/settings.json`
- [x] Confirm all hook scripts are executable: `ls -la .claude/hooks/` — all three show `-rwxr-xr-x`
- [x] Test block-host-exec hook manually:
  - Run a safe command through Claude Code Bash to confirm it passes (e.g., `make --version`)
  - Attempt a blocked command to confirm it's rejected (e.g., try `python src/agents/test.py` — hook should block)
- [x] Confirm all agent files exist: `ls .claude/agents/`
- [x] Confirm all skill files exist: `ls .claude/skills/*/SKILL.md`
- [x] Confirm `.mcp.json` is valid JSON: `python -m json.tool .mcp.json`

---

## 8. Integration Tests

- [x] Create `tests/integration/__init__.py`
- [x] Create `tests/integration/test_foundation/` directory and `__init__.py`
- [x] Write `tests/integration/test_foundation/test_postgres.py`:
  - `@pytest.mark.integration`
  - `test_postgres_connection` — connect with psycopg2 using `DATABASE_URL`, run `SELECT 1`
  - `test_tables_exist` — query `information_schema.tables`, verify 3 expected tables exist
  - Both tests use `pytest.importorskip("psycopg2")` and skip if `DATABASE_URL` not set
- [x] Write `tests/integration/test_foundation/test_sandbox.py`:
  - `@pytest.mark.integration`
  - `test_hello_sandbox` — runs `sandbox_exec.py` with `hello_sandbox.py`, checks stdout
  - Skip if Docker not running (`docker ps` fails)
- [x] Verify: `make test` runs unit tests and skips integration tests gracefully
- [x] Verify (optional, if Docker running): `pytest tests/integration/ -v -m integration` exits 0

---

## 9. Final Lint and Format Pass

- [x] Run `ruff check --fix src/ tests/ scripts/`
- [x] Run `black src/ tests/ scripts/`
- [x] Run `make lint` — exits 0
- [x] Run `make test` — exits 0

---

## 10. Acceptance Checklist

Run each done-when criterion from `spec.md` and verify:

- [x] `make setup` exits 0 (from a clean state: `make clean` first)
- [x] `make lint` exits 0
- [x] `make test` exits 0
- [x] `docker compose -f config/docker/docker-compose.yml ps` shows `benchmark-db` as `healthy`
- [x] `make db-shell` → `\dt` → shows `llm_cache`, `trace_events`, `run_records`; `\dv` → shows `run_summary`, `task_cost_breakdown`
- [x] `docker build -f config/docker/Dockerfile -t swe-sandbox:test .` exits 0
- [x] `make sandbox-run SCRIPT=scripts/hello_sandbox.py` prints `Hello from sandbox`
- [x] Block-host-exec hook verified working (see task 7)
- [x] `make clean` exits 0
- [x] Add `## Status: Complete` to `spec.md`
