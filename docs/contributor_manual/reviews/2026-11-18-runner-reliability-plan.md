# Plan: make every runner pause, say why, and go on (2026-11-18)

> The reviewer, for the owner and the harness. Built from `2026-11-18-runner-reliability.md` (the findings, with their
> code citations) and the contract `../specs/compute/runner-reliability.md`. Each step below is one a builder lane can
> take alone, with the behaviours it builds, the tests that prove it, and the issues it closes. Nothing here was filed,
> closed or moved: the hygiene section lists what should change and why.

## The ten things that matter most

1. Make `no-credit`, `key-refused`, `network` and `memory` PAUSE, through the one pause path the rate limit already
   takes; stop failing pages for them (#6675, #6569). Step 1.1.
2. Make Continue take up the first item not done for every pausing kind, and make the recipe park on the paused step
   (#5933's path). Step 1.2.
3. Show the engine's `words` and `fix` in the Activity row and the Inspector, raise the one alert (`RunFailurePrompt` is
   built and unwired), stop swallowing pane verb errors into counts, and say "Continue" everywhere (#6354, #6597, #6599).
   Step 1.3.
4. Route the vision tool through the one retry layer so a 429 pauses there too; turn LangChain's own retries off (#5944).
   Step 2.1.
5. Type Kraken's "reader not on this Mac", MLX's set-up errors and a 5xx correctly; make a zero-output page not done and
   not silent; log Kraken's three geometry drops (#6271, #6673). Step 2.2.
6. Make spaCy absent `model-missing` (blocked, downloadable) instead of a names step "done" with nothing. Step 2.2.
7. Downloads: bytes and time left for every runtime, installed only after a load check, resume at launch whatever project
   started them; a vanished download row never counts as landed (#6592, #6591, #5649). Step 2.3.
8. Remote: a dropped Slurm login pauses the watch instead of failing the run with shards out; `send_ahead` keeps its
   refusal; the Inspector's remote buttons report; HF and cluster rows under their step (#5740). Step 2.4.
9. Memory and the Mac: a memory hold that gives up pauses (never a failed MLX page); half the cores while in use; a
   started run begins at once (#6230, #6263, #6075). Step 3.1.
10. The hand-run paths (Start, the folder's context menu, the workflow bar, the selection runner) on the contract: no
    silent `guard`, no "Import Error" title for a workflow start, the typed refusal and the one alert mid-run (#4961,
    #4963, #3931). Step 3.2. Then the Models and Compute window (its own spec and build order).

## The build order (one lane, one step at a time)

The shape is the harness's (`#### Step N.M`); the same steps are in `runner-reliability.md` "Build order" so the
harness can file one issue per step. Sizes are the spec's.

### Stage 1 — The shared foundation

#### Step 1.1 — The table's pause-or-fail and retry columns; no-credit and key-refused pause (#6675)
- Builds: `runner.kinds.pause-or-fail-is-the-tables`, `runner.pause.one-path`, `runner.kinds.one-table`.
- Where: `llm/failure.py` (two columns on `RunFailure` and a `PAUSES` set), `llm/retry.resilient` (a fatal answer asks
  the run to pause through `spend._ask_run_to_pause` as a rate limit does, and records the cause), `execution/runner.py`
  (`_finish_as_paused` with `failure` set for every pausing kind; `SystemicErrorDetected` for a pausing kind settles
  paused), `workflows/builder.py:2374-2392` (the quota wrap becomes `WorkflowPaused`), `execution/jobs.py` `_PAUSED_NOT_FAILED`
  reads the table's column instead of its own two names.
- Tests: `fichero-server/tests/unit/llm/test_pause_or_fail_is_the_tables_6675.py` (new: a 402 with no in-flight reason on
  page 4 of 10 leaves the run `paused`, `failure.kind == "no-credit"`, 3 pages kept, nothing more sent to that provider;
  a 401 the same with `key-refused`; a bare `RuntimeError` fails that page and the run ends partial; a `MemoryShortError`
  after the hold's patience pauses), `test_run_failure_kinds_6354.py` (the two columns on every kind).
- Closes: #6675; the pause half of #6569; `activity.failure.credit-exhausted-pauses` to [OK].

#### Step 1.2 — Continue from the first item not done, for every pausing kind; the recipe parks on it (#6569)
- Builds: `runner.pause.continue-from-first-not-done`, `runner.pause.survives-relaunch` (already OK; re-pinned for the new kinds).
- Where: `recipes/runner.py` (`ParkedOnStepRun` for a step paused for a cause; Continue clears the cause with
  `forget_rate_limit_pause` / `forget_cap_stop` and a new `forget_provider_pause`, then takes the step up over the pages
  not done), `api/routes/system/activity.py` (Continue on the recipe row reaches it), `llm/retry._DEAD` (Continue clears
  the dead mark for that provider so the first call is a real probe).
- Tests: `fichero-server/tests/unit/recipes/test_recipe_pause_5933.py` (extend: paused for `no-credit`, Continue after the
  stub recovers reads pages 4 to 10 only and ends done; a Continue before it recovers pauses again with the alert updated,
  not repeated), `test_a_page_waits_for_its_inputs_6673.py` (a continued run makes only the missing calls).
- Closes: #6569; verifies #6331 and #6332 on a build (Retry inside a run) or re-files them with the failing case.

#### Step 1.3 — One dialogue per cause; the row and the alert (#6354, #6597, #6599)
- Builds: `runner.ask.one-dialogue-per-cause`, `runner.surface.one-row-one-alert`, `runner.cli-mcp.same-words`.
- Where (app): wire `RunFailurePrompt` (`Models/RunFailurePrompt.swift`) from `ActivityStore` when a run gains a
  `failure` with a pausing kind that needs the person, keyed `id@failed_at`, coalesced by cause and provider; render
  `failure.words` and `failure.fix` in the Inspector heading and under the table's row words
  (`Views/Activity/Pane/ActivityPane+Row.swift`, `ActivityDetailsSections.swift`); make every pane verb report the engine's
  words in the status line and the Inspector (`ActivityPaneView+Actions.swift:118-148`), not a count; `ActivityRunControlsBar`
  shows its notice, not a tooltip; "Resume" becomes "Continue" in `ActivityMonitorModel.Control.label`; `open-settings`
  lands on the control named (`settings.ai.providers`). Where (engine): `failure` on every job row (`BackgroundJob.failure`
  for jobs of their own, downloads, remote shards), from `failed_reason`'s classification.
- Tests: `fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift` (extend: a `no-credit` pause builds one prompt
  with Open provider page / Continue / Stop run; two pages meeting it build one; the words and fix are rendered; a verb
  that fails shows the engine's words), `fichero-server/tests/unit/execution/test_failure_in_words_6212.py` (every job row's
  `failure` is set when it fails).
- Closes: #6597, #6599 (the fix-button and needs-you parts), the alert half of #6354 (Stage 2 of `run-failure-alerts.md`).

### Stage 2 — Each runner on the contract

#### Step 2.1 — Cloud providers: one retry layer, network pauses, the batch's kinds (#5944)
- Builds: `runner.cloud.provider`, `runner.cloud.batch`.
- Where: `workflows/tools/vision_base.py:4383` (the per-call breaker goes; the vision call runs through `retry.resilient`
  so the 429 pause and the per-provider cap apply), LangChain `max_retries=0` behind the breaker, `transient` after the
  retries → `network` pause (not a failed page), the `network` words for a 5xx ("<Provider> answered with an error" vs
  "Could not reach <Provider>"), `provider_batch` lines `errored`/`expired` → `model-error` per page, a batch the account
  cannot pay for → `no-credit` pause.
- Tests: `fichero-server/tests/unit/workflows/test_in_flight_budget_6671.py`, `test_rate_limit_backs_off_then_pauses_6584.py`
  (extend: the vision path sees the same gaps and the same pause), a new `test_one_retry_layer_5944.py` (the worst-case
  sends per page bounded; LangChain never retries behind the breaker; a 503 ×5 pauses as `network`).
- Closes: #5944; the 5xx-words finding; the vision bypass finding.

#### Step 2.2 — Local runtimes: Kraken, spaCy, the embedder, MLX (#5267, #6271)
- Builds: `runner.local.kraken`, `runner.local.spacy`, `runner.local.embedder`, `runner.local.mlx`,
  `runner.results.no-silent-loss`, `runner.results.counted-done-only-with-a-result`.
- Where: `llm/kraken_runtime.py:432-456` raises `LocalModelNotInstalledError` (typed `model-missing`); the three geometry
  drop sites (`:1764, 1851, 1942`, `_usable`) count and log what they drop onto the page's call log beside
  `lines_without_outline`; `recipes/done.py` a page with zero lines and no blank judgement is "not done, no result" and the
  read step reports it ("N pages had no lines to read"), `failed_reads` counts it; `knowledge/spacy_ner.py:326-363` raises
  `PipelineMissing` on the default path too (the names step blocks under the download, `runtime.spacy.pipelines-download-as-data`
  fetches it); `llm/failure.py:177-178` `EmbedderUnavailable` while fetching → `model-missing`, broken → `model-broken`;
  `llm/mlx_runtime.py:253, 277` typed `runtime-unavailable`; `llm/local_inference.py:371-372` a memory deadline → pause, not
  a failed page; the Kraken unit tests stub the layout model (#6587).
- Tests: `fichero-server/tests/unit/llm/test_kraken_line_without_outline_is_boxed_6673.py` (extend: the three drop sites
  count), a new `test_zero_line_page_is_not_done_6271.py`, `test_spacy_pipelines_as_files_to_spec.py` (extend: the default
  path blocks), `test_embedder_model_missing_says_so.py` (the kind while fetching), `test_mlx_memory_guard.py` (a deadline
  pauses).
- Closes: #6271, #6587, the typed-kind findings; part of #5267 (the per-runtime smoke stays with it).

#### Step 2.3 — Apple, Whisper, YOLO, OpenCV and the downloads (#6288, #6592, #5649)
- Builds: `runner.local.apple`, `runner.local.whisper-yolo-opencv`, `runner.download`.
- Where: `workflows/tools/apple_vision_worker.py` (a stopped worker said once per run, `model-error` per page; the plan
  never routes handwriting to Apple Vision, #5451); `llm/whisper_runtime.py`, `llm/yolo_runtime.py`, `recipes/prepare_suggest.py`
  (`cv2` import failure typed `runtime-unavailable`); `llm/local_models.py` `_run_download` reports bytes for every runtime
  (the typed fields on the row, #6592); `installed` after a load check in the local-models list (#6591); downloads recorded
  in the global project and resumed at launch (#5649 option A, the owner to confirm); `recipes/runner._await_downloads`
  treats a `None` row as failed, never landed.
- Tests: `fichero-server/tests/unit/llm/test_every_download_reports_bytes_6592.py`, a new `test_download_row_gone_is_not_landed.py`,
  `test_search_model_downloads_in_the_app.py` (installed only after a load), an Apple worker test with a stub that stops
  (said once).
- Closes: #6592, #6591, #5649 (with the ruling), part of #6288 (the saying-once half; the root cause stays open).

#### Step 2.4 — Remote places: another Mac, the cluster, HF Jobs under their step (#5740, #5412)
- Builds: `runner.remote.mac`, `runner.remote.cluster`, `runner.remote.hf-jobs`.
- Where: `remote_read/slurm_target.py` `SlurmError` for a lost login joins `cannot_reach` so the row waits out of reach
  and says so (`compute.hpc.mfa-modes`), `remote_read/pipeline.send_ahead` keeps `_why` on the batch's row;
  `training/job.py` a cancel before submit sends nothing (#5412); `sacct` states mapped onto the table (TIMEOUT/OOM →
  `memory` with a smaller slice on Retry, NODE_FAIL/PREEMPTED → `interrupted`, resent once); the remote row under its
  recipe step with far-side state, shards and cost (`activity.remote-under-its-step`, #5740); the app's
  `RemoteRunInspector` reports each button's result; another Mac as an endpoint place whose loss pauses its pages.
- Tests: `fichero-server/tests/unit/remote_read/test_slurm_target.py` (a dropped login waits, never fails), `test_read_at_scale_job.py`
  (the mapped states and the single resend), `fichero-server/tests/unit/training/test_cancel_before_submit_5412.py`,
  `ActivityRemoteInspectorTests.swift`.
- Closes: #5412, #5740; part of #5457 and #5951.

### Stage 3 — Memory and the hand-run paths

#### Step 3.1 — Hold, then pause, never kill; the Mac stays usable (#6075, #6230, #6263)
- Builds: `runner.memory.hold-not-kill`, `runner.mac.stays-usable`.
- Where: `execution/throttle.py` (a hold that lasts past its patience, default ten minutes, becomes a `memory` pause on the
  run with Continue; the first paging reading reads the previous sample from the run's record so it can hold; warn-level
  pressure with swap growing holds), `execution/jobs.py` (a started run begins at once, throttled, never waits for Run now;
  in-use slows to half the performance cores, `activity.throttle.in-use-slows-to-half`), the popover's paging line.
- Tests: `fichero-server/tests/unit/jobs/test_kraken_holds_under_swap_and_pressure_6075.py` (extend: the hold becomes a
  pause), `test_throttle.py` (half the cores while in use; a started run runs while in use), a new `test_started_run_begins_at_once_6263.py`.
- Closes: #6263, #6230, the pause half of #6075 and #4987 §3.

#### Step 3.2 — Context menus, the workflow bar and the selection runner on the contract (#4961, #4963, #3931)
- Builds: `runner.hand-run.same-contract`, `runner.hand-run.never-swallowed`.
- Where: `App/Menus/FocusedCommands/FocusedCommandButtons+Recipe.swift:137-151` (Start's `guard … else { return }` shows the
  engine's refusal; the folder's "Run the Recipe on This Folder…" shows why before opening Set Up),
  `ContentView+WorkflowActions.swift` (the start-failure alert is titled for a workflow, never "Import Error"; a dropped
  model pin is said; `try?` on stop reports), `ContentView+WorkflowChainEngine.swift:389-425` (poll errors and the deadline
  say so), `LibraryView+BatchWorkflow.swift:76-80, 200-214` (an empty scope and a workflow not runnable here say so),
  `ContentView+WorkflowScope.swift` (a selected workflow row is never the scope, #4961; no override a workflow cannot take,
  #4963), `AddProviderSheet+Helpers.swift:84-86` and `ProvidersView+ProviderDetailView.swift` (errors shown, not logged),
  the 182 `.undocumented` sites that start work read `detail` (#3931, the run-starting subset first).
- Tests: `fichero/Tests/Unit/general/Views/RunFailureAlertTests.swift` (a hand run's mid-run failure raises the one
  alert), `fichero/Tests/Unit/general/Models/WorkflowScopeTests.swift` (#4961, #4963), `fichero/Tests/Unit/general/Views/WorkflowStartFailureTests.swift`
  (new: the title and words of a start failure).
- Closes: #4961, #4963, #6602, part of #3931.

### Then: the Models and Compute window

Its own spec and build order (`../specs/ui/models-and-compute-window.md`, four stages). It depends on Stage 1 here
(the window's "Last failed" column reads `failure`) and on Activity's Models tree (built, `activity.window.models-tree`).

## The context menus, the workflow bar and the recipe runner: what makes each unreliable, and the fix

**The context menus that run things.** "Run the Recipe on This Folder…" and "Run a Step Again on This Folder"
(`FocusedCommandButtons+Recipe.swift:190-232`) open Set Up when the start is refused and say nothing at the menu; Project
› Start's refusal is a silent `guard` (`:145`); Find the Documents writes the error to a store nobody traced to a view
(`:304-305`); Run Workflow on Selection labels a start failure "Import Error" (`ContentViewModifiers.swift:135-141`); a batch
run with an empty scope logs and returns (`LibraryView+BatchWorkflow.swift:76-80`); Duplicate and Make Alias log only
(`LibraryView+ContextMenu.swift:183, 206`); Translate shows no progress (`isTranslating` never read). What is right: Run
Workflow's submenu says "Models unavailable" and "needs API key" in place (`RunWorkflowSubmenuItems.swift:46-74`); Stop and
Read Again report the engine's words (`FocusedCommandButtons+Activity.swift:38-52`); a cloud refusal before Start is the
typed alert. Fix: Step 3.2 (every start path shows the engine's refusal; every failure mid-run is the one alert of Step 1.3).

**The workflow bar.** The chain's start says the right things (`Models/ChainRunWords.swift`), but a step that cannot be
realised just turns its chip red (`ContentView+WorkflowChainEngine.swift:299`), the poll swallows errors and ends silently
at four hours (`:389-425`), Stop's failures are logged (`:277`), auto-save failures are logged (`ContentView+WorkflowActions.swift:155`),
and a model pin the tool cannot take is dropped so the sentence shows a different model (`:27-97`). A run started while a
workflow row is selected takes the workflow as its scope (#4961); the bar sends an override to workflows with no
language or vision node (#4963). What is right: the step chip's "This step failed — double-click to see why" and its
popover (`WorkflowBar+ChainRail.swift:374`, `WorkflowStepInspectPopover.swift:184-208`); Compare's failed capsules with their
reasons (`WorkflowBar+Compare.swift:159-182`). Fix: Step 3.2 for the scope and override bugs and the silent paths; Step
1.3 for the alert.

**The recipe runner.** The engine's half is the most solid: batches, checkpoints, resume, pause, a page waits for its
inputs, models fetched first, memory recorded (all §13 [OK]). What breaks it is the failure kinds that still fail the run
(no credit, a key), the zero-output page (#6271), the vision path's own breaker, and the app: the summary's words exist but
the alert is unwired, the Start guard is silent, "Done with failures" is a `Partial` glyph with no words in the table when
the reason runs past eight words. Fix: Steps 1.1 to 1.3 and 2.2; the load leg (`recipes-run.reliability.hundred-pages-finish`)
run on the M4 with a provider stub that runs out of credit at page 40.

## Milestone hygiene

### Milestones to merge or retire (no new milestone)

| Milestone | Open | Do | Why |
|---|---|---|---|
| `engine-memory-at-scale` (#349) | 1 (#6076) | fold into `recipes-run` | one issue; `recipes-run.md` Step 2.3 owns it |
| `workflows-scope-and-empty-states` (#350) | 2 (#4397, #4387) | fold into `workflows` | its spec steps are `workflows.md` 4.1 and 3.5 |
| `compute-linux-image` (#353) | 1 (#5642) | fold into `remote-compute` | `linux-server-image.md` is a slice of the compute set |
| `provider-keys` (#305) | 2 (#4632, #4631) | fold into `ai-settings` | `ai/provider-keys.md` was folded into `ai-settings.md` on 2026-10-04 |
| `ACENet` (#335), `HF` (#334) | 4, 19 | fold into `remote-compute` with `phase:` labels | parked buckets; `recipe-steps-at-scale.md` orders HF before ACENET; the window spec lists both as places |
| `cloud-permission-and-spend` (#348) | 9 | keep | its spec is live and its steps are being built |
| `Next release` (#333) | 92 | file each reliability issue into its spec's milestone (list below) | a grab-bag, per `build-order.md` Parked |
| (none) `run-failure-alerts` | — | do NOT create; the spec's `Milestone:` line now reads `activity` | #6354 already sits in `activity`; one window, one milestone |

### Issues with no milestone that belong to this work

#6675 → `recipes-run` · #6569 → `recipes-run` (closes with Step 1.2) · #6587 → `Bugs - Tests - Engine` (Step 2.2) · #6602 →
`activity` (Step 3.2) · #6671 is closed; leave it.

### From `Next release` into a spec's milestone

`recipes-run`: #5944, #5943 (dup of #5987's cap: close one), #5987, #6000, #6001, #5935, #5936, #5937, #5938, #5920,
#5919, #5874, #5877, #5881, #5863, #5862, #5861, #5859, #5872, #5865, #5870, #5939, #5963, #5952, #5953, #5954, #5955,
#5956, #6351, #6352. `activity`: #5878, #5868, #5866, #5958, #5957, #5959, #6023 (see below). `ai-settings`: #5922, #5964
(iPhone, no), #6033 … the Set Up review items stay with `recipe-designer`.

### Duplicates, stale, or done (with the evidence)

| Issue | Verdict | Evidence |
|---|---|---|
| #5853 Stop on a page / Retry within run | fold into #6331 + #6332 (the concrete cases); close #5853 as the umbrella | `recipes-run.steps.retry-flows-through` [OK] with `test_a_page_waits_for_its_inputs_6673.py`; #6331/#6332 report a build where it did not hold: verify on a build first |
| #5355 global Pause Background Work survives relaunch | likely done: `needs-your-test` | `activity.window.run-controls` built 2026-11-15 (`jobs.pause_all`, `PUT /jobs/paused`); `test_pause_all_continue_all_6588.py` |
| #5356 pause/resume/cancel/retry on every job | mostly done: re-scope to the remainder (jobs of their own have no `failure`, Step 1.3) | `ActivityPaneVerbs.allows`; the states table in `activity-pane.md` |
| #5357 durable work | close as done, residue to Step 1.2 | `recipes-run.journey.resume-after-quit` [OK], `activity.relaunch.only-running-work-resumes` [OK] |
| #5352, #5353, #5354, #5116, #5117 SPEC umbrellas | close: the specs are APPROVED (`activity-and-automatic-work.md`) and superseded by `activity-pane.md` | the spec headers |
| #5415, #4960, #1559, #1264, #493 Activity window designs | close as superseded by #6441 (built: the pane, the window, the sidebar) | `activity.window.sidebar` built 2026-11-15 |
| #5622 two heavy jobs under memory pressure | duplicate of #6000 (close one) | `recipes-run.memory.one-heavy-model` [OK], `test_one_heavy_when_memory_tight.py` |
| #5920, #5939, #5963 model juggling / order | `needs-your-test`: built | `MODEL_ORDER` (`execution/jobs.py`), `activity.lane.one-model-at-a-time` [PARTIAL: test unrun], `test_a_run_does_not_juggle_models_5939.py` |
| #5592 fallback across places needs a ruling | close the ruling half (given: `ai.where.fallback-free-and-asked` [OK]); re-title the rest "mid-run: a failed place pauses and asks" (Step 1.1) | `where-models-run.md` §F |
| #4987 memory budget (needs-spec, in recipe-designer) | move to `recipes-run`; §1-2 and §5 done (`settings.local-model-refused-before-it-loads`, one heavy model, idle unload); §3-4 to Step 3.1 and the window | the cited ids |
| #5267 runtimes work end to end, #4620, #4621, #4626, #4628, #4629 capability audits | merge into #5267 ("each runtime proves it runs on a real page, weekly, on the owner's Mac") | five issues, one job |
| #4307, #4302, #4304, #4665, #4883, #1059, #1200 one models list / pickers / browser | re-home under the window spec; #4304 and #4302 likely done (`test_search_model_downloads_in_the_app.py`) | `models-and-compute-window.md` |
| #5649 download resumes only in its project | needs the owner's ruling (A recommended); Step 2.3 | the issue's three options |
| #6023 speed controls in Settings | close or rule: the contract and `recipes-run.md` add no setting ("the engine measures and decides") | `recipes-run.md` Prior art |
| #5370 runtimes reload per call | partly done (Kraken resident cache, `_resident`; spaCy loaded once) → `needs-your-test`, the rest to #5267 | `activity.limits.load-a-model-once` verified 2026-11-14 |
| #6354 | keep open as the alert's umbrella; its engine half is built (`run.fail.*` PARTIAL/OK) | `run-failure-alerts.md` |
| #3931 182 sites drop the error body | re-scope: the run-starting subset first (Step 3.2) | the review's silent list |

### New issues to file (title, then one paragraph)

1. **Out of credit or a refused key pauses the run through the one pause path** — exists as #6675; add to it the
   `pauses`/`engine_retries` columns on `RunFailure` and the `_PAUSED_NOT_FAILED` set reading them, so `execution/jobs.py`,
   `llm/retry.py` and `execution/runner.py` agree on which kinds pause. No new issue; a comment.
2. **The vision tool bypasses the one retry layer, so a 429 fails the page instead of pausing** — `workflows/tools/vision_base.py:4383`
   builds a per-call `ProviderCircuitBreaker` and calls `call_with_breaker` directly; `llm/retry.resilient`, where the
   rate-limit pause and the dead marks live, never sees it. Route the vision call through `resilient`; pin with a stub
   provider answering 429 five times (the run pauses, no page fails). Spec: `runner.cloud.provider`.
3. **Kraken's "reader is not on this Mac yet" is a plain RuntimeError and reads as a bug in Fichero** —
   `llm/kraken_runtime.py:432-456` raises `RuntimeError`; `llm/failure.kind_of` types it `unexpected` and the row says
   "Something went wrong in Fichero". Raise `LocalModelNotInstalledError` (typed `model-missing`); the same for
   `llm/mlx_runtime.py:253, 277` (`runtime-unavailable`). Spec: `runner.local.kraken`, `runner.local.mlx`.
4. **A page Kraken found no lines on is read anyway and the read ends done with no text** — `recipes/done.py:705-737`
   says not done (`found > 0`), the read runs, `failed_reads` (`:446-466`) counts only pages with reasons, so the step
   ends done. Sibling of #6271. A zero-line page with no blank judgement is "no result": not done, counted and named on
   the step ("N pages had no lines to read"). Spec: `runner.results.counted-done-only-with-a-result`.
5. **Kraken's three geometry drop sites log nothing** — `kraken_runtime.py:1764, 1851, 1942` skip a polygon under three
   points and `_usable` (`:1544-1545`) drops short baselines, with no count and no line; verify whether the boxing of
   31f94d0dda runs before them, and either way count what is dropped on the page's call log beside `lines_without_outline`.
   Spec: `runner.results.no-silent-loss`.
6. **spaCy absent on the default path makes a names step "done" with no names** — `knowledge/spacy_ner.py:326-363` returns
   `None` with a warning and `extract_entities` returns `[]`; only a pinned pipeline raises `PipelineMissing`. Raise it on the
   default path too, so the step blocks under the pipeline's download (`runtime.spacy.pipelines-download-as-data`). Spec:
   `runner.local.spacy`.
7. **A 5xx is typed `network` and reads "Could not reach <Provider>"** — `llm/failure.py:197`; a provider that answered
   with an error is reachable. Add the words "<Provider> answered with an error" for 5xx under the same `network` kind (or a
   `provider-error` row words), keep "could not reach" for DNS and connection errors. Spec: `runner.cloud.provider`.
8. **`EmbedderUnavailable` while the model is being fetched is typed `model-broken`** — `llm/failure.py:177-178`; the
   words say "could not be loaded" when the model is merely not here yet. Type the fetch case `model-missing`, the load
   failure `model-broken`. Spec: `runner.local.embedder`.
9. **An MLX model that waits for memory past its deadline fails the page; it should pause** —
   `llm/local_inference.py:371-372` raises `LocalModelMemoryUnavailableError` after the wait; the contract's `memory` kind
   pauses with Continue and "Choose a smaller model". Spec: `runner.memory.hold-not-kill`.
10. **`_await_downloads` counts a download row that vanished as landed** — `recipes/runner.py:1040-1078`: `if row is None
    or row["state"] == "done": entry["landed"] = True`. A `None` row is a download that was deleted or never queued; treat it
    as failed so the step blocks, never runs without its model. Spec: `runner.download`.
11. **A dropped Slurm login fails the run with shards still out** — `remote_read/slurm_target.py:182-190` raises
    `SlurmError`, which `training/hf_jobs.cannot_reach` does not know, so `remote_read/job.py:408-428` re-raises and the row
    fails; the shards keep running. Treat it as out of reach (the row waits and says "sign in again"), and keep `send_ahead`'s
    refusal (`remote_read/pipeline.py:31-54`) on the batch's row. Spec: `runner.remote.cluster`.
12. **Activity shows neither the failure's words nor its fix, and the pane's verbs swallow their errors** —
    `failure.words`/`fix` are rendered nowhere; `ActivityPaneView+Actions.swift:118-148` turns every verb's error into
    "Retried 0 · 1 skipped"; `ActivityRunControlsBar.swift:67` shows Pause All's failure as a tooltip; the table says
    "Continue" and the Inspector "Resume"; a reason over eight words with no row words leaves the State cell blank
    (`ActivityPane+Row.swift:156-175`). One item, Step 1.3. Spec: `runner.surface.one-row-one-alert`.
13. **`RunFailurePrompt` is built and called only from tests** — `Models/RunFailurePrompt.swift:8-40` has no caller
    outside `RunFailureAlertTests`. Wire it from `ActivityStore` for a run that gains a `failure` the person must act on,
    keyed `id@failed_at`. Part of #6354 Step 2.1; file as its own step issue.
14. **Start, the folder's "Run the Recipe on This Folder…" and a workflow start fail silently or under the wrong title** —
    `FocusedCommandButtons+Recipe.swift:145` (`guard await store.start() else { return }`), `:216-232` (opens Set Up with no
    word), `ContentViewModifiers.swift:135-141` ("Import Error" for a workflow start). Show the engine's refusal in words at
    the place the person pressed. Spec: `runner.hand-run.same-contract`.
15. **The workflow bar drops a model pin the tool cannot take and swallows its poll's errors** —
    `ContentView+WorkflowActions.swift:27-97` sends the tier default with no notice; `ContentView+WorkflowChainEngine.swift:389-425`
    `try?`s the status poll and exits at four hours with no word; `:299` a step that cannot be realised turns red with no
    message. Spec: `runner.hand-run.same-contract`.
16. **Settings' Add Provider, Test Connection and delete-model errors are log-only or a tooltip** —
    `AddProviderSheet+Helpers.swift:84-86`, `ProvidersView+ProviderDetailView.swift:183-185, 497-526`. They move to the
    window (`models-and-compute-window.md`), where every verb reports; until then show the words. Spec:
    `runner.hand-run.never-swallowed`.
17. **A `disk-full` failure kind** — `activity-and-automatic-work.md` §J named it; `llm/failure.py` has none; `ENOSPC` and
    DuckDB's out-of-space land as `unexpected`. Add the kind (pauses; fix "Free disk space"; the volume named, no path).
    Spec: `runner.kinds.one-table`.
18. **A memory hold that lasts past its patience becomes a pause that says so** — `execution/throttle.py` holds for ever
    while memory is short; nothing tells the person why nothing moves except the grey line. After ten minutes (owner to
    confirm) the run pauses as `memory` with Continue and "Choose a smaller model". Spec: `runner.memory.hold-not-kill`.
19. **Spec task: the runner-reliability contract** (`specs/compute/runner-reliability.md`, DRAFT) — the owner's approval,
    then the harness files its eight steps; the open questions (network's scope, the memory patience, `disk-full`) ruled.
20. **Spec task: the Models and Compute window** (`specs/ui/models-and-compute-window.md`, DRAFT) — approval, the
    milestone question (ai-settings or activity), the four stages filed; Settings › AI slimmed in its Step 4.1.

### Issues to close with the evidence above

#5622 (dup of #6000), #5943 (dup of #5987), #5853 (umbrella; #6331/#6332 carry it), #5352/#5353/#5354/#5116/#5117
(spec umbrellas, specs approved), #5415/#4960/#1559/#1264/#493 (superseded by #6441), #5357 (done; residue in Step 1.2),
the ruling half of #5592; `needs-your-test` on #5355, #5920, #5939, #5963, #5370, #4302, #4304.
