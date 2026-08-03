# Demo video shot list (~90 seconds)

Record after a real `multi` benchmark run exists (Spec 09 Phase 4) so the dashboard has real data
to show. Screen recording, no narration required — captions/on-screen text are enough.

| # | Seconds | Shot | Command / action |
|---|---|---|---|
| 1 | 0-10 | Clean tree, recent history | `git status` (clean) then `git log --oneline -10` |
| 2 | 10-25 | Pre-warmed setup | `make setup` running with Docker already warm (compose up, schema, sandbox image build) — speed up or cut dead time in editing |
| 3 | 25-55 | The real run | `make benchmark TASKS=lite-5 SOLVER=multi` — let the agent handoff log lines scroll (Architect → Developer → Tester → Reviewer) so the four-agent structure is visible, not just a spinner |
| 4 | 55-65 | Sandbox isolation | Cut to `docker ps` or the container logs mid-run, showing the `swe-sandbox:0.1.0` container executing the generated patch — this is the one non-negotiable shot: it's the proof the sandbox rule is real, not asserted |
| 5 | 65-85 | Results landing | `make dashboard`, browser open to `localhost:8501`, showing the new row appear in the headline table (refresh or `st.cache_data` TTL expiry) and the cost/latency scatter |
| 6 | 85-90 | Close | Headline table full-screen for a beat — end on the number, not a title card |

Notes:
- Keep terminal font large enough to read at 1080p.
- If `make benchmark` takes longer than the recording budget, pre-run it once, then do a second
  take with the terminal history replayed at 2-4x in editing rather than narrating over dead air.
- Prefer a task that's likely to actually pass for the "results landing" shot — a `FAIL` row is
  fine to show once, but don't end the video on it.

## Manual publish checklist (user-performed, not automated)

- [ ] Record the video per the shot list above.
- [ ] Upload it (YouTube unlisted or Loom).
- [ ] Paste the URL into the `## Demo video` section of `README.md`.
- [ ] Decide: keep `specs/`, `CLAUDE.md`, `progress_report.md`, `MANUAL_TESTING.md` private
      (currently `.gitignore`'d — `.gitignore:34,49-52`) or un-ignore them before publishing. For a
      portfolio piece the spec-driven-development trail is often the most impressive part; the
      current default keeps it local-only. This is a deliberate call, not an oversight — make it
      before flipping visibility.
- [ ] `gh repo edit --visibility public` (only after the above is decided).
- [ ] Confirm the CI badge/workflow run on `main` is green after the first push.
