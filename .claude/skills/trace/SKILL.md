---
description: Retrieve and display a benchmark run trace from Postgres. Usage: /trace <run-id>. Shows agent turns, token usage, costs, and failure points for a given run UUID.
---

# Skill: trace

Query the Postgres metrics database for a complete run trace and display a structured summary.

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `run-id` | Yes | UUID of the benchmark run (printed at end of `make benchmark` and by `/run-bench`) |

## Instructions

1. Parse the run UUID from the user's message. Validate it looks like a UUID (8-4-4-4-12 hex format). If invalid, tell the user.

2. Query Postgres via `make db-shell` or `psql` directly. Run the following queries (adapt table names to match the actual schema in `scripts/db_init.sql`):

   **a) Run metadata:**
   ```sql
   SELECT run_id, solver_mode, task_set, started_at, finished_at,
          total_tasks, resolved_tasks, total_cost_usd
   FROM benchmark_runs
   WHERE run_id = '<run-id>';
   ```

   **b) Per-task summary:**
   ```sql
   SELECT task_id, status, resolve_status, cost_usd,
          input_tokens, output_tokens, iteration_count, error_message
   FROM task_results
   WHERE run_id = '<run-id>'
   ORDER BY started_at;
   ```

   **c) Agent turn events for failed tasks:**
   ```sql
   SELECT task_id, agent_name, turn_index, event_type,
          input_tokens, output_tokens, cost_usd, created_at, notes
   FROM agent_events
   WHERE run_id = '<run-id>'
     AND task_id IN (
       SELECT task_id FROM task_results
       WHERE run_id = '<run-id>' AND resolve_status = 'FAIL'
     )
   ORDER BY task_id, turn_index;
   ```

3. Format and display:

   ```
   Run Trace: <run-id>
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Solver      : single | multi
   Task set    : lite-5 / lite-30 / etc.
   Started     : 2024-01-15 10:23:44 UTC
   Finished    : 2024-01-15 11:02:11 UTC  (38m 27s)
   Resolve     : 3 / 5 (60.0%)
   Total cost  : $0.214

   Per-Task Results:
   ┌─────────────────────────────────┬──────┬────────┬──────────┬────────┬──────┐
   │ Task ID                         │Status│Resolved│ Cost USD │Tokens  │Iters │
   ├─────────────────────────────────┼──────┼────────┼──────────┼────────┼──────┤
   │ django__django-11099            │ OK   │ PASS   │  $0.041  │ 15,230 │  2   │
   │ sympy__sympy-20442              │ OK   │ FAIL   │  $0.038  │ 14,100 │  3   │
   │ ...                             │      │        │          │        │      │
   └─────────────────────────────────┴──────┴────────┴──────────┴────────┴──────┘

   Failed Task Details:
   ─── sympy__sympy-20442 ───────────────────────────────
   Error    : patch did not apply cleanly
   Turn log :
     [0] Architect  →  plan (1,200 in / 420 out)  $0.004
     [1] Developer  →  patch (3,100 in / 890 out)  $0.012
     [2] Tester     →  test (2,800 in / 310 out)  $0.009
     [3] Developer  →  retry (3,400 in / 760 out)  $0.013
     [4] Reviewer   →  reject (1,900 in / 280 out)  $0.007
   Failure at turn 4: Reviewer rejected patch (diff too large, likely hallucinated file)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

4. After displaying, offer next steps:
   - "Use `/score-patch <task-id>` to re-score a task with a revised patch."
   - "Use `make db-shell` for ad-hoc SQL queries on this run."
   - "If failures are Docker/env related, use the `/harness-debugger` agent."

## Notes

- If the run_id is not found in Postgres, the run may have failed before inserting a row — check `logs/benchmark-<date>.log`.
- Token costs in the trace use per-token prices from `config/litellm_config.yaml`, not live Anthropic pricing (these are the open model costs).
