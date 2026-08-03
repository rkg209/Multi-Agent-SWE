# Writeup: Does Multi-Agent Coding Pay For Itself?

> **Status: draft skeleton, not yet finalized.** This writeup is written *after* the numbers exist,
> per Spec 09's plan — and as of this draft, no real benchmark run has ever been executed in this
> project (Docker has not been available in any development session so far; see
> `progress_report.md` Sequence 14, and the open item in `README.md`). Every `TODO` below is a
> real gap, not a formatting placeholder. Fill it in from `reports/headline.md` and
> `reports/headline_env.md` after running:
>
> ```bash
> make setup
> make benchmark TASKS=lite-5 SOLVER=single
> make benchmark TASKS=lite-5 SOLVER=multi
> make headline
> ```

## The answer

TODO — one sentence, e.g.: "On SWE-bench Lite (N=5 tasks), the four-agent system resolved **X%**
of tasks vs. the single agent's **Y%**, at **K×** the cost per solved task." If multi loses on
this subset, say so plainly here — that is itself a finding, not a failure to report.

## Results

| Metric | Single agent | Multi agent |
|---|---|---|
| Success rate | TODO | TODO |
| Mean cost / solved task ($) | TODO | TODO |
| Total cost ($) | TODO | TODO |
| p50 latency (s) | TODO | TODO |
| p99 latency (s) | TODO | TODO |
| Mean iterations | TODO | TODO |
| Hallucination rate | TODO | TODO |

Cost multiple = `multi.total_cost_usd / single.total_cost_usd` from `fetch_latest_totals()`
(`dashboard/data.py`); success-rate delta and the rest come straight from
`headline_metrics`/`reports/headline.md`.

## Where it helped, where it burned tokens

TODO — this section requires reading actual `trace_events` from a real run, not guessing. Source
material once a run exists:

- `task_cost_breakdown` view (`scripts/db_init.sql:285`) for per-agent token splits on the `multi`
  runs — did the Architect's plan measurably change what the Developer produced, or did the
  Reviewer just re-serialize the same diff at extra cost?
- Pick 2-3 individual multi-agent task traces (`/trace <run-id>` or a direct `trace_events` query)
  and read them end-to-end: cases where the Tester caught a real regression before Review, cases
  where the Architect→Developer handoff added tokens without changing the resulting patch, cases
  where the Reviewer's requested changes actually fixed something the Developer got wrong.
- Compare per-task outcomes directly: did `multi` solve any task `single` failed, and vice versa?
  That asymmetry (not just the aggregate rate) is the more informative number on a 5-task subset.

## Threats to validity

- **5-task subset.** `lite-5` is a smoke-test-sized sample; one flipped task moves the pass rate by
  20 percentage points. `lite-30` is the credible-headline upgrade path (see `README.md`).
- **Single seed, one run per solver (plus one repeat `multi` run for spread).** No statistical
  confidence interval — the repeat `multi` run's spread is reported as the honest tolerance
  (**±1 task**), not a computed standard error.
- **Temperature > 0.** Both solvers are stochastic; a rerun on the same subset can disagree with
  itself, independent of any real capability difference between single and multi.
- **One model pairing.** Strong tier = Qwen-2.5-72B-Instruct (OpenRouter), small tier =
  Llama-3.1-8B-Instant (Groq) — see `config/litellm_config.yaml`. The single-vs-multi delta
  measured here is conditional on this specific model pairing; a stronger or weaker small-tier
  model could change which side wins.
