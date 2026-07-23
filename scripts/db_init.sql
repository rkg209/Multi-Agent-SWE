-- =============================================================================
-- DATABASE SCHEMA — Multi-Agent SWE Benchmark System
-- =============================================================================
-- Ported from planning/04-database-design.md / planning/04-database-schema.sql
-- (the "Implementation-Ready v1.0" schema). Run idempotently by `make setup`
-- via `psql $DATABASE_URL -f scripts/db_init.sql`.
--
-- Conventions:
--   - All primary keys are UUIDs (gen_random_uuid() via pgcrypto).
--   - Timestamps are TIMESTAMPTZ (UTC). Monetary amounts are NUMERIC(12,8).
--   - JSON payloads are JSONB. All tables live in the "benchmark" schema.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS benchmark;

SET search_path = benchmark, public;

-- Persist the search_path on the database itself so that `make db-shell`
-- (a fresh psql connection) sees `benchmark` objects without manual SET.
ALTER DATABASE benchmark_db SET search_path TO benchmark, public;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- TABLE: llm_cache
-- =============================================================================
-- Permanent, immutable LLM response cache keyed on SHA-256(model||messages).
-- First write wins (ON CONFLICT DO NOTHING); no TTL — exists for reproducible
-- benchmark runs, not cost savings on ad-hoc queries.
-- =============================================================================

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key       CHAR(64)        NOT NULL,   -- SHA-256 hex, always 64 chars
    model           TEXT            NOT NULL,
    content         TEXT            NOT NULL,
    tool_calls      JSONB           NULL,
    usage           JSONB           NOT NULL,   -- {prompt_tokens, completion_tokens}
    cost_usd        NUMERIC(12, 8)  NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT llm_cache_pk PRIMARY KEY (cache_key),
    CONSTRAINT llm_cache_cost_non_negative CHECK (cost_usd >= 0)
);

COMMENT ON TABLE  llm_cache                IS 'Permanent, immutable LLM response cache keyed on SHA-256(model||messages). First write wins; no TTL.';
COMMENT ON COLUMN llm_cache.cache_key      IS 'SHA-256 hex digest of (model_name || canonical_json(messages)).';
COMMENT ON COLUMN llm_cache.model          IS 'Fully-qualified LiteLLM model name used for this call.';
COMMENT ON COLUMN llm_cache.content        IS 'Raw assistant-turn text content.';
COMMENT ON COLUMN llm_cache.tool_calls     IS 'JSON array of tool-call objects, or NULL if none.';
COMMENT ON COLUMN llm_cache.usage          IS 'TokenUsage snapshot: {prompt_tokens: int, completion_tokens: int}.';
COMMENT ON COLUMN llm_cache.cost_usd       IS 'USD cost computed at write time from config/models.yaml pricing.';

-- =============================================================================
-- TABLE: trace_events
-- =============================================================================
-- Append-only log of every observable event in a solver run. Written by
-- src/metrics/trace_store.py; never updated or deleted.
--
-- event_type: llm_call | tool_call | tool_error | budget_exceeded | cap_hit | agent_turn
-- agent_role: architect | developer | tester | reviewer | system
-- =============================================================================

CREATE TABLE IF NOT EXISTS trace_events (
    event_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    run_id              UUID            NOT NULL,
    task_id             TEXT            NOT NULL,
    agent_role          TEXT            NOT NULL,
    turn_index           INTEGER         NOT NULL,
    event_type          TEXT            NOT NULL,
    model               TEXT            NULL,       -- NULL for non-LLM events
    prompt_tokens       INTEGER         NULL,       -- NULL for non-LLM events
    completion_tokens   INTEGER         NULL,       -- NULL for non-LLM events
    cost_usd            NUMERIC(12, 8)  NULL,       -- NULL for non-LLM events
    cache_hit           BOOLEAN         NOT NULL DEFAULT FALSE,
    payload             JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT trace_events_pk
        PRIMARY KEY (event_id),
    CONSTRAINT trace_events_turn_index_non_negative
        CHECK (turn_index >= 0),
    CONSTRAINT trace_events_prompt_tokens_non_negative
        CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    CONSTRAINT trace_events_completion_tokens_non_negative
        CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    CONSTRAINT trace_events_cost_non_negative
        CHECK (cost_usd IS NULL OR cost_usd >= 0),
    CONSTRAINT trace_events_event_type_valid
        CHECK (event_type IN (
            'llm_call', 'tool_call', 'tool_error', 'budget_exceeded', 'cap_hit'
        )),
    CONSTRAINT trace_events_agent_role_valid
        CHECK (agent_role IN (
            'architect', 'developer', 'tester', 'reviewer', 'system'
        ))
);

COMMENT ON TABLE  trace_events                    IS 'Append-only event log for every observable action in a solver run. Never updated or deleted.';
COMMENT ON COLUMN trace_events.event_id           IS 'UUID primary key, generated by the application.';
COMMENT ON COLUMN trace_events.run_id             IS 'UUID of the benchmark run that produced this event. FK to run_records.run_id (not enforced as FK to allow out-of-order writes).';
COMMENT ON COLUMN trace_events.task_id            IS 'SWE-bench or custom task identifier string.';
COMMENT ON COLUMN trace_events.agent_role         IS 'Which agent produced this event: architect|developer|tester|reviewer|system.';
COMMENT ON COLUMN trace_events.turn_index         IS 'Zero-based index of the agent turn within this run+task.';
COMMENT ON COLUMN trace_events.event_type         IS 'Discriminator: llm_call|tool_call|tool_error|budget_exceeded|cap_hit.';
COMMENT ON COLUMN trace_events.model              IS 'Fully-qualified model name; NULL for non-LLM events.';
COMMENT ON COLUMN trace_events.prompt_tokens      IS 'Input token count; NULL for non-LLM events.';
COMMENT ON COLUMN trace_events.completion_tokens  IS 'Output token count; NULL for non-LLM events.';
COMMENT ON COLUMN trace_events.cost_usd           IS 'USD cost for this call; 0 for cache hits; NULL for non-LLM events.';
COMMENT ON COLUMN trace_events.cache_hit          IS 'TRUE if this LLM call was served from the response cache.';
COMMENT ON COLUMN trace_events.payload            IS 'Event-type-specific JSON data. See table comment for per-type schema.';
COMMENT ON COLUMN trace_events.created_at         IS 'Wall-clock UTC timestamp of the event.';

CREATE INDEX IF NOT EXISTS trace_events_run_id_idx
    ON trace_events (run_id);

CREATE INDEX IF NOT EXISTS trace_events_task_id_idx
    ON trace_events (task_id);

CREATE INDEX IF NOT EXISTS trace_events_run_id_cost_idx
    ON trace_events (run_id, cost_usd)
    WHERE event_type = 'llm_call';

CREATE INDEX IF NOT EXISTS trace_events_run_id_created_at_idx
    ON trace_events (run_id, created_at);

-- Spec 05: full agent-turn tracing (FR-29). Idempotent — safe to re-run on an
-- existing volume (`make setup` after this spec landed).
ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS duration_ms INTEGER NULL;

ALTER TABLE trace_events DROP CONSTRAINT IF EXISTS trace_events_event_type_valid;
ALTER TABLE trace_events ADD  CONSTRAINT trace_events_event_type_valid
    CHECK (event_type IN (
        'llm_call', 'tool_call', 'tool_error', 'budget_exceeded', 'cap_hit', 'agent_turn'
    ));

ALTER TABLE trace_events DROP CONSTRAINT IF EXISTS trace_events_duration_non_negative;
ALTER TABLE trace_events ADD  CONSTRAINT trace_events_duration_non_negative
    CHECK (duration_ms IS NULL OR duration_ms >= 0);

COMMENT ON COLUMN trace_events.duration_ms IS 'Wall-clock duration of an agent_turn event in milliseconds; NULL for non-turn events.';

CREATE INDEX IF NOT EXISTS trace_events_run_task_turn_idx
    ON trace_events (run_id, task_id, turn_index);

-- =============================================================================
-- TABLE: run_records
-- =============================================================================
-- One row per (run_id, task_id) pair. Written once by MetricsWriter after the
-- scorer returns. Immutable: ON CONFLICT DO NOTHING.
-- =============================================================================

CREATE TABLE IF NOT EXISTS run_records (
    run_id                  UUID            NOT NULL,
    task_id                 TEXT            NOT NULL,
    solver_config           JSONB           NOT NULL,
    outcome                 TEXT            NOT NULL,
    total_cost_usd          NUMERIC(12, 8)  NOT NULL DEFAULT 0,
    total_tokens            INTEGER         NOT NULL DEFAULT 0,
    iteration_count         INTEGER         NOT NULL DEFAULT 0,
    hallucination_score     NUMERIC(5, 4)   NOT NULL DEFAULT 0,
    duration_seconds        NUMERIC(10, 3)  NOT NULL DEFAULT 0,
    cap_hit                 BOOLEAN         NOT NULL DEFAULT FALSE,
    budget_exceeded         BOOLEAN         NOT NULL DEFAULT FALSE,
    patch_size_bytes        INTEGER         NULL,    -- byte length of the final unified diff
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT run_records_pk
        PRIMARY KEY (run_id, task_id),
    CONSTRAINT run_records_outcome_valid
        CHECK (outcome IN ('PASS', 'FAIL')),
    CONSTRAINT run_records_total_cost_non_negative
        CHECK (total_cost_usd >= 0),
    CONSTRAINT run_records_total_tokens_non_negative
        CHECK (total_tokens >= 0),
    CONSTRAINT run_records_iteration_count_non_negative
        CHECK (iteration_count >= 0),
    CONSTRAINT run_records_hallucination_score_range
        CHECK (hallucination_score >= 0.0 AND hallucination_score <= 1.0),
    CONSTRAINT run_records_duration_non_negative
        CHECK (duration_seconds >= 0)
);

COMMENT ON TABLE  run_records                       IS 'One immutable row per (run_id, task_id). Written once by MetricsWriter; ON CONFLICT DO NOTHING.';
COMMENT ON COLUMN run_records.run_id                IS 'UUID4 generated by benchmark/cli.py at the start of each benchmark run.';
COMMENT ON COLUMN run_records.task_id               IS 'SWE-bench or custom task identifier string.';
COMMENT ON COLUMN run_records.solver_config         IS 'JSON-serialized SolverConfig: {solver, max_dev_tester_iterations, max_dev_reviewer_iterations, max_tokens_per_task}.';
COMMENT ON COLUMN run_records.outcome               IS 'Deterministic scorer verdict: PASS or FAIL.';
COMMENT ON COLUMN run_records.total_cost_usd        IS 'Sum of cost_usd across all trace_events for this (run_id, task_id).';
COMMENT ON COLUMN run_records.total_tokens          IS 'Sum of prompt_tokens + completion_tokens across all LLM trace_events.';
COMMENT ON COLUMN run_records.iteration_count       IS 'dev_tester_iterations + dev_reviewer_iterations from the final GraphState.';
COMMENT ON COLUMN run_records.hallucination_score   IS 'Float [0,1] from HallucinationChecker: fraction of patch references that do not exist in the repo.';
COMMENT ON COLUMN run_records.duration_seconds      IS 'Wall-clock seconds from graph.invoke() start to scorer return.';
COMMENT ON COLUMN run_records.cap_hit               IS 'TRUE if any iteration cap was reached before the graph reached END naturally.';
COMMENT ON COLUMN run_records.budget_exceeded       IS 'TRUE if BudgetGuard halted the run.';
COMMENT ON COLUMN run_records.patch_size_bytes      IS 'Byte length of the final unified diff string; NULL if no patch was produced.';
COMMENT ON COLUMN run_records.created_at            IS 'Wall-clock UTC timestamp when MetricsWriter committed this record.';

CREATE INDEX IF NOT EXISTS run_records_run_id_idx
    ON run_records (run_id);

CREATE INDEX IF NOT EXISTS run_records_task_id_idx
    ON run_records (task_id);

CREATE INDEX IF NOT EXISTS run_records_solver_idx
    ON run_records ((solver_config->>'solver'));

CREATE INDEX IF NOT EXISTS run_records_created_at_idx
    ON run_records (created_at DESC);

CREATE INDEX IF NOT EXISTS run_records_outcome_solver_idx
    ON run_records (outcome, (solver_config->>'solver'));

-- =============================================================================
-- VIEW: run_summary
-- =============================================================================
-- Per-run aggregate statistics. Used by the Streamlit dashboard comparison
-- table. Not materialised — dataset is small enough for a live view.
-- =============================================================================

CREATE OR REPLACE VIEW run_summary AS
SELECT
    r.run_id,
    r.solver_config->>'solver'                          AS solver,
    COUNT(*)                                            AS total_tasks,
    SUM(CASE WHEN r.outcome = 'PASS' THEN 1 ELSE 0 END) AS tasks_passed,
    ROUND(
        SUM(CASE WHEN r.outcome = 'PASS' THEN 1 ELSE 0 END)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100,
        2
    )                                                   AS pass_rate_pct,
    SUM(r.total_cost_usd)                               AS total_cost_usd,
    SUM(r.total_tokens)                                 AS total_tokens,
    ROUND(AVG(r.iteration_count), 2)                    AS avg_iterations,
    ROUND(AVG(r.hallucination_score), 4)                AS avg_hallucination_score,
    ROUND(AVG(r.duration_seconds), 2)                   AS avg_duration_seconds,
    SUM(CASE WHEN r.cap_hit        THEN 1 ELSE 0 END)   AS cap_hit_count,
    SUM(CASE WHEN r.budget_exceeded THEN 1 ELSE 0 END)  AS budget_exceeded_count,
    MIN(r.created_at)                                   AS run_started_at,
    MAX(r.created_at)                                   AS run_finished_at,
    ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY r.duration_seconds)::NUMERIC, 3)
                                                         AS p50_duration_seconds,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY r.duration_seconds)::NUMERIC, 3)
                                                         AS p99_duration_seconds,
    ROUND(SUM(r.total_cost_usd) / NULLIF(SUM(CASE WHEN r.outcome = 'PASS' THEN 1 ELSE 0 END), 0), 8)
                                                         AS mean_cost_per_solved_task,
    ROUND(AVG(CASE WHEN r.hallucination_score > 0 THEN 1 ELSE 0 END)::NUMERIC, 4)
                                                         AS hallucination_rate
FROM run_records r
GROUP BY r.run_id, r.solver_config->>'solver';

COMMENT ON VIEW run_summary IS 'Per-run aggregate statistics across all tasks. Used by the Streamlit dashboard comparison table.';

-- =============================================================================
-- VIEW: headline_metrics
-- =============================================================================
-- FR-33: a single SELECT reproduces the full headline metric set for a named
-- solver configuration. Thin projection over run_summary — no new aggregation.
-- =============================================================================

CREATE OR REPLACE VIEW headline_metrics AS
SELECT
    solver,
    run_id,
    total_tasks,
    pass_rate_pct,
    mean_cost_per_solved_task,
    p50_duration_seconds,
    p99_duration_seconds,
    hallucination_rate,
    avg_iterations
FROM run_summary;

COMMENT ON VIEW headline_metrics IS 'FR-33: one-query headline table (success rate, mean cost per solved task, p50/p99 latency, hallucination rate, mean iterations) per solver config.';

-- =============================================================================
-- VIEW: task_cost_breakdown
-- =============================================================================
-- Per-(run_id, task_id, agent_role) cost and token breakdown. Used by the
-- dashboard drill-down panel.
-- =============================================================================

CREATE OR REPLACE VIEW task_cost_breakdown AS
SELECT
    te.run_id,
    te.task_id,
    te.agent_role,
    COUNT(*)                            AS llm_call_count,
    SUM(te.prompt_tokens)               AS total_prompt_tokens,
    SUM(te.completion_tokens)           AS total_completion_tokens,
    SUM(te.cost_usd)                    AS total_cost_usd,
    SUM(CASE WHEN te.cache_hit THEN 1 ELSE 0 END) AS cache_hit_count
FROM trace_events te
WHERE te.event_type = 'llm_call'
GROUP BY te.run_id, te.task_id, te.agent_role;

COMMENT ON VIEW task_cost_breakdown IS 'Per-(run_id, task_id, agent_role) LLM cost and token breakdown for dashboard drill-down.';
