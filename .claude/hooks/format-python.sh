#!/usr/bin/env bash
# format-python.sh — PostToolUse hook for Write|Edit tools
#
# PURPOSE: Auto-format any Python file that Claude Code writes or edits.
#   Runs `ruff check --fix` (lint + auto-fix) then `black` (formatting).
#
# EXIT CODES:
#   0  always — this hook is informational; it never blocks writes.
#
# INPUT: JSON from stdin in the format:
#   {"session_id": "...", "hook_event_name": "PostToolUse", "tool_name": "Write"|"Edit",
#    "tool_input": {"file_path": "/abs/path/to/file.py", ...}, "tool_response": {...}}

set -uo pipefail

# ── Read stdin ────────────────────────────────────────────────────────────────
INPUT="$(cat)"

# Require jq
if ! command -v jq &>/dev/null; then
  echo "format-python: jq not found, skipping format step" >&2
  exit 0
fi

FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Only act on Python files
if [[ "$FILE_PATH" != *.py ]]; then
  exit 0
fi

# File must actually exist on disk (might have been a Delete, etc.)
if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# ── Run ruff ──────────────────────────────────────────────────────────────────
if command -v ruff &>/dev/null; then
  echo "format-python: ruff check --fix $FILE_PATH" >&2
  if ! ruff check --fix --quiet "$FILE_PATH" 2>&1; then
    echo "format-python: ruff reported unfixable issues in $FILE_PATH (see above)" >&2
    # Continue to black; do not exit 2
  fi
else
  echo "format-python: ruff not found in PATH — skipping ruff step" >&2
fi

# ── Run black ─────────────────────────────────────────────────────────────────
if command -v black &>/dev/null; then
  echo "format-python: black $FILE_PATH" >&2
  if ! black --quiet "$FILE_PATH" 2>&1; then
    echo "format-python: black failed on $FILE_PATH" >&2
  fi
else
  echo "format-python: black not found in PATH — skipping black step" >&2
fi

# ── Always exit 0 ─────────────────────────────────────────────────────────────
exit 0
