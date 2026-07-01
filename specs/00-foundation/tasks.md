# Tasks — Spec 00: Foundation

Work through in order. Check off each task only after `make lint && make test` pass (or tests skip cleanly) for that task's code.

---

## 1. Directory Skeleton

- [ ] Create top-level directories: `src/`, `tests/`, `config/`, `scripts/`, `specs/`, `reports/`, `logs/`, `dashboard/`
- [ ] Create subdirectories: `config/docker/`, `tests/unit/`, `tests/unit/test_foundation/`, `tests/integration/`
- [ ] Add `.gitkeep` to empty directories: `reports/`, `logs/`, `dashboard/`
- [ ] Write `.gitignore`:
  - Python standard: `__pycache__/`, `*.pyc`, `*.pyo`, `*.egg-info/`, `dist/`, `build/`, `.venv/`
  - Project-specific: `.env`, `reports/*`, `logs/*`, `!reports/.gitkeep`, `!logs/.gitkeep`
  - Tools: `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`
- [ ] Write `.env.example` with all required env vars:
  ```
  DATABASE_URL=postgresql://postgres:password@localhost:5432/benchmark_db
  POSTGRES_PASSWORD=password
  LITELLM_CONFIG=config/litellm_config.yaml
  MAX_TASK_SECONDS=300
  MAX_ITERATIONS=5
  ```
- [ ] Add `__init__.py` to `src/`, `tests/`, `tests/unit/`, `tests/unit/test_foundation/`, `tests/integration/`
- [ ] Verify: `find . -name "__init__.py" | grep -v ".venv"` shows all expected locations

---

## 2. Python Packaging (`pyproject.toml`)

- [ ] Create `pyproject.toml` with `[build-system]` using `setuptools`
- [ ] Add `[project]` section: name, version (0.1.0), description, `requires-python = ">=3.11"`, authors
- [ ] Add `[project.dependencies]`:
  ```
  langgraph>=0.2.0
  litellm>=1.40.0
  psycopg2-binary>=2.9.9
  streamlit>=1.35.0
  python-dotenv>=1.0.0
  docker>=7.0.0
  ```
- [ ] Add `[project.optional-dependencies]` for `dev`:
  ```
  pytest>=8.0.0
  pytest-cov>=5.0.0
  ruff>=0.4.0
  black>=24.0.0
  mypy>=1.10.0
  ```
- [ ] Add `[tool.ruff]` config: `line-length = 100`, `select = ["E", "F", "I", "UP", "B", "ANN"]`, `ignore = ["ANN101", "ANN102"]`
- [ ] Add `[tool.ruff.lint.per-file-ignores]`: `"tests/**" = ["ANN"]`
- [ ] Add `[tool.black]` config: `line-length = 100`, `target-version = ["py311"]`
- [ ] Add `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `addopts = "-q"`, `markers = ["integration: requires Docker/Postgres"]`
- [ ] Create `.venv/`: `python3.11 -m venv .venv`
- [ ] Activate and install: `.venv/bin/pip install -e ".[dev]"` — exits 0
- [ ] Verify: `.venv/bin/pip check` — no conflicts

---

## 3. Makefile

- [ ] Create `Makefile` with `.PHONY` declarations for all targets
- [ ] Implement `setup` target:
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
- [ ] Implement `lint` target: `ruff check src/ tests/ && black --check src/ tests/`
- [ ] Implement `test` target: `pytest tests/unit/ tests/integration/ -q`
- [ ] Implement `benchmark` target (stub):
  ```makefile
  benchmark:
      @echo "Benchmark not yet implemented. See specs/01+ for implementation."
      @exit 1
  ```
- [ ] Implement `sandbox-run` target:
  ```makefile
  sandbox-run:
      .venv/bin/python scripts/sandbox_exec.py --script $(SCRIPT) $(if $(ARGS),--args "$(ARGS)",)
  ```
- [ ] Implement `dashboard` target: `streamlit run dashboard/app.py --server.port 8501`
- [ ] Implement `db-shell` target: `psql "$(DATABASE_URL)"`
- [ ] Implement `clean` target: stop compose, remove pycache, clean reports/logs
- [ ] Add `check-docker` and `check-python` helper targets that exit with error messages if prerequisites are missing
- [ ] Add `Makefile` variable: `DATABASE_URL ?= $(shell grep DATABASE_URL .env 2>/dev/null | cut -d= -f2-)` with `.env` loading
- [ ] Verify: `make lint` exits 0 on empty `src/__init__.py`
- [ ] Verify: `make test` exits 0 (no tests yet, pytest shows "no tests ran")

---

## 4. Docker Compose + Postgres

- [ ] Create `config/docker/docker-compose.yml`:
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
- [ ] Create `scripts/db_init.sql` with `CREATE TABLE IF NOT EXISTS`:
  - `benchmark_runs (run_id UUID PRIMARY KEY, solver_mode TEXT, task_set TEXT, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, total_tasks INT, resolved_tasks INT, error_tasks INT, total_cost_usd NUMERIC(10,6))`
  - `task_results (id SERIAL PRIMARY KEY, run_id UUID REFERENCES benchmark_runs, task_id TEXT, status TEXT, resolve_status TEXT, cost_usd NUMERIC(10,6), input_tokens INT, output_tokens INT, iteration_count INT, hallucination_count INT, error_message TEXT, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ)`
  - `agent_events (id SERIAL PRIMARY KEY, run_id UUID REFERENCES benchmark_runs, task_id TEXT, agent_name TEXT, turn_index INT, event_type TEXT, input_tokens INT, output_tokens INT, cost_usd NUMERIC(10,6), notes TEXT, created_at TIMESTAMPTZ DEFAULT NOW())`
  - Add indices: `CREATE INDEX IF NOT EXISTS idx_task_results_run_id ON task_results(run_id)` and similar
- [ ] Create `scripts/wait_for_postgres.py` — polls `DATABASE_URL` until Postgres is ready (max 30s)
- [ ] Run: `docker compose -f config/docker/docker-compose.yml up -d`
- [ ] Verify: `docker compose -f config/docker/docker-compose.yml ps` shows `benchmark-db` as `healthy`
- [ ] Run: `psql "postgresql://postgres:password@localhost:5432/benchmark_db" -f scripts/db_init.sql` — exits 0
- [ ] Verify: `make db-shell` opens psql and `\dt` shows 3 tables

---

## 5. Docker Sandbox Image

- [ ] Create `config/docker/Dockerfile`:
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
- [ ] Create `requirements.txt` (subset of deps needed inside the sandbox — NOT all dev deps)
- [ ] Build: `docker build -f config/docker/Dockerfile -t swe-sandbox:latest .` — exits 0
- [ ] Verify: `docker run --rm swe-sandbox:latest -c "print('sandbox ok')"` prints `sandbox ok`
- [ ] Verify: `docker run --rm swe-sandbox:latest -c "import litellm; print(litellm.__version__)"` prints a version

---

## 6. Sandbox Wrapper + Smoke Test

- [ ] Create `scripts/sandbox_exec.py`:
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
- [ ] Create `scripts/hello_sandbox.py`:
  ```python
  #!/usr/bin/env python3
  """Smoke test script for the Docker sandbox. Prints a marker string and exits 0."""
  print("Hello from sandbox")
  ```
- [ ] Verify: `make sandbox-run SCRIPT=scripts/hello_sandbox.py` prints `Hello from sandbox` and exits 0
- [ ] Write `tests/unit/test_foundation/test_sandbox_exec.py`:
  - Import `sandbox_exec` (may need to adjust `sys.path` or make it importable)
  - `test_build_docker_command_basic` — mock subprocess, verify `docker run` args
  - `test_build_docker_command_with_args` — verify extra args are appended
  - `test_script_not_found_raises` — verify `FileNotFoundError` or `SystemExit` when script missing
  - `test_network_none_in_command` — verify `--network none` is present (sandbox rule)
  - `test_readonly_mount_in_command` — verify `:ro` mount flag is present
- [ ] Verify: `make test` exits 0 with these unit tests passing

---

## 7. Claude Code Infrastructure Verification

- [ ] Confirm `.claude/settings.json` is valid JSON: `python -m json.tool .claude/settings.json`
- [ ] Confirm all hook scripts are executable: `ls -la .claude/hooks/` — all three show `-rwxr-xr-x`
- [ ] Test block-host-exec hook manually:
  - Run a safe command through Claude Code Bash to confirm it passes (e.g., `make --version`)
  - Attempt a blocked command to confirm it's rejected (e.g., try `python src/agents/test.py` — hook should block)
- [ ] Confirm all agent files exist: `ls .claude/agents/`
- [ ] Confirm all skill files exist: `ls .claude/skills/*/SKILL.md`
- [ ] Confirm `.mcp.json` is valid JSON: `python -m json.tool .mcp.json`

---

## 8. Integration Tests

- [ ] Create `tests/integration/__init__.py`
- [ ] Create `tests/integration/test_foundation/` directory and `__init__.py`
- [ ] Write `tests/integration/test_foundation/test_postgres.py`:
  - `@pytest.mark.integration`
  - `test_postgres_connection` — connect with psycopg2 using `DATABASE_URL`, run `SELECT 1`
  - `test_tables_exist` — query `information_schema.tables`, verify 3 expected tables exist
  - Both tests use `pytest.importorskip("psycopg2")` and skip if `DATABASE_URL` not set
- [ ] Write `tests/integration/test_foundation/test_sandbox.py`:
  - `@pytest.mark.integration`
  - `test_hello_sandbox` — runs `sandbox_exec.py` with `hello_sandbox.py`, checks stdout
  - Skip if Docker not running (`docker ps` fails)
- [ ] Verify: `make test` runs unit tests and skips integration tests gracefully
- [ ] Verify (optional, if Docker running): `pytest tests/integration/ -v -m integration` exits 0

---

## 9. Final Lint and Format Pass

- [ ] Run `ruff check --fix src/ tests/ scripts/`
- [ ] Run `black src/ tests/ scripts/`
- [ ] Run `make lint` — exits 0
- [ ] Run `make test` — exits 0

---

## 10. Acceptance Checklist

Run each done-when criterion from `spec.md` and verify:

- [ ] `make setup` exits 0 (from a clean state: `make clean` first)
- [ ] `make lint` exits 0
- [ ] `make test` exits 0
- [ ] `docker compose -f config/docker/docker-compose.yml ps` shows `benchmark-db` as `healthy`
- [ ] `make db-shell` → `\dt` → shows `benchmark_runs`, `task_results`, `agent_events`
- [ ] `docker build -f config/docker/Dockerfile -t swe-sandbox:test .` exits 0
- [ ] `make sandbox-run SCRIPT=scripts/hello_sandbox.py` prints `Hello from sandbox`
- [ ] Block-host-exec hook verified working (see task 7)
- [ ] `make clean` exits 0
- [ ] Add `## Status: Complete` to `spec.md`
