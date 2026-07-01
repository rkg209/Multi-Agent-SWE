# Implementation Plan — Spec 02: Tool Layer + Sandbox

## Overview

Build the sandbox wrapper first (`src/sandbox/docker_sandbox.py`), then wrap it and the filesystem/git operations in three MCP servers that speak the MCP stdio protocol. The sandbox is the single choke-point for all code execution; the run-code server never shells out on the host — it always delegates to the sandbox. Filesystem and git operations are path-scoped to the task snapshot directory. The whole layer is exercised in this spec by a plain Python test driver (standing in for the future agent nodes).

## Key Decisions

1. **Sandbox is the only exec path.** `docker_sandbox.py::run(cmd, task_dir)` is the one function that invokes Docker. The run-code server calls it; nothing else executes commands. This makes NFR-1 layer (a) a single auditable point.
2. **Per-task, one-shot containers.** Each exec is `docker run --rm --network none --cap-drop ALL --read-only --user <non-root> -v {task_dir}:/workspace:rw -w /workspace swe-sandbox:<pinned>`. The task dir is the only writable mount (agents must write code somewhere); root FS is read-only (NFR-2, FR-18).
3. **MCP stdio servers, spawned as subprocesses.** Per the architecture doc, the benchmark CLI spawns each server as a subprocess using MCP stdio transport; agent nodes talk JSON-RPC over stdin/stdout. No network ports for the tool layer.
4. **Path scoping enforced at the server boundary.** Filesystem/git servers resolve every path against the task snapshot root and reject (structured error) anything that escapes it (`..`, absolute paths outside root, symlink escape).
5. **Structured errors, not exceptions, across the tool boundary.** A rejected action returns `{"error": {...}}` to the caller (agent), matching FR-45's later contract; internal bugs still raise.
6. **`CMD=` added to `make sandbox-run`.** Spec 00's target took `SCRIPT=`; extend it to also accept `CMD="..."` for arbitrary in-sandbox commands (FR-19), keeping `SCRIPT=` working.

## Implementation Order

1. **`src/sandbox/docker_sandbox.py`** — `run(cmd, task_dir, timeout) -> SandboxResult(stdout, stderr, exit_code)`; build the hardened `docker run` invocation; enforce 30s startup abort (NFR-16). Unit-test the command construction with mocked subprocess.
2. **`make sandbox-run CMD=...`** — extend the Makefile target; smoke-test with a trivial command.
3. **`src/tools/runcode_server.py`** — MCP server exposing `exec(command, working_dir)`; delegates to the sandbox; rejects host-targeted / out-of-mount requests with a structured error.
4. **`src/tools/filesystem_server.py`** — MCP server exposing `read_file`, `write_file`, `list_dir`, `exists`; all path-scoped to the snapshot root.
5. **`src/tools/git_server.py`** — MCP server exposing `diff`, `stage`, `commit`; runs git against the sandboxed clone (via the sandbox or a scoped subprocess in the task dir).
6. **Test driver + tests** — a small in-repo driver that spins up the servers and performs the full read→write→run→diff loop against a fixture repo.

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| Read-only root FS breaks tools that write to `/tmp` | Mount a small `tmpfs` at `/tmp`; keep task dir the only persistent writable mount. |
| Non-root user can't write to mounted task dir | Set ownership / `--user` to match; document required uid; test the write path. |
| MCP stdio plumbing is fiddly | Start with a minimal MCP server using the reference Python MCP SDK; one tool end-to-end before adding the rest. |
| Path-escape via symlinks | Resolve realpath and assert it is within the snapshot root before any op. |
| Docker not present in CI | Unit tests mock subprocess; integration tests skip when `docker ps` fails (DR-6). |
| Sandbox startup > 30s | Abort and surface a harness error, not a solver FAIL (NFR-16). |

## Testing Strategy

- Unit tests: `tests/unit/test_tools/` — sandbox command construction (flags present: `--network none`, `--cap-drop ALL`, `--read-only`, non-root user, correct mount); path-scoping rejects `..`/absolute escapes; run-code rejects host exec with a structured error.
- Integration tests: `tests/integration/test_tools/` — real Docker: run `pytest` in the sandbox on a fixture repo; assert no-network (a network command fails); full read→write→run→diff loop. Skip when Docker unavailable.
- Manual check: `make sandbox-run CMD="python -c 'print(42)'"` → `42`; `make sandbox-run CMD="curl https://example.com"` fails (no network).
