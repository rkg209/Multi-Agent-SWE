#!/usr/bin/env bash
# fast-tests.sh — PostToolUse hook for Write|Edit tools (src/ files only)
#
# PURPOSE: Run the fast unit test suite whenever a file under src/ is edited.
#   Gives rapid feedback without blocking Claude Code's write operation.
#
# EXIT CODES:
#   0  always — failures are printed to stderr but do not block writes.
#
# INPUT: JSON from stdin in the format:
#   {"session_id": "...", "hook_event_name": "PostToolUse", "tool_name": "Write"|"Edit",
#    "tool_input": {"file_path": "/abs/path/to/file.py", ...}, "tool_response": {...}}

set -uo pipefail

# ── Read stdin ────────────────────────────────────────────────────────────────
INPUT="$(cat)"

if ! command -v jq &>/dev/null; then
  echo "fast-tests: jq not found, skipping test run" >&2
  exit 0
fi

FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# ── Only trigger for files under src/ ─────────────────────────────────────────
# Normalise: strip trailing slashes, support both absolute and relative paths
NORMALISED="$(realpath "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")"

# Check if path contains /src/ or ends with a src/ prefix pattern
if ! echo "$NORMALISED" | grep -qE '/src/'; then
  exit 0
fi

# Only run for Python files (no point running tests for a changed .yaml, etc.)
if [[ "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# ── Find project root (where Makefile lives) ───────────────────────────────────
# Walk up from the file's directory until we find a Makefile or pyproject.toml
PROJECT_ROOT="$(dirname "$NORMALISED")"
while [[ "$PROJECT_ROOT" != "/" ]]; do
  if [[ -f "$PROJECT_ROOT/Makefile" ]] || [[ -f "$PROJECT_ROOT/pyproject.toml" ]]; then
    break
  fi
  PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done

if [[ "$PROJECT_ROOT" == "/" ]]; then
  echo "fast-tests: could not locate project root (no Makefile/pyproject.toml)" >&2
  exit 0
fi

echo "" >&2
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
echo "fast-tests: src/ file changed — running unit tests"    >&2
echo "  File   : $FILE_PATH"                                 >&2
echo "  Root   : $PROJECT_ROOT"                              >&2
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2

cd "$PROJECT_ROOT"

# ── Prefer `make test` if Makefile exists; fallback to pytest directly ─────────
if [[ -f "Makefile" ]] && grep -q '^test:' Makefile 2>/dev/null; then
  TEST_OUTPUT="$(make test 2>&1)"
  TEST_EXIT=$?
else
  # Fallback: run unit tests directly
  if command -v pytest &>/dev/null; then
    TEST_OUTPUT="$(pytest tests/unit/ -x -q --tb=short 2>&1)"
    TEST_EXIT=$?
  else
    echo "fast-tests: pytest not found in PATH — skipping" >&2
    exit 0
  fi
fi

# ── Report results ────────────────────────────────────────────────────────────
if [[ $TEST_EXIT -eq 0 ]]; then
  echo "fast-tests: all unit tests passed." >&2
  # Print last line of output (usually something like "3 passed in 0.12s")
  echo "$TEST_OUTPUT" | tail -1 >&2
else
  echo "" >&2
  echo "fast-tests: FAILURES DETECTED — review before marking task done:" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "$TEST_OUTPUT" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "" >&2
fi

echo "" >&2

# Always exit 0 — informational only, never block the write.
exit 0
