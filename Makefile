.PHONY: setup lint test benchmark sandbox-run dashboard db-shell clean check-docker check-python

PYTHON ?= python3
VENV := .venv
DATABASE_URL ?= $(shell grep -s '^DATABASE_URL=' .env | cut -d= -f2-)
DATABASE_URL := $(if $(DATABASE_URL),$(DATABASE_URL),postgresql://postgres:password@localhost:5432/benchmark_db)
COMPOSE_FILE := config/docker/docker-compose.yml
# docker compose's project directory defaults to the compose file's directory,
# not the repo root, so it won't pick up a root .env unless told to explicitly.
ENV_FILE := $(if $(wildcard .env),--env-file .env,)

check-docker:
	@command -v docker >/dev/null 2>&1 || { echo "Error: Docker is required but not installed. See https://docs.docker.com/get-docker/"; exit 1; }

check-python:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || { echo "Error: Python >=3.11 is required."; exit 1; }

setup: check-docker check-python
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]" -q
	docker compose -f $(COMPOSE_FILE) $(ENV_FILE) up -d
	DATABASE_URL="$(DATABASE_URL)" $(VENV)/bin/python scripts/wait_for_postgres.py
	docker compose -f $(COMPOSE_FILE) $(ENV_FILE) exec -T postgres psql -U postgres -d benchmark_db < scripts/db_init.sql
	docker build -f config/docker/Dockerfile -t swe-sandbox:latest .
	@echo "Setup complete."

lint:
	$(VENV)/bin/ruff check src/ benchmark/ tests/
	$(VENV)/bin/black --check src/ benchmark/ tests/

test:
	$(VENV)/bin/pytest tests/unit/ tests/integration/ -q

TASKS ?= lite-5
SOLVER ?= noop

benchmark:
	DATABASE_URL="$(DATABASE_URL)" TASKS="$(TASKS)" SOLVER="$(SOLVER)" $(VENV)/bin/python -m benchmark.cli

sandbox-run:
ifdef CMD
	$(VENV)/bin/python scripts/sandbox_exec.py --cmd "$(CMD)"
else
	$(VENV)/bin/python scripts/sandbox_exec.py --script $(SCRIPT) $(if $(ARGS),--args "$(ARGS)",)
endif

dashboard:
	$(VENV)/bin/streamlit run dashboard/app.py --server.port 8501

db-shell:
	docker compose -f $(COMPOSE_FILE) $(ENV_FILE) exec postgres psql -U postgres -d benchmark_db

clean:
	docker compose -f $(COMPOSE_FILE) $(ENV_FILE) down -v
	find . -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find reports logs -mindepth 1 -not -name ".gitkeep" -exec rm -rf {} +
	@echo "Clean complete."
