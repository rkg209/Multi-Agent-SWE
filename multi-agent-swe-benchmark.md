# Multi-Agent SWE System + Benchmark — Project & Build Doc

> **What this document is.** The single, self-contained source of truth for *one* project: an open-model multi-agent software-engineering system wrapped in a reproducible benchmark. It is split into four parts:
> - **Part A — Specification:** what the project is, the locked design decisions, architecture, stack, metrics, and scope.
> - **Part B — Claude Code SDD environment:** exactly what to put in `CLAUDE.md`, which skills, slash commands, hooks, sub-agents, MCP servers, and plugins to use *while building it*.
> - **Part C — The specs to build, in order:** a high-level, spec-driven-development backlog. Exact technical implementation is written later, per spec.
> - **Part D — Appendix:** file tree, model/provider shortlist, metric scorecard, risks.
>
> **The one idea to keep straight.** This project has **two separate model layers**:
> 1. **Claude Code** — the tool you build *with*. Runs on your Claude subscription. Unaffected by the exhausted API budget.
> 2. **The agents inside the system** (Architect / Developer / Tester / Reviewer) — application code you write. These run **only on open/cheap models via a router**. No Anthropic API.
> Whenever this doc says "agent," it means layer 2 unless it says "Claude Code."

---

## Part A — Specification

### A.1 What it is (plain language)
A system where several AI agents — each with a specific job — collaborate to resolve a coding ticket: plan the change, write the code, test it, review it. Around that system sits a **benchmark**: a fair, repeatable harness that runs the same fixed set of tasks and records whether the generated code passes hidden tests, how many tokens it cost, how long it took, and how often it hallucinated. The benchmark produces the headline result: **does a multi-agent team beat a single agent, and at what cost multiple?**

### A.2 Why it's worth doing (honest framing — read this before anything else)
The *agent* is not the differentiator. As a coding agent it will be far weaker than Cursor, Codex, Claude Code, OpenHands, etc., and "I built another coding agent" impresses no one. **The value is the measurement discipline** — building a reproducible harness and running a controlled study is rare among early-career candidates and reads as senior.

Frame the project as **"a controlled study of when multi-agent coding pays off,"** not "proof that multi-agent is better." Current (2025–26) research shows single agents often *match or beat* multi-agent systems on sequential, context-heavy tasks like coding under equal compute, and that coordination mainly wins on *parallel, independent specialist* work (e.g., separate security/perf reviewers that don't coordinate). That means an honest, nuanced result — "multi-agent bought +X% success at Y× the cost; here's exactly where it helped and where it just burned tokens" — is the *strong* outcome, and it's robust no matter which way the numbers fall. Lead the résumé bullet and the README with that number, not with the agent.

### A.3 The real problem / audience
Single agents fail on non-trivial tickets, and almost nobody measures agent quality before trusting it. The system helps resolve a ticket; the benchmark helps anyone choosing or tuning an agent. The portfolio audience is applied-AI / ML interviewers screening for genuine agent + evaluation depth.

### A.4 How it differs from existing tools
It is **measurement-first**: an objective, deterministic scorer (do the hidden tests pass?), plus token/cost/latency/hallucination tracking, plus a clean single-vs-multi comparison on a *fixed* task set. The output is evidence, not a demo.

### A.5 Locked design decisions
| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Model strategy | **Open models only, behind a model-agnostic router (LiteLLM)** | No Anthropic API budget. Router gives one interface over OpenRouter / Together / Groq / Fireworks / local Ollama. Tier a stronger open model for Architect/Reviewer, a smaller/faster one for Developer/Tester bulk turns. Bonus: model becomes a cheap extra comparison axis. |
| D2 | Benchmark dataset | **Small fixed subset (~30–50) of SWE-bench Lite / Verified + 3–5 hand-made tickets** | Credible standard tasks for the headline; tiny custom tickets for near-zero-cost iteration. You're comparing scaffolds on a fixed set, not chasing the leaderboard, so the benchmark's known saturation/contamination doesn't hurt you (note it in the writeup as a sign of rigor). |
| D3 | Experiment scope | **Build the best multi-agent system; keep one cheap baseline run (best-multi vs single) for the headline; drop heavy ablations** | The harness runs both for ~free (single = the graph with one node). Keeps the word "Benchmark" honest without weeks of experimentation. Parallel-specialist-reviewer ablation is an *optional stretch*, not required. |
| D4 | Build vs reuse | **Build orchestration + metrics + dashboard; reuse the official SWE-bench harness for env setup + scoring** | The orchestration is the signal; the env/scoring plumbing is fiddly, undifferentiated, and the #1 timeline-killer. |
| D5 | GitHub PRs | **Sandbox-only eval; real PR creation is a demo-only extra** | Benchmark needs determinism. Real PRs are for the demo video, not the scored run. |
| D6 | Orchestration | **LangGraph** | Résumé-relevant; gives state-machine + checkpointing vocabulary. |
| D7 | Task language | **Python** | Aligns with SWE-bench. |
| D8 | Scope | **Heaviest of the portfolio; thin-slice first, hard task-count cap** | Env setup sinks most attempts; protect against it. |
| D9 | Claude Code's role | **Development environment only** | Not a component of the system. Determines Part B. |

### A.6 Architecture & data flow
```
Fixed task (SWE-bench subset OR custom ticket: issue text + repo snapshot)
        │
        ▼
   MODEL ROUTER (LiteLLM)  ──► routes every agent call to an open model
        │                       (tiered: strong = Architect/Reviewer, small = Developer/Tester)
        ▼
   ┌─────────────────────────── MULTI-AGENT GRAPH (LangGraph) ───────────────────────────┐
   │  ARCHITECT  ─ plans files to touch + approach                                         │
   │      ▼                                                                                │
   │  DEVELOPER  ─ writes code  ── (executes ONLY in Docker sandbox via the tool layer)    │
   │      ▼                                                                                │
   │  TESTER     ─ writes/runs tests ─ on fail ──► back to DEVELOPER (capped loop)         │
   │      ▼ (pass)                                                                         │
   │  REVIEWER   ─ critiques quality/security ─ on issues ──► back to DEVELOPER (capped)   │
   │      ▼ (approved or cap hit)                                                          │
   └──────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
   BENCHMARK HARNESS  ─ runs hidden tests in sandbox ──► PASS/FAIL (deterministic scorer)
        │                records: success?, tokens→$, latency, hallucination?, iterations
        ▼
   METRICS STORE (Postgres)  ──►  DASHBOARD: single-agent vs best multi-agent
```
- **Tool layer:** filesystem, run-code, and git are exposed to the agents through **your own MCP servers** (application code — see Spec 02). These are *separate* from the MCP servers Claude Code uses while you develop (Part B).
- **Sandbox rule (non-negotiable):** generated code executes only inside an isolated Docker container, never on the host. This is enforced both in code and via a Claude Code hook (Part B).

### A.7 Tech stack
- **Router / models:** LiteLLM; open coding models (e.g., Qwen3-Coder, DeepSeek-V3.x, GLM-4.6, Kimi, gpt-oss) via OpenRouter/Together/Groq/Fireworks, or **local Ollama on the college GPU for $0**.
- **Orchestration:** LangGraph (+ checkpointing).
- **Tool layer:** your own MCP servers (filesystem / run-code / git).
- **Sandbox:** Docker (Firecracker optional, later).
- **Benchmark:** official SWE-bench harness + `sb-cli` for env/scoring; your own loader/scorer glue for custom tickets.
- **Storage:** Postgres (traces + metrics).
- **Dashboard:** Streamlit (fast) or a small React app.
- **Lang:** Python.
- **CI:** GitHub Actions for `make benchmark` reproducibility.

### A.8 Metrics
- **Headline:** task success rate (% of tasks whose hidden tests pass) — **single-agent vs best multi-agent**, plus the **cost multiple** (tokens/$ per *solved* task).
- **Cost:** mean tokens (and $) per solved task, per configuration and per model.
- **Latency:** p50 / p99 end-to-end per task.
- **Hallucination rate:** % of runs that reference a file/symbol that doesn't exist in the repo (static check against the repo's symbol table).
- **Iterations:** mean Developer↔Tester loops to pass.

### A.9 What to deploy / show
Architecture diagram + **demo video** (always-on hosting burns inference) + public repo with `make benchmark`, a results table, and plots. The README's headline is the single-vs-multi cost/quality table. A short **writeup/blog** answering "does multi-agent coding pay for itself?" is the most recruiter-legible artifact — treat it as a deliverable, not an afterthought.

### A.10 Skills it proves
Agentic systems, multi-agent orchestration (LangGraph), LLM evaluation / LLMOps, reproducible benchmarking, model routing & cost control, guardrails, MCP tool layer, sandboxed execution, hallucination/cost/latency measurement, CI/CD, Python, AI system design.

### A.11 Non-goals (say no to these to survive the timeline)
- Beating real coding agents on absolute score.
- Running the full SWE-bench (hundreds of tasks). Cap at the fixed subset.
- Real-time/always-on hosting.
- A polished IDE/chat UX. The dashboard is for *results*, not interaction.
- Heavy multi-way ablations beyond the one headline comparison (unless time remains).

---

## Part B — Claude Code spec-driven-development environment

> Everything here configures **Claude Code (the dev tool)**. None of it is the system's runtime. Claude Code subagents/hooks/skills help you *build*; they are not the Architect/Developer/Tester/Reviewer agents (those are LangGraph nodes you write in Python).

### B.0 Repo & config layout
```
multi-agent-swe-benchmark/
├── CLAUDE.md                     # project constitution (always-on context)
├── .mcp.json                     # MCP servers for DEVELOPMENT (project scope)
├── .claude/
│   ├── settings.json             # hooks + permission allowlist (committed)
│   ├── settings.local.json       # machine-local overrides (gitignored)
│   ├── skills/                   # invocable dev workflows (/name)
│   │   ├── new-spec/SKILL.md
│   │   ├── run-bench/SKILL.md
│   │   ├── score-patch/SKILL.md
│   │   ├── trace/SKILL.md
│   │   └── eval-conventions/SKILL.md   # reference skill (definitions)
│   ├── agents/                   # dev sub-agents (isolated context)
│   │   ├── spec-writer.md
│   │   ├── planner.md
│   │   ├── code-reviewer.md
│   │   ├── test-runner.md
│   │   ├── explorer.md
│   │   └── harness-debugger.md
│   └── hooks/                    # hook scripts called by settings.json
│       ├── block-host-exec.sh
│       ├── format-python.sh
│       └── fast-tests.sh
├── specs/                        # SDD: one folder per spec (Part C)
│   └── 00-foundation/{spec.md,plan.md,tasks.md}
├── src/ ...                      # the actual system
├── benchmark/ ...                # harness, task loaders, scorer
└── Makefile                      # make benchmark, make test, make lint
```

### B.1 `CLAUDE.md` (hand-write it; keep it tight)
Research is clear that a short, human-curated `CLAUDE.md` beats a long auto-generated one — bloated machine-written rules add no benefit and can slightly *reduce* success. Keep it to the essentials below; update it whenever you correct the same mistake twice.

```markdown
# Project: Multi-Agent SWE System + Benchmark

## What this is
An open-model multi-agent SWE system wrapped in a reproducible benchmark.
Goal = measure when a multi-agent team beats a single agent on coding tasks
(success rate, cost, latency, hallucination). The MEASUREMENT is the product.

## Two model layers — never conflate them
- Claude Code (you) = dev tool, runs on subscription.
- System agents (Architect/Developer/Tester/Reviewer) = Python/LangGraph nodes
  that call OPEN models via the LiteLLM router. Never wire them to a paid API.

## Hard safety rule
Code generated by the system runs ONLY inside the Docker sandbox wrapper
(`make sandbox-run`). Never execute generated/untrusted code on the host.
Never weaken this to "just test quickly."

## Stack
Python · LangGraph · LiteLLM · Docker · Postgres · SWE-bench harness · Streamlit.

## Commands
- Install:        make setup
- Run tests:      make test            # fast unit subset
- Lint/format:    make lint            # ruff + black, must pass before commit
- Benchmark:      make benchmark TASKS=lite-30   # the fixed subset
- Single sandbox: make sandbox-run CMD="..."

## Conventions
- Type hints required; ruff strict; no bare excepts.
- Every agent call goes through the router; never import a provider SDK directly.
- Every benchmark run writes a full trace to Postgres (no silent runs).
- Costs/tokens are recorded per call, not estimated after the fact.

## Spec-driven workflow
Work one spec at a time from specs/. For a spec: read spec.md → confirm plan.md →
implement tasks.md task-by-task → run make lint && make test → update CLAUDE.md if a
convention emerged. Don't start a spec whose dependencies aren't merged.

## Definition of done (per spec)
Lint clean · tests pass · the spec's "done-when" met · a one-paragraph note in
the spec folder on what changed and what's still stubbed.
```

### B.2 Skills (`.claude/skills/<name>/SKILL.md`)
In current Claude Code, skills and slash commands are unified — every skill is invocable as `/name`, and Claude can auto-invoke it when its `description` matches the task (set `disable-model-invocation: true` for manual-only). Create these **action** skills plus one **reference** skill:

- **`/new-spec`** — scaffolds `specs/NN-name/{spec.md,plan.md,tasks.md}` from a template (goal, scope, done-when, depends-on). Use at the start of every spec.
- **`/run-bench`** — runs the harness on a named task subset and writes results to Postgres; prints the summary table. (`run-bench lite-30`)
- **`/score-patch`** — runs the deterministic scorer on a single generated patch against its hidden tests; good for debugging one task without a full run.
- **`/trace`** — pulls one run's trace from Postgres and summarizes agent turns, tokens, and where it failed.
- **`eval-conventions`** *(reference skill, `disable-model-invocation` off)* — the canonical definitions: what counts as "success," "hallucination," how cost is computed, how iterations are counted. Keeps measurement consistent across sessions. Claude loads it whenever it reasons about metrics.

> Tip: skills support `$ARGUMENTS` / `$1` / `${CLAUDE_SKILL_DIR}` substitution and can run in an isolated subagent with `context: fork` — use that for `/run-bench` so a long run doesn't flood your main context.

### B.3 Custom slash commands (`.claude/commands/*.md`)
Commands still work as single-file prompt templates; use them for lightweight "insert this prompt" actions that don't need helper files (skills win when there's real logic or shipped scripts). Worth having:
- **`/spec-review`** — re-reads the current spec and the diff, checks the implementation against the spec's done-when, and lists gaps.
- **`/cost-check`** — summarizes token/$ usage of the last run and flags the most expensive agent step.
- **`/sandbox-audit`** — asks Claude to verify no code path executes generated code outside the Docker wrapper.

(If a command and a skill share a name, the skill wins — so keep names distinct.)

### B.4 Sub-agents (`.claude/agents/*.md`)
Isolated-context helpers for the *dev* loop. **Restrict each to read-only tools** (omit `Edit`/`Write`; defer edits to the main session, which can handle approvals) and point exploration agents at a **cheaper model**:
- **`spec-writer`** — turns a feature idea into a well-formed `spec.md` (goal, scope, non-goals, done-when).
- **`planner`** — turns a spec into `plan.md` + a granular `tasks.md`.
- **`explorer`** — scans the repo / fetches library docs and returns a distilled map; keeps your main context clean (especially in plan mode).
- **`code-reviewer`** — reviews a diff against `CLAUDE.md` conventions + security; read-only.
- **`test-runner`** — runs `make test` (and `/score-patch`) in the sandbox and reports failures; read-only.
- **`harness-debugger`** — dedicated to the fiddly SWE-bench env failures (missing deps, image build errors). Isolating this is high-value because env setup is the timeline risk.

### B.5 Hooks (`.claude/settings.json`)
Hooks are deterministic, prompt-free automation on lifecycle events. The high-value ones for this project:
- **`PreToolUse` on `Bash` → `block-host-exec.sh`** — the guardrail that enforces the sandbox rule: deny (exit code 2) any command that would run generated/untrusted code outside the Docker wrapper, plus block destructive patterns (`rm -rf`, etc.). This is the single most important hook here.
- **`PostToolUse` on `Write`/`Edit` → `format-python.sh`** — auto-run ruff+black on touched Python files so the tree stays clean.
- **`PostToolUse` on `Write`/`Edit` (src/ only) → `fast-tests.sh`** — run the fast unit subset after edits; surface failures immediately.
- **`Stop`/`SubagentStop` → notification** *(optional)* — desktop ping when a long benchmark run finishes.

Example shape:
```json
{
  "hooks": {
    "PreToolUse":  [{ "matcher": "Bash",        "hooks": [{ "type": "command", "command": ".claude/hooks/block-host-exec.sh" }] }],
    "PostToolUse": [{ "matcher": "Write|Edit",  "hooks": [{ "type": "command", "command": ".claude/hooks/format-python.sh" }] }]
  }
}
```

### B.6 MCP servers (for development — `.mcp.json`, project scope)
These connect **Claude Code** to your toolchain while you build. They are *not* the system's own tool layer.
- **GitHub MCP** — manage the repo, issues, PRs, and CI from inside Claude Code. `claude mcp add github -- npx -y @modelcontextprotocol/server-github`
- **Postgres MCP** — let Claude Code inspect the metrics/trace DB ("show the last run's failing tasks") without you writing SQL by hand.
- **Filesystem** — mostly covered by built-in tools; add only if you want scoped access to a specific data dir.

> Don't confuse these with **Spec 02's MCP servers** (filesystem/run-code/git) — those are application code the *system's* agents call at runtime, and you build them yourself.

### B.7 Plugins
A plugin bundles skills + commands + hooks + subagents + MCP defs into one installable unit. For a **solo** project you don't need one — plain `.claude/` files are simpler. Two reasons you might make one anyway: (a) you want the same setup on the college-cluster machine and your laptop without copy-paste, or (b) you want to *show* the skill on the résumé. If so, package the B.2–B.6 set as a local plugin (`/plugin`) named e.g. `swe-bench-dev`. Otherwise, skip it. **Agent Teams** (multi-session coordination) are also overkill here — note them as "explored, deliberately not used; the system's coordination is the LangGraph graph, not Claude Code teams."

### B.8 Model tiering for Claude Code itself
Use a strong model for architecture/spec reasoning and review; let exploration sub-agents run on a cheaper/faster model to save your subscription quota. (Independent of the open-model router, which only governs the system's own agents.)

---

## Part C — The specs to build, in order

> **SDD loop per spec:** `/new-spec` → write `spec.md` (goal, scope, non-goals, done-when, depends-on) → confirm `plan.md` → generate `tasks.md` → implement task-by-task with `code-reviewer`/`test-runner` gates → `make lint && make test` → note what's done/stubbed. **Build the thin end-to-end slice first** (Specs 00–05 give you a working single-agent benchmark before any multi-agent work).

| Order | Spec | Goal (high level) | Done-when | Depends on |
|---|---|---|---|---|
| **00** | **Foundation** | Repo, `CLAUDE.md`, Makefile, Postgres up, Docker sandbox wrapper skeleton, the Part B Claude Code setup. | `make setup`, `make lint`, `make test` all run; sandbox wrapper executes a hello-world in a container; host-exec hook blocks a host run. | — |
| **01** | **Model router** | LiteLLM abstraction: call any open model behind one interface; per-call token/cost accounting; tier config (strong vs small). | One function returns a completion from ≥2 open providers (and local Ollama); every call logs tokens + $ to Postgres. | 00 |
| **02** | **Tool layer (your MCP servers) + sandbox** | Filesystem / run-code / git tools exposed via your own MCP servers; all code-exec routed through Docker. | An agent-style caller can read a repo, write a file, and run tests *only* in the sandbox. | 00 |
| **03** | **Benchmark harness** | Task loader for the fixed SWE-bench subset + custom tickets; deterministic scorer (hidden tests → pass/fail); results schema in Postgres. | `make benchmark TASKS=lite-5` loads tasks, runs a no-op solver, and records pass/fail rows. | 00, 02 |
| **04** | **Single-agent baseline (THIN E2E SLICE)** | One agent: ticket → plan → write code (sandbox) → run tests → score. The first real end-to-end result. | A single agent resolves ≥1 task end-to-end and the harness records a real success/fail + cost + latency. | 01, 02, 03 |
| **05** | **Instrumentation & metrics** | Full trace store; compute cost, latency p50/p99, hallucination (symbol-existence check), iterations. | Every run yields the full metric set; a query reproduces the headline table for the single agent. | 04 |
| **06** | **Multi-agent system** | LangGraph graph: Architect → Developer → Tester → Reviewer with capped feedback loops + checkpointing; tiered models per role. | The team resolves tasks end-to-end with capped loops; traces show per-agent turns. | 04, 05 |
| **07** | **Guardrails & cost control** | Action allow-list, safety check before any exec, per-task iteration + token-budget caps, response cache, graceful stop-on-cap. | A runaway task halts at the cap and reports where it stuck; cache cuts repeat-run cost. | 06 |
| **08** | **Comparison run + dashboard** | Run the fixed subset through single vs best-multi; Streamlit dashboard of the headline table + plots. | One command produces the single-vs-multi success/cost/latency comparison; dashboard renders it. | 06, 07 |
| **09** | **Writeup, demo & reproducibility** | README with architecture diagram + results table; `make benchmark` reproducibility; demo video; short blog answering "does multi-agent coding pay off?". | Repo is public, reproducible from clean clone, and the headline number is front-and-center. | 08 |
| **S1** *(stretch)* | **Parallel specialist reviewers** | Add independent security/perf/style reviewers run in parallel (the architecturally sound multi-agent case); measure if *this* is where coordination wins. | Comparison isolates parallel-review gains. | 08 |
| **S2** *(stretch)* | **Multi-model cost-per-success** | Re-run the harness across 2–3 open models; plot cost-per-solved-task by model. | A second result axis with near-zero new code. | 08 |
| **S3** *(stretch)* | **Real GitHub PR demo** | Best-multi opens a real PR on a throwaway repo — for the video only, outside the scored run. | Demo video shows a real PR; scored runs stay sandbox-only. | 08 |

---

## Part D — Appendix

### D.1 Open-model / provider shortlist (prices move; verify before committing)
- **Hosted (router via LiteLLM):** OpenRouter (widest catalog, some free-tier models), Together, Groq (fast), Fireworks, DeepInfra.
- **Strong coding open models to try:** Qwen3-Coder, DeepSeek-V3.x / R-series, GLM-4.6, Kimi, gpt-oss.
- **$0 path:** run a quantized coding model locally on the **college GPU via Ollama**; point the router at the local endpoint. Use this for development and the bulk Developer/Tester turns; reserve a hosted strong model for Architect/Reviewer if needed.
- **Tiering:** strong model → Architect + Reviewer; small/fast model → Developer + Tester bulk loops.

### D.2 Metric scorecard (fill in as you build)
| Configuration | Success rate | p50 / p99 latency | Tokens / $ per solved task | Hallucination rate | Mean iterations |
|---|---|---|---|---|---|
| Single agent | | | | | |
| Multi-agent (best) | | | | | |
| *(stretch)* + parallel reviewers | | | | | |
| *(stretch)* model B / model C | | | | | |

### D.3 Top risks & mitigations
- **SWE-bench env setup eats the timeline.** → Reuse the official harness; isolate failures in the `harness-debugger` sub-agent; cap the task set; get the thin slice (Spec 04) working on *custom* tickets before touching SWE-bench images.
- **Multi-agent doesn't beat single.** → Expected and fine; it's the honest finding. Report the cost multiple and *where* it helped. This is the strong result, not a failure.
- **Cost creep.** → Caps + cache + cheap models + local Ollama; record cost per call from day one (Spec 01).
- **Scope sprawl.** → Non-goals in A.11 are binding; stretch specs only if time remains after Spec 09.
- **Conflating the two model layers / the two MCP layers.** → The `CLAUDE.md` rule and B.6 note exist precisely to prevent this.

### D.4 Definition of "done" for the whole project
Public, reproducible repo; architecture diagram; the single-vs-multi headline table with real numbers; a demo video; and a short writeup whose first sentence states the measured answer to "does multi-agent coding pay for itself?" That sentence is the résumé bullet.
