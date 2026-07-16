# Spec 02: Tool Layer (System MCP Servers) + Sandbox

## Goal

Give the system's agents a safe, uniform way to touch a repository and run code. This spec implements three **application-level MCP servers** — filesystem, run-code, and git — as Python code in this repository (distinct from the Claude Code dev MCP servers), plus the per-task Docker sandbox they route through. The filesystem server reads/writes/lists/checks paths scoped to a task's repo snapshot; the run-code server executes shell commands **only** inside an isolated Docker container with no host access; the git server does diff/stage/commit against the sandboxed clone. This is the layer that makes the sandbox-safety rule real at runtime (NFR-1 layer (a)) and the substrate every solver in Specs 04+ writes code and runs tests through.

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-14 | Filesystem MCP server: read/write/list/exists, scoped to the task repo snapshot. |
| FR-15 | Run-code MCP server: execute shell commands **only** inside Docker; reject host-targeted execution. |
| FR-16 | Git MCP server: read diff, stage files, create commit, scoped to the sandboxed clone. |
| FR-17 | All three servers implemented as Python app code here and invocable by LangGraph agent nodes at runtime. |
| FR-18 | The Docker sandbox is a separate, isolated container per task run; no host network; mounts only the task snapshot dir. |
| FR-19 | `make sandbox-run CMD="..."` executes a command in the sandbox and returns stdout/stderr/exit-code. |
| NFR-1 | Generated code never runs on host — run-code server rejects non-sandbox execution (layer (a)). |
| NFR-2 | Sandbox runs non-root, read-only root FS (except mounted task dir), `--cap-drop ALL`. |

## Non-Goals

- No agent logic — these are tools an agent *will* call, not an agent. The caller in this spec is a test harness / thin driver.
- No benchmark task loading or scoring — that is Spec 03.
- No action allow-list / safety pre-check gate — the structured allow-list enforcement is Spec 07 (`src/guardrails/allowlist.py`). This spec enforces the hard sandbox boundary only.
- No LangGraph wiring — servers must be *invocable* by nodes, but the graph is Specs 04/06.
- No SWE-bench-specific image provisioning — the sandbox image is the general one from Spec 00 (extended if needed).

## Done-When

All of the following are true and verifiable:

- [x] `src/tools/filesystem_server.py`, `src/tools/runcode_server.py`, `src/tools/git_server.py` exist as MCP servers (stdio transport) exposing their documented tools.
- [x] `src/sandbox/docker_sandbox.py` creates a per-task container, runs a command, returns `(stdout, stderr, exit_code)`, and tears it down (`--rm`), with `--network none`, non-root user, `--cap-drop ALL`, read-only root FS, and only the task dir mounted.
- [x] The run-code server refuses any exec that targets a path outside the mounted task dir or attempts host execution, returning a **structured error** (not a crash).
- [x] An agent-style caller (test driver) can, against a sample repo snapshot: read a file, write a file, list a dir, check existence, run `pytest` in the sandbox, and get a git diff of its change.
- [x] `make sandbox-run CMD="python -c 'print(42)'"` prints `42` with exit code 0 (extends the Spec 00 `SCRIPT=` form to accept `CMD=`).
- [x] A test asserts the sandbox has no host network access (e.g. a command needing the network fails inside the sandbox).
- [x] `make lint` exits 0.
- [x] `make test` exits 0 (unit tests mock Docker/subprocess; integration tests that need Docker skip cleanly when Docker is unavailable).
- [x] No agent-generated code runs on the host (sandbox rule intact).

## Depends-On

- `specs/00-foundation` — Docker sandbox image (`swe-sandbox:latest`), `scripts/sandbox_exec.py`, Makefile, `block-host-exec` hook.

## Status

Complete.
