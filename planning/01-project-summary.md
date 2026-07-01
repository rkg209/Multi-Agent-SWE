# project-summary.md

```markdown
# Multi-Agent SWE System + Benchmark — Executive Summary

## What It Is

A controlled measurement study, packaged as a working software system.

The system itself is a multi-agent coding pipeline: four AI agents — an
Architect, a Developer, a Tester, and a Reviewer — collaborate to resolve
a software engineering ticket. Each agent has a defined role and calls an
open-source language model through a cost-tracking router. The pipeline is
wrapped in a reproducible benchmark harness that runs the same fixed set of
~30–50 coding tasks, scores the results objectively (do the hidden tests
pass?), and records exactly what each run cost in tokens, time, and money.

The headline output is a single, honest comparison table:

> **Does a multi-agent team outperform a single agent on coding tasks,
> and if so, at what cost multiple?**

## Who It Is For

**Primary audience: applied-AI and ML engineering interviewers** evaluating
candidates for roles that involve building, evaluating, or operating AI
systems in production.

**Secondary audience: anyone choosing or tuning a coding agent** — the
benchmark harness and results table are directly useful to practitioners
who need evidence, not demos, before trusting an agent with real work.

## Why It Matters

### The measurement is the product

Coding agents are commoditized. What is rare — and what this project
delivers — is *measurement discipline*: a deterministic scorer, full
token/cost/latency/hallucination tracking per run, and a clean controlled
comparison on a fixed, credible task set (SWE-bench Lite/Verified). The
result is evidence, not a demo reel.

### The finding is valuable either way

Current research (2025) shows single agents often match or beat multi-agent
systems on sequential, context-heavy tasks under equal compute. This project
is designed to surface that nuance honestly. A result of "multi-agent bought
+X% success at Y× the cost, and here is exactly where coordination helped
and where it just burned tokens" is the strong outcome — and it is robust
no matter which way the numbers fall. The résumé bullet leads with the
measured number, not a claim that multi-agent is better.

### It proves a rare combination of skills

Most candidates demonstrate either agent-building *or* evaluation. This
project requires both simultaneously: multi-agent orchestration (LangGraph),
model routing and cost control (LiteLLM, open models), sandboxed execution
(Docker), reproducible benchmarking (SWE-bench harness), hallucination
detection, trace storage (Postgres), and a results dashboard (Streamlit) —
all in one coherent, end-to-end system with a CI-reproducible `make
benchmark` entry point.

## What Gets Built and Delivered

| Artifact | Purpose |
|---|---|
| Multi-agent pipeline (Architect → Developer → Tester → Reviewer) | The system under study |
| Single-agent baseline | The comparison baseline (same graph, one node) |
| Benchmark harness + deterministic scorer | Objective, repeatable measurement |
| Metrics store + dashboard | Single-vs-multi headline table and plots |
| Public repo with `make benchmark` | Reproducibility for any reviewer |
| Architecture diagram + demo video | Accessible explanation of the system |
| Short writeup / blog post | The recruiter-legible artifact; answers "does multi-agent coding pay for itself?" in plain language |

## What It Is Not

It is not a competitor to Cursor, Codex, or Claude Code on absolute coding
performance. It does not run the full SWE-bench suite. It does not offer a
polished chat interface. These are deliberate non-goals that protect the
timeline and keep the project's claim honest: this is a measurement study,
and the measurement is what makes it worth doing.
```