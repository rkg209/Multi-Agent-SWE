# requirements.md

## 1. Business Goals

**BG-1.** Produce a reproducible, measurement-first benchmark that quantifies whether a multi-agent coding team outperforms a single agent on software-engineering tasks, expressed as a success-rate delta and a cost multiple (tokens/$ per solved task).

**BG-2.** Demonstrate senior-level competency in agentic systems, LLM evaluation, reproducible benchmarking, and AI system design to applied-AI/ML interviewers.

**BG-3.** Deliver a public, clonable repository where `make benchmark` reproduces the headline single-vs-multi comparison from scratch, serving as a credible portfolio artifact.

**BG-4.** Publish a short writeup whose opening sentence states the measured answer to "does multi-agent coding pay for itself?", constituting the primary résumé bullet.

**BG-5.** Operate entirely on open/free models (no Anthropic API spend) to keep marginal inference cost at or near zero during development and benchmarking.

---

## 2. Stakeholders

| ID | Stakeholder | Interest |
|----|-------------|----------|
| SH-1 | Project author (solo developer) | Builds and owns the system; primary user of the dev environment and benchmark harness. |
| SH-2 | Applied-AI/ML interviewers | Evaluate the portfolio artifact for depth in agent design, evaluation methodology, and measurement rigor. |
| SH-3 | Researchers / practitioners choosing or tuning coding agents | Consume the benchmark results and methodology as evidence for agent-selection decisions. |
| SH-4 | Open-source community | May fork, reproduce, or extend the benchmark; require reproducibility and clear documentation. |

---

## 3. Users / Personas

**U-1 — Solo Developer (SH-1).** Runs the full development loop: writes specs, implements code, triggers benchmark runs, inspects traces, and iterates. Uses Claude Code as the development tool. Needs fast feedback (lint, tests, trace queries) and strong guardrails against accidental host execution of generated code.

**U-2 — Benchmark Reproducer (SH-3, SH-4).** Clones the public repo on a clean machine, runs `make benchmark`, and expects the same headline numbers (within stochastic tolerance). Has no knowledge of the internal dev environment. Needs clear setup instructions and a deterministic scoring path.

**U-3 — Results Consumer / Interviewer (SH-2, SH-3).** Reads the README, views the dashboard or results table, and watches the demo video. Does not run the code. Needs the headline metric table, architecture diagram, and writeup to be immediately legible without code context.

---

## 4. Functional Requirements

### 4.1 Foundation & Repository

**FR-1.** The repository SHALL contain a `Makefile` exposing at minimum the targets: `setup`, `lint`, `test`, `benchmark`, and `sandbox-run`.

**FR-2.** `make setup` SHALL install all dependencies and initialise the Postgres database schema in a single, idempotent command.

**FR-3.** `make lint` SHALL run `ruff` and `black` across all Python source files and exit non-zero on any violation.

**FR-4.** `make test` SHALL execute the fast unit-test subset and exit non-zero on any failure.

**FR-5.** The repository SHALL include a `CLAUDE.md` file at the root that documents: project purpose, the two-model-layer distinction, the sandbox safety rule, the tech stack, all `make` commands, coding conventions, the spec-driven workflow, and the per-spec definition of done.

**FR-6.** The repository SHALL include a `.mcp.json` (project-scoped) configuring the GitHub MCP server and the Postgres MCP server for use by Claude Code during development.

**FR-7.** The repository SHALL include `.claude/settings.json` defining the hooks specified in FR-47 through FR-50.

**FR-8.** The repository SHALL include a `specs/` directory; each spec SHALL occupy its own subdirectory named `NN-name/` and SHALL contain `spec.md`, `plan.md`, and `tasks.md`.

---

### 4.2 Model Router

**FR-9.** The system SHALL provide a single model-router abstraction (implemented via LiteLLM) through which every agent LLM call is made; no agent or application code SHALL import a provider SDK directly.

**FR-10.** The router SHALL support at minimum two provider back-ends simultaneously (e.g., OpenRouter and local Ollama), selectable via configuration without code changes.

**FR-11.** The router SHALL implement a two-tier model configuration: a **strong tier** (assigned to Architect and Reviewer agents) and a **small/fast tier** (assigned to Developer and Tester agents), with tier assignments defined in a single configuration file.

**FR-12.** The router SHALL record, per LLM call: provider, model name, prompt tokens, completion tokens, and computed cost in USD, writing each record to Postgres before returning the response to the caller.

**FR-13.** The router SHALL support local Ollama endpoints as a zero-cost provider option, configurable by setting an environment variable or config entry.

---

### 4.3 Tool Layer (System MCP Servers)

**FR-14.** The system SHALL expose a **filesystem MCP server** (application code, distinct from any Claude Code dev MCP) that provides agents with tools to: read a file, write a file, list directory contents, and check whether a path exists, all scoped to the task's repository snapshot.

**FR-15.** The system SHALL expose a **run-code MCP server** that executes arbitrary shell commands exclusively inside an isolated Docker container; it SHALL reject any execution request that targets the host filesystem or process namespace.

**FR-16.** The system SHALL expose a **git MCP server** that provides agents with tools to: read the current diff, stage files, and create a commit, scoped to the sandboxed repository clone.

**FR-17.** All three MCP servers (FR-14 through FR-16) SHALL be implemented as Python application code within this repository and SHALL be invocable by LangGraph agent nodes at runtime.

**FR-18.** The Docker sandbox used by the run-code MCP server SHALL be a separate, isolated container per task run; it SHALL have no network access to the host and SHALL mount only the task's repository snapshot directory.

**FR-19.** `make sandbox-run CMD="..."` SHALL execute the given command inside the Docker sandbox and return its stdout/stderr/exit-code to the caller, demonstrating the sandbox wrapper in isolation.

---

### 4.4 Benchmark Harness

**FR-20.** The benchmark harness SHALL load tasks from two sources: (a) a fixed subset of SWE-bench Lite/Verified (30–50 tasks, IDs locked in a config file) and (b) 3–5 hand-authored custom tickets stored in the repository.

**FR-21.** The harness SHALL use the official SWE-bench harness and `sb-cli` for environment setup and hidden-test scoring of SWE-bench tasks; the project SHALL NOT reimplement SWE-bench environment provisioning.

**FR-22.** The harness SHALL implement its own scorer for custom tickets: given a generated patch and a set of hidden test files, it SHALL apply the patch in the sandbox, run the tests, and return PASS or FAIL deterministically.

**FR-23.** `make benchmark TASKS=<subset-id>` SHALL: load the named task subset, invoke the configured solver (single-agent or multi-agent), record all results to Postgres, and print a summary table to stdout.

**FR-24.** The harness SHALL write one **run record** to Postgres per task execution containing at minimum: task ID, solver configuration, PASS/FAIL outcome, total tokens, total cost USD, end-to-end latency seconds, hallucination flag, and iteration count.

**FR-25.** The harness SHALL support a **no-op solver** mode (for harness validation) that returns an empty patch; `make benchmark TASKS=lite-5` with the no-op solver SHALL complete without error and write FAIL records to Postgres.

---

### 4.5 Single-Agent Baseline

**FR-26.** The system SHALL implement a **single-agent solver**: given a task (issue text + repo snapshot), the agent SHALL produce a plan, write code changes via the tool layer (sandbox only), run the task's tests, and return a patch.

**FR-27.** The single-agent solver SHALL resolve at least one task end-to-end (PASS recorded in Postgres with real cost and latency) before multi-agent work begins.

**FR-28.** The single-agent solver SHALL be implemented as a degenerate case of the multi-agent LangGraph graph (a graph with one active node), not as a separate code path, so that both configurations share instrumentation.

---

### 4.6 Instrumentation & Metrics

**FR-29.** Every agent turn SHALL be recorded as a **trace event** in Postgres containing: run ID, task ID, agent role, turn index, model used, prompt tokens, completion tokens, cost USD, wall-clock duration, and any tool calls made.

**FR-30.** The system SHALL compute and store **hallucination flags** per run: a run is flagged as hallucinated if any agent references a file path or symbol name that does not exist in the task's repository snapshot, verified by static check against the repo's file tree and symbol table.

**FR-31.** The system SHALL compute and store **iteration count** per run: the number of Developer↔Tester feedback loop cycles completed before the run terminated.

**FR-32.** The system SHALL compute **p50 and p99 end-to-end latency** across all runs in a benchmark execution and store these aggregates in Postgres alongside the per-run records.

**FR-33.** A single SQL query (or equivalent ORM call) against the Postgres schema SHALL be sufficient to reproduce the full headline metric table (success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations) for any named solver configuration.

---

### 4.7 Multi-Agent System

**FR-34.** The system SHALL implement a **multi-agent LangGraph graph** with four named nodes: **Architect**, **Developer**, **Tester**, and **Reviewer**, executing in that default order.

**FR-35.** The **Architect** node SHALL receive the task issue text and repository snapshot and SHALL output: a list of files to modify, a high-level implementation approach, and any constraints for the Developer.

**FR-36.** The **Developer** node SHALL receive the Architect's plan and SHALL produce code changes by invoking the filesystem and run-code MCP tools (sandbox only); it SHALL write changes to the sandboxed repository clone.

**FR-37.** The **Tester** node SHALL run the task's test suite inside the sandbox and SHALL return a structured result: PASS or FAIL with failure details. On FAIL, the graph SHALL route back to the Developer node.

**FR-38.** The **Reviewer** node SHALL receive the final passing patch and SHALL evaluate it for code quality and security issues, returning either APPROVED or a list of issues. On issues, the graph SHALL route back to the Developer node.

**FR-39.** The Developer↔Tester feedback loop SHALL be capped at a configurable maximum number of iterations (default: 3); on cap, the run SHALL terminate with the best available patch and a `cap_hit=true` flag in the run record.

**FR-40.** The Developer↔Reviewer feedback loop SHALL be capped at a configurable maximum number of iterations (default: 2); on cap, the run SHALL terminate with the current patch and a `cap_hit=true` flag.

**FR-41.** The LangGraph graph SHALL use LangGraph's built-in checkpointing mechanism so that a run interrupted mid-graph can be resumed from the last completed node without re-executing prior nodes.

**FR-42.** Each agent node SHALL use the model tier assigned to its role as defined in FR-11 (Architect and Reviewer → strong tier; Developer and Tester → small/fast tier).

---

### 4.8 Guardrails & Cost Control

**FR-43.** The system SHALL enforce a **per-task token budget cap** (configurable); when a run's cumulative token count reaches the cap, the run SHALL halt immediately, record `budget_exceeded=true`, and return the best available patch.

**FR-44.** The system SHALL implement a **response cache**: identical (model, prompt) pairs SHALL return the cached response without a new LLM call; cache hits SHALL be recorded in the trace with `cache_hit=true` and zero cost.

**FR-45.** Before any tool-layer execution (file write or code run), the system SHALL perform a **safety pre-check** that verifies the action is within the allowed action list; disallowed actions SHALL be rejected with a structured error returned to the agent, not raised as an exception.

**FR-46.** The allowed action list (FR-45) SHALL be defined in a single configuration file and SHALL be checked at the tool-layer boundary, not inside individual agent prompts.

---

### 4.9 Claude Code Development Environment Hooks

**FR-47.** A `PreToolUse` hook on `Bash` SHALL execute `.claude/hooks/block-host-exec.sh`; this script SHALL exit with code 2 (blocking the tool call) if the command would execute generated or untrusted code outside the Docker sandbox wrapper, or if the command matches destructive patterns (e.g., `rm -rf`).

**FR-48.** A `PostToolUse` hook on `Write` and `Edit` tool calls SHALL execute `.claude/hooks/format-python.sh`, which SHALL run `ruff` and `black` on any Python file touched by the tool call.

**FR-49.** A `PostToolUse` hook on `Write` and `Edit` tool calls targeting files under `src/` SHALL execute `.claude/hooks/fast-tests.sh`, which SHALL run the fast unit-test subset and print any failures to stderr.

**FR-50.** Hook scripts SHALL be stored under `.claude/hooks/`, SHALL be executable, and SHALL be committed to the repository.

---

### 4.10 Claude Code Skills & Sub-Agents

**FR-51.** The repository SHALL include the following Claude Code skills under `.claude/skills/`, each invocable as a slash command:
- `/new-spec` — scaffolds `specs/NN-name/{spec.md,plan.md,tasks.md}` from a template.
- `/run-bench` — runs the harness on a named task subset and writes results to Postgres; executes in a forked subagent context.
- `/score-patch` — runs the deterministic scorer on a single patch against its hidden tests.
- `/trace` — retrieves one run's trace from Postgres and summarises agent turns, tokens, and failure point.
- `/eval-conventions` — reference skill defining: what counts as success, hallucination, how cost is computed, and how iterations are counted; loaded whenever metric reasoning is required.

**FR-52.** The repository SHALL include the following Claude Code sub-agents under `.claude/agents/`, each restricted to read-only tools (no `Edit`/`Write`):
- `spec-writer` — converts a feature idea into a well-formed `spec.md`.
- `planner` — converts a `spec.md` into `plan.md` and a granular `tasks.md`.
- `explorer` — scans the repository or fetches library documentation and returns a distilled summary.
- `code-reviewer` — reviews a diff against `CLAUDE.md` conventions and security rules.
- `test-runner` — executes `make test` and `/score-patch` and reports failures.
- `harness-debugger` — dedicated to diagnosing SWE-bench environment failures (missing dependencies, image build errors).

---

### 4.11 Comparison Run & Dashboard

**FR-53.** `make benchmark TASKS=<subset-id>` SHALL accept a `SOLVER=single|multi` argument (or equivalent config flag) to select which solver configuration to run; running both in sequence SHALL produce directly comparable Postgres records.

**FR-54.** The system SHALL provide a **Streamlit dashboard** that reads from Postgres and renders at minimum: the headline comparison table (success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations — single vs multi-agent), and at least one plot (e.g., success rate vs cost per solved task).

**FR-55.** The dashboard SHALL be launchable with a single command (e.g., `make dashboard` or `streamlit run dashboard/app.py`) and SHALL require no manual data export step.

---

### 4.12 Reproducibility, Documentation & Deliverables

**FR-56.** The repository SHALL be public on GitHub and SHALL include a `README.md` whose first visible section presents the headline single-vs-multi metric table with real numbers.

**FR-57.** The `README.md` SHALL include an architecture diagram (image or ASCII) matching the data-flow described in A.6.

**FR-58.** `make benchmark` run on a clean clone (after `make setup`) SHALL reproduce the headline results within the stochastic tolerance documented in the README (e.g., ±2 percentage points due to model non-determinism at temperature > 0).

**FR-59.** The repository SHALL include a short writeup (Markdown or linked blog post) whose opening sentence states the measured answer to "does multi-agent coding pay for itself?" and which reports: the success-rate delta, the cost multiple, and a qualitative analysis of where multi-agent coordination helped and where it did not.

**FR-60.** A demo video SHALL be produced showing the system resolving a task end-to-end; the video SHALL be linked from the README.

**FR-61.** GitHub Actions SHALL include a CI workflow that runs `make lint && make test` on every push to the main branch and reports pass/fail status.

---

### 4.13 Stretch Functional Requirements

**FR-S1.** *(Stretch)* The system SHALL support a **parallel specialist reviewer** configuration in which independent Security, Performance, and Style reviewer agents run concurrently after the Tester passes; the benchmark SHALL record results for this configuration separately to isolate parallel-review gains.

**FR-S2.** *(Stretch)* The benchmark harness SHALL support a **multi-model sweep** mode that re-runs the fixed task subset across 2–3 distinct open models and produces a cost-per-solved-task comparison plot per model.

**FR-S3.** *(Stretch)* The system SHALL support a **real GitHub PR mode** (demo only, outside scored runs) in which the best-multi solver opens a pull request on a designated throwaway repository using the GitHub MCP server.

---

## 5. Non-Functional Requirements

### 5.1 Safety & Security

**NFR-1.** Generated or untrusted code SHALL never execute on the host machine under any code path, configuration, or error condition. This constraint is enforced at three independent layers: (a) the run-code MCP server rejects non-sandbox execution (FR-15), (b) the `block-host-exec.sh` hook blocks unsafe Bash calls during development (FR-47), and (c) the Docker sandbox has no host network access (FR-18).

**NFR-2.** The Docker sandbox container SHALL run with a non-root user, a read-only root filesystem (except the mounted task directory), and no capability escalation (`--cap-drop ALL`).

**NFR-3.** API keys and provider credentials SHALL be stored exclusively in environment variables or a `.env` file that is listed in `.gitignore`; no credential SHALL appear in committed code or configuration files.

**NFR-4.** The action allow-list (FR-46) SHALL be the single authoritative gate for all agent-initiated tool calls; bypassing it via direct function calls SHALL be treated as a defect.

### 5.2 Correctness & Determinism

**NFR-5.** The benchmark scorer SHALL be deterministic: given the same patch and the same hidden tests, it SHALL always return the same PASS/FAIL result.

**NFR-6.** All benchmark run records written to Postgres SHALL be immutable after creation; re-runs SHALL create new records rather than overwriting existing ones, preserving full experimental history.

**NFR-7.** The fixed SWE-bench task subset (task IDs) SHALL be committed to the repository in a versioned config file; the subset SHALL not change between runs unless the config file is explicitly updated with a commit.

### 5.3 Observability & Traceability

**NFR-8.** Every LLM call SHALL produce a trace record in Postgres (FR-29) before the response is returned to the caller; there SHALL be no "silent" LLM calls that are not recorded.

**NFR-9.** Every benchmark run SHALL be assigned a unique `run_id` (UUID) that links all trace events, tool calls, and the final run record for that task execution.

**NFR-10.** The Postgres schema SHALL include indexes on `run_id`, `task_id`, and `solver_config` to support the dashboard and trace queries at interactive latency (< 2 s for the full task subset).

### 5.4 Cost Control

**NFR-11.** The per-task token budget cap (FR-43) SHALL default to a value that keeps the expected cost of a full 50-task benchmark run under $5 USD at current open-model pricing; the default SHALL be documented in the configuration file.

**NFR-12.** The response cache (FR-44) SHALL be persistent across process restarts (e.g., stored in Postgres or a local SQLite file) so that re-running a benchmark after a crash does not re-incur LLM costs for already-completed calls.

**NFR-13.** Cost SHALL be recorded in USD per call at the time of the call using the provider's published per-token price stored in the router's model config; cost SHALL NOT be estimated retroactively from token counts alone.

### 5.5 Performance & Latency

**NFR-14.** The benchmark harness overhead (excluding LLM inference and test execution time) SHALL add no more than 5 seconds per task to end-to-end latency.

**NFR-15.** The Streamlit dashboard SHALL load and render the full comparison table and plots in under 10 seconds on the machine where Postgres is running.

**NFR-16.** The Docker sandbox container SHALL start within 30 seconds for any task; if startup exceeds this threshold, the run SHALL be aborted and recorded as a harness error (not a solver FAIL).

### 5.6 Maintainability & Code Quality

**NFR-17.** All Python source files SHALL include type hints on all function signatures; `ruff` SHALL be configured in strict mode and SHALL pass with zero violations.

**NFR-18.** No bare `except` clauses SHALL appear anywhere in the codebase; all exceptions SHALL be caught by type or re-raised.

**NFR-19.** Every public function and class SHALL have a docstring stating its purpose, parameters, and return value.

**NFR-20.** The codebase SHALL maintain a minimum unit-test coverage of 70% on `src/` as measured by `pytest-cov`; coverage SHALL be reported in CI.

**NFR-21.** The two model layers (Claude Code dev tool vs. system agents) SHALL be architecturally separated: no import or call path SHALL cross from the system's agent code into Claude Code tooling, and vice versa.

### 5.7 Reproducibility

**NFR-22.** All Python dependencies SHALL be pinned in a `requirements.txt` or `pyproject.toml` lockfile committed to the repository; `make setup` SHALL install exactly those pinned versions.

**NFR-23.** The Docker sandbox image SHALL be built from a committed `Dockerfile`; the image tag used in benchmark runs SHALL be pinned to a digest or explicit version tag, not `latest`.

**NFR-24.** The README SHALL document the exact hardware and software environment (OS, Python version, Docker version, GPU if used) on which the headline results were produced.

### 5.8 Usability (Developer Experience)

**NFR-25.** A developer cloning the repository for the first time SHALL be able to reach a passing `make lint && make test` state in under 15 minutes by following only the README setup instructions.

**NFR-26.** All error messages produced by the harness, router, or tool layer SHALL include: the component name, the task ID (if applicable), the run ID (if applicable), and a human-readable description of the failure; stack traces SHALL be written to a log file, not to stdout.

---

## 6. Constraints

**C-1. No Anthropic API.** The system's agents (Architect, Developer, Tester, Reviewer) SHALL use only open models accessed via the LiteLLM router. No Anthropic API key SHALL be required to run the benchmark.

**C-2. Fixed task subset cap.** The benchmark task set is capped at 50 SWE-bench tasks plus 5 custom tickets. The harness SHALL refuse to run more than this cap without an explicit override flag, to prevent accidental full-suite runs.

**C-3. Sandbox-only execution (non-negotiable).** Generated code execution outside the Docker sandbox is prohibited under all circumstances, including development, debugging, and demo modes. This constraint supersedes any convenience argument.

**C-4. No always-on hosting.** The system SHALL NOT be deployed as a persistent hosted service. The dashboard and demo are run locally or on-demand.

**C-5. Python only.** All application code (agents, harness, tool layer, dashboard) SHALL be written in Python. Shell scripts are permitted only for Makefile targets and Claude Code hooks.

**C-6. SWE-bench harness reuse.** The project SHALL reuse the official SWE-bench harness and `sb-cli` for SWE-bench task environment setup and hidden-test scoring. Reimplementing SWE-bench environment provisioning is out of scope.

**C-7. Single developer.** The project is built and maintained by one person. Architectural decisions SHALL favour simplicity and debuggability over scalability or team conventions.

**C-8. Spec-driven development order.** Implementation SHALL follow the spec order defined in Part C (Specs 00–09 before any stretch specs). A spec SHALL NOT be started until all its declared dependencies are merged.

**C-9. No polished chat/IDE UX.** The dashboard is for results display only. Building an interactive coding assistant UI is explicitly out of scope.

**C-10. Real GitHub PRs are demo-only.** Real PR creation (FR-S3) SHALL never be part of a scored benchmark run; it is permitted only in a clearly labelled demo mode.

---

## 7. Technologies

### 7.1 Mandated Technologies

| Layer | Technology | Notes |
|-------|-----------|-------|
| Orchestration | **LangGraph** | Multi-agent graph, state machine, checkpointing. |
| Model router | **LiteLLM** | Single interface over all providers; per-call cost accounting. |
| Language | **Python** | All application code. |
| Sandbox | **Docker** | Isolated container per task run; Firecracker optional stretch. |
| Database | **Postgres** | Trace events, run records, metrics, response cache. |
| Dashboard | **Streamlit** | Results display; no interactive agent UX. |
| Benchmark base | **SWE-bench harness + `sb-cli`** | Environment setup and hidden-test scoring for SWE-bench tasks. |
| Linting/formatting | **ruff + black** | Enforced via Makefile and PostToolUse hook. |
| Testing | **pytest + pytest-cov** | Unit tests; coverage reporting in CI. |
| CI | **GitHub Actions** | `make lint && make test` on every push. |
| Dev tool | **Claude Code** | Development environment only; not a runtime component. |

### 7.2 Implied / Recommended Technologies

| Layer | Technology | Notes |
|-------|-----------|-------|
| Model providers | OpenRouter, Together, Groq, Fireworks, DeepInfra, local Ollama | Via LiteLLM router; at least two must be configured. |
| Open models | Qwen3-Coder, DeepSeek-V3.x, GLM-4.6, Kimi, gpt-oss | Strong-tier and small-tier candidates; final selection in config. |
| MCP (dev) | `@modelcontextprotocol/server-github`, Postgres MCP | Claude Code development MCP servers only. |
| Version control | Git + GitHub | Repository hosting, CI, optional PR demo. |
| Environment management | `pyproject.toml` or `requirements.txt` with pinned deps | Reproducibility. |
| Secrets management | `.env` file (gitignored) + `python-dotenv` | API keys and credentials. |

---

## 8. Deployment Requirements

**DR-1.** The system SHALL be deployable on a single machine (laptop or university GPU server) running Linux or macOS with Docker, Python ≥ 3.11, and Postgres available locally or via a Docker Compose service.

**DR-2.** A `docker-compose.yml` (or equivalent) SHALL be provided to start Postgres and any required infrastructure services with a single command, so that `make setup` can complete without manual database installation.

**DR-3.** The repository SHALL include a `Dockerfile` for the benchmark sandbox image; the image SHALL be buildable with `docker build` from the repository root without external dependencies beyond those declared in the Dockerfile.

**DR-4.** The system SHALL support a **local Ollama endpoint** as a zero-cost model provider, configurable by setting `OLLAMA_BASE_URL` (or equivalent) in the environment; no code changes SHALL be required to switch between hosted and local model providers.

**DR-5.** All infrastructure (Postgres, sandbox containers) SHALL be startable and stoppable via `make` targets; no persistent background services SHALL be required outside of a benchmark run.

**DR-6.** The CI workflow (GitHub Actions) SHALL run `make lint && make test` without requiring Docker or Postgres (unit tests SHALL mock or stub infrastructure dependencies); integration tests requiring Docker SHALL be in a separate, manually triggered workflow.

**DR-7.** The public repository SHALL be reproducible from a clean clone on a machine that has never seen the project: `make setup && make benchmark TASKS=lite-5` SHALL complete successfully (modulo model provider availability) following only the README instructions.

**DR-8.** The README SHALL document the minimum hardware requirements for a full benchmark run, including estimated GPU VRAM if local Ollama is used, and estimated wall-clock time for the fixed 50-task subset.