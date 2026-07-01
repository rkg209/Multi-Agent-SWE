# api-design.md

**Version:** 1.0
**Status:** Implementation-Ready
**Derived From:** planning/02-architecture.md v1.0, planning/03-system-design.md v1.0, planning/04-database-design.md v1.0

---

## Table of Contents

1. [Scope and Boundaries](#1-scope-and-boundaries)
2. [Authentication Scheme](#2-authentication-scheme)
3. [Error Handling Conventions](#3-error-handling-conventions)
4. [Pagination Strategy](#4-pagination-strategy)
5. [Versioning Policy](#5-versioning-policy)
6. [OpenAPI Specification](#6-openapi-specification)
7. [Design Rationale and Rejected Alternatives](#7-design-rationale-and-rejected-alternatives)

---

## 1. Scope and Boundaries

### 1.1 What This API Is

This document specifies the **HTTP REST API** exposed by the benchmark system for programmatic access to run records, trace events, and aggregate metrics. It is consumed by:

- The **Streamlit dashboard** (`dashboard/app.py`), which replaces direct SQLAlchemy calls with HTTP requests so the dashboard process does not require a Postgres connection string.
- **External tooling** — scripts, notebooks, or CI jobs that query benchmark results without importing the Python package.
- **The benchmark CLI** itself, for the specific case of writing run records when a future `--remote` flag is added (not implemented in v1, but the API is designed to support it without breaking changes).

### 1.2 What This API Is Not

- It is **not** a control plane. The API does not start benchmark runs, invoke agents, or manage tasks. Those operations are driven exclusively by the CLI (`make benchmark`). The API is read-heavy with one narrow write surface (run record ingestion).
- It is **not** a streaming interface. Agent output is not streamed over HTTP. The LangGraph graph runs in-process; the API only surfaces completed results.
- It is **not** a public API. It runs on `localhost` only, on the same machine as the benchmark harness. There is no TLS termination, no CDN, and no rate limiting beyond what the OS provides.

### 1.3 Server Location

```
Base URL (development):  http://localhost:8000
Base URL (production):   http://localhost:8000   (same; single-machine deployment)
```

The API server is started by `make api` and runs as a separate process alongside the benchmark CLI and the Streamlit dashboard. It is implemented with **FastAPI** and served by **Uvicorn**.

### 1.4 Transport

HTTP/1.1 over TCP on `localhost`. No HTTPS. The threat model (§7 of architecture.md) identifies the primary threat as arbitrary code execution via agent-generated code, not network interception. Since the API is localhost-only and carries no user credentials or PII, plaintext HTTP is the correct choice. Adding TLS for a localhost-only service would introduce certificate management complexity with zero security benefit.

---

## 2. Authentication Scheme

### 2.1 Design Decision: Static Bearer Token

The API uses a **single static bearer token** for authentication. The token is:

- Generated once during `make setup` via `python -c "import secrets; print(secrets.token_hex(32))"`.
- Written to `.env` as `API_SECRET_TOKEN=<hex>`.
- Read by the API server at startup from the environment; never hardcoded.
- Required on every request in the `Authorization` header.

```
Authorization: Bearer <token>
```

### 2.2 Rationale

This system has exactly one "user": the developer running the benchmark. The authentication requirement exists not to distinguish between users but to prevent accidental exposure if the developer's machine is on a shared network and the API port is inadvertently reachable. A static bearer token satisfies this requirement with minimal operational overhead.

The alternatives considered and rejected are documented in §7.1.

### 2.3 Token Validation

The API server validates the token on every request using a FastAPI dependency:

```python
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import hmac, os

bearer_scheme = HTTPBearer()

def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> None:
    expected = os.environ["API_SECRET_TOKEN"]
    provided = credentials.credentials
    # Constant-time comparison prevents timing attacks.
    # Relevant even on localhost: defense-in-depth.
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

This dependency is applied at the **router level**, not per-endpoint, so it is impossible to add a new endpoint and accidentally omit authentication.

### 2.4 What Happens on Missing or Invalid Token

| Condition | HTTP Status | Response Body |
|---|---|---|
| `Authorization` header absent | `401 Unauthorized` | `{"error": {"code": "UNAUTHORIZED", "message": "Authorization header is required."}}` |
| Header present but scheme is not `Bearer` | `401 Unauthorized` | `{"error": {"code": "UNAUTHORIZED", "message": "Bearer scheme required."}}` |
| Token present but does not match | `401 Unauthorized` | `{"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing bearer token."}}` |

The response body is intentionally vague: it does not distinguish between "header absent" and "token wrong" to avoid leaking information about the expected format. The `WWW-Authenticate: Bearer` header is always included on 401 responses, per RFC 6750.

### 2.5 Token Rotation

Token rotation is a manual operation:

1. Generate a new token: `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Update `API_SECRET_TOKEN` in `.env`.
3. Restart the API server: `make api`.
4. Update the token in any consuming scripts or the dashboard's `.env`.

No token revocation endpoint is provided. The token is a shared secret, not a JWT; there is no expiry.

---

## 3. Error Handling Conventions

### 3.1 Error Response Envelope

All error responses use a consistent JSON envelope:

```json
{
  "error": {
    "code": "SNAKE_CASE_ERROR_CODE",
    "message": "Human-readable description of what went wrong.",
    "details": {}
  }
}
```

- `code`: A machine-readable string constant. Consumers should branch on `code`, not on `message`.
- `message`: A human-readable string. May change between API versions without being considered a breaking change.
- `details`: An optional object with error-specific structured data. Present only when additional context is useful to the caller. Absent (not `null`) when there is nothing to add.

### 3.2 HTTP Status Code Mapping

| Situation | HTTP Status | `code` |
|---|---|---|
| Missing or invalid bearer token | `401 Unauthorized` | `UNAUTHORIZED` |
| Valid token but insufficient scope (reserved for future use) | `403 Forbidden` | `FORBIDDEN` |
| Resource not found (e.g., unknown `run_id`) | `404 Not Found` | `NOT_FOUND` |
| Request body fails schema validation | `422 Unprocessable Entity` | `VALIDATION_ERROR` |
| Query parameter has an invalid value | `400 Bad Request` | `INVALID_PARAMETER` |
| Requested page is beyond the last page | `400 Bad Request` | `PAGE_OUT_OF_RANGE` |
| Database write conflict (duplicate run record) | `409 Conflict` | `CONFLICT` |
| Unexpected server error | `500 Internal Server Error` | `INTERNAL_ERROR` |
| Database unreachable | `503 Service Unavailable` | `DATABASE_UNAVAILABLE` |

### 3.3 Validation Errors

When a request body or query parameter fails validation, the `422` response includes a `details` array that mirrors FastAPI's default validation error format, normalized into the envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request body failed schema validation.",
    "details": {
      "fields": [
        {
          "field": "outcome",
          "issue": "value is not a valid enum member",
          "accepted_values": ["PASS", "FAIL"]
        }
      ]
    }
  }
}
```

FastAPI's default `422` response format (a `detail` array of Pydantic validation errors) is suppressed and replaced with this envelope via a custom exception handler registered at application startup.

### 3.4 Internal Errors

`500` responses never include stack traces, exception types, or internal file paths. The response body contains only:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred. Check server logs for details.",
    "details": {
      "request_id": "7f3a2b1c-..."
    }
  }
}
```

The `request_id` is a UUID generated per-request (injected by middleware) and written to the server log alongside the full exception. This allows correlation between a client-reported error and the server log without exposing internals to the client.

### 3.5 Database Unavailability

If the Postgres connection pool is exhausted or the database is unreachable, the API returns `503` rather than `500`. This distinction matters for the dashboard: a `503` means "retry later," while a `500` means "something is wrong with the request or server logic."

```json
{
  "error": {
    "code": "DATABASE_UNAVAILABLE",
    "message": "The database is temporarily unavailable. Retry after a short delay.",
    "details": {
      "retry_after_seconds": 5
    }
  }
}
```

The `Retry-After: 5` HTTP header is also set on `503` responses.

### 3.6 No Partial Success

The API does not return partial success responses (e.g., `207 Multi-Status`). Every response is either fully successful (`2xx`) or fully failed (`4xx`/`5xx`). Batch write endpoints (if added in a future version) will use database transactions to ensure atomicity: either all records are written or none are.

---

## 4. Pagination Strategy

### 4.1 Design Decision: Keyset Pagination

The API uses **keyset pagination** (also called cursor-based pagination) for all list endpoints. Offset pagination is explicitly rejected; the rationale is in §7.2.

### 4.2 Cursor Format

The cursor is an **opaque, base64url-encoded string** that encodes the sort key values of the last item on the previous page. Clients treat it as an opaque token: they must not parse, construct, or modify it.

Internally, the cursor encodes a JSON object:

```json
{
  "created_at": "2024-11-15T14:23:01.000Z",
  "run_id": "7f3a2b1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "task_id": "django__django-11099"
}
```

This is base64url-encoded (no padding) and returned as the `next_cursor` field in list responses. The specific fields encoded depend on the sort order of the endpoint; the structure above is for `GET /v1/runs/{run_id}/results` sorted by `(created_at ASC, task_id ASC)`.

### 4.3 Request Parameters

All list endpoints accept:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | `20` | Number of items per page. Range: 1–100. |
| `cursor` | string | absent | Opaque cursor from the previous page's `next_cursor`. Absent on the first request. |

### 4.4 Response Envelope for Lists

```json
{
  "data": [ ... ],
  "pagination": {
    "limit": 20,
    "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNC0xMS0xNVQxNDoyMzowMS4wMDBaIiwicnVuX2lkIjoiN2YzYTJiMWMtNGQ1ZS02ZjdhLThiOWMtMGQxZTJmM2E0YjVjIiwidGFza19pZCI6ImRqYW5nb19fZGphbmdvLTExMDk5In0",
    "has_more": true
  }
}
```

- `next_cursor`: Present only when `has_more` is `true`. Absent (not `null`) when on the last page.
- `has_more`: `true` if there are more items beyond the current page. `false` on the last page.
- There is no `total_count` field. Computing `COUNT(*)` on large tables is expensive and the count changes between requests. Clients that need a count should use the dedicated aggregate endpoints.

### 4.5 Reaching the Last Page

When the client sends a `cursor` that corresponds to the last item in the result set, the response contains:

```json
{
  "data": [],
  "pagination": {
    "limit": 20,
    "has_more": false
  }
}
```

An empty `data` array with `has_more: false` is the canonical signal that pagination is complete. Clients must not treat an empty `data` array as an error.

### 4.6 Cursor Expiry and Stability

Cursors do not expire. Because `run_records` and `trace_events` are immutable after insert, the sort order of existing rows never changes. A cursor generated in one session is valid in any future session.

New rows inserted after a cursor is generated will appear on subsequent pages if their sort key is greater than the cursor's encoded value. This is the correct behavior: a client paginating through results will see new runs appended at the end without disrupting earlier pages.

### 4.7 Invalid Cursor Handling

If a client sends a cursor that cannot be base64url-decoded, or whose decoded JSON does not match the expected schema for the endpoint, the API returns:

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "The 'cursor' parameter is malformed or was not issued by this endpoint.",
    "details": {
      "parameter": "cursor"
    }
  }
}
```

HTTP status: `400 Bad Request`.

---

## 5. Versioning Policy

### 5.1 URL Path Versioning

The API version is encoded in the URL path as the first path segment:

```
/v1/runs
/v1/runs/{run_id}/results
/v1/runs/{run_id}/traces
/v1/metrics/summary
```

All v1 endpoints share the prefix `/v1`. When v2 is introduced, v1 endpoints remain available at `/v1` until explicitly deprecated and removed.

### 5.2 What Constitutes a Breaking Change

The following changes require a new major version (`v1` → `v2`):

| Change Type | Example | Breaking? |
|---|---|---|
| Removing an endpoint | Deleting `GET /v1/runs/{run_id}/traces` | **Yes** |
| Removing a required request field | Removing `outcome` from the run record write body | **Yes** |
| Removing a response field | Removing `total_cost_usd` from run record responses | **Yes** |
| Changing a field's type | `iteration_count` from `integer` to `string` | **Yes** |
| Changing a field's name | Renaming `total_cost_usd` to `cost_usd_total` | **Yes** |
| Changing an error `code` string | `NOT_FOUND` → `RESOURCE_NOT_FOUND` | **Yes** |
| Changing pagination cursor format | Switching from keyset to offset | **Yes** |
| Adding a new optional response field | Adding `p50_duration_seconds` to summary | **No** |
| Adding a new optional request parameter | Adding `?solver=multi` filter | **No** |
| Adding a new endpoint | Adding `GET /v1/runs/{run_id}/hallucination` | **No** |
| Changing `message` text in an error | Rewording a human-readable error string | **No** |
| Adding a new `details` field to an error | Adding `retry_after_seconds` to a 503 | **No** |

### 5.3 Deprecation Process

When a v1 endpoint or field is deprecated in favor of a v2 equivalent:

1. The deprecated endpoint continues to function without modification.
2. The API adds a `Deprecation` response header to the deprecated endpoint:
   ```
   Deprecation: true
   Sunset: Sat, 01 Mar 2025 00:00:00 GMT
   Link: </v2/runs>; rel="successor-version"
   ```
   These headers follow [RFC 8594](https://datatracker.ietf.org/doc/html/rfc8594).
3. The deprecation is documented in `CHANGELOG.md` with the sunset date.
4. The endpoint is removed only after the sunset date has passed.

For a single-developer project, the sunset period is a minimum of **30 days** from the deprecation announcement. This is sufficient time to update the dashboard and any scripts.

### 5.4 Version Negotiation

There is no `Accept-Version` header negotiation. The version is in the URL path. This is intentional: URL-based versioning is explicit, cacheable, and requires no client-side header management. The dashboard constructs URLs with the version prefix hardcoded; changing the version requires a code change, which is the correct forcing function for a deliberate upgrade.

### 5.5 Current Version Status

| Version | Status | Base Path | Notes |
|---|---|---|---|
| `v1` | **Current** | `/v1` | Specified in this document |
| `v2` | Not planned | — | Will be introduced only if a breaking change is required |

---

## 6. OpenAPI Specification

```yaml
openapi: "3.1.0"

info:
  title: "Multi-Agent SWE Benchmark API"
  version: "1.0.0"
  description: |
    Read-oriented HTTP API for querying benchmark run records, trace events,
    and aggregate metrics produced by the multi-agent SWE benchmark harness.

    **Authentication:** All endpoints require a static bearer token supplied in
    the `Authorization: Bearer <token>` header. The token is generated during
    `make setup` and stored in `.env` as `API_SECRET_TOKEN`.

    **Base URL:** `http://localhost:8000`

    **Transport:** HTTP/1.1 over localhost only. No TLS.

servers:
  - url: "http://localhost:8000"
    description: "Local development and production (single-machine deployment)"

security:
  - BearerAuth: []

components:

  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      description: |
        Static bearer token generated during `make setup`.
        Stored in `.env` as `API_SECRET_TOKEN`.
        Pass as `Authorization: Bearer <token>`.

  # ── Reusable parameter definitions ──────────────────────────────────────────

  parameters:

    LimitParam:
      name: limit
      in: query
      required: false
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
      description: "Number of items to return per page."

    CursorParam:
      name: cursor
      in: query
      required: false
      schema:
        type: string
      description: |
        Opaque keyset pagination cursor returned as `next_cursor` in a previous
        response. Omit on the first request. Do not construct or modify this
        value; treat it as opaque.

    RunIdPath:
      name: run_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
      description: "UUID of the benchmark run."

    TaskIdPath:
      name: task_id
      in: path
      required: true
      schema:
        type: string
        maxLength: 255
      description: "Task identifier, e.g. `django__django-11099`."

  # ── Reusable schema definitions ──────────────────────────────────────────────

  schemas:

    # ── Error envelope ──────────────────────────────────────────────────────

    ErrorResponse:
      type: object
      required: [error]
      properties:
        error:
          type: object
          required: [code, message]
          properties:
            code:
              type: string
              description: "Machine-readable error code. Branch on this, not on `message`."
              examples:
                - "NOT_FOUND"
                - "UNAUTHORIZED"
                - "VALIDATION_ERROR"
            message:
              type: string
              description: "Human-readable description. May change between releases."
            details:
              type: object
              description: |
                Optional structured context. Present only when additional
                information is useful to the caller. Absent when empty.
              additionalProperties: true

    # ── Pagination envelope ─────────────────────────────────────────────────

    PaginationMeta:
      type: object
      required: [limit, has_more]
      properties:
        limit:
          type: integer
          description: "The `limit` value used for this page."
        next_cursor:
          type: string
          description: |
            Opaque cursor for the next page. Present only when `has_more`
            is `true`. Absent (not null) on the last page.
        has_more:
          type: boolean
          description: "`true` if additional items exist beyond this page."

    # ── SolverConfig (embedded in RunRecord) ────────────────────────────────

    SolverConfig:
      type: object
      required: [solver, max_dev_tester_iterations, max_dev_reviewer_iterations,
                 max_tokens_per_task]
      properties:
        solver:
          type: string
          enum: [single, multi]
          description: "Solver mode used for this run."
        max_dev_tester_iterations:
          type: integer
          minimum: 1
          description: "Maximum developer↔tester loop iterations."
        max_dev_reviewer_iterations:
          type: integer
          minimum: 1
          description: "Maximum developer↔reviewer loop iterations."
        max_tokens_per_task:
          type: integer
          minimum: 1
          description: "Per-task token budget cap."

    # ── RunRecord ───────────────────────────────────────────────────────────

    RunRecord:
      type: object
      required:
        - run_id
        - task_id
        - solver_config
        - outcome
        - test_output
        - total_cost_usd
        - total_tokens
        - iteration_count
        - hallucination_score
        - duration_seconds
        - created_at
      properties:
        run_id:
          type: string
          format: uuid
          description: "UUID of the benchmark run this record belongs to."
        task_id:
          type: string
          maxLength: 255
          description: "Task identifier."
        solver_config:
          $ref: "#/components/schemas/SolverConfig"
        outcome:
          type: string
          enum: [PASS, FAIL]
          description: "Deterministic scorer outcome."
        test_output:
          type: string
          description: |
            Truncated stdout+stderr from the scorer (max 32 KB).
            Present for debugging; not used in aggregations.
        total_cost_usd:
          type: number
          format: double
          minimum: 0
          description: "Sum of all LLM call costs for this task, in USD."
        total_tokens:
          type: integer
          minimum: 0
          description: "Sum of prompt + completion tokens across all LLM calls."
        iteration_count:
          type: integer
          minimum: 0
          description: "dev_tester_iterations + dev_reviewer_iterations."
        hallucination_score:
          type: number
          format: double
          minimum: 0
          maximum: 1
          description: |
            Fraction of file/symbol references in the patch that do not exist
            in the repo. 0.0 = no hallucinations; 1.0 = all references hallucinated.
        duration_seconds:
          type: number
          format: double
          minimum: 0
          description: "Wall-clock time of graph.invoke() for this task, in seconds."
        created_at:
          type: string
          format: date-time
          description: "UTC timestamp of record insertion. Set by the database."

    # ── RunSummary (aggregate view, one row per run_id) ─────────────────────

    RunSummary:
      type: object
      required:
        - run_id
        - solver
        - task_count
        - pass_count
        - fail_count
        - pass_rate
        - avg_cost_usd
        - total_cost_usd
        - avg_iterations
        - avg_hallucination_score
        - avg_duration_seconds
        - run_started_at
      properties:
        run_id:
          type: string
          format: uuid
        solver:
          type: string
          enum: [single, multi]
        task_count:
          type: integer
          minimum: 0
        pass_count:
          type: integer
          minimum: 0
        fail_count:
          type: integer
          minimum: 0
        pass_rate:
          type: number
          format: double
          minimum: 0
          maximum: 1
          description: "pass_count / task_count. 0 if task_count is 0."
        avg_cost_usd:
          type: number
          format: double
          minimum: 0
        total_cost_usd:
          type: number
          format: double
          minimum: 0
        avg_iterations:
          type: number
          format: double
          minimum: 0
        avg_hallucination_score:
          type: number
          format: double
          minimum: 0
          maximum: 1
        avg_duration_seconds:
          type: number
          format: double
          minimum: 0
        run_started_at:
          type: string
          format: date-time
          description: "Earliest `created_at` among all run_records for this run_id."

    # ── TraceEvent ──────────────────────────────────────────────────────────

    TraceEvent:
      type: object
      required:
        - event_id
        - run_id
        - task_id
        - agent_role
        - turn_index
        - event_type
        - cache_hit
        - payload
        - created_at
      properties:
        event_id:
          type: string
          format: uuid
        run_id:
          type: string
          format: uuid
        task_id:
          type: string
          maxLength: 255
        agent_role:
          type: string
          enum: [architect, developer, tester, reviewer, system]
          description: |
            The agent that produced this event. `system` is used for
            budget_exceeded and harness-level events.
        turn_index:
          type: integer
          minimum: 0
          description: |
            Monotonically increasing within (run_id, task_id, agent_role).
            Used to reconstruct the conversation timeline.
        event_type:
          type: string
          enum: [llm_call, tool_call, tool_error, budget_exceeded, cache_hit]
        model:
          type: string
          nullable: true
          description: "LiteLLM model identifier. Null for non-LLM events."
        prompt_tokens:
          type: integer
          nullable: true
          minimum: 0
          description: "Null for non-LLM events."
        completion_tokens:
          type: integer
          nullable: true
          minimum: 0
          description: "Null for non-LLM events."
        cost_usd:
          type: number
          format: double
          nullable: true
          minimum: 0
          description: |
            Cost of this LLM call in USD. 0 for cache hits.
            Null for non-LLM events.
        cache_hit:
          type: boolean
          description: "`true` if this LLM response was served from the cache."
        payload:
          type: object
          additionalProperties: true
          description: |
            Event-type-specific structured data. Schema varies by event_type:
            - llm_call: `{"messages_hash": "...", "temperature": 0.2}`
            - tool_call: `{"server": "filesystem", "tool": "read_file",
                           "arguments": {"path": "src/foo.py"}, "result_ok": true}`
            - tool_error: `{"server": "runcode", "tool": "exec",
                            "error": "ToolDeniedError: curl is not allowed"}`
            - budget_exceeded: `{"tokens_used": 50001, "cap": 50000}`
        created_at:
          type: string
          format: date-time

    # ── AgentCostBreakdown ──────────────────────────────────────────────────

    AgentCostBreakdown:
      type: object
      required: [agent_role, total_cost_usd, call_count, cache_hit_count,
                 prompt_tokens, completion_tokens]
      properties:
        agent_role:
          type: string
          enum: [architect, developer, tester, reviewer, system]
        total_cost_usd:
          type: number
          format: double
          minimum: 0
        call_count:
          type: integer
          minimum: 0
          description: "Total LLM calls (cache hits + misses)."
        cache_hit_count:
          type: integer
          minimum: 0
        prompt_tokens:
          type: integer
          minimum: 0
        completion_tokens:
          type: integer
          minimum: 0

    # ── RunRecord write body ────────────────────────────────────────────────

    RunRecordCreate:
      type: object
      required:
        - run_id
        - task_id
        - solver_config
        - outcome
        - test_output
        - total_cost_usd
        - total_tokens
        - iteration_count
        - hallucination_score
        - duration_seconds
      properties:
        run_id:
          type: string
          format: uuid
        task_id:
          type: string
          maxLength: 255
        solver_config:
          $ref: "#/components/schemas/SolverConfig"
        outcome:
          type: string
          enum: [PASS, FAIL]
        test_output:
          type: string
          default: ""
        total_cost_usd:
          type: number
          format: double
          minimum: 0
        total_tokens:
          type: integer
          minimum: 0
        iteration_count:
          type: integer
          minimum: 0
        hallucination_score:
          type: number
          format: double
          minimum: 0
          maximum: 1
        duration_seconds:
          type: number
          format: double
          minimum: 0

  # ── Reusable response definitions ────────────────────────────────────────────

  responses:

    Unauthorized:
      description: "Missing or invalid bearer token."
      headers:
        WWW-Authenticate:
          schema:
            type: string
            example: "Bearer"
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/ErrorResponse"
          example:
            error:
              code: "UNAUTHORIZED"
              message: "Invalid or missing bearer token."

    NotFound:
      description: "The requested resource does not exist."
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/ErrorResponse"
          example