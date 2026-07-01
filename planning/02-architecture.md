# architecture.md

## Multi-Agent SWE System + Benchmark — Architecture Document

**Version:** 1.0  
**Status:** Implementation-Ready  
**Audience:** Engineers implementing Specs 00–09

---

## 1. System Overview

This system is a measurement-first multi-agent coding pipeline wrapped in a reproducible benchmark harness. It has two separable concerns that share infrastructure but must never be conflated in code:

1. **The solver pipeline** — a LangGraph graph of four agents (Architect, Developer, Tester, Reviewer) that accepts a coding ticket and produces a patch. This is the system under study.
2. **The benchmark harness** — a task loader, deterministic scorer, and metrics store that runs the solver against a fixed task set and records objective results.

The system operates entirely on open models via a LiteLLM router. No Anthropic API is used at runtime. Claude Code is the development tool only and has zero presence in the runtime architecture.

### Top-Level Boundaries

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BENCHMARK HARNESS                                                           │
│  (task loader · solver driver · scorer · metrics writer)                    │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  SOLVER PIPELINE  (LangGraph graph)                                  │  │
│   │  Architect → Developer → Tester → Reviewer                          │  │
│   │  (all LLM calls via LiteLLM router · all code exec via sandbox)     │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   ┌──────────────┐   ┌─────────────────┐   ┌──────────────────────────┐    │
│   │  LiteLLM     │   │  Tool Layer     │   │  Postgres                │    │
│   │  Router      │   │  (MCP servers)  │   │  (traces · metrics)      │    │
│   └──────────────┘   └─────────────────┘   └──────────────────────────┘    │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  Docker Sandbox  (isolated container per task run)                   │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Architecture

### 2.1 Component Inventory

| Component | Module Path | Responsibility |
|---|---|---|
| **CLI / Makefile entrypoint** | `benchmark/cli.py` | Parses `make benchmark` arguments; drives the harness loop |
| **Task Loader** | `benchmark/loader.py` | Loads SWE-bench subset and custom tickets from config |
| **Solver Driver** | `benchmark/driver.py` | Instantiates the correct solver graph; calls it per task |
| **Deterministic Scorer** | `benchmark/scorer.py` | Applies patch in sandbox; runs hidden tests; returns PASS/FAIL |
| **Metrics Writer** | `benchmark/metrics.py` | Writes run records and aggregates to Postgres |
| **LangGraph Graph** | `src/graph/graph.py` | Defines the agent graph, edges, and conditional routing |
| **Graph State** | `src/graph/state.py` | Typed `TypedDict` for all shared graph state |
| **Architect Node** | `src/agents/architect.py` | Plans files to touch and implementation approach |
| **Developer Node** | `src/agents/developer.py` | Writes code via tool layer; produces patch |
| **Tester Node** | `src/agents/tester.py` | Runs tests in sandbox; returns structured PASS/FAIL |
| **Reviewer Node** | `src/agents/reviewer.py` | Evaluates patch quality and security |
| **Router** | `src/router/router.py` | LiteLLM wrapper; per-call token/cost accounting |
| **Router Config** | `src/router/config.py` | Tier assignments, model names, per-token prices |
| **Filesystem MCP Server** | `src/tools/filesystem_server.py` | MCP server: read/write/list/exists scoped to task repo |
| **Run-Code MCP Server** | `src/tools/runcode_server.py` | MCP server: executes commands in Docker sandbox only |
| **Git MCP Server** | `src/tools/git_server.py` | MCP server: diff/stage/commit in sandboxed repo clone |
| **Sandbox Wrapper** | `src/sandbox/docker_sandbox.py` | Creates, runs, and tears down per-task Docker containers |
| **Hallucination Checker** | `src/metrics/hallucination.py` | Static check: referenced paths/symbols vs. repo tree |
| **Trace Store** | `src/metrics/trace_store.py` | SQLAlchemy models; write/read trace events and run records |
| **Response Cache** | `src/router/cache.py` | Postgres-backed (model, prompt) → response cache |
| **Action Allow-List** | `src/guardrails/allowlist.py` | Reads config; enforces allowed tool actions at boundary |
| **Budget Guard** | `src/guardrails/budget.py` | Tracks cumulative tokens per run; halts on cap |
| **Dashboard** | `dashboard/app.py` | Streamlit app; reads Postgres; renders comparison table + plots |
| **DB Schema / Migrations** | `src/db/schema.py`, `src/db/migrations/` | SQLAlchemy models; Alembic migrations |

### 2.2 Component Dependency Graph

```
CLI
 └── Solver Driver
      ├── Task Loader
      ├── LangGraph Graph
      │    ├── Architect Node ──► Router
      │    ├── Developer Node ──► Router
      │    │                  ──► Tool Layer (Filesystem MCP, RunCode MCP, Git MCP)
      │    │                       └── Sandbox Wrapper
      │    ├── Tester Node    ──► Router
      │    │                  ──► Tool Layer (RunCode MCP)
      │    │                       └── Sandbox Wrapper
      │    └── Reviewer Node  ──► Router
      ├── Budget Guard        ──► Trace Store
      ├── Action Allow-List
      └── Response Cache      ──► Trace Store
 └── Deterministic Scorer     ──► Sandbox Wrapper
 └── Metrics Writer           ──► Trace Store
      └── Hallucination Checker
```

---

## 3. Data Flow

### 3.1 Benchmark Run (Full Flow)

```
make benchmark TASKS=lite-30 SOLVER=multi
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. CLI (benchmark/cli.py)                                                   │
│    • Parses TASKS, SOLVER args                                              │
│    • Generates run_id (UUID4)                                               │
│    • Calls Task Loader → list[Task]                                         │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │  list[Task]
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Task Loader (benchmark/loader.py)                                        │
│    • Reads task IDs from config/tasks/lite-30.yaml                         │
│    • For SWE-bench tasks: calls sb-cli to provision repo snapshot          │
│    • For custom tasks: reads from benchmark/custom_tasks/                  │
│    • Returns: Task(id, issue_text, repo_path, hidden_test_paths)           │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │  Task
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Solver Driver (benchmark/driver.py)                                      │
│    • Instantiates LangGraph graph with solver config                       │
│    • Calls graph.invoke(state) per task                                    │
│    • Catches cap_hit / budget_exceeded signals                             │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │  GraphState
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. LangGraph Graph (src/graph/graph.py)                                     │
│                                                                             │
│  ┌──────────────┐                                                           │
│  │  ARCHITECT   │ ← issue_text, repo_path                                  │
│  │  strong tier │ → plan: {files_to_modify, approach, constraints}         │
│  └──────┬───────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────┐  ←──────────────────────────────────────────────────┐    │
│  │  DEVELOPER   │ ← plan, [tester_feedback], [reviewer_feedback]      │    │
│  │  small tier  │ → invokes Filesystem MCP (read/write)               │    │
│  │              │ → invokes RunCode MCP (sandbox exec)                │    │
│  │              │ → invokes Git MCP (diff/stage)                      │    │
│  │              │ → patch (unified diff)                              │    │
│  └──────┬───────┘                                                     │    │
│         │                                                             │    │
│         ▼                                                             │    │
│  ┌──────────────┐                                                     │    │
│  │   TESTER     │ ← patch, test_paths                                 │    │
│  │  small tier  │ → invokes RunCode MCP (run test suite in sandbox)   │    │
│  │              │ → result: PASS | FAIL(details)                      │    │
│  └──────┬───────┘                                                     │    │
│         │ FAIL (iter < cap)                                           │    │
│         └─────────────────────────────────────────────────────────────┘    │
│         │ PASS                                                              │
│         ▼                                                                   │
│  ┌──────────────┐  ←──────────────────────────────────────────────────┐    │
│  │   REVIEWER   │ ← patch                                             │    │
│  │  strong tier │ → result: APPROVED | ISSUES(list)                   │    │
│  └──────┬───────┘                                                     │    │
│         │ ISSUES (iter < cap)                                         │    │
│         └─────────────────────────────────────────────────────────────┘    │
│         │ APPROVED (or cap hit)                                            │
│         ▼                                                                   │
│  GraphState { patch, iterations, cap_hit, budget_exceeded, trace_events }  │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │  final GraphState
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Deterministic Scorer (benchmark/scorer.py)                               │
│    • For SWE-bench: delegates to sb-cli score command                      │
│    • For custom: applies patch in sandbox → runs hidden tests → PASS/FAIL  │
│    • Returns: ScorerResult(outcome, test_output)                           │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │  ScorerResult
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. Metrics Writer (benchmark/metrics.py)                                    │
│    • Calls Hallucination Checker on patch vs. repo symbol table            │
│    • Computes iteration count from trace events                            │
│    • Writes RunRecord to Postgres (immutable, never updated)               │
│    • Writes all TraceEvents to Postgres                                    │
│    • Prints summary row to stdout                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 LLM Call Flow (Every Agent Turn)

```
Agent Node
    │
    │  (model_name, messages, tier)
    ▼
Router.complete(request)
    │
    ├── Check Response Cache (Postgres)
    │       hit  → return cached response, write trace (cache_hit=True, cost=0)
    │       miss → continue
    │
    ├── Check Budget Guard (cumulative tokens for this run_id)
    │       exceeded → raise BudgetExceededError → graph terminates
    │       ok       → continue
    │
    ├── LiteLLM.completion(model, messages, ...)
    │       → provider API call (OpenRouter / Together / Groq / Ollama)
    │
    ├── Extract: prompt_tokens, completion_tokens
    ├── Compute: cost_usd = tokens × per_token_price[model]
    ├── Write TraceEvent to Postgres (synchronous, before returning)
    ├── Store in Response Cache (Postgres)
    │
    └── Return: LLMResponse(content, usage, cost_usd)
```

### 3.3 Tool Call Flow (Developer / Tester Nodes)

```
Agent Node
    │
    │  tool_call: {tool_name, arguments}
    ▼
Action Allow-List (src/guardrails/allowlist.py)
    │
    ├── allowed  → forward to MCP server
    └── denied   → return ToolError to agent (no exception raised)

MCP Server (filesystem / runcode / git)
    │
    ├── Filesystem MCP: read/write/list/exists
    │       → operates on /sandbox/repo/{task_id}/ (mounted volume)
    │       → never touches host filesystem outside mount
    │
    ├── RunCode MCP: exec(command, working_dir)
    │       → calls Sandbox Wrapper
    │       │
    │       └── docker run
    │               --rm
    │               --network none
    │               --cap-drop ALL
    │               --user nobody
    │               --read-only
    │               --tmpfs /tmp
    │               -v /sandbox/repo/{task_id}:/workspace:rw
    │               {sandbox_image}:{pinned_digest}
    │               sh -c "{command}"
    │       → returns: stdout, stderr, exit_code
    │
    └── Git MCP: diff/stage/commit
            → runs git commands inside sandbox container
            → returns: diff text or commit sha
```

### 3.4 Single-Agent Mode

The single-agent solver is the same LangGraph graph with the Architect, Tester, and Reviewer nodes disabled via solver config. The Developer node runs alone. This shares all instrumentation, the router, the tool layer, and the metrics writer — there is no separate code path.

```
GraphConfig(solver="single")
    → graph skips Architect (uses default plan), skips Tester loop, skips Reviewer
    → Developer node runs once (or with self-loop capped at 3)
    → same trace events, same run record schema
```

---

## 4. Service Boundaries

### 4.1 Process Boundaries

At runtime, the following processes run:

| Process | How Started | Lifetime |
|---|---|---|
| **Benchmark CLI** | `make benchmark` | One process per benchmark run; exits when all tasks complete |
| **Postgres** | `docker compose up -d postgres` | Persistent across runs; started by `make setup` |
| **Filesystem MCP Server** | Spawned by benchmark CLI as subprocess | One per benchmark run; killed on exit |
| **RunCode MCP Server** | Spawned by benchmark CLI as subprocess | One per benchmark run; killed on exit |
| **Git MCP Server** | Spawned by benchmark CLI as subprocess | One per benchmark run; killed on exit |
| **Docker sandbox container** | Spawned by RunCode MCP per exec call | One per exec call; `--rm` ensures auto-removal |
| **Streamlit dashboard** | `make dashboard` | On-demand; exits when user closes |

The three MCP servers are spawned as subprocesses by the benchmark CLI using the MCP stdio transport. They communicate with the LangGraph agent nodes via JSON-RPC over stdin/stdout. This means no network ports are opened for the tool layer — communication is purely in-process via subprocess pipes.

### 4.2 Interface Contracts

**Router interface** (`src/router/router.py`):
```python
def complete(
    request: LLMRequest,          # model, messages, temperature, max_tokens
    run_id: UUID,
    task_id: str,
    agent_role: AgentRole,
    turn_index: int,
) -> LLMResponse:                 # content, usage, cost_usd, cache_hit
```
No caller imports a provider SDK. All callers use this function.

**MCP tool interface** (JSON-RPC, MCP protocol):
```
filesystem/read_file    {path: str}                    → {content: str}
filesystem/write_file   {path: str, content: str}      → {ok: bool}
filesystem/list_dir     {path: str}                    → {entries: list[str]}
filesystem/exists       {path: str}                    → {exists: bool}

runcode/exec            {command: str, workdir: str}   → {stdout, stderr, exit_code}

git/diff                {}                             → {diff: str}
git/stage               {paths: list[str]}             → {ok: bool}
git/commit              {message: str}                 → {sha: str}
```

**Scorer interface** (`benchmark/scorer.py`):
```python
def score(
    task: Task,
    patch: str,
    run_id: UUID,
) -> ScorerResult:                # outcome: Literal["PASS","FAIL"], test_output: str
```

**Graph state** (`src/graph/state.py`):
```python
class GraphState(TypedDict):
    run_id: UUID
    task_id: str
    issue_text: str
    repo_path: Path
    solver_config: SolverConfig
    plan: Plan | None
    patch: str
    tester_feedback: list[str]
    reviewer_feedback: list[str]
    dev_tester_iterations: int
    dev_reviewer_iterations: int
    cap_hit: bool
    budget_exceeded: bool
    trace_events: list[TraceEvent]
```

### 4.3 What Crosses Boundaries

| Boundary | What Crosses | What Does Not Cross |
|---|---|---|
| CLI → Graph | `Task`, `SolverConfig`, `run_id` | Postgres connection (graph uses trace store directly) |
| Graph → Router | `LLMRequest`, `run_id`, `agent_role` | Raw provider credentials (router reads from env) |
| Graph → MCP servers | JSON-RPC over stdio | File handles, Python objects |
| MCP servers → Sandbox | Shell command string, volume mount path | Host filesystem paths outside mount |
| Scorer → Sandbox | Patch text, test file paths | LLM calls (scorer is LLM-free) |
| Any component → Postgres | SQLAlchemy session (via `TraceStore`) | Raw SQL strings from agent code |

---

## 5. Deployment Architecture

### 5.1 Target Environment

Single machine: developer laptop (macOS/Linux) or university GPU server (Linux). No cloud deployment. No always-on services beyond Postgres.

### 5.2 Directory Layout

```
multi-agent-swe-benchmark/
├── CLAUDE.md
├── Makefile
├── pyproject.toml                    # pinned deps, ruff config, pytest config
├── docker-compose.yml                # postgres service
├── Dockerfile.sandbox                # sandbox image (pinned, committed)
├── .env.example                      # template; .env is gitignored
├── .mcp.json                         # Claude Code dev MCP servers
├── .claude/
│   ├── settings.json                 # hooks
│   ├── skills/                       # /new-spec, /run-bench, etc.
│   ├── agents/                       # spec-writer, planner, etc.
│   └── hooks/                        # block-host-exec.sh, format-python.sh, fast-tests.sh
├── config/
│   ├── models.yaml                   # tier assignments, model names, per-token prices
│   ├── guardrails.yaml               # action allow-list, iteration caps, token budget cap
│   └── tasks/
│       ├── lite-30.yaml              # locked SWE-bench task IDs
│       ├── lite-5.yaml               # smoke-test subset
│       └── custom.yaml               # 3–5 hand-authored tickets
├── specs/
│   └── NN-name/{spec.md,plan.md,tasks.md}
├── src/
│   ├── agents/
│   │   ├── architect.py
│   │   ├── developer.py
│   │   ├── tester.py
│   │   └── reviewer.py
│   ├── graph/
│   │   ├── graph.py
│   │   └── state.py
│   ├── router/
│   │   ├── router.py
│   │   ├── config.py
│   │   └── cache.py
│   ├── tools/
│   │   ├── filesystem_server.py
│   │   ├── runcode_server.py
│   │   └── git_server.py
│   ├── sandbox/
│   │   └── docker_sandbox.py
│   ├── guardrails/
│   │   ├── allowlist.py
│   │   └── budget.py
│   ├── metrics/
│   │   ├── hallucination.py
│   │   └── trace_store.py
│   └── db/
│       ├── schema.py
│       └── migrations/
├── benchmark/
│   ├── cli.py
│   ├── loader.py
│   ├── driver.py
│   ├── scorer.py
│   └── metrics.py
├── dashboard/
│   └── app.py
├── tests/
│   ├── unit/
│   └── integration/
└── .github/
    └── workflows/
        ├── ci.yml                    # lint + unit tests on every push
        └── integration.yml           # manual trigger; requires Docker
```

### 5.3 Infrastructure Services

```
docker-compose.yml defines:

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: swe_benchmark
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready"]
      interval: 5s
      timeout: 3s
      retries: 5
```

Postgres is the only persistent service. All other infrastructure is ephemeral (sandbox containers are `--rm`).

### 5.4 Makefile Targets

```makefile
setup:          # pip install -e .[dev] + docker compose up -d postgres
                # + alembic upgrade head + docker build -t sandbox:$(DIGEST) .
lint:           # ruff check src/ benchmark/ dashboard/ tests/ + black --check
test:           # pytest tests/unit/ --cov=src --cov-report=term-missing
benchmark:      # python -m benchmark.cli --tasks $(TASKS) --solver $(SOLVER)
sandbox-run:    # python -m src.sandbox.docker_sandbox --cmd "$(CMD)"
dashboard:      # streamlit run dashboard/app.py
db-shell:       # psql $DATABASE_URL
clean:          # docker compose down -v + rm -rf .pytest_cache __pycache__
```

### 5.5 Environment Variables

Stored in `.env` (gitignored). `.env.example` is committed with placeholder values.

```
# Model providers
OPENROUTER_API_KEY=
TOGETHER_API_KEY=
GROQ_API_KEY=
FIREWORKS_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434   # optional; enables local Ollama

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/swe_benchmark
POSTGRES_USER=
POSTGRES_PASSWORD=

# SWE-bench
SWEBENCH_CACHE_DIR=~/.cache/swebench

# Sandbox
SANDBOX_IMAGE_DIGEST=sha256:...         # pinned at build time
SANDBOX_REPO_MOUNT=/tmp/swe_sandbox

# Guardrails (overrides config/guardrails.yaml defaults)
MAX_TOKENS_PER_TASK=50000
MAX_DEV_TESTER_ITERATIONS=3
MAX_DEV_REVIEWER_ITERATIONS=2
```

---

## 6. Scaling Strategy

This is a single-developer portfolio project with a hard cap of 50 tasks. The scaling strategy is deliberately minimal and documented here to show the decisions were made consciously, not overlooked.

### 6.1 Task Parallelism

Tasks in a benchmark run are executed **sequentially** by default. This is the correct choice because:
- The bottleneck is LLM inference latency, not CPU.
- Sequential execution makes traces readable and debugging straightforward.
- The 50-task cap means a full run completes in acceptable wall-clock time.

A `--parallel N` flag is architecturally supported (each task gets its own `run_id`, its own sandbox container, and its own Postgres connection from the pool) but is not implemented in the initial build. Adding it later requires no schema changes.

### 6.2 Database

Postgres with SQLAlchemy connection pooling (pool size 5, max overflow 10). For 50 tasks × ~20 trace events each = ~1,000 rows per run. This is trivially small; no partitioning or indexing beyond the three required indexes (`run_id`, `task_id`, `solver_config`) is needed.

### 6.3 Model Provider Rate Limits

The router implements **exponential backoff with jitter** (max 3 retries, base delay 1s) on provider 429/503 responses. This is sufficient for sequential task execution at open-model provider rate limits.

### 6.4 Sandbox Container Pool

Containers are created per exec call and destroyed immediately (`--rm`). For sequential execution this is fine. If parallel execution is added later, a container pool (pre-warmed containers) can be introduced in `docker_sandbox.py` without changing the MCP server interface.

### 6.5 What This Architecture Does Not Support (Intentionally)

- Horizontal scaling across multiple machines.
- Concurrent multi-user access to the benchmark.
- Real-time streaming of agent output to a web UI.
- Persistent agent memory across tasks.

---

## 7. Security Architecture

### 7.1 Threat Model

The primary threat is **arbitrary code execution on the host machine** via agent-generated code. Secondary threats are credential leakage and runaway cost from unbounded LLM calls.

### 7.2 Defense-in-Depth: Three Independent Layers

```
Layer 1: Development-time (Claude Code hook)
    block-host-exec.sh
    → PreToolUse on Bash
    → Blocks any command that would run generated code outside sandbox
    → Blocks destructive patterns (rm -rf /, etc.)
    → Exit code 2 = hard block (Claude Code does not execute the command)

Layer 2: Application-time (Action Allow-List)
    src/guardrails/allowlist.py
    → Checked at every MCP tool call boundary
    → Reads allowed actions from config/guardrails.yaml
    → Returns ToolError to agent on violation (no exception propagation)
    → This is the runtime enforcement layer

Layer 3: Infrastructure-time (Docker sandbox)
    src/sandbox/docker_sandbox.py
    → --network none          (no outbound network from generated code)
    → --cap-drop ALL          (no Linux capability escalation)
    → --user nobody           (non-root execution)
    → --read-only             (root filesystem is read-only)
    → --tmpfs /tmp            (writable tmp in memory only)
    → -v {task_repo}:/workspace:rw  (only the task repo is writable)
    → --rm                    (container destroyed after each exec)
    → image pinned to digest  (no supply-chain drift)
```

All three layers must be independently defeated for host code execution to occur. Weakening any one layer is a defect, not a configuration option.

### 7.3 Credential Security

- All API keys in `.env` (gitignored). `.env.example` has no real values.
- `.gitignore` explicitly lists `.env`, `*.env`, `secrets/`.
- The router reads credentials from environment variables only; no credential appears in `config/models.yaml` or any committed file.
- CI secrets are stored in GitHub Actions secrets, not in workflow YAML.

### 7.4 Sandbox Image Supply Chain

- `Dockerfile.sandbox` is committed and pinned to specific base image digests.
- `SANDBOX_IMAGE_DIGEST` env var pins the exact image used at runtime.
- `make setup` builds the image and writes the digest to `.env`.
- Using `latest` is a lint error (checked in CI).

### 7.5 Database Security

- Postgres runs on localhost only (no external port binding in production).
- The application uses a single Postgres role with INSERT/SELECT/UPDATE on the benchmark schema only; no DDL privileges at runtime.
- Alembic migrations run under a separate admin role during `make setup`.

### 7.6 Action Allow-List Schema

`config/guardrails.yaml`:
```yaml
allowed_tools:
  filesystem:
    - read_file
    - write_file
    - list_dir
    - exists
  runcode:
    - exec
  git:
    - diff
    - stage
    - commit

# Paths the filesystem MCP may access (relative to task repo root)
filesystem_scope: "."

# Commands the runcode MCP will refuse regardless of allow-list
exec_blocklist:
  - "curl"
  - "wget"
  - "nc"
  - "ncat"
  - "ssh"
  - "scp"
  - "pip install"   # no network installs inside sandbox
```

The exec blocklist is a secondary check inside the RunCode MCP server, applied after the allow-list and before Docker invocation. It is not a substitute for `--network none`; it is defense-in-depth.

### 7.7 Cost Control as a Security Property

Unbounded LLM spend is treated as a security/reliability concern, not just a cost concern.

- **Per-task token budget cap**: default 50,000 tokens (~$0.10 at current open-model prices). Configurable in `config/guardrails.yaml` and overridable via env var.
- **Per-run hard stop**: `BudgetGu