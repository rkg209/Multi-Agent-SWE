#!/usr/bin/env bash
# block-host-exec.sh — PreToolUse hook for Bash tool
#
# PURPOSE: Enforce the sandbox safety rule.
#   - Generated/untrusted code must NEVER run directly on the host.
#   - All execution of agent-generated code must go through `make sandbox-run`
#     or the Docker wrapper (scripts/sandbox_exec.py).
#
# EXIT CODES (Claude Code hook contract):
#   0  = allow the command
#   2  = hard block (Claude Code will NOT run the command; shows this script's stderr)
#
# INPUT: JSON from stdin in the format:
#   {"session_id": "...", "hook_event_name": "PreToolUse", "tool_name": "Bash",
#    "tool_input": {"command": "the shell command string"}}

set -euo pipefail

# ── Read and parse stdin ───────────────────────────────────────────────────────
INPUT="$(cat)"

# Require jq; if missing, fail open (allow) to avoid blocking all bash.
if ! command -v jq &>/dev/null; then
  echo "block-host-exec: jq not found, skipping safety check" >&2
  exit 0
fi

CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)"

if [[ -z "$CMD" ]]; then
  # Not a Bash tool call with a command field — allow.
  exit 0
fi

# ── Helper ─────────────────────────────────────────────────────────────────────
block() {
  local reason="$1"
  echo "" >&2
  echo "╔══════════════════════════════════════════════════════════════╗" >&2
  echo "║  SAFETY BLOCK: block-host-exec hook                        ║" >&2
  echo "╠══════════════════════════════════════════════════════════════╣" >&2
  printf "║  Reason: %-51s║\n" "$reason" >&2
  echo "╠══════════════════════════════════════════════════════════════╣" >&2
  echo "║  To run agent code, use:                                   ║" >&2
  echo "║    make sandbox-run SCRIPT=<path>                          ║" >&2
  echo "║    python scripts/sandbox_exec.py <path>                   ║" >&2
  echo "╚══════════════════════════════════════════════════════════════╝" >&2
  echo "" >&2
  echo "Blocked command was:" >&2
  echo "  $CMD" >&2
  exit 2
}

# ── Rule 1: Direct execution of agent/tool/benchmark code outside Docker ──────
# Patterns that indicate running project source directly on the host.

# python src/agents/... or python -m src.agents...
if echo "$CMD" | grep -qE '(^|[[:space:]|;|&])python[0-9.]?\s+(src/agents/|src/tools/|src/harness/|benchmark/)'; then
  block "Direct host execution of agent/tool/benchmark code"
fi

# python -m src.agents / python -m src.tools / python -m benchmark
if echo "$CMD" | grep -qE '(^|[[:space:]|;|&])python[0-9.]?\s+-m\s+src\.(agents|tools|harness|router)|python[0-9.]?\s+-m\s+benchmark'; then
  block "Direct host execution via -m of agent/benchmark module"
fi

# uvicorn / gunicorn starting the agent server directly (outside docker compose)
if echo "$CMD" | grep -qE '(uvicorn|gunicorn)\s+src\.(agents|harness)'; then
  block "Launching agent server directly on host (use docker compose)"
fi

# Running any .py file that lives under src/agents, src/tools, src/harness, benchmark/
if echo "$CMD" | grep -qE '(^|[[:space:]|;|&])(python[0-9.]?|python3)\s+[^[:space:]]*(src/(agents|tools|harness)|benchmark/)[^[:space:]]*\.py'; then
  block "Direct host execution of file in src/agents|src/tools|src/harness|benchmark/"
fi

# ── Rule 2: Destructive filesystem operations ─────────────────────────────────
if echo "$CMD" | grep -qE 'rm\s+-rf\s+/([[:space:]]|$)'; then
  block "rm -rf / (root filesystem wipe)"
fi

if echo "$CMD" | grep -qE 'rm\s+-rf\s+~([[:space:]]|$|/)'; then
  block "rm -rf ~ (home directory wipe)"
fi

if echo "$CMD" | grep -qE 'rm\s+-rf\s+\$HOME([[:space:]]|$|/)'; then
  block "rm -rf \$HOME (home directory wipe)"
fi

# Wipe the entire project directory
if echo "$CMD" | grep -qE 'rm\s+-rf\s+\.\s*$'; then
  block "rm -rf . (project directory wipe)"
fi

# ── Rule 3: Dangerous git operations ──────────────────────────────────────────
if echo "$CMD" | grep -qE 'git\s+push\s+(--force|-f)(\s|$)'; then
  block "git push --force (use a safer push strategy)"
fi

if echo "$CMD" | grep -qE 'git\s+reset\s+--hard(\s|$)'; then
  block "git reset --hard (destructive; could lose uncommitted work)"
fi

# ── Rule 4: Dangerous SQL ─────────────────────────────────────────────────────
# Catch DROP TABLE / DROP DATABASE / TRUNCATE with no obvious psql -c wrapper
if echo "$CMD" | grep -iqE '(drop\s+table|drop\s+database|truncate\s+table)'; then
  # Allow if it's clearly inside a psql invocation (migration script) — still warn
  if echo "$CMD" | grep -qE '(psql|pg_dump|pg_restore)'; then
    echo "block-host-exec WARNING: SQL DROP/TRUNCATE detected inside psql call — proceeding but verify intent." >&2
  else
    block "DROP TABLE / DROP DATABASE / TRUNCATE outside a psql call"
  fi
fi

# ── Rule 5: Curl/wget piped directly to bash (arbitrary code execution) ───────
if echo "$CMD" | grep -qE '(curl|wget)\s+.*\|\s*(bash|sh|zsh|python)'; then
  block "curl/wget piped directly to shell interpreter"
fi

# ── All checks passed — allow ──────────────────────────────────────────────────
exit 0
