# Writeup: Does Multi-Agent Coding Pay For Itself?

Run date: 2026-08-04. Task subset: `lite-5` (`config/tasks/lite-5.txt`, 5 SWE-bench Lite instance
IDs) plus the 2 in-repo custom tickets the loader always includes — 7 tasks per run. Strong tier:
`openrouter/qwen/qwen-2.5-72b-instruct`. Small tier: `groq/llama-3.1-8b-instant`. Run IDs: single
`132b99e1`, multi `821c670b` (cold cache) and `07667bb4` (warm-cache repeat).

## The answer

**On this subset, multi-agent did not resolve any task the single agent didn't, and cost 4.5× as
much per solved task doing it.** Both solvers passed exactly the same 2 of 7 tasks (28.57%) — and
those 2 are the only tasks in the subset capable of passing at all (see "What this subset can
actually measure" below), so the honest reading is **2/2 vs. 2/2, not a 28.57% SWE-bench Lite pass
rate for either solver.** On real SWE-bench issues, this run measured nothing, because the harness
can't execute them yet. Where a real capability delta could show up — the 2 custom tickets — multi
added cost without adding correctness.

## What this subset can actually measure

`benchmark/solver.py:128` short-circuits both `SingleAgentSolver` and `MultiAgentSolver` to an
empty patch for any task whose `source != "custom"`, because the task loader (Spec 03) resolves
only instance IDs, not an actual repo checkout — there is no local `base_dir` for
`astropy__astropy-12907` or the three `django__django-*` instances to hand the agents. On top of
that, `sb-cli` scoring is unavailable without `SWEBENCH_API_KEY`, so even a real patch against
those 5 couldn't be scored yet. This is a documented Spec 03 non-goal, not a regression introduced
here — but it means **5 of the 7 "tasks" in every `lite-5` run are structurally unwinnable**, for
either solver, before a single token is spent. The only two tasks either solver has ever had a
chance to actually solve are `custom-001-calc-add` and `custom-002-str-reverse`. Both passed, both
times, for both solvers. That is the entire signal this run contains. Fixing dataset fetching so
the real SWE-bench instances are winnable is out of scope for Spec 09 (see `specs/09.../spec.md`'s
Non-Goals) and is the single highest-leverage next step for making this comparison mean something.

## Results

| Metric | Single (`132b99e1`) | Multi, cold cache (`821c670b`) | Multi, warm cache (`07667bb4`) |
|---|---|---|---|
| Success rate (of 7) | 28.57% (2/7) | 28.57% (2/7) | 28.57% (2/7) |
| Total cost ($) | 0.00011041 | 0.00050018 | 0.00003069 |
| Mean cost / solved task ($) | 0.00005521 | 0.00025009 | 0.00001535 |
| Total tokens | 2,973 | 6,600 | 6,600 |
| p50 latency (s) | 0.001 | 0.001 | 0.001 |
| p99 latency (s) | 3.556 | 8.162 | 3.566 |
| Mean iterations | 0.86 | 0.86 | 0.86 |
| Hallucination rate | 0 | 0 | 0 |

**Cost multiple: 4.5×** (`0.00050018 / 0.00011041`, cold-cache multi vs. single — the representative
comparison). **Token multiple: 2.2×** (6,600 / 2,973) — architect + tester calls on top of the same
developer work single already does. The warm-cache multi run's far lower cost ($0.00003069, a 16×
swing from the cold run) is **not** stochastic variance — `src/router`'s response cache (Spec 01)
served nearly every call from the earlier identical run for free, because both custom tasks are
short, deterministic prompts. p99 latency tells the same cold/warm story: 8.162s cold vs. 3.566s
warm, both against literally the same two tasks seconds apart. **The tolerance this project
documents (±1 task on a 5-task subset, temperature > 0) never came into play here** — the actual
observed spread between repeat runs was entirely a caching artifact, not the solver disagreeing
with itself. That's a different, and arguably more important, threat to validity than the one
originally anticipated (see below).

Mean iterations (0.86) is identical across every run because it's the same fixed 7-task subset
producing the same fixed per-task iteration counts each time — not evidence of consistency under
real variation, just evidence that these particular runs were close to deterministic.

## Where it helped, where it burned tokens

**The Reviewer never ran, in either multi run — and given how this harness is built, it structurally
couldn't have.** `src/graph/graph.py`'s `_after_tester` only routes to `reviewer` when
`state["test_passed"]` is `True`, and `test_passed` is not the model's opinion — both
`tester_node` and `developer_node` set it from the real sandbox `pytest -q` exit code
(`src/agents/tester.py:48`). The catch: `hidden_test.py` for each custom ticket is "not part of
`base/` — copied in only at score time" (`src/agents/developer.py:7-8` and every custom ticket's
own docstring). Inside the graph, the workspace never contains a hidden test to run against — only
whatever test file the Developer chooses to write itself. Neither model, on either custom task,
wrote a self-verifying test alongside its fix, so `pytest -q` collected zero tests every iteration
(a non-zero exit), `test_passed` stayed `False` for all `DEFAULT_MAX_TEST_ITERATIONS=3` attempts,
and both tasks exited via `_after_tester`'s iteration-cap branch to `END` — never reaching
`reviewer` — even though `benchmark/scorer.py`'s separate, real hidden-test run at score time
confirmed both final patches were in fact correct. So the actual finding is sharper than "the
Tester was wrong": **the harness only ever lets the Developer's own test-writing behavior open the
door to Review, and on this run, with these models, the Developer never wrote one.** The
integration test `tests/integration/test_multi_agent/test_e2e.py` originally hard-asserted
`reviewer` always appears in the trace; running it against real infrastructure for the first time
(this session) proved that assumption false, so it now asserts only
`{architect, developer, tester}` and documents why `reviewer` isn't guaranteed. Any claim about the
Reviewer catching real defects is unverifiable from this data — there is no Reviewer trace to
inspect on any run so far. This is the single most important qualitative finding here, and it
directly explains the headline result: if the pipeline structurally can't reach its most
differentiated agent without the Developer choosing to write tests unprompted, multi-agent degrades
to "developer + an expensive architect + an expensive tester" — cost without the mechanism that was
supposed to justify it.

**Where the extra cost went (from `task_cost_breakdown`/`trace_events` per-agent split, cold-cache
run `821c670b`):** Architect — 2 calls, 663 tokens, $0.00023935 (one per custom task, cache-miss
both times — openrouter pricing is the most expensive per-token tier in this config). Developer —
6 calls, 3,353 tokens, $0.00015851. Tester — 6 calls, 2,584 tokens, $0.00010232. The Architect is
the single most expensive per-call agent (highest $/token tier, `strong` pricing) for a role that,
on these 2 tasks, produces a one-shot plan the Developer follows without visible disagreement in
the trace — there's no evidence in this run that the Architect's plan changed what the Developer
would have produced on its own for a task this small (`calc-add`, `str-reverse`).

## Threats to validity

- **5 of 7 tasks per run cannot pass, for either solver, by construction** (see above) — this is
  the dominant threat, more significant than sample size. The comparison that exists is 2 tasks,
  not 5 or 7.
- **The observed "spread" between repeat `multi` runs was a caching artifact (16× cost swing), not
  the documented ±1-task stochastic tolerance** — running the same fixed, tiny, deterministic task
  set twice in quick succession mostly measures the response cache, not solver variance. A
  meaningful repeat-run comparison needs either cache disabled or genuinely different task content
  between runs.
- **The Reviewer path is entirely untested by this run** — zero Reviewer invocations means zero
  evidence either way about whether the fourth agent helps or hurts. Any future subset should be
  sized/composed so at least some tasks are capable of exercising the full four-agent pipeline.
- **Single seed, one model pairing.** Strong tier = Qwen-2.5-72B-Instruct (OpenRouter), small tier
  = Llama-3.1-8B-Instant (Groq). A model more inclined to write its own tests unprompted might
  actually reach the Reviewer and change which solver wins — this run can't distinguish "the
  Reviewer wouldn't have helped" from "the Reviewer never got the chance."
- **`lite-5` is a smoke-test-sized sample by design** (NFR-7's version-locked subset). `lite-30`
  is the documented upgrade path, and — given the finding above — is necessary, not just nice to
  have, before this comparison says anything about multi-agent SWE-bench performance specifically.
