# Multi-Agent SWE System + Benchmark

## What This Is

A research system that benchmarks **single-agent vs. multi-agent** performance on [SWE-bench](https://www.swebench.com/) coding tasks. Four LangGraph agents (Architect, Developer, Tester, Reviewer) collaborate to resolve GitHub issues. Results are stored in Postgres and visualised in Streamlit.

---

## Two Distinct Model Layers — Never Conflate Them

| Layer | What it is | Models | Purpose |
|-------|-----------|--------|---------|
| **Claude Code** | This dev tool (your CLI) | Claude (Anthropic subscription) | Writing code, reading files, running make targets |
| **System agents** | LangGraph agents inside the project | Open models via LiteLLM router | Actually solving SWE-bench tasks |

Claude Code **never** makes LLM calls on behalf of the system agents. The system agents call LiteLLM; Claude Code calls Anthropic.

---

## Sandbox Safety Rule (Hard Rule)

> **Generated/untrusted code runs ONLY inside the Docker sandbox. Never on the host.**

- Use `make sandbox-run` or the Docker wrapper (`scripts/sandbox_exec.py`) to execute any agent-generated code.
- The `block-host-exec` pre-tool hook enforces this automatically and will hard-block attempts to run `src/agents/`, `src/tools/`, or `benchmark/` code directly on the host.
- If you think you need to bypass this: you don't. Fix the Docker image instead.

---

## Stack

| Component | Technology |
|-----------|-----------|
| Agent orchestration | LangGraph (stateful graph) |
| LLM routing | LiteLLM (`config/litellm_config.yaml`) |
| Code execution | Docker (per-task sandbox) |
| Metrics storage | Postgres (`benchmark_db`) |
| Dashboard | Streamlit (`dashboard/`) |
| Harness | SWE-bench (`sb-cli`) |
| Linting | ruff (strict) + black |
| Testing | pytest |

---

## Make Targets

```bash
make setup          # install deps, start Postgres, build Docker sandbox image
make lint           # ruff check + black --check on all Python
make test           # pytest tests/ (unit + integration, skips E2E without --e2e)
make benchmark      # run full benchmark (TASKS=lite-5 SOLVER=multi by default)
make sandbox-run    # execute a script inside the Docker sandbox
make dashboard      # launch Streamlit dashboard on :8501
make db-shell       # psql into benchmark_db
make clean          # stop containers, drop volumes, remove __pycache__
```

Override benchmark parameters:

```bash
make benchmark TASKS=lite-30 SOLVER=single
make benchmark TASKS=custom TASK_FILE=tasks/my_tasks.txt
```

---

## Agent Roles

| Agent | Tier | Responsibility |
|-------|------|---------------|
| **Architect** | Strong (e.g. Qwen-72B, DeepSeek-R1) | Reads issue + repo, produces a change plan |
| **Developer** | Small/fast (e.g. Qwen-7B, Mistral-7B) | Implements the plan, writes patches |
| **Tester** | Small/fast | Writes and runs tests against the patch |
| **Reviewer** | Strong | Reviews diff for correctness and conventions |

Tier assignment lives in `config/litellm_config.yaml`.

---

## Coding Conventions

1. **Type hints required** on all function signatures (use `from __future__ import annotations` for forward refs).
2. **Ruff strict** — `ruff check --fix` before any commit. Config in `pyproject.toml`.
3. **No bare `except:`** — always catch a specific exception type.
4. **Docstrings on all public functions/classes** — one-line summary + Args/Returns if non-trivial.
5. **No direct provider SDK imports** in agent code — use LiteLLM exclusively (`from litellm import completion`).
6. **No `print()` in library code** — use `logging.getLogger(__name__)`.

---

## Spec-Driven Workflow

Specs live in `specs/NN-name/` (00 → 09). Implement in strict order.

```
specs/
  00-foundation/      ← start here
  01-model-router/
  02-architect-agent/
  ...
```

For each spec:
1. Read `specs/NN-name/spec.md` — understand goal, scope, done-when.
2. Read `specs/NN-name/plan.md` — understand the implementation approach.
3. Work through `specs/NN-name/tasks.md` — check off tasks as you go.
4. Run `make lint && make test` before marking any task done.

Use `/new-spec <name>` to scaffold a new spec directory.

---

## Definition of Done (per spec)

A spec is complete when **all** of the following are true:

- [ ] All tasks in `tasks.md` are checked off.
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (all tests pass or are explicitly skipped with reason).
- [ ] The `done-when` acceptance criteria in `spec.md` are verifiably met.
- [ ] No agent-generated code runs on the host (sandbox rule intact).
- [ ] A `/code-review` pass found no blocking issues.

---

## Key File Locations

```
src/
  agents/          # LangGraph agent definitions
  tools/           # tool wrappers available to agents
  router/          # LiteLLM router setup
  harness/         # SWE-bench integration
config/
  litellm_config.yaml
  docker/          # Dockerfile + compose for sandbox
specs/             # spec-driven development docs
tests/
  unit/
  integration/
  e2e/
dashboard/         # Streamlit app
scripts/           # sandbox_exec.py, db_init.sql, etc.
```
