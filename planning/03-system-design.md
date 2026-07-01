# system-design.md

**Version:** 1.0  
**Status:** Implementation-Ready  
**Derived From:** planning/02-architecture.md v1.0

---

## Table of Contents

1. [Modules](#1-modules)
2. [Services](#2-services)
3. [Internal Workflows](#3-internal-workflows)
4. [Event Flows](#4-event-flows)
5. [State Transitions](#5-state-transitions)
6. [Design Patterns](#6-design-patterns)
7. [Integration Points](#7-integration-points)

---

## 1. Modules

This section describes every Python module in the system: its public interface, its internal responsibilities, and its direct dependencies. Modules are grouped by package.

---

### 1.1 `benchmark/` — Harness Package

The benchmark package is the outermost shell. It drives the solver and records results. It never imports from `src/agents/` directly; it only touches the graph through `driver.py`.

---

#### `benchmark/cli.py`

**Purpose:** Parse command-line arguments, generate a `run_id`, and orchestrate the top-level harness loop.

**Public interface:**
```python
def main() -> None   # entry point: python -m benchmark.cli
```

**Internal responsibilities:**
- Parse `--tasks <set_name>` and `--solver <single|multi>` via `argparse`.
- Generate `run_id = uuid.uuid4()`.
- Instantiate `TaskLoader`, `SolverDriver`, `DeterministicScorer`, `MetricsWriter`.
- Iterate over tasks: call driver → scorer → metrics writer in sequence.
- Spawn MCP server subprocesses before the loop; terminate them on exit (via `atexit` or `contextlib.ExitStack`).
- Print a final summary table to stdout.

**Dependencies:** `benchmark/loader.py`, `benchmark/driver.py`, `benchmark/scorer.py`, `benchmark/metrics.py`, `src/tools/*_server.py` (as subprocesses).

---

#### `benchmark/loader.py`

**Purpose:** Produce a typed list of `Task` objects from a named task set.

**Public interface:**
```python
@dataclass
class Task:
    id: str
    issue_text: str
    repo_path: Path
    hidden_test_paths: list[Path]
    source: Literal["swebench", "custom"]

class TaskLoader:
    def load(self, task_set_name: str) -> list[Task]: ...
```

**Internal responsibilities:**
- Read `config/tasks/{task_set_name}.yaml` to get a list of task IDs.
- For `source: swebench` tasks: invoke `sb-cli` as a subprocess to provision the repo snapshot into `SWEBENCH_CACHE_DIR`; return the local path.
- For `source: custom` tasks: read from `benchmark/custom_tasks/{id}/` directory; parse `issue.md` and `tests/` subdirectory.
- Validate that `repo_path` exists and `hidden_test_paths` are present before returning.

**Dependencies:** `config/tasks/*.yaml`, `subprocess` (for `sb-cli`), `pathlib`.

---

#### `benchmark/driver.py`

**Purpose:** Instantiate the LangGraph graph for a given solver config and invoke it once per task.

**Public interface:**
```python
@dataclass
class SolverConfig:
    solver: Literal["single", "multi"]
    max_dev_tester_iterations: int
    max_dev_reviewer_iterations: int
    max_tokens_per_task: int

class SolverDriver:
    def __init__(self, config: SolverConfig, run_id: UUID): ...
    def solve(self, task: Task) -> GraphState: ...
```

**Internal responsibilities:**
- Build the initial `GraphState` from the `Task` and `SolverConfig`.
- Call `graph.invoke(initial_state)` from `src/graph/graph.py`.
- Catch `BudgetExceededError` and return a terminal `GraphState` with `budget_exceeded=True`.
- Catch any unhandled exception from the graph; log it; return a terminal state with `cap_hit=True` so the harness continues to the next task.

**Dependencies:** `src/graph/graph.py`, `src/graph/state.py`.

---

#### `benchmark/scorer.py`

**Purpose:** Apply a patch in an isolated sandbox and determine PASS/FAIL against hidden tests. This module contains zero LLM calls.

**Public interface:**
```python
@dataclass
class ScorerResult:
    outcome: Literal["PASS", "FAIL"]
    test_output: str
    duration_seconds: float

class DeterministicScorer:
    def score(self, task: Task, patch: str, run_id: UUID) -> ScorerResult: ...
```

**Internal responsibilities:**
- For `source: swebench`: delegate entirely to `sb-cli score --task-id {id} --patch {patch_file}` as a subprocess; parse its JSON output.
- For `source: custom`:
  1. Copy the task repo to a fresh temp directory.
  2. Apply the patch via `git apply`.
  3. Invoke `DockerSandbox.run_command("pytest {hidden_test_paths} --tb=short -q")`.
  4. Parse exit code: 0 → PASS, non-zero → FAIL.
  5. Return stdout+stderr as `test_output`.
- Never modify the original `task.repo_path`; always work on a copy.

**Dependencies:** `src/sandbox/docker_sandbox.py`, `subprocess`, `tempfile`.

---

#### `benchmark/metrics.py`

**Purpose:** Persist a completed run record and all trace events to Postgres.

**Public interface:**
```python
class MetricsWriter:
    def __init__(self, trace_store: TraceStore): ...
    def write(
        self,
        task: Task,
        state: GraphState,
        scorer_result: ScorerResult,
        run_id: UUID,
        solver_config: SolverConfig,
    ) -> None: ...
```

**Internal responsibilities:**
- Call `HallucinationChecker.check(patch, repo_path)` to get a hallucination score.
- Compute `total_cost_usd` by summing `cost_usd` across all `TraceEvent`s in `state.trace_events`.
- Compute `iteration_count` from `state.dev_tester_iterations + state.dev_reviewer_iterations`.
- Construct a `RunRecord` and call `trace_store.write_run_record(record)`.
- Call `trace_store.write_trace_events(state.trace_events)`.
- Print a one-line summary row to stdout: `task_id | outcome | cost | iterations | hallucination_score`.

**Dependencies:** `src/metrics/trace_store.py`, `src/metrics/hallucination.py`.

---

### 1.2 `src/graph/` — LangGraph Graph Package

---

#### `src/graph/state.py`

**Purpose:** Define the single shared state type that flows through the entire LangGraph graph.

**Public interface:**
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

@dataclass
class Plan:
    files_to_modify: list[str]
    approach: str
    constraints: list[str]
```

**Design note:** `GraphState` is a `TypedDict` (not a dataclass) because LangGraph requires dict-compatible state. All fields are explicitly typed; no `Any`. The `trace_events` list is append-only during a run; each node appends its own events and returns the updated list.

---

#### `src/graph/graph.py`

**Purpose:** Construct and export the compiled LangGraph `StateGraph` with all nodes, edges, and conditional routing.

**Public interface:**
```python
def build_graph(solver_config: SolverConfig) -> CompiledGraph: ...
```

**Internal responsibilities:**

Build the graph with these nodes and edges:

```
START
  │
  ▼
[architect_node]  ← skipped if solver_config.solver == "single"
  │
  ▼
[developer_node]  ◄──────────────────────────────────────────┐
  │                                                           │
  ▼                                                           │
[tester_node]  ← skipped if solver_config.solver == "single" │
  │                                                           │
  ├── route_after_tester() ──► FAIL + iter < cap ────────────┘
  │
  ├── route_after_tester() ──► PASS
  │
  ▼
[reviewer_node]  ← skipped if solver_config.solver == "single"
  │
  ├── route_after_reviewer() ──► ISSUES + iter < cap ──► [developer_node]
  │
  └── route_after_reviewer() ──► APPROVED ──► END
```

Conditional edge functions:
```python
def route_after_tester(state: GraphState) -> str:
    if state["budget_exceeded"] or state["cap_hit"]:
        return "reviewer"   # exit tester loop regardless
    if state["dev_tester_iterations"] >= state["solver_config"].max_dev_tester_iterations:
        return "reviewer"
    last_feedback = state["tester_feedback"][-1] if state["tester_feedback"] else ""
    if last_feedback.startswith("PASS"):
        return "reviewer"
    return "developer"      # loop back

def route_after_reviewer(state: GraphState) -> str:
    if state["budget_exceeded"] or state["cap_hit"]:
        return END
    if state["dev_reviewer_iterations"] >= state["solver_config"].max_dev_reviewer_iterations:
        return END
    last_feedback = state["reviewer_feedback"][-1] if state["reviewer_feedback"] else ""
    if last_feedback.startswith("APPROVED"):
        return END
    return "developer"      # loop back
```

For `solver == "single"`: architect, tester, and reviewer nodes are replaced with pass-through identity functions that return state unchanged.

**Dependencies:** `src/agents/*.py`, `src/graph/state.py`, `langgraph`.

---

### 1.3 `src/agents/` — Agent Nodes

Each agent module exports a single function with the signature `(state: GraphState) -> GraphState`. Nodes are pure functions from the graph's perspective: they receive state, call the router, optionally call tools, and return updated state. They never write to Postgres directly; they append `TraceEvent` objects to `state["trace_events"]`.

---

#### `src/agents/architect.py`

**Purpose:** Analyze the issue and produce a structured plan.

**Public interface:**
```python
def architect_node(state: GraphState) -> GraphState: ...
```

**Internal responsibilities:**
1. Build a system prompt that includes the issue text and a directory listing of `repo_path` (obtained via a `filesystem/list_dir` call).
2. Call `Router.complete(request, tier="strong", ...)`.
3. Parse the LLM response into a `Plan` object (structured output via JSON mode or response parsing).
4. Return state with `plan` set and the new `TraceEvent` appended.

**Prompt contract:** The architect is instructed to return a JSON object with keys `files_to_modify: list[str]`, `approach: str`, `constraints: list[str]`. If parsing fails, return a default `Plan` with `files_to_modify=[]` and log a warning trace event.

**Dependencies:** `src/router/router.py`, `src/graph/state.py`.

---

#### `src/agents/developer.py`

**Purpose:** Write code changes using the tool layer to produce a unified diff patch.

**Public interface:**
```python
def developer_node(state: GraphState) -> GraphState: ...
```

**Internal responsibilities:**
1. Build a system prompt including: issue text, plan (if present), tester feedback (if any), reviewer feedback (if any).
2. Enter a **tool-use loop** (max 10 tool calls per developer turn):
   - Call `Router.complete(request, tier="small", tools=[filesystem_tools, runcode_tools, git_tools])`.
   - If the response contains tool calls, dispatch each through `ActionAllowList.check()` then to the appropriate MCP client.
   - Accumulate tool results; feed them back as the next message.
   - Break when the LLM returns a non-tool-call response or the tool-call limit is reached.
3. After the tool loop, call `git/diff` to capture the current patch.
4. Increment `dev_tester_iterations` if returning from a tester loop; increment `dev_reviewer_iterations` if returning from a reviewer loop.
5. Return updated state with `patch` set.

**MCP client usage:** The developer node holds references to `FilesystemMCPClient`, `RunCodeMCPClient`, and `GitMCPClient` (thin wrappers around the stdio JSON-RPC transport). These are injected at graph construction time, not imported as globals.

**Dependencies:** `src/router/router.py`, `src/guardrails/allowlist.py`, MCP client wrappers.

---

#### `src/agents/tester.py`

**Purpose:** Run the test suite against the current patch and return structured feedback.

**Public interface:**
```python
def tester_node(state: GraphState) -> GraphState: ...
```

**Internal responsibilities:**
1. Call `runcode/exec` with `pytest {task_test_paths} --tb=short -q` in the sandbox.
2. Parse stdout/stderr: if exit code 0, produce `"PASS"` feedback; otherwise produce `"FAIL: {truncated_output}"`.
3. Optionally call `Router.complete(tier="small")` to summarize failure output into actionable feedback for the developer (this LLM call is optional and skipped if the output is already short).
4. Append the feedback string to `state["tester_feedback"]`.
5. Return updated state.

**Design note:** The tester node does not apply the patch itself. The developer node's tool calls (via `git/stage` and `git/commit`) have already modified the sandbox repo. The tester runs tests against the current state of `/workspace`.

**Dependencies:** `src/router/router.py` (optional), `RunCodeMCPClient`.

---

#### `src/agents/reviewer.py`

**Purpose:** Evaluate patch quality, correctness, and security; return APPROVED or ISSUES.

**Public interface:**
```python
def reviewer_node(state: GraphState) -> GraphState: ...
```

**Internal responsibilities:**
1. Build a prompt including: the full unified diff (`state["patch"]`), the original issue text, and the plan.
2. Call `Router.complete(request, tier="strong")`.
3. Parse the response: expect a JSON object with `result: "APPROVED" | "ISSUES"` and `issues: list[str]`.
4. Append `"APPROVED"` or `"ISSUES: {issues_joined}"` to `state["reviewer_feedback"]`.
5. Return updated state.

**Review criteria (encoded in system prompt):**
- Does the patch address the issue as described?
- Are there obvious security problems (shell injection, path traversal, hardcoded secrets)?
- Are there unrelated changes (scope creep)?
- Does the code follow the existing style of the repo?

**Dependencies:** `src/router/router.py`.

---

### 1.4 `src/router/` — LLM Router Package

---

#### `src/router/router.py`

**Purpose:** Single choke point for all LLM calls. Enforces caching, budget, and per-call accounting.

**Public interface:**
```python
@dataclass
class LLMRequest:
    model: str
    messages: list[dict]
    temperature: float
    max_tokens: int
    tools: list[dict] | None = None

@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] | None
    usage: TokenUsage          # prompt_tokens, completion_tokens
    cost_usd: float
    cache_hit: bool

class Router:
    def __init__(
        self,
        config: RouterConfig,
        cache: ResponseCache,
        budget_guard: BudgetGuard,
        trace_store: TraceStore,
    ): ...

    def complete(
        self,
        request: LLMRequest,
        run_id: UUID,
        task_id: str,
        agent_role: AgentRole,
        turn_index: int,
        tier: Literal["strong", "small"],
    ) -> LLMResponse: ...
```

**Internal call sequence:**
1. Resolve `model` from `RouterConfig.tier_to_model[tier]`.
2. Compute cache key: `sha256(model + canonical_json(messages))`.
3. Check `ResponseCache.get(cache_key)` → if hit, build `LLMResponse(cache_hit=True, cost_usd=0)`, write trace event, return.
4. Check `BudgetGuard.check(run_id, estimated_tokens)` → if exceeded, raise `BudgetExceededError`.
5. Call `litellm.completion(model, messages, temperature, max_tokens, tools)` with retry logic (3 retries, exponential backoff with jitter, on 429/503).
6. Extract `usage.prompt_tokens`, `usage.completion_tokens`.
7. Compute `cost_usd = (prompt_tokens × price_in + completion_tokens × price_out)` from `RouterConfig`.
8. Call `BudgetGuard.record(run_id, total_tokens)`.
9. Call `ResponseCache.set(cache_key, response)`.
10. Build and write `TraceEvent` to `TraceStore`.
11. Return `LLMResponse`.

**Dependencies:** `litellm`, `src/router/config.py`, `src/router/cache.py`, `src/guardrails/budget.py`, `src/metrics/trace_store.py`.

---

#### `src/router/config.py`

**Purpose:** Load and expose model tier assignments and per-token pricing.

**Public interface:**
```python
@dataclass
class ModelPricing:
    price_per_prompt_token: float    # USD
    price_per_completion_token: float

@dataclass
class RouterConfig:
    tier_to_model: dict[str, str]    # "strong" → "openrouter/..."
    pricing: dict[str, ModelPricing] # model_name → pricing

def load_router_config(path: Path = Path("config/models.yaml")) -> RouterConfig: ...
```

**Internal responsibilities:**
- Parse `config/models.yaml` using `PyYAML`.
- Validate that every model referenced in `tier_to_model` has a corresponding entry in `pricing`.
- Raise `ConfigurationError` on missing or malformed entries at startup (fail fast).

---

#### `src/router/cache.py`

**Purpose:** Postgres-backed response cache keyed on `(model, canonical_messages_hash)`.

**Public interface:**
```python
class ResponseCache:
    def __init__(self, db_session_factory: sessionmaker): ...
    def get(self, cache_key: str) -> LLMResponse | None: ...
    def set(self, cache_key: str, response: LLMResponse) -> None: ...
```

**Internal responsibilities:**
- `get`: `SELECT content, tool_calls, usage, cost_usd FROM llm_cache WHERE cache_key = $1`.
- `set`: `INSERT INTO llm_cache ... ON CONFLICT (cache_key) DO NOTHING` (idempotent; first write wins).
- Deserialize stored JSON back into `LLMResponse`.
- Cache entries are permanent (no TTL); this is intentional for reproducibility.

**Dependencies:** `src/db/schema.py` (`LLMCacheEntry` model), SQLAlchemy.

---

### 1.5 `src/tools/` — MCP Server Modules

Each MCP server is a standalone Python process that communicates via JSON-RPC over stdio (MCP stdio transport). They are not imported by the agent nodes; agents communicate with them through thin MCP client wrappers injected at graph construction time.

---

#### `src/tools/filesystem_server.py`

**Purpose:** Expose safe file operations scoped to the task repo directory.

**Exposed tools:**
```
filesystem/read_file   {path: str}                → {content: str}
filesystem/write_file  {path: str, content: str}  → {ok: bool}
filesystem/list_dir    {path: str}                → {entries: list[str]}
filesystem/exists      {path: str}                → {exists: bool}
```

**Internal responsibilities:**
- At startup, receive `--repo-root {path}` argument; store as `REPO_ROOT`.
- For every request: resolve the requested path relative to `REPO_ROOT`; call `path.resolve()` and assert it is still under `REPO_ROOT` (path traversal guard).
- `read_file`: `open(resolved_path).read()`. Return `ToolError` if file not found.
- `write_file`: `open(resolved_path, 'w').write(content)`. Create parent directories if needed.
- `list_dir`: `os.listdir(resolved_path)`. Return entries as relative names.
- `exists`: `resolved_path.exists()`.
- All operations are synchronous; no async.

**Security invariant:** No path outside `REPO_ROOT` is ever accessed. The path traversal check is the first operation in every handler, before any I/O.

---

#### `src/tools/runcode_server.py`

**Purpose:** Execute shell commands inside a Docker sandbox container.

**Exposed tools:**
```
runcode/exec  {command: str, workdir: str}  → {stdout: str, stderr: str, exit_code: int}
```

**Internal responsibilities:**
- At startup, receive `--task-id {id}` and `--repo-mount {path}` arguments.
- For every `exec` request:
  1. Check `command` against the exec blocklist from `config/guardrails.yaml` (substring match on each blocked term). Return `ToolError` if matched.
  2. Call `DockerSandbox.run_command(command, workdir, task_id)`.
  3. Return `{stdout, stderr, exit_code}`.
- Truncate stdout/stderr to 32 KB before returning (prevents memory exhaustion from runaway output).

**Dependencies:** `src/sandbox/docker_sandbox.py`, `config/guardrails.yaml`.

---

#### `src/tools/git_server.py`

**Purpose:** Expose git operations within the sandboxed repo clone.

**Exposed tools:**
```
git/diff    {}                      → {diff: str}
git/stage   {paths: list[str]}      → {ok: bool}
git/commit  {message: str}          → {sha: str}
```

**Internal responsibilities:**
- At startup, receive `--repo-root {path}` argument.
- `diff`: Run `git diff HEAD` in `repo_root` via `subprocess.run`. Return stdout.
- `stage`: Run `git add {paths}` in `repo_root`. Validate each path is under `repo_root` (same traversal guard as filesystem server).
- `commit`: Run `git commit -m {message}` in `repo_root`. Return the new commit SHA from stdout.
- All git commands run on the host (not inside Docker) because the repo is a host directory mounted into Docker. Git operations on the host directory are safe; only code execution goes into Docker.

---

### 1.6 `src/sandbox/` — Sandbox Package

---

#### `src/sandbox/docker_sandbox.py`

**Purpose:** Create, run, and destroy per-exec Docker containers with strict isolation.

**Public interface:**
```python
@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float

class DockerSandbox:
    def __init__(self, image_digest: str, repo_mount_base: Path): ...

    def run_command(
        self,
        command: str,
        workdir: str,
        task_id: str,
        timeout_seconds: int = 120,
    ) -> SandboxResult: ...
```

**Internal responsibilities:**
- Build the `docker run` command:
  ```
  docker run
    --rm
    --network none
    --cap-drop ALL
    --user nobody
    --read-only
    --tmpfs /tmp:size=256m
    -v {repo_mount_base}/{task_id}:/workspace:rw
    --workdir {workdir}
    --memory 2g
    --cpus 2
    {image_digest}
    sh -c "{command}"
  ```
- Execute via `subprocess.run(..., capture_output=True, timeout=timeout_seconds)`.
- On `subprocess.TimeoutExpired`: kill the container by name (using `--name` flag set at invocation), return `SandboxResult(exit_code=124, stderr="timeout")`.
- Return `SandboxResult` with decoded stdout/stderr.

**Design note:** `--memory 2g` and `--cpus 2` are not in the architecture doc but are required for safety; they are added here as implementation detail. The image is referenced by digest (`sha256:...`), never by tag.

---

### 1.7 `src/guardrails/` — Guardrails Package

---

#### `src/guardrails/allowlist.py`

**Purpose:** Enforce the action allow-list at every MCP tool call boundary.

**Public interface:**
```python
@dataclass
class AllowListConfig:
    allowed_tools: dict[str, list[str]]   # server → [tool_names]
    filesystem_scope: str
    exec_blocklist: list[str]

class ActionAllowList:
    def __init__(self, config: AllowListConfig): ...

    def check(self, server: str, tool: str) -> None:
        """Raises ToolDeniedError if the tool is not allowed."""
```

**Internal responsibilities:**
- `check(server, tool)`: Look up `config.allowed_tools[server]`; if `tool` not in the list, raise `ToolDeniedError(server, tool)`.
- `ToolDeniedError` is caught by the MCP server dispatcher and returned as a `ToolError` JSON-RPC response to the agent. It is never propagated as a Python exception to the graph.
- The allow-list is loaded once at startup from `config/guardrails.yaml`; it is immutable at runtime.

---

#### `src/guardrails/budget.py`

**Purpose:** Track cumulative token usage per `run_id` and halt execution when the cap is reached.

**Public interface:**
```python
class BudgetGuard:
    def __init__(self, max_tokens_per_task: int): ...

    def check(self, run_id: UUID, estimated_tokens: int) -> None:
        """Raises BudgetExceededError if adding estimated_tokens would exceed cap."""

    def record(self, run_id: UUID, actual_tokens: int) -> None:
        """Record actual token usage after a successful LLM call."""

    def get_usage(self, run_id: UUID) -> int:
        """Return total tokens used so far for this run_id."""
```

**Internal responsibilities:**
- Maintain an in-memory `dict[UUID, int]` of cumulative tokens per `run_id`.
- `check`: if `current + estimated > max_tokens_per_task`, raise `BudgetExceededError`.
- `record`: add `actual_tokens` to the running total.
- Thread-safety: use a `threading.Lock` around dict access (needed if `--parallel N` is ever enabled).
- `BudgetExceededError` propagates up through the router to the graph, where it is caught by `SolverDriver` and sets `state["budget_exceeded"] = True`.

---

### 1.8 `src/metrics/` — Metrics Package

---

#### `src/metrics/hallucination.py`

**Purpose:** Statically detect references in a patch to files or symbols that do not exist in the repo.

**Public interface:**
```python
@dataclass
class HallucinationResult:
    score: float                    # 0.0 (none) to 1.0 (all references hallucinated)
    missing_paths: list[str]
    missing_symbols: list[str]

class HallucinationChecker:
    def check(self, patch: str, repo_path: Path) -> HallucinationResult: ...
```

**Internal responsibilities:**
1. Parse the unified diff to extract all `+++ b/{path}` file references.
2. For each referenced path: check if it exists in `repo_path`. Collect missing ones.
3. Parse added lines (`+` prefix) for Python import statements and function/class references.
4. Build a symbol table by scanning `repo_path` with `ast.parse` on all `.py` files.
5. Check each referenced symbol against the symbol table. Collect missing ones.
6. `score = (len(missing_paths) + len(missing_symbols)) / max(1, total_references)`.

**Design note:** This is a best-effort static check, not a semantic analysis. False positives (new symbols being defined in the patch itself) are acceptable; the score is a signal, not a gate.

---

#### `src/metrics/trace_store.py`

**Purpose:** SQLAlchemy-backed persistence for trace events and run records.

**Public interface:**
```python
@dataclass
class TraceEvent:
    event_id: UUID
    run_id: UUID
    task_id: str
    agent_role: str
    turn_index: int
    event_type: str              # "llm_call", "tool_call", "tool_error", "budget_exceeded"
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None
    cache_hit: bool
    payload: dict                # arbitrary JSON for event-specific data
    created_at: datetime

@dataclass
class RunRecord:
    run_id: UUID
    task_id: str
    solver_config: str           # JSON-serialized SolverConfig
    outcome: Literal["PASS", "FAIL"]
    total_cost_usd: float
    total_tokens: int
    iteration_count: int
    hallucination_score: float
    duration_seconds: float
    created_at: datetime

class TraceStore:
    def __init__(self, session_factory: sessionmaker): ...
    def write_trace_event(self, event: TraceEvent) -> None: ...
    def write_trace_events(self, events: list[TraceEvent]) -> None: ...
    def write_run_record(self, record: RunRecord) -> None: ...
    def get_run_records(self, filters: dict | None = None) -> list[RunRecord]: ...
    def get_trace_events(self, run_id: UUID) -> list[TraceEvent]: ...
```

**Internal responsibilities:**
- All writes use `session.add(); session.commit()` within a try/except; on failure, log and re-raise.
- `write_run_record` uses `INSERT ... ON CONFLICT (run_id, task_id) DO NOTHING` — run records are immutable; duplicate writes are silently ignored.
- `get_run_records` supports filtering by `solver_config`, `outcome`, and date range for the dashboard.

---

### 1.9 `src/db/` — Database Schema Package

---

#### `src/db/schema.py`

**Purpose:** SQLAlchemy ORM models for all database tables.

**Tables:**

```python
class LLMCacheEntry(Base):
    __tablename__ = "llm_cache"
    cache_key