---
description: Score a single patch against SWE-bench hidden tests. Usage: /score-patch <task-id>. Useful for debugging a specific task without running the full benchmark.
context: fork
---

# Skill: score-patch

Run the deterministic SWE-bench scorer on a single task's patch. Use this for rapid debugging of an individual task without incurring the cost of a full benchmark run.

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `task-id` | Yes | SWE-bench task ID, e.g. `django__django-11099` or `sympy__sympy-20442` |
| `patch-file` | No | Path to a `.patch` file. If omitted, reads the most recent patch from `reports/latest/patches/<task-id>.patch` |

## Instructions

1. Parse the task ID from the user's message. If no task ID is provided, ask for one.

2. Locate the patch file:
   - If `patch-file` argument given: use it directly (verify it exists).
   - Otherwise: look for `reports/latest/patches/<task-id>.patch`.
   - If neither exists: list available patches in `reports/latest/patches/` and ask the user to specify.

3. Confirm the task ID and patch location before scoring.

4. Run the scorer:
   ```bash
   make sandbox-run SCRIPT=scripts/score_patch.py ARGS="--task <task-id> --patch <patch-file>"
   ```
   
   This executes entirely inside Docker (sandbox rule applies).

5. Parse and display the scorer output:

   ```
   Score result for <task-id>
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Status        : PASS | FAIL | ERROR
   Tests passed  : N / M
   Tests failed  : list of failing test names
   Error         : (if status=ERROR, the error message)
   Patch applied : yes | no (patch apply failed)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

6. If `status=FAIL`:
   - Show the first 3 failing test names.
   - Suggest the Architect agent review the plan for this task type.
   - Remind the user that the hidden tests check correctness, not just linting.

7. If `status=ERROR`:
   - Show the error in full.
   - Suggest `/harness-debugger` if the error looks like a Docker or dependency issue.
   - Suggest `/trace <run-id>` if the error occurred during a benchmark run.

## Notes

- Scoring is deterministic: same patch + same task always produces the same result.
- The scorer uses the official SWE-bench test harness inside Docker; it does NOT run on the host.
- Cost: essentially zero (no LLM calls), only Docker execution time (~10-60s per task).
