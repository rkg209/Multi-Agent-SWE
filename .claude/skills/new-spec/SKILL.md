---
description: Scaffold a new spec directory (specs/NN-name/) with spec.md, plan.md, and tasks.md templates. Usage: /new-spec <NN-name> or /new-spec <name> (auto-numbers). Example: /new-spec 03-sandbox-exec or /new-spec sandbox-exec
---

# Skill: new-spec

Scaffold a new spec directory under `specs/` with the three required files: `spec.md`, `plan.md`, and `tasks.md`.

## Instructions

You will receive an argument like `03-sandbox-exec` or just `sandbox-exec`. Follow these steps:

### Step 1 — Determine spec number and name

1. If the argument starts with two digits and a dash (e.g., `03-sandbox-exec`), extract:
   - `NN = 03`
   - `name = sandbox-exec`
2. If only a name is given (e.g., `sandbox-exec`), scan `specs/` for the highest existing `NN-` prefix and increment by 1 (zero-padded to 2 digits). If `specs/` is empty, start at `01`.
3. The directory to create is `specs/NN-name/`.

### Step 2 — Check for conflicts

If `specs/NN-name/` already exists, stop and tell the user. Do not overwrite.

### Step 3 — Create the directory and write the three files

**specs/NN-name/spec.md**

```markdown
# Spec NN: <Title-Case Name>

## Goal

<!-- One paragraph: what problem this spec solves and why it matters. -->

## Scope

Functional requirements addressed:

| ID | Requirement |
|----|-------------|
| FR-? | ... |

## Non-Goals

- <!-- What this spec explicitly does NOT do. -->

## Done-When

All of the following are true:

- [ ] <!-- Observable, testable acceptance criterion 1 -->
- [ ] <!-- Observable, testable acceptance criterion 2 -->
- [ ] `make lint` exits 0
- [ ] `make test` exits 0
- [ ] No agent-generated code runs on the host (sandbox rule intact)

## Depends-On

<!-- List earlier specs this one builds on, e.g.: -->
- `specs/00-foundation` — Makefile, Docker, Postgres must be running
```

**specs/NN-name/plan.md**

```markdown
# Implementation Plan — Spec NN: <Title-Case Name>

## Overview

<!-- 2-3 sentences describing the overall approach. -->

## Key Decisions

1. **Decision**: <!-- What you chose and why. -->
2. **Decision**: <!-- ... -->

## Implementation Order

1. <!-- First thing to implement and why it must come first. -->
2. <!-- Second thing. -->
3. <!-- etc. -->

## Risk Areas

| Risk | Mitigation |
|------|-----------|
| <!-- e.g., Docker image build time --> | <!-- e.g., use cached base layer --> |

## Testing Strategy

- Unit tests: `tests/unit/test_<name>/`
- Integration tests: `tests/integration/test_<name>/`
- Manual check: <!-- describe the manual verification step -->
```

**specs/NN-name/tasks.md**

```markdown
# Tasks — Spec NN: <Title-Case Name>

Work through these in order. Check off each task only after `make lint && make test` pass.

## Setup

- [ ] Create directory structure for this spec's code
- [ ] Add any new dependencies to `pyproject.toml` and `requirements.txt`

## Implementation

- [ ] <!-- Task 1: specific, actionable, testable -->
- [ ] <!-- Task 2 -->
- [ ] <!-- Task 3 -->

## Tests

- [ ] Write unit tests in `tests/unit/test_<name>/`
- [ ] Write integration tests in `tests/integration/test_<name>/` (if applicable)
- [ ] All tests pass: `make test`

## Lint & Format

- [ ] `make lint` exits 0
- [ ] No type errors (if using mypy)

## Acceptance

- [ ] All done-when criteria in `spec.md` are verified
- [ ] Spec marked complete in `specs/NN-name/spec.md` (add a `## Status: Complete` section)
```

### Step 4 — Confirm to the user

Print a summary:
```
Created specs/NN-name/ with:
  spec.md   — fill in Goal, Scope, Non-Goals, Done-When
  plan.md   — fill in Overview, Key Decisions, Implementation Order
  tasks.md  — fill in Implementation tasks
```
