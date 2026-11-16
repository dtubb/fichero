# Review of `performance-sweep.md` (skeptical pass, 2026-11-15)

Reviewer stance: this spec is ambitious for a harness whose perf rung has never produced one number. Judge it by whether
Step 1 and Step 2 alone would already have given the owner something, and cut the rest until they have.

## Gaps and weak claims
- **Unverified tool details.** The `xcresulttool get build-results` JSON shape, the xctrace table schema names beyond
  `time-profile`/`potential-hangs`/`os-signpost`, the test-plan keys for Thread Performance Checker, and which MetricKit
  fields macOS fills are all stated as "pinned on the first real run". That is honest but means Steps 6 and 8 cannot be
  fully fixture-tested before someone runs the tool on the M4 once. Each needs a 30-minute probe on the M4 before its
  lane starts, with the real outputs committed as the fixtures.
- **Root cause of #6589 is guessed, not found.** The spec names three ways `_remote_build` returns `None` and says the
  first real reason gets written into the issue. Good, but Step 1 should be the manager's own two-hour task, not a lane.
- **The stable build tree filter.** If `_stable_build_tree` excludes `scripts/` or `fichero-server/tests/`, the engine
  rung can never run remotely as written; the spec asks Step 1 to check, it should assert it with a test.
- **`FICHERO_PERF_WORKLOAD` scenarios in the app** are new app code (W6–W10 drivers) on top of the smoke scenario's test
  hooks. That is a Swift lane's work, not a harness lane's, and depends on dev-workflows Step 2.8 landing first.
- **Simulator rows** are "recorded, never ratcheted" but can still file issues via the filing rule; add "simulator rows
  never file" or they will produce noise.
- **No budget for the readers' own cost.** Parsing a 2 GB `.trace` export or a memray `.bin` on the M4 is minutes; the
  nightly window needs a total cap and an order of eviction (which workload is dropped first when the night overruns).

## Cost and runtime per batch / per night (estimates, M4)
- Batch (unchanged by this spec): engine perf + security ≤ 6 min, app perf ≤ 5 min, the warnings ratchet ≈ 10 s on an
  existing result bundle. `-resultBundlePath` adds ~50–200 MB per build to the Dev Disk: needs the same 30-day sweep.
- Nightly, new: engine profiles W1, W3–W5 ≈ 10–15 min; W2 (Kraken, 20 pages) ≈ 5–15 min under memray (a third slower);
  five xctrace templates × five app workloads ≈ 25 recordings × 1–3 min ≈ 40–60 min plus export; the diagnostics plan
  under TSan then ASan ≈ 2 × the unit-test time (20–40 min). Total ≈ 2–2.5 h a night on the M4 behind the heavy lock,
  on top of the daily builds. Fine while nothing else runs overnight; wrong the moment the M4 is also a batch runner at
  night. The spec should state the window (e.g. 01:00–05:00) and what is skipped when it is missed.
- Model cost: zero for measuring; the filer and reviewer are the existing ones. Issue noise is the real cost: 10 issues a
  day at the filer's cap is too many for one owner to read. Start at 3 a day for the sweep as a whole.

## Flaky-measurement risks
- The M4 is headless with a GUI session kept alive by hand; a locked screen voids every app recording silently
  (`locked-session-blocks-screenshots-and-cgevents`). The driver must check the session before recording and mark
  `not-run`, or the trend column will show 40% swings that are the lock screen.
- Thermal: W2 heats the machine; running app recordings after it skews them. The spec orders profiles after builds but
  should put W2 LAST of everything and require `nominal` before each recording (perf_trial's VOID rule applied per step).
- First-run effects: Kraken and spaCy model loads, DuckDB WAL replay, the simulator boot. The cold-discarded rule covers
  the engine; the app workloads need an explicit warm launch before the measured one.
- Noise band of 15% as the "never enforce" line: likely too tight for W6 launch on a machine that also runs builds;
  expect launch to be `noisy` for weeks. Acceptable if it still files hotspots; say so.

## Cut for v1
OVERRULED 2026-11-15: all eight build-order steps are v1 and none is deferred (see `performance-sweep.md`, Build order).
- Keep: Step 1, Step 2 (log readers + table + console), Step 5 (filing from log rows alone), Step 6 (warnings).
- Defer: py-spy (pyinstrument is enough to name the first ten hotspots), memray (peak RSS from `time -l` first), the
  diagnostics test plan, MetricKit subscriber and Organizer read, iOS/iPad simulator profiles, `Energy Log`, `builder
  perf diff`, the rolling overflow issue. Reduce xctrace to Time Profiler + SwiftUI on W6–W8 only.
- Reduce workloads to W1, W2, W3, W6, W7, W8 for the first month; W4, W5, W9, W10 once the table is being read.
- One corpus: the generated fixture. No external HTR set until the owner picks one (question 5).

## Open questions for the owner
1. ANSWERED 2026-11-15: new `performance-sweep` milestone (see `performance-sweep.md`, Open questions 1).
2. ANSWERED 2026-11-15: a `sudoers` line for `py-spy` on the M4 only, allowing nothing else (see `performance-sweep.md`, Open questions 2).
3. Profiles stay on the M4's disk with the run id in the issue, or are pushed somewhere attachable?
4. PARTLY ANSWERED 2026-11-15: no daily cap; every spot over its floor is filed, deduped by key (see `performance-sweep.md`, Filing rule). Filing floors (5% / 50 MB / 10 MB / 250 ms) still open.
5. Which open corpus beyond the generated one, if any; and is an iOS device on the M4 wanted for energy?
6. The nightly window on the M4 (proposed 01:00–05:00) and whether app recordings may be skipped on a locked session.
