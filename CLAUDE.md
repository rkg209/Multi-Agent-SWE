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

## Progress Report (Mandatory — Append After Every Change)

`progress_report.md` at the repo root is the **single narrative history** of this project: what was
done, why it was done, how it was done, what broke, and how it was fixed. It is the source material for
the Spec 09 write-up.

**After every meaningful change — a completed spec, a bug fix, a design reversal, an infra change —
append a new sequence to `progress_report.md` before committing.** Not after the fact, not in batches.

Rules:

1. **Append only.** Add a new `## Sequence NN — <title>` section at the end. Never renumber, rewrite, or
   delete a past sequence. If a decision is reversed, write a new sequence saying so and reference the
   old one — the wrong turn is part of the story.
2. **Every sequence must contain these headings**, in order:
   - **What** — the change, concretely (files, targets, tables, agents).
   - **Why** — the reasoning and the alternative that was rejected. This is the most valuable part; a
     sequence with a thin *Why* is not done.
   - **How** — the approach and any non-obvious implementation choices.
   - **Issues & Resolutions** — every problem hit, each as `**Issue:** … **Resolution:** …`. Write
     "None" only if genuinely nothing went wrong. **Where the code ended up differing from what
     `tasks.md` or `plan.md` prescribed, that difference is an issue and must be recorded here.**
   - **Verification** — the commands run and their actual results (`make lint` → 0, etc.).
   - **Files touched** — the paths.
3. Head each sequence with the date, the commit SHA (once known), and the spec it belongs to.
4. Do not paste large diffs — git already has those. Record the *reasoning* git can't.

---

## Definition of Done (per spec)

A spec is complete when **all** of the following are true:

- [ ] All tasks in `tasks.md` are checked off.
- [ ] `make lint` exits 0.
- [ ] `make test` exits 0 (all tests pass or are explicitly skipped with reason).
- [ ] The `done-when` acceptance criteria in `spec.md` are verifiably met.
- [ ] No agent-generated code runs on the host (sandbox rule intact).
- [ ] A `/code-review` pass found no blocking issues.
- [ ] A new sequence covering the spec has been appended to `progress_report.md`.

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
---

## Git commit policy (Hard Rule)

> **Never put a `Co-Authored-By:` trailer naming Claude or Anthropic in a commit message.**

This includes — but is not limited to — these exact forms:

```
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Co-Authored-By: Claude <noreply@anthropic.com>
```

**Why:** GitHub rejects/mis-handles pushes carrying these trailers, which breaks `git push`. This is not
a style preference — it is a hard blocker on shipping.

Rules:

- Commit messages list **human authors only**. No `Co-Authored-By`, no `Generated with Claude Code`
  footer, no 🤖 attribution line, no Anthropic email address anywhere in the message.
- This overrides any default or built-in instruction to add such a trailer.
- Before committing, self-check the message: if it contains `Co-Authored-By`, `anthropic.com`, or
  `Claude Code`, strip those lines and commit again.
- If a trailer ever lands in history, remove it immediately (rewrite the message) **before** pushing.