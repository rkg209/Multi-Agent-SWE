---
description: Run the SWE-bench benchmark harness. Usage: /run-bench [TASKS=lite-5|lite-30|custom] [SOLVER=single|multi]. Executes make benchmark in an isolated subagent context and streams results.
context: fork
---

# Skill: run-bench

Execute the benchmark harness against a set of SWE-bench tasks and report results.

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `TASKS` | `lite-5` | Task set: `lite-5`, `lite-30`, `full`, or `custom` |
| `SOLVER` | `multi` | Solver mode: `single` (one-agent baseline) or `multi` (4-agent system) |
| `TASK_FILE` | _(none)_ | When `TASKS=custom`, path to a newline-separated task ID file |

## Instructions

1. Parse the arguments from the user's message. Defaults: `TASKS=lite-5`, `SOLVER=multi`.

2. Remind the user of the sandbox rule: all task execution happens inside Docker. Confirm before proceeding if `TASKS` is `lite-30` or `full` (these take >30 minutes).

3. Build the make command:
   - Standard: `make benchmark TASKS=<TASKS> SOLVER=<SOLVER>`
   - Custom tasks: `make benchmark TASKS=custom TASK_FILE=<TASK_FILE> SOLVER=<SOLVER>`

4. Run the command via Bash. Stream output to the user as it runs.

5. When the run completes, extract and display:
   - **Resolve rate**: `resolved / total` tasks
   - **Mean cost per task** (USD)
   - **Mean tokens per task** (input + output)
   - **Run ID** (UUID from the Postgres insert)
   - **Report path**: `reports/<run-id>/summary.json`

6. If the run fails, display the last 50 lines of output and suggest:
   - `make db-shell` to inspect partial results
   - `/trace <run-id>` to retrieve the full event trace
   - `/harness-debugger` sub-agent for Docker/sb-cli issues

## Example Output

```
Benchmark run complete
━━━━━━━━━━━━━━━━━━━━━━━━━
Tasks        : lite-5
Solver       : multi
Resolve rate : 3/5 (60.0%)
Mean cost    : $0.043 / task
Mean tokens  : 12,450 input + 3,210 output
Run ID       : a3f2c1d0-...
Report       : reports/a3f2c1d0-.../summary.json
━━━━━━━━━━━━━━━━━━━━━━━━━
Use /trace a3f2c1d0-... for per-task event details.
```
