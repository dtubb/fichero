# Performance sweep — find the slow and heavy parts, then keep them fast — Design Spec (#6600, #6610, #6589)

> Milestone: performance-sweep
> Manual: TBD — contributor-facing only (`docs/contributor_manual/how-fichero-is-built.md` gets one paragraph: where
> the hotspot table and the warnings list live and how a `Performance - <area>` issue is born). No user-facing surface.

> Design-led (Testing Constitution). **Status: DRAFT — awaiting the owner's approval (written 2026-11-15 from the owner's
> rulings of 2026-11-14 and 2026-11-15 on #6600, paraphrased).**
> Tags: [OK] built and tested by name · [PARTIAL] exists, not wired · [GAP] not built · [BROKEN] built, does not run.
> Scope with other specs: `harness/dev-workflows.md` keeps the ladder, the rungs and the method
> (`quality.perf-method`, `quality.perf-rung-engine`, `quality.perf-rung-app`, `quality.security-scan-rung`,
> `quality.perf-security-sweep`, Steps 2.30–2.32). This spec owns what those rungs FEED and what comes OUT: the sources, the
> fixed workloads, the ranked hotspot table, the filing rule, the ratchet's budgets and the warnings list. Where a bullet
> here changes a dev-workflows bullet, the change is named under "Changes to dev-workflows" at the end.

## Intent

The owner's first goal (2026-11-15, paraphrased): the builder finds the slow and heavy parts of the app and the engine,
and lanes speed them up; past "look at X and make it fast" asks produced the biggest wins, so the harness should produce
those asks on its own. The dimensions are time, CPU, RAM, disk, energy and efficiency (work done per unit of each), for the
Swift app on Mac, iPhone and iPad and for the Python engine. The second goal is that nothing gets slower unnoticed. The
third is that compiler, SwiftLint and Xcode build-system warnings are found, listed and worked down the same way; the
example given is the build-system line about a script phase that runs on every build because it names no outputs.
The sweep's output is a RANKED list of slow and heavy spots (time, CPU, RAM, disk, energy, warnings), each of which becomes a "speed up X" lane, and it reads the logs the app already makes (the `LaunchProfile` and `InteractionProfile` signposts, the engine's `PERF … duration_ms` lines, and Xcode Organizer and MetricKit field data).

Three rules shape everything below. **Platform tools measure, we only read:** `xctrace`, `xcresulttool`, XCTest metrics,
MetricKit, `log show`, pyinstrument/py-spy, memray, `du`; no timer of ours (`adopt-tools-dont-write-our-own`). **Heavy
work runs on the M4 build runner** (`[machines].m4air`, `[check].build_remote`), never on the manager's 16 GB Pro; an app
profile needs the M4's GUI session (`m4-smoke-needs-a-gui-session`). **A measurement that did not happen is NOT GREEN:**
a rung whose tool refused, whose runner was down or whose run printed nothing shows as `not-run`, in the ladder, the
journal and the console (rule 0 of the ladder; #6589 item 1–2 are exactly this failure).

## Sources — what is measured, with what, where

Every source produces rows of one shape (see `perf-sweep.output.row`); the readers below are the only code this spec adds
on the measuring side. Machine: **M4** for everything in this section unless a row says otherwise.

- `perf-sweep.source.app-log-phases` [PARTIAL] (#6600) — the app's existing launch and interaction timelines are read from
  every smoke, UI-test and perf run, not only from fresh profiles. `LaunchProfile.milestone` logs
  `⏱ <name> @ <ms>ms` (category `LaunchProfile`) and `InteractionProfile` logs a measured-milliseconds line per phase and
  lap (category `InteractionProfile`), both under subsystem `app.fichero.fichero`, each beside an `os_signpost` on the
  Points of Interest track. Capture is LIVE, because `.info` lines are not persisted to the on-disk log store (the trap
  recorded in `LaunchProfile.swift`): the driver starts `log stream --info --style json --predicate 'subsystem ==
  "app.fichero.fichero" AND (category == "LaunchProfile" OR category == "InteractionProfile" OR category ==
  "BodyCount")' > <run>/app-log.jsonl` BEFORE launching the app, and also launches with
  `FICHERO_LAUNCH_PROFILE_STDOUT=1` and keeps stderr, so a run with no log stream still has the launch timeline. When a
  `.trace` exists for the run, the `os-signpost` table (`xcrun xctrace export --input <t> --xpath
  '/trace-toc/run[@number="1"]/data/table[@schema="os-signpost"]'`) is the authoritative source for the same phases and
  the log is the cross-check. The reader groups by phase name (launch milestones become the gap to the previous milestone;
  interaction intervals and laps keep their names) and emits per phase: count, p50, p95, max, in ms. Acceptance (a fixture
  `app-log.jsonl` and a fixture signpost export, no Mac): 40 `sidebar expand` intervals give one row with count 40 and the
  right p50/p95; the launch milestones become ordered gaps whose sum is the last milestone's elapsed; a run with the
  stderr timeline only still yields the launch rows; the signpost export and the log for the same run agree within 5 ms or
  the row is marked `disagree` (never silently averaged). Test (to write):
  the new test_perf_log_readers file in fichero-server/tests/unit/scripts, case test_launch_and_interaction_lines_become_phase_rows_with_p50_p95_count.
  Built: the log and stderr readers. Not built: the signpost-export cross-check and the `disagree` mark (Step 8).
- `perf-sweep.source.engine-perf-lines` [PARTIAL] (#6600) — `core/perf.py::perf_span` logs `PERF <name> <k=v …>
  duration_ms=<n>` and `model_load` logs `model-lane: loaded <model> in <s> s (load <n> in this engine)` plus the
  WARNING `model loaded again`. The reader takes an engine log (the run's, or the app's embedded-engine log from a smoke
  run) and emits one row per span name with count, p50, p95, max, total (count × p50, the "how often" figure the owner
  asked for: a 4 ms span that runs 9 000 times outranks a 200 ms span that runs once), plus one row per model with its
  load count and total load seconds, and a `reload` flag when the warning fired. Context keys that vary per call
  (`doc_id`, paths) are dropped; a key named in `[perf].group_by` (e.g. `provider`, `pages`) splits the row. The
  slow-path lines `quality.slow-path-ratchet` names (the Kraken per-page line, the cloud-batch waits) are read by that
  ratchet, not here; this reader hands it the same parsed rows. Acceptance (fixture log): three names with known
  durations give three rows with exact p50/p95/total; a model loaded twice 30 s apart yields `reload: true`; a line that
  is not `PERF` or `model-lane` is ignored; an empty log gives zero rows and the run is marked `no-engine-log`, not
  green. Test (to write): test_perf_log_readers (a new test file), case test_perf_spans_group_by_name_with_count_total_and_model_reloads.
- `perf-sweep.source.engine-profiles` [PARTIAL] (#6600, #6614) — fresh engine profiles over the engine workloads (W1–W5 below),
  nightly, on the M4's gate venv, one workload at a time behind the heavy lock. **Time:** `pyinstrument -r json -o
  <run>/<w>.pyinstrument.json -r html -o <run>/<w>.html -- <driver>` is the batch and nightly default (in-process, no
  root). `py-spy record --format speedscope -o <run>/<w>.speedscope --subprocesses -- <driver>` is used when the runner's
  `sudoers` allows `py-spy` without a password for the gate user (py-spy attaches with `task_for_pid` and needs root on
  macOS); it is the only profiler that sees the worker processes the engine forks (`--subprocesses`) and native frames in
  DuckDB, numpy and MLX, which pyinstrument attributes to the calling Python line. Whether `py-spy` is permitted is a
  declared machine fact (`[machines].m4air.sudo = ["py-spy"]`), never probed by trying. Owner 2026-11-15: py-spy may run with sudo on the M4 only, through one narrow sudoers line that allows nothing but py-spy; no other machine gets it, and pyinstrument is the fallback everywhere else. **RAM:** `memray run --native
  --follow-fork -o <run>/<w>.bin <driver>` then `memray stats --json -o <run>/<w>.memray.json <run>/<w>.bin` (peak,
  top allocators by size and by count) and `memray flamegraph -o <run>/<w>.memray.html <run>/<w>.bin` for the reviewer;
  `/usr/bin/time -l` wraps every driver for the zero-overhead peak RSS (`maximum resident set size`) that the rung holds.
  **Disk:** `du -sk` of the scratch library, the engine cache dir, its log dir and the models dir before and after
  (`perf-rung-engine`'s pairs, unchanged), the delta per directory held exactly; DuckDB spill and old-row-version MiB
  from `db/busy_evidence.py`'s lines. **CPU and energy:** CPU seconds from `/usr/bin/time -l` (`user` + `sys`) and the
  ratio CPU/wall (parallel efficiency; a workload at 0.9 on an 8-core run is serial work waiting to be found); energy on
  the Mac is CPU time (no per-process energy counter is available without root; `powermetrics` is NOT used). Rows: the
  top 15 self-time frames that are ours (`fichero_server/`, `fichero_cli/`, `fichero_mcp/`), each with self ms, total ms,
  call count where the tool gives it, and share of the workload's wall; the top 10 allocation sites by peak bytes; one
  row per directory with its delta KiB; one row per workload with wall, CPU, CPU/wall, peak RSS. Acceptance (fixture tool
  outputs, no engine): a pyinstrument JSON yields our frames only, ranked by self time with the share computed against
  the root's time; a memray stats JSON yields allocator rows by peak bytes; a `time -l` text yields RSS, user and sys;
  `du` pairs yield deltas; a machine without `sudo = ["py-spy"]` never spawns py-spy and the run says
  `profiler: pyinstrument`. Test: fichero-builder/tests/test_perf_sweep.py, case test_engine_profile_readers_rank_own_frames_allocators_disk_and_cpu_efficiency.
  Built (#6614): the readers and `builder perf profile --gate <dir>` (`perf_profiles.py`); py-spy only when declared and its sudoers line is on the machine (else a row says so). Not built: the nightly schedule entry and a real run on the M4.
- `perf-sweep.source.app-profiles` [GAP] (#6600) — fresh app profiles over the app workloads (W6–W10), nightly, on the
  M4's GUI session, the Dev Local build from the daily `tests` build's derived data (`build-for-testing` output). The
  recorder is `xcrun xctrace record --template '<T>' --time-limit <s>s --launch -- <app> --env
  FICHERO_PRINT_CHANGES=1 --env FICHERO_PERF_WORKLOAD=<w> --output <run>/<w>.<T>.trace` for the templates `Time
  Profiler` (includes the Hangs instrument's `potential-hangs` table in Xcode 15+, which `scripts/check_hang_ratchet.py`
  already reads, and the `os-signpost` table), `Allocations`, `Leaks`, `SwiftUI` (view body counts and update causes),
  `File Activity` (bytes written per file and per call, the app's disk figure), `App Launch` (W6 only). `Energy Log`
  records on an iOS device only: it runs when a device is attached to the M4 and is otherwise a `not-run` row, not a
  gap; on the Mac CPU time stands in. The app drives itself through the workload (`FICHERO_PERF_WORKLOAD` selects a
  scripted scenario in the Dev Local build's test hooks, the smoke scenario's mechanism) so no XCUITest runner competes
  for the GUI during a recording. Export is `xcrun xctrace export --input <t> --toc` once (the table list is recorded
  with the run) then `--xpath '/trace-toc/run[@number="1"]/data/table[@schema="<s>"]'` for `time-profile`,
  `potential-hangs`, `os-signpost`, and the allocation, leak, SwiftUI and file-activity schemas the toc names (their
  exact names are pinned in `scripts/perf_trace_schemas.json` on the first real export and REFUSED when a toc lacks one).
  Rows: top 15 self-time symbols in our module (`Fichero`), with share of the scenario's wall; every hang over 250 ms
  with its stack's top own frame; persistent bytes at scenario end by category and the top own allocation sites; every
  leak (count held at zero); body evaluations per view per scenario (cross-checked against the `BodyCount` log lines the
  `perf-rung-app` bullet reads); bytes written per path and per scenario; the launch phases from `App Launch`. The
  xcresult of the perf test plan (`perf-sweep.source.xctest-metrics`) is a sixth input to the same rows. Acceptance
  (fixture exports, no Xcode): a `time-profile` export yields own-symbol rows with shares; a `potential-hangs` export goes
  through `check_hang_ratchet.py`'s parser unchanged and yields one row per hang; a leaks export with one row is a red row;
  a SwiftUI export with `SidebarView` at 31 bodies for `sidebar-click` yields that row; a file-activity export yields
  bytes per path; a toc missing a pinned schema is REFUSED naming it. Test (to write):
  test_perf_sweep (a new test file), case test_app_trace_exports_become_rows_per_template_and_a_missing_schema_refuses.
- `perf-sweep.source.runtime-checkers` [GAP] (#6600) — Xcode's runtime checkers run as scheme diagnostics in a dedicated
  test plan, `fichero/Tests/plans/fichero-diagnostics.xctestplan`, with two configurations because the Thread and
  Address sanitizers exclude each other: `tsan` (Thread Sanitizer, Main Thread Checker, Thread Performance Checker) and
  `asan` (Address Sanitizer, Undefined Behavior Sanitizer, Main Thread Checker, Thread Performance Checker), each toggled
  in the test-plan editor so the keys are the ones Xcode writes. It runs the existing unit and smoke tests (not the perf
  plan: a sanitized build is 2–5× slower and its timings are void) nightly on the M4 after the daily `tests` build:
  `xcodebuild test -project fichero/fichero.xcodeproj -scheme "Fichero (Dev Local)" -testPlan fichero-diagnostics
  -only-test-configuration <c> -destination platform=macOS -derivedDataPath derived-diagnostics -resultBundlePath
  <run>/diag-<c>.xcresult`. The reader takes runtime issues from the xcresult (`xcrun xcresulttool get test-results
  tests --path <x>` and the test's console log, where Main Thread Checker and TPC lines are `=== Main Thread Checker:
  …` / `Thread Performance Checker: …`) and the sanitizer reports (`SUMMARY: ThreadSanitizer: data race …`), one row per
  distinct (checker, top own frame), held at zero: a new row is a finding filed as `Performance - <area>` for TPC and MTC
  (main-thread I/O and priority inversions are performance) and as a bug for the sanitizers. Acceptance (fixture console
  logs): one TPC line yields one row with checker `tpc` and the frame; two identical MTC lines yield one row with count
  2; a clean log yields none; a plan run that did not finish is `not-run`. Test (to write):
  test_perf_sweep (a new test file), case test_runtime_checker_logs_become_rows_held_at_zero.
- `perf-sweep.source.xctest-metrics` [PARTIAL] (#6600; `quality.perf-rung-app` owns the plan) — the perf test plan
  `FicheroPerfTests` measures each app workload's scripted action with `measure(metrics: [XCTClockMetric(),
  XCTCPUMetric(), XCTMemoryMetric(), XCTStorageMetric(), XCTOSSignpostMetric(subsystem: "app.fichero.fichero", category:
  "PointsOfInterest", name: <interval>)])`, and W6 with `XCTApplicationLaunchMetric()` as
  `LaunchPerformanceUITests.swift` does today; `.xcbaseline` plists committed beside the target are Xcode's own judge
  (`xcresulttool get test-results summary` is what the rung reads). This spec adds nothing to the mechanism; it reads the
  per-metric averages out of the xcresult (`xcrun xcresulttool get test-results tests --path <x>`, the
  `performanceMetrics` of each test) as rows, so the table has one line per workload for clock, CPU, memory and storage
  even when the baseline passes. Built: `LaunchPerformanceUITests.swift` (launch only). Open: the plan, the four other
  actions, the baselines (Step 2.31). Test (to write): test_perf_sweep (a new test file), case test_xcresult_performance_metrics_become_rows.
- `perf-sweep.source.metrickit-and-field` [GAP] (#6600) — two field sources, both light. **In the app:** a
  `MXMetricManagerSubscriber` registered at launch in every channel writes each daily `MXMetricPayload` and every
  `MXDiagnosticPayload` as the JSON MetricKit itself produces (`jsonRepresentation()`) into
  `Application Support/Fichero/Metrics/<date>-<kind>.json`, keeps 30 days, and the Dev Local build's test hooks expose
  the folder; the reader takes launch (`applicationLaunchMetrics`), responsiveness/hang histograms
  (`applicationResponsivenessMetrics`), disk writes (`diskIOMetrics.cumulativeLogicalWrites`), memory (peak, average
  suspended) and CPU time, plus `MXHangDiagnostic`, `MXDiskWriteExceptionDiagnostic` and `MXCPUExceptionDiagnostic` call
  trees (top own frame), as rows tagged `field`. Which fields macOS fills versus iOS is recorded from the first real
  payload, not assumed. **From Xcode Organizer:** the Xcode MCP's `GetTopFieldPerformanceIssues` and
  `GetFieldPerformanceIssueLogs` (hangs, launch, disk writes, memory, energy for TestFlight builds) are called by the
  quality lane's nightly from any Mac signed into the team's App Store Connect; this is an API call, so it may run on the
  manager's Mac. Each reported issue is a row tagged `organizer` with its build and device class; every hang and disk-write
  exception is a filing candidate regardless of rank. Acceptance (fixture payloads): a hang diagnostic yields a row with
  the top own frame; a disk-write exception yields a row with bytes; a payload with no responsiveness metrics yields no
  hang row and the run notes the missing field; a field issue list of three yields three rows tagged `organizer`. Test
  (to write): test_perf_sweep (a new test file), case test_metrickit_payloads_and_organizer_issues_become_field_rows.
- `perf-sweep.source.machines` [PARTIAL] (#6600; `pool.machines-declare-capabilities`) — where each source runs is declared,
  not discovered: `[machines].m4air` gains `tags = ["pytest", "guards", "swift-build", "xcode-tests", "gui", "profile"]`
  and the optional `sudo = ["py-spy"]`; the sweep refuses to profile on a machine without `profile`, refuses an app
  profile without `gui`, and never places anything on the manager's Mac (`pool.hold-holds-one-machine`). The nightly
  order on the M4 is fixed so profiles never overlap a build: daily builds, the diagnostics plan, the perf plan, then the
  xctrace recordings and the engine profiles, each under the heavy lock. Acceptance: a rules file whose only `profile`
  machine lacks `gui` runs the engine profiles and marks the app profiles `not-run: no GUI machine`; a sweep configured
  with no `profile` machine refuses at load naming the tag.
  Test: fichero-builder/tests/test_perf_sweep.py::test_profiles_place_only_on_declared_machines_and_say_not_run_otherwise
  Built: tags and sudo are declared in `harness.toml [perf.machines.<name>]` (not in `[machines]`, whose line stays as it was), read by `fichero_builder/perf_workloads.py`. Not built: the fixed nightly order under the heavy lock (nothing calls `place()` yet, and there is no xctrace or sequencing code), and the rule that nothing is placed on the manager's Mac (`place()` would accept it if it carried a `profile` tag; today it holds only because that Mac is not declared).

## Workloads — the fixed, reproducible set

- `perf-sweep.workload.set` [PARTIAL] (#6600) — ten workloads, each a named scripted scenario with a fixed corpus, declared
  in `harness.toml [perf.workloads]` (name, side, driver, corpus, declared outputs, budget seconds). Engine (pytest
  drivers under `fichero-server/tests/perf/`, run one test per workload against a uvicorn engine, never `main()`):
  **W1 import** (the generated 200-page library: `scripts/perf_fixture.py` pages plus the pdf and image fixtures already
  under `fichero-server/tests/fixtures/`, imported from scratch), **W2 reader/OCR** (`fichero-server/scripts/bench_reading.py
  --pages 20` on W1's library with the bundled Kraken model; the one workload that may take minutes), **W3 search**
  (200 queries from a committed list over W1's library, text and semantic), **W4 KG** (the entity list, entity detail and
  neighbourhood perf tests, `test_entity_list_perf.py` / `test_entity_detail_perf.py`, against W1), **W5 Activity**
  (`scripts/perf_activity_store_5645.py`'s 200-job store, the jobs list and job tree routes). App (scripted in the Dev
  Local build under `FICHERO_PERF_WORKLOAD`, measured by the perf plan and recorded by xctrace): **W6 launch** (cold, to
  `launch-to-engine-ready`, on W1's library), **W7 sidebar** (click five rows, expand three folders, the
  `InteractionProfile` phases), **W8 canvas/reader** (open a 20-page document, swipe through 10 pages, five region
  presses: `preview swipe → image` and `preview region press`), **W9 library grid** (first scroll of 200 cells),
  **W10 Activity view** (the table with 200 rows updating). Each app workload runs on macOS; W6–W8 also run in the iOS
  and iPad simulators for CPU, memory and body counts (simulator timings are recorded but never ratcheted: a simulator
  is not a device). Acceptance: the table loads with ten workloads; one missing a corpus or a budget is refused by name;
  a workload's declared outputs are what the disk reader subtracts. Test (to write):
  test_perf_sweep (a new test file), case test_the_workload_table_loads_and_refuses_an_undeclared_corpus_or_budget. Built: the `[perf.workloads]` table (W1–W5 pytest and script drivers, W3 is `test_search_workload_perf.py` over `scripts/perf_search_queries.txt`, text queries only) and the `PerfWorkload` selector for W6–W10. Not built: the scripted scenario steps in the view layer, and the simulator runs.
- `perf-sweep.workload.corpus` [PARTIAL] (#6600; `ruling-2026-11-13-no-archive-names-in-specs`) — every corpus is synthetic
  or openly licensed, and none is the owner's archive material: the generated perf fixture (`scripts/perf_fixture.py`,
  deterministic by seed), the repo's own test fixtures, and at most one open HTR test set from the vetted list the project
  keeps (PAGE/ALTO with a licence that permits redistribution), pinned in `scripts/perf_corpus.json` by name, licence,
  URL, sha256 and page count. The runner holds each under `~/fichero-gate/corpus/<name>-<sha256[:12]>/`, fetched once by
  `builder install --corpus` and verified by hash before every run; a corpus whose hash differs is REFUSED (two runs
  must measure one corpus). No corpus, manifest or workload names a real archive, box, place or person; the
  public-boundary grep that guards landings covers `scripts/perf_corpus.json` and the workload table. Acceptance: a
  manifest entry without a licence or a hash is refused; a mismatched hash on the runner refuses the run naming the
  corpus; the boundary grep over a fixture manifest carrying an archive name is red. Test (to write):
  the new test_perf_corpus file in fichero-server/tests/unit/scripts, case test_the_corpus_manifest_is_open_hashed_and_names_no_archive. Built: `scripts/perf_corpus.json` (two generated or in-repo corpora) and `builder install --corpus`. Not built: the one open HTR download entry, which needs a vetted set and a hash taken by the manager.

## Output — the ranked hotspot table and the filing rule

- `perf-sweep.output.row` [OK] (#6600) — one row shape for every source: `{run, machine_model, workload, side
  (engine|app|field), area, kind (time|cpu|ram|disk|energy|hang|leak|body|efficiency), where (frame, view, span,
  phase or file:line), value, unit, count, share (of the workload's total for the kind, when it exists), source (the
  tool), trend_pct (vs the previous run on the same machine model and workload, null on the first), runs_seen,
  profile (the run-relative path of the trace, flamegraph or JSON the row came from)}`. `area` is derived from `where` by
  the same path-to-area map the review lenses use (`fichero_builder/review_lenses.py`; `recipes/` → recipes,
  `Views/Sidebar/` → sidebar, and so on) so a hotspot and a reviewer finding land in the same bucket. Acceptance: a row
  missing `where`, `value` or `source` is refused; `area` for `fichero/fichero/Views/Sidebar/SidebarView.swift` is
  `sidebar`. Test: fichero-builder/tests/test_perf_sweep.py, case test_rows_have_one_shape_and_an_area_from_the_lens_map.
- `perf-sweep.output.table` [PARTIAL] (#6600) — a run writes `<state>/perf/<run-id>/hotspots.json` (all rows) and
  `<state>/perf/latest.json` (a pointer plus the ranked top 50), where `<state>` is the builder's state dir
  (`journal.STATE`), and the profiles sit beside them for 30 days (the M4's Dev Disk; the manager's Mac holds the JSON
  only, rsynced back with the ladder's results). **Ranking:** within a kind, by `share` where it exists, else by `value`;
  across kinds the table shows the top 10 of each so a disk hog is never buried under time rows; ties by `count`. The
  **trend** column is `trend_pct` with the noise band (`ratchet.noise-band`) greyed: a move inside the band is shown as
  `~`, a worsening beyond it as `+N%` and an improvement as `−N%`. **Console:** `console.html` gains a `Hotspots` panel
  (the top 50 from `latest.json`, filter by workload, kind, area; a row links to its issue when one exists and to its
  profile path) and the daily digest carries the top 10 and the three counts of `perf-security-sweep` (findings, held
  up, fixed). `builder perf show [<run-id>]` prints the same table in the terminal; `builder perf diff <a> <b>` prints
  the rows whose trend crossed the band. Acceptance (fixture rows): the top 50 contains at most 10 per kind; a row 3%
  slower under a 6% band shows `~`; `show` prints every column; `diff` lists only band-crossing rows. Test (to write):
  test_perf_sweep (a new test file), case test_the_table_ranks_per_kind_greys_moves_inside_the_band_and_the_console_reads_latest.
- `perf-sweep.output.filing-rule` [GAP] (#6600) — a hotspot becomes a `Performance - <area>` issue when ALL hold:
  (1) it is above the kind's floor: time or CPU ≥ 5% of its workload's total, or a span whose `count × p50` ≥ 5% of the
  workload's wall; RAM ≥ 50 MB persistent or a top-10 allocator ≥ 25 MB peak; disk ≥ 10 MB written per run or ANY
  delta in a directory with no declared output; efficiency CPU/wall ≤ 1.2 on a workload declared parallel; ANY hang ≥
  250 ms, ANY leak, ANY runtime-checker row, ANY Organizer hang or disk-write exception; a body count above its
  baseline; (2) it appeared in two consecutive runs on the same machine model (field rows are exempt: one report is
  enough); (3) no open issue carries its key. **Key and dedupe:** `perf:<area>:<kind>:<where>` (where normalised: no
  line numbers for frames, the view name for bodies, the span name for spans), written as a `<!-- perf-key: … -->` line
  in the body and found with `gh issue list --search "perf-key: <key>" --state open`; a closed issue with the same key
  reopens with a comment (a regression, not a duplicate; the comment carries both runs' figures). **Through the filer:**
  the watcher's filer (`builder watch`, #6369) and its placement (`builder triage --move` into `performance-sweep`,
  `builder steps` under the area's step), so related hotspots group into one speed-up batch. Owner 2026-11-15: every
  spot over its floor is filed, with no daily cap and no rolling overflow issue; dedupe by key is the only brake. **The
  issue:** title `Performance - <area>: <where> <value><unit> (<share>% of <workload>, <trend>)`; body: the row, the
  workload and corpus, the machine model, the top 20 frames or allocators inline as text, the profile's run id and
  path (`builder perf show <run-id>` reopens it), the test or benchmark that would hold the fix (the workload's perf
  test, or "add a signpost interval around <where>"), and the ask in the owner's form: look at `<where>` and speed it
  up. Issues with no file to attach (field rows) carry the Organizer or MetricKit JSON inline instead. Acceptance
  (fixture rows, a fake `gh`): a frame at 7% in two runs files one issue with the key, the title and the inline frames; the
  same row in a third run files nothing; the same key on a closed issue reopens it with a comment; a 7% row seen once
  files nothing; a hang of 300 ms seen once files; a fourth and a tenth new key in one pass each file their own issue (no cap, owner 2026-11-15). Test (to
  write): test_perf_sweep (a new test file), case test_the_filing_rule_floors_two_runs_dedupe_by_key_reopen_and_no_cap.

## Ratchet — second goal: nothing gets slower

- `perf-sweep.ratchet.budgets` [GAP] (#6600; `quality.perf-method` is the decider) — `scripts/perf_baseline.json`
  (exists at HEAD with tolerances and empty `figures`, commit dd5e46fe3d) gains `figures[<machine.model>][<workload>]
  [<measure>] = {median, tolerance, band, since_run, runs}` for the measures the rungs hold: wall ms, CPU ms, peak RSS MB,
  disk KiB (exact), hang count (exact), leak count (exact), body count per view (exact), and the batch-level budgets from
  `perf-method` (engine perf + security under 6 min, app perf under 5 min). `perf_trial.py` stays the judge: cold run
  discarded, median of the warm runs, thermal `fair` is VOID, keyed by machine model and workload. Acceptance: a figure
  file without `band` for a tolerance-bearing measure is REFUSED; a measure held exactly carries `tolerance: 0`. Test:
  extends `fichero-server/tests/unit/scripts/test_perf_trial.py` (to write:
  `test_figures_carry_band_and_runs_and_an_exact_measure_has_zero_tolerance`).
- `perf-sweep.ratchet.baseline-from-n-runs` [GAP] (#6600) — a baseline figure is never one run: a measure is
  **report-only** until it has `N = 5` green runs on the same machine model (a week of nightlies, or five batches), then
  `builder perf baseline --write` writes the median of those five as the figure with `runs: 5` and `since_run`; the rung
  then ENFORCES that measure (`[check.perf].enforce` becomes a list of measures or `"all"`, so enforcement comes one
  measure at a time, never a flag day). A write in the same batch as code is refused (`ratchets-held-exactly`); a figure
  may only fall afterwards (`baseline-falls-every-batch`: a better median is printed as the figure to lower to, and the
  nightly lowers it by `builder perf baseline --lower`, its own commit). Acceptance: four runs and a `--write` refuses
  naming the count; five write the median; an enforced measure 8% over is red naming it, the figures and the machine; a
  report-only measure over prints the figure and stays `report-only`, never green-by-silence; `--write` with a diff of
  code in the same tree is refused. Test (to write): test_perf_sweep (a new test file), case test_a_baseline_needs_five_runs_enforces_per_measure_and_only_falls.
- `perf-sweep.ratchet.noise-band` [GAP] (#6600) — the band is measured, not guessed: over the N baseline runs, `band =
  (p95 − p5) / median`; the tolerance applied is `max(tolerance from the file, 2 × band)` for time, CPU and RSS (exact
  measures ignore the band); a measure whose band exceeds 15% is marked `noisy`, never enforced, and files one
  `Performance - measurement: <workload>/<measure> too noisy` issue (the fix is in the workload or the runner, e.g. a
  model warm-up or a dirty library, not a wider tolerance). Simulator measures and any run under `thermal != nominal`
  never enter the band. Acceptance: runs 100, 101, 99, 104, 100 ms give a band of 5% and a tolerance of 10%; runs with
  a 20% band mark the measure `noisy` and file once; a VOID run is excluded from the band. Test (to write):
  test_perf_sweep (a new test file), case test_the_noise_band_widens_the_tolerance_and_a_noisy_measure_is_never_enforced.

## Warnings — compiler, build-system and SwiftLint, listed and ratcheted the same way (#6610)

- `perf-sweep.warnings.from-the-result-bundle` [GAP] (#6610) — the build rung and the daily builds (`[check].build`,
  `[check.daily_builds].ios-sim`, `.tests`, and a new `.ipad-sim` with `-destination 'generic/platform=iOS Simulator'
  and the iPad test plan's scheme) each pass `-resultBundlePath <run>/<name>.xcresult`, and the warnings are read with
  the platform's reader, `xcrun xcresulttool get build-results --path <x>` (JSON: every warning with its message, file,
  line and the issue type), never a regex over the log alone; the kept log (`build-logs/<name>-…log`) is the fallback
  when the bundle is missing (`^(.+?):(\d+):(\d+): warning: (.*)$` for compiler lines, `^warning: (.*)$` for
  build-system lines) and a read that gets neither is BLIND (exit 2, `check_swiftlint_warning_ratchet.py`'s meaning),
  never green. Each warning is normalised to `(platform, kind, file, message)` where `kind` is: for Swift, the message
  with quoted identifiers and numbers replaced by `_` (so `'foo' is deprecated` and `'bar' is deprecated` are one kind,
  `deprecated: _`), prefixed by its family when the compiler gives one (`Sendable`, `concurrency`, `unused`,
  `deprecated`); for clang, the `[-W…]` flag; for the build system, the message with the phase or target name kept
  (`script phase without outputs: 'Validate App Store Bundle'`, `duplicate output file`, `deployment target`, `missing
  Info.plist key`, `linker`). Acceptance (fixture JSON and a fixture log): a build-results JSON with 12 warnings yields 12
  normalised rows and the right kind counts; the owner's example line yields kind `script phase without outputs` with
  the phase named; two deprecations of different symbols are one kind with count 2; no bundle and no log is BLIND.
  Test (to write): the new test_check_xcode_warning_ratchet file in fichero-server/tests/unit/scripts, case test_warnings_are_read_from_the_bundle_normalised_to_kinds_and_blind_without_input.
- `perf-sweep.warnings.ratchet` [GAP] (#6610) — the new check_xcode_warning_ratchet file in scripts, shaped exactly like
  `check_swiftlint_warning_ratchet.py` (exit 0 held, 1 grew, 2 BLIND; `--update-baseline`; `--since <base>` for one
  item), holds `scripts/xcode_warning_baseline.json` = `{platform: {kind: count}}` EXACTLY: a batch that adds a warning
  of any kind on any platform is red naming the platform, the kind, the file and line, and both counts; a batch that
  removes one lowers the baseline in the same batch or the land step lowers it (`baseline-falls-every-batch`); a raised
  baseline in a diff is refused. The rung runs it over the mac build's bundle on every batch that touches `fichero/`;
  the iOS and iPad counts are held by the daily builds (red there is an alert plus the ratchet's red lines). A warning
  that moves file is not new (counts are per kind, not per file, the SwiftLint ratchet's netting rule). Acceptance: a
  bundle with one more `Sendable` warning than the baseline is red naming it; one fewer is green and prints the lower
  count; a baseline edit that raises a count is refused; `--since` over a fixture pair reports only the item's own new
  lines. Test (to write): test_check_xcode_warning_ratchet (a new test file), case test_the_count_per_kind_and_platform_may_only_fall_and_since_names_the_item_s_lines.
- `perf-sweep.warnings.ranked-list-and-issues` [GAP] (#6610) — one list for all three warning sources: the xcode ratchet's
  kinds, `check_swiftlint_warning_ratchet.py`'s per-rule counts (`TOP_N_RULES` already computed there; the script gains
  `--json <out>` and nothing else) and ruff's per-rule counts where the quality stream holds them, written to
  `<state>/perf/<run-id>/warnings.json` as rows `{source (xcode|swiftlint|ruff), platform, kind, count, trend, example
  file:line}`, ranked by count, shown in the console beside Hotspots and in the digest's top 10. **One issue per kind,**
  `Build warnings - <source>: <kind> (<count>)`, with the dedupe key `warn:<source>:<platform>:<kind>` in the body, the
  example lines (up to 20) and the way to clear it; the same filer and caps as hotspots; a kind whose count reaches zero
  closes its issue with the run id. The **first issue** is already known and is filed by hand in Step 6: the `Validate
  App Store Bundle` phase (and any other `PBXShellScriptBuildPhase` with no `outputPaths` and no `alwaysOutOfDate`) runs
  on every build; the fix is a declared output file per phase (or `alwaysOutOfDate = 1` where the phase must run), which
  also shortens every incremental build and is itself a build-time hotspot. Acceptance (fixture rows, fake `gh`): the
  list ranks three sources together; one issue per kind with the key; a repeat run files nothing new; a kind at zero
  closes; the Validate phase in a fixture pbxproj is listed as `script phase without outputs`. Test (to write):
  test_perf_sweep (a new test file), case test_warning_kinds_rank_across_sources_file_one_issue_each_and_close_at_zero.

## Rung states — a measurement that did not happen is not green

- `perf-sweep.rung.not-run-is-visible` [BROKEN] (#6589 items 1–2; `check_tool.perf`, `check_tool.security`) — today
  `_remote_build` returns `None` for three different reasons (ssh or `mkdir` failed, rsync failed, a non-zero exit with
  no Swift source error, which is what a missing `pytest-benchmark` or a `scripts/perf_baseline.json` absent from the
  rsynced tree looks like), `perf()` turns every `None` into one alert "the build runner is unreachable", and
  `_report_only` makes a REFUSED tool a green rung; so both rungs have been green on every ladder since 22:41 on
  2026-11-14 and neither has measured anything. Wanted: `_remote_build` returns the row for an env-red (ok false,
  `remote_env_red: true`, the remote stderr tail kept) and `None` only for a runner it could not reach; `perf()` and the
  security rung map a `None` to state `not-run: runner down`, a REFUSED tool or an unpinned version to `not-run:
  <tool> refused`, and a missing baseline or workload file to `not-run: <path> missing on the runner`; a `not-run` rung
  is shown in the ladder, the journal row and the console as `not-run` (grey, never the green tick), the ladder still
  passes while `enforce` is off, and three consecutive `not-run` of the same rung file one `Builder - <rung> not
  running` issue. Every alert row gets an id (#6589 item 3) so the console can answer or dismiss one. Acceptance (a fake
  ssh and fake rows): a 255 exit yields `not-run: runner down`; a remote exit 1 with "No module named pytest_benchmark"
  in stderr yields `not-run: perf tool refused` with the stderr in the row, never "unreachable"; empty pins yield
  `not-run: bandit refused`; a journal row for a `not-run` rung carries `state: not-run` and an `id`; the third in a row
  files the issue once. Test: new cases in `fichero-builder/tests/test_perf_rung.py` and `fichero-builder/tests/test_security_rung.py`
  with `test_a_rung_that_did_not_measure_is_not_run_never_green_and_names_why`.

## Build order

Smallest first; each step is one lane batch unless marked. Steps 1–2 produce value with no new tool on any machine. Owner 2026-11-15: all eight steps are v1 and none is deferred, so the review's v1 cut does not apply.

#### Step 1 — the #6589 blockers: the rungs run, or say they did not (#6589)
- Behaviours: `perf-sweep.rung.not-run-is-visible`
- Tests: fichero-builder/tests/test_perf_rung.py, fichero-builder/tests/test_security_rung.py
- Size: S
- Order: (a) `_remote_build` keeps the env-red row and `perf()` / the security rung map the three causes to `not-run` with
  the remote stderr (tests first, red on base); (b) the manager runs `scripts/install_security_tools.sh --write-pins` on
  the M4 and the iMac and commits the pins (`[check.security].pins`), and `--check` runs in the rung before the scan;
  (c) confirm `scripts/perf_baseline.json` and `fichero-server/tests/perf/` reach the rsynced stable tree
  (`_stable_build_tree`'s filter) and that `[check].remote_python` points at the gate venv with `pytest-benchmark` and
  `pyinstrument`; the first real `not-run` reason seen on the M4 is written into #6589 as the finding; (d) alert ids.
  Done when one ladder shows `perf` and `security` with a figure or a named `not-run`, never a bare green.

#### Step 2 — read what is already logged: app phases and engine spans into the first hotspot table (#6600)
- Behaviours: `perf-sweep.source.app-log-phases`, `perf-sweep.source.engine-perf-lines`, `perf-sweep.output.row`,
  `perf-sweep.output.table`
- Tests: fichero-server/tests/unit/scripts/test_perf_log_readers (new), fichero-builder/tests/test_perf_sweep (new)
- Depends on: 1
- Size: S
- Order: the two readers over fixture logs; the row shape and the area map; `hotspots.json` + `latest.json` from the
  logs of the existing smoke and perf-test runs (the daily `tests` build's run and the engine perf rung's log); `builder
  perf show`; the console panel last. No new tool, no new workload: the table exists after this step.

#### Step 3 — the workloads and the corpus manifest (#6600)
- Behaviours: `perf-sweep.workload.set`, `perf-sweep.workload.corpus`, `perf-sweep.source.machines`
- Tests: fichero-builder/tests/test_perf_sweep (new), fichero-server/tests/unit/scripts/test_perf_corpus (new)
- Depends on: 2
- Size: M
- Order: the manifest and `builder install --corpus` (hash-verified); the `[perf.workloads]` table with W1–W5 as pytest
  drivers (the seven perf tests regrouped, methods unchanged) and W6–W10 as `FICHERO_PERF_WORKLOAD` scenarios in the Dev
  Local build's test hooks; the machine tags. The boundary grep covers the two new files.

#### Step 4 — engine profiles nightly: pyinstrument or py-spy, memray, du, CPU/wall (#6600)
- Behaviours: `perf-sweep.source.engine-profiles`
- Tests: fichero-builder/tests/test_perf_sweep (new)
- Depends on: 3
- Size: M
- Order: readers over fixture outputs first; the nightly driver on the M4 behind the heavy lock, one workload at a time,
  W2 last and with its own budget; rows into the table. py-spy runs with sudo on the M4 only, through the one sudoers line the owner approved on 2026-11-15 (Open questions, 2).

#### Step 5 — the filing rule through the watcher's filer (#6600)
- Behaviours: `perf-sweep.output.filing-rule`
- Tests: fichero-builder/tests/test_perf_sweep (new)
- Depends on: 2 (useful from the log rows alone), 4
- Size: S
- Order: floors, the two-run rule, the key, reopen-on-regression, the caps and placement, the issue body with the inline
  frames and the owner's ask. Owner 2026-11-15: no daily cap; every spot over its floor is filed, deduped by key.

#### Step 6 — the warnings ratchet and list (#6610)
- Behaviours: `perf-sweep.warnings.from-the-result-bundle`, `perf-sweep.warnings.ratchet`,
  `perf-sweep.warnings.ranked-list-and-issues`
- Tests: fichero-server/tests/unit/scripts/test_check_xcode_warning_ratchet (new), fichero-builder/tests/test_perf_sweep (new)
- Depends on: 1 (the kept build logs and result bundles)
- Size: M
- Order: `-resultBundlePath` on the build rung and the daily builds plus the `ipad-sim` daily build; the reader and the
  normaliser over fixtures; the baseline written from the next green mac, iOS and iPad builds (its own commit); the
  ratchet in the build rung for `fichero/` batches; the SwiftLint `--json`; the ranked list, the console panel and one
  issue per kind, the script-phase issue filed first and fixed in its own small batch (a pbxproj edit: owner or manager,
  `builder-ladder-traps`). Step 2.20's "compiler warnings from the build log" line in dev-workflows points here.

#### Step 7 — the ratchet: budgets, five-run baselines, the noise band, enforce per measure (#6600)
- Behaviours: `perf-sweep.ratchet.budgets`, `perf-sweep.ratchet.baseline-from-n-runs`, `perf-sweep.ratchet.noise-band`
- Tests: fichero-server/tests/unit/scripts/test_perf_trial.py, fichero-builder/tests/test_perf_sweep (new)
- Depends on: 4, and five nightly runs having happened
- Size: M
- Order: the figure shape in `perf_trial.py`; `builder perf baseline --write/--lower`; the band; `[check.perf].enforce`
  as a list; the first measures enforced are the exact ones (disk, leaks, hangs, bodies), time and RSS only after their
  band is known.

#### Step 8 — app profiles, runtime checkers, XCTest metrics and MetricKit (#6600; with dev-workflows Step 2.31)
- Behaviours: `perf-sweep.source.app-profiles`, `perf-sweep.source.runtime-checkers`, `perf-sweep.source.xctest-metrics`,
  `perf-sweep.source.metrickit-and-field`
- Tests: fichero-builder/tests/test_perf_sweep (new), fichero/Tests/UI/general/Launch/LaunchPerformanceUITests.swift
- Depends on: 3, dev-workflows 2.8 (the Swift tests on the M4's GUI session) and 2.31
- Size: L (two batches: recordings and exports; then the diagnostics plan and MetricKit)
- Order: xctrace recordings of W6–W10 with the toc pinned and the exports read (the hang ratchet unchanged as the hang
  judge); the diagnostics test plan with its two configurations, nightly; the perf plan's metrics as rows; the MetricKit
  subscriber in the app (its own small app batch) and the Organizer read from the nightly.

## Changes to dev-workflows

- dev-workflows' `quality.perf-rung-engine`: py-spy is allowed when `[machines].<m>.sudo` names it, and the owner ruled 2026-11-15 that this is the M4 only; pyinstrument stays the default.
  The "not run" alert becomes the `not-run` state above.
- dev-workflows' `quality.perf-rung-app`: the nightly xctrace form gains `File Activity` and `App Launch`; the SwiftUI template's body
  table is the cross-check it already names.
- dev-workflows' `quality.perf-security-sweep` (Step 2.32): the "profile inputs handed to the reviewer" are this spec's `hotspots.json`
  rows and profile paths; the filer's buckets and caps are shared; the module rotation stays.
- Step 2.20: the compiler-warning count moves here (`perf-sweep.warnings.*`); the SwiftLint and ruff ratchets stay there.

## Open questions for the owner

Questions 1 and 2 are answered (owner, 2026-11-15). Question 4 is partly answered: the daily cap is gone. Questions 3, 4's
floors, 5 and 6 are still open; the owner has not ruled on them.

1. Answered 2026-11-15: the work lives in a new GitHub milestone named `performance-sweep`, and #6600, #6610 and the perf
   part of #6589 move into it.
2. Answered 2026-11-15: yes, on the M4 only, through one narrow sudoers line that allows exactly `py-spy` and nothing
   else. Other machines never get it. Without it the engine time profile is pyinstrument's, which does not see forked
   workers or native frames.
3. The profiles cannot be attached to a GitHub issue from the CLI: the issue carries the top frames inline and the run id,
   and the trace lives on the M4's Dev Disk for 30 days. Is that enough, or should the nightly also push a `gh gist` /
   release asset per filed issue?
4. Partly answered 2026-11-15: no daily cap (see the filing rule). Still open: floors for filing (5% of a workload's
   time, 50 MB, 10 MB written, 250 ms hang), to be accepted as the first values and tuned after the first three passes?
5. Which open HTR test set, if any, is the one corpus beyond the generated fixture; or v1 uses the generated 200-page
   library only?
6. The energy dimension on the Mac is CPU time (no per-process energy counter without root; `Energy Log` is iOS-device
   only): acceptable, or should an iOS device live on the M4 for the nightly?
