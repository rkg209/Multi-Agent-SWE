# Tasks — Spec 02: Tool Layer + Sandbox

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [x] Create `src/sandbox/` and `src/tools/` packages with `__init__.py`
- [x] Add the MCP SDK (`mcp`) to `pyproject.toml` (only — servers run on the host, not in-container, so
      `requirements.txt` doesn't need it; see plan.md and progress_report.md Sequence 08)
- [x] Create `tests/unit/test_tools/` and `tests/integration/test_tools/` with `__init__.py`
- [x] Add a small fixture repo under `tests/fixtures/sample_repo/` for tool tests

## Sandbox wrapper

- [x] `src/sandbox/docker_sandbox.py`: `SandboxResult` dataclass + `run(cmd, task_dir, timeout=...)`
- [x] Build hardened `docker run`: `--rm --network none --cap-drop ALL --read-only --user <non-root> --tmpfs /tmp -v {task_dir}:/workspace:rw -w /workspace swe-sandbox:<pinned>`
- [x] Enforce 30s startup abort → return a harness-error result, not a solver FAIL (NFR-16)
- [x] Type hints + docstrings; no bare except; `logging` not `print`

## Makefile

- [x] Extend `sandbox-run` to accept `CMD="..."` (keep `SCRIPT=` working)

## Run-code MCP server

- [x] `src/tools/runcode_server.py`: MCP stdio server exposing `exec(command, working_dir)`
- [x] Delegate all execution to `docker_sandbox.run`; never shell out on host
- [x] Reject host-targeted / out-of-mount exec with a **structured error** (no exception across boundary)

## Filesystem MCP server

- [x] `src/tools/filesystem_server.py`: MCP server exposing `read_file`, `write_file`, `list_dir`, `exists`
- [x] Resolve every path against the snapshot root; reject escapes (`..`, absolute, symlink) with a structured error

## Git MCP server

- [x] `src/tools/git_server.py`: MCP server exposing `diff`, `stage`, `commit`
- [x] Operate only on the sandboxed repo clone / task dir

## Test driver + tests

- [x] Small driver that starts the servers and runs read→write→run→diff against the fixture repo
- [x] Unit: sandbox command has all hardening flags + correct mount
- [x] Unit: path scoping rejects escapes; run-code rejects host exec (structured error)
- [x] Integration: run `pytest` in sandbox; assert no-network; full loop — skip if Docker down
- [x] `make lint` exits 0
- [x] `make test` exits 0

## Acceptance

- [x] Verify each done-when criterion in `spec.md`
- [x] Add `## Status` → `Complete.` to `spec.md`
