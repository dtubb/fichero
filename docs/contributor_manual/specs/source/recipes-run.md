# Recipes run — a recipe started on 20 to 100+ pages finishes, every time — Design Spec (#6212)

> Milestone: recipe-designer
> Manual: TBD — a "Running your recipe" section in the Projects part, after "Designing your recipe":
> what Start does, where to watch it (Activity), what the waiting lines mean (thumbnails first, memory,
> one model at a time), what happens when you quit, sleep or the engine crashes (nothing lost, nothing
> done twice), Stop, Pause and Run again on what was missed, and what the summary at the end says.
> **Status: DRAFT 2026-10-26 — awaiting the owner.** Written from the owner's ruling of 2026-10-26
> (paraphrased): what matters most is that recipes RUN, reliably: the engine does not crash, memory does
> not leak, a run on 20 to 100+ pages finishes, and the recipe runner was never properly finished as a
> spec. Facts read from the code of origin/integration at 2e6e62c8a and from the dogfood run of
> 2026-10-26 (`agent-work/status/briefs/dogfood-b12-2026-10-26.md`: one 20-page run wedged three times).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built · [BROKEN] the
code contradicts the intent. This spec does **not** replace `source/recipe-designer.md` (how a recipe is
designed), `source/models-chains-and-projects.md` (the run's engine behaviours, `source.recipe.*`) or
`ui/activity-and-automatic-work.md` (lanes, throttle, durability, the Activity window). It walks the one
journey **from Start to the summary** and states the RELIABILITY behaviours as testable lines, each with
its honest tag, its test and its issue. Where an existing id already says it, this spec cites it (the
owning spec stays the place to change it) and adds a `recipes-run.*` line only for what no spec said.
Under "Exists", an id with no mark is [OK]; **(P)** marks PARTIAL, **(G)** GAP, **(B)** BROKEN.

## Intent (the design)

A person presses Start on a project of 20, 100 or 400 pages, goes to make tea, and comes back to a project
that is read, named and searchable, with Activity saying what happened in words. Nothing they do in the
meantime (quit the app, let the Mac sleep, open another project, use the Mac hard) and nothing the engine
suffers (a crash, a kill, a full disk, a Mac with 65 MB free and 6 GB of swap) loses work or does it twice.
The engine never dies of memory: it knows what a model needs before loading it, runs one heavy model at a
time, holds new pages while the Mac is paging, caps its database, and gives memory back between steps.
A restart takes every unfinished claim up again and frees every lane; one wedged project never blocks
another. Pages finish in the order the sidebar shows them; search, names and vectors run once at the end
of the reading, not after every step; and the run records how long each step took, so the next recipe can
be designed from measured numbers.

It lives in the recipe runner (`fichero-server/src/fichero_server/recipes/runner.py`: `_batches`,
`_run_batch`, `_run_embed`, `BATCH_PAGE_LIMIT`, `OUTRIGHT_IN_A_ROW`), the job scheduler and lanes
(`fichero-server/src/fichero_server/execution/jobs.py`: `resume`, `settle_made_thumbnails`,
`FIRST_REASON`, `READING_FIRST_REASON`, `release_idle_models`, `_wait_for_lane_blocking`), the throttle
(`fichero-server/src/fichero_server/execution/throttle.py`: `memory_short`, `paging_now_on_this_mac`,
`footprint_bytes`, `peak_rss_bytes`, `decide`), Kraken's page gate (`fichero-server/src/fichero_server/llm/kraken_runtime.py`:
`pages_at_once`, `page_fan_out`, `PAGES_AT_ONCE_GATE_5929`, `IDLE_RELEASE_SECONDS`), the DuckDB budget
(`fichero-server/src/fichero_server/core/duckdb_session.py` `apply_memory_limit`), the derivative queue
(`fichero-server/src/fichero_server/importers/derivatives.py` `EMBED_KIND`, `NLP_KIND`) and the run's
account (`fichero-server/src/fichero_server/workflows/run_account.py` `engine_peak_memory_bytes`). The
app only shows what the engine says (`fichero/fichero/Views/Activity/`); no rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **Spotlight and Photos indexing.** Long background work that never gets in the way, survives every
  quit and crash, and resumes where it was; the activity spec adopts this as its north star
  (`ui/activity-and-automatic-work.md` "Intent"). We add nothing; this spec makes the recipe run honour it.
- **Durable queues: claim with a lease, transactional outbox, exactly-once effect.** The pattern of every
  job queue that survives its workers (Sidekiq, Celery with acks-late, Postgres `SKIP LOCKED` queues): a
  `running` row whose lease lapsed goes back to `waiting`, never to `failed`
  (`activity.durable.lease-not-fail` (P), `activity.durable.queue-is-rows` (P)). The dogfood wedge is
  exactly the failure this pattern exists for: a claim held by a dead process.
- **Checkpointed pipelines (LangGraph).** Resume from the last checkpoint after a restart; Fichero
  persists checkpoints to DuckDB already (`workflows/checkpointer.py`, `activity.durable.paused-stays-paused`).
- **Memory budgets in ML serving (vLLM, llama.cpp, Ollama).** Declare the model's resident need before
  loading, admit only what fits, one model resident per device by default, unload on idle
  (`ai.where.one-memory-number`, `compute.memory.reads-follow-memory`, `activity.lane.idle-unload`). The
  DuckDB side is DuckDB's own `memory_limit` and `temp_directory` (its documented spill design).
- **Load testing by running, not by registration** (Testing Constitution article 4, #4634): a model is
  proven by a run on a real page under a time and memory bound. This spec's load leg (#6212) is that
  article applied to the whole recipe.
- **What we do differently.** No setting for any of it (dead-simple UX): the engine measures the Mac
  and decides; the person sees one grey line of why in Activity.

## The journey, as the app does it today

Numbered in the order a person meets them. "Exists" cites the owning specs.

### 1. Set Up, and a stage's Try on a few pages

**Exists.** Set Up walks the stages and each page tries its result on 3 to 5 of the person's pages
(`source.onboard.stages.samples-proposed` (P), `source.onboard.stages.sample-result` (P),
`source.try.never-over-existing` (P), `source.try.kept-and-rerunnable` (P)); a try is watched work and
goes ahead of a bulk run (`activity.throttle.try-ahead-of-bulk`); a try's row counts its pages and says
why it waits (`source.onboard.stages.try-waiting-says-why` (P), `test_a_waiting_try_says_why_5837.py`).

- `recipes-run.journey.try-is-not-the-work` — **[OK]** (#5668; `source.onboard.stages.samples-are-not-the-work` (P)
  owns the wording; pinned by `fichero-server/tests/unit/recipes/test_stage_try_does_not_wait_or_hide_5806.py`)
  a stage's Try runs on the sample pages only, as a person-started job on the lanes, and never starts
  the recipe; what it made is kept and shown as the try's, never counted as the run's.

### 2. Start: on the project, or on one folder

**Exists.** Start is the first yes and shows the plan first (`source.project.automatic-after-first-yes` (P),
`source.recipe.start-runs-the-steps`); a step Start cannot run is skipped and says why
(`source.recipe.step-skipped-says-why`); Start can be given one folder (`source.recipe.folder-scoped-start` (P);
the engine done, the app not seen in a build); a started recipe does not redo what is done
(`source.recipe.done-is-not-redone`); a project with no pages says so and queues nothing.

- `recipes-run.journey.start-on-project-or-folder` — **[PARTIAL]** (#5540; `source.recipe.folder-scoped-start` (P)
  owns it) Start on the project, "Run the Recipe on This Folder…" on a folder, and an import's own run are
  one loop (`runner.enqueue`); the folder's plan covers only its live pages. *Left:* the app's folder Start
  seen in a build; Set Up… shows the whole project's plan when a folder's refusal is the reason.
- `recipes-run.journey.start-opens-the-run` — **[GAP]** (#5576) pressing Start closes Set Up and opens the
  run in Activity (the window, the run's row selected), so the person sees where the work went; today Set
  Up closes and nothing points at the run.

### 3. The run: batches, order, progress

**Exists.** A run goes a batch at a time (one folder, or 500 pages of it), every step finishing on a batch
before the next batch starts, folders in the order of the material (`source.recipe.batch-at-archive-scale`);
within a batch the steps are step-major: Kraken's cards, then the readers, then spaCy, then the embedder,
each heavy model loaded once a batch (`activity.run.step-major-per-batch`,
`fichero-server/tests/unit/recipes/test_recipe_runs_step_major_per_batch.py`, `test_one_mlx_load_per_batch.py`);
pages are queued in Finder order (`source.recipe.pages-in-finder-order`); every finished batch is a
checkpoint (`source.recipe.batch-checkpoint`); a step that fails on a batch does not end the run, three
outright failures in a row do (`source.recipe.batch-at-archive-scale`, `OUTRIGHT_IN_A_ROW`); a step counts
its pages (`source.recipe.step-counts-its-pages`); the run's status is Activity's
(`source.recipe.run-status-is-activity`); a run still waiting says what for (`activity.lane.thumbnails-first` (P),
`activity.throttle.one-heavy-when-memory-tight`, `test_a_waiting_run_says_what_it_waits_for_5818.py`).

- `recipes-run.journey.progress-in-words` — **[PARTIAL]** (#6091, #5960) the run's row and the opened run
  say the stage in words ("Find lines and Read each line · stage 1 of 5", never `find-lines`), pages done
  of total with the time left from measured pages, and one grey line of why when it waits. Built: the stage
  bar, page grid and `up_next` (`activity.window.open-a-run` (P), `activity.summary.up-next` (P)); the
  job-id wording is #6091. *Seen in the dogfood:* "Finding regions: 0 of 1 pages" on a find-lines stage,
  and `start_project` saying 95 pages while the run took 58 with no reason shown (the blank-verso and
  already-done counts belong on the row; `source.recipe.done-is-not-redone` has the numbers).

### 4. Finish: the summary

**Exists.** The run's summary counts what it made and lists failed pages with Read Again
(`source.onboard.auto.results-summary`, `fichero-server/tests/unit/recipes/test_run_summary_counts_6001.py`);
a summary that raises never fails the tree (`activity.summary.never-fails-the-tree` (B), #6001); a run with
failures ends "Done with failures", each cause said once (`source.recipe.batch-at-archive-scale`,
`test_one_failure_one_line.py`).

- `recipes-run.journey.finish-summary` — **[GAP]** (#5577) when a run ends the project shows the
  summary once, in words: pages read, names by kind, dates, documents proposed, failed pages with Read
  Again, skipped steps with their fix; a run whose steps had failed pages never reads a bare "Done".

### 5. Resume: after a quit, a sleep, a crash, a Stop

**Exists.** A quit pauses every live run with a checkpoint and the next open resumes it
(`activity.run.quit-pauses`, `activity.durable.paused-stays-paused`,
`fichero-server/tests/unit/jobs/test_durable_5357.py`); when the engine dies mid-job the next open puts
every queued job back to waiting, "Interrupted; carries on", and takes it up from its checkpoint
(`activity.durable.dies-with-the-engine`, `jobs.resume`,
`fichero-server/tests/unit/jobs/test_a_job_that_dies_with_the_engine.py`); a recipe run that was stopped
or lost is started again and skips every step and page it finished
(`source.recipe.done-is-not-redone`, `fichero-server/tests/unit/recipes/test_start_stop_restart_resumes.py`,
`test_every_stage_resumes_after_a_stop_1134.py`); Stop on the run's row stops the run and its waiting
pages (`activity.recipe-run.stop-reaches-its-step`, `fichero-server/tests/unit/jobs/test_cancel_recipe_run_5609.py`).

- `recipes-run.journey.resume-after-quit` — **[OK]** (#5357; `activity.run.quit-pauses` owns it; pinned by
  `fichero-server/tests/unit/jobs/test_durable_5357.py`) a quit mid-run leaves the run paused with its
  checkpoint; the next open lists it paused and Resume carries on without a page done twice.
- `recipes-run.journey.resume-after-crash` — **[PARTIAL]** (#5357, #6203) a crash or kill mid-run: the
  recipe run itself carries on from its checkpoint on the next open (built, `activity.durable.dies-with-the-engine`);
  its workflow step is still flipped to failed, "Interrupted: the engine stopped at HH:MM", and offered as a
  new run instead of resumed in place (`activity.durable.lease-not-fail` (P), `compute.run.interrupted-on-start`);
  and the import's thumbnail claims the dead process held are not taken up at all (#6203, section 7 below).
  *Seen in the dogfood (23:26Z):* the interrupted run resumed itself at once and fanned its 58 pages out
  again before the person could say anything (open question 2).
- `recipes-run.journey.run-again-on-what-was-missed` — **[GAP]** (#6170; `source.recipe.run-again-on-what-was-missed` (G)
  owns it) after a restart, a crash or a Stop the recipe says what it did not finish and offers one action,
  Run again on what was missed, which runs only what is not done.

## Reliability: the behaviours that make a run finish

Each line is one testable statement. The test named is the one that pins it, or the one to write (red
first). "Ceiling" and "band" figures are proposals until the owner rules (open question 1).

### 6. The engine does not crash, and a 100-page run finishes

- `recipes-run.reliability.hundred-pages-finish` — **[GAP]** (#6212) a recipe run over 100 pages on a temp
  engine (`FICHERO_BASE_PATH` a fresh directory, never the owner's app database) ends done with no step
  failed outright, the engine process alive throughout and `/api/health` answering within 1 s at every
  sample; it is the M4 gate's load leg (#4634), marked slow and skipped on the Pro. Nothing today runs a
  whole recipe at that size: the owner's 20-page runs wedged three times (dogfood B12) and a Dev Local
  engine was SIGKILLed at 14.9 of 16 GB of swap (#6075). Test (to write): fichero-server/tests/perf/test_recipe_run_100_pages.py.
- `recipes-run.engine.answers-while-a-run-goes` — **[BROKEN]** (#6178, #6001) while a run goes, every
  Activity poll, the run's status and `/api/health` answer within 1 s and never hold the event loop:
  every database read of a poll runs on a worker thread, and a poll under a held writer answers with what
  it has rather than waiting. Ann's engine log shows 754 `loop_lag` warnings up to 16.9 s in
  `get_job_tree -> run_account -> execute_fetchone` and polls of 14 to 21 s; the dogfood engine's
  `/api/health` timed out for 9 minutes. `activity.summary.off-the-loop` (B) is the recipe summary's half.
  Test (to write): fichero-server/tests/unit/core/test_loop_lag_activity_polls.py.
- `recipes-run.engine.local-call-judged-by-progress` — **[OK]** (#5537; `compute.memory.local-call-judged-by-progress`
  owns it; pinned by `fichero-server/tests/unit/jobs/test_local_no_progress_retry_5537.py`) a page whose
  local model stopped answering is read once more before it fails, with the model's output in the log;
  the run carries on past it.

### 7. Memory is bounded

- `recipes-run.memory.peak-ceiling-per-model-kind` — **[GAP]** (#6212, #6076, #4987) the engine tree's
  peak resident memory during a run stays under a ceiling per model kind in use: for Kraken the card's
  `memory_gb` plus 1.5 GB a page in flight (`kraken_runtime.page_fan_out`'s own constant); for a served
  MLX model its card's one memory number (`ai.where.one-memory-number`, `test_one_memory_number_5537.py`);
  for the embedder its measured size; a run that would pass the ceiling holds its next page and says so,
  never loads another model. Built: the run's account records `engine_peak_memory_bytes`
  (`workflows/run_account.py`, `throttle.peak_rss_bytes`) and the throttle's one decision
  (`throttle.decide`); not built: a ceiling the run is held to, and the measured figures (#6076 is the
  20-page measurement). Test (to write): fichero-server/tests/perf/test_recipe_run_100_pages.py.
- `recipes-run.memory.flat-over-pages` — **[GAP]** (#6212, #5529) resident memory does not grow page over
  page: over a 100-page run the engine tree's RSS sampled on pages 80 to 100 is within 10% of pages 20 to
  40 (sampled every 2 s, `throttle.footprint_bytes`). The 2026-10-06 leak (8,418 compiled MPS graphs,
  18 GB in 25 minutes) is pinned at its seam by `fichero-server/tests/unit/jobs/test_engine_memory.py`;
  the whole-run assertion is not written. Test (to write): fichero-server/tests/perf/test_recipe_run_100_pages.py.
- `recipes-run.memory.duckdb-cap-applies` — **[BROKEN]** (#6177) every open DuckDB instance runs under its
  share of the budget (about 10% of physical memory split across the open instances, a 256 MiB floor,
  `fichero-server/tests/unit/core/test_duckdb_memory_budget.py`); a refused spill-directory switch
  ("Cannot switch temporary directory after the current one has been used") is logged once and never
  skips the cap. Today `apply_memory_limit` sets the spill directory first, the instance that has already
  spilled refuses, the exception skips the cap, and the instance runs at DuckDB's default of 80% of RAM
  (Ann's log: the warning 6,671 times). Test (to write): fichero-server/tests/unit/core/test_duckdb_memory_cap.py.
- `recipes-run.memory.one-heavy-model` — **[BROKEN]** (#6000, #6167; `activity.lane.small-mac-one-heavy-model` (B)
  and `designer.model.one-resident-local-model` (G) own it) on a Mac of 16 GB or less the model lane never
  keeps two heavy models loaded: before a Kraken load it stops the served MLX model and before a served
  model it frees Kraken, whatever the free-memory reading says; the run's row says which model it swapped
  for and why. Built: one heavy job at a time while memory is tight (`activity.throttle.one-heavy-when-memory-tight`,
  `fichero-server/tests/unit/jobs/test_one_heavy_when_memory_tight.py`), the idle release of Kraken after
  120 s and the embedder after 600 s (`activity.lane.idle-unload`), the memory hold freeing idle models
  (`fichero-server/tests/unit/jobs/test_memory_gate_frees_idle_models_6129.py`). Not built: the release of
  the served model before a Kraken load (`_RELEASE["local-model"]` frees nothing).
- `recipes-run.memory.hold-when-paging` — **[PARTIAL]** (#6075; `activity.throttle.hold-when-swapping` (P)
  owns it) new heavy work is held, and Kraken reads one page at a time, while this Mac is paging NOW under
  memory pressure at warn or above (pageouts or swap grown by 64 MB within the last minute); static swap
  never holds. Built and pinned by `fichero-server/tests/unit/jobs/test_kraken_holds_under_swap_and_pressure_6075.py`;
  left: the owner's check that the Test 13 run finishes on the 16 GB Mac, and the popover's paging line.
- `recipes-run.memory.pages-at-once-bounded` — **[PARTIAL]** (#5931, #5929) the pages a step reads at once
  are the Mac's performance cores held down by memory, never below 1, gated at 2 until the exit-time MPS
  crash (#5929) closes; one for every automatic run and one whoever asked while the Mac is paging
  (`kraken_runtime.pages_at_once`, `PAGES_AT_ONCE_GATE_5929`, `source.read.pages-at-once-scales` (P),
  `fichero-server/tests/unit/jobs/test_kraken_page_gate_two_at_once.py`). *Seen in the dogfood:* a try of 5
  pages launched all 5 in the same millisecond and the engine peaked at 2.9 GB; whether the gate held them
  to 2 is not shown anywhere a person reads (open question 3).
- `recipes-run.memory.fan-out-does-not-decode-ahead` — **[PARTIAL]** (#5846; `activity.lane.same-model-pages-together` (P))
  a fan-out node hands the lane at most `pages_at_once` pages, and a page waiting for the lane holds no
  decoded image: 58 pages queued is 58 rows, not 58 bitmaps (58 × 32 MB RGB ≈ 1.9 GB before any model).
  Built: the lane admits pages by the gate; not pinned: that the waiting pages hold no image. Test (to
  write): fichero-server/tests/unit/workflows/test_fan_out_decodes_only_admitted_pages_5846.py.

### 8. A restart requeues unfinished work and releases every lane

- `recipes-run.restart.requeues-unfinished` — **[BROKEN]** (#6203; `activity.lane.no-wait-on-a-job-that-will-not-run`
  is the file-exists half) after a kill and restart, every claim a dead process left (a thumbnail with no
  file, a page half-read, an embed) goes back to waiting within one claim cycle and runs; `Make thumbnails`
  reaches N of N and the thumbnails-first hold lifts. Today the recipe run and the import's pages do
  (`activity.durable.dies-with-the-engine`), but a thumbnail claim whose file does NOT exist is neither
  run nor released, so `activity.lane.thumbnails-first` held every Kraken, embed and spaCy job forever
  across three restarts (dogfood B12: 81 of 95 thumbnails, the 14 missing pages never made).
  Test (to write): fichero-server/tests/unit/jobs/test_thumbnail_claims_requeued_after_crash.py.
- `recipes-run.restart.releases-lanes` — **[BROKEN]** (#6213; `activity.durable.reopen-leaves-live-jobs` is
  the live half) a lane holder is a RUNNING row with a live worker thread of this engine; a row left
  running by a dead process holds no lane after the restart, so the next job of that kind in any project
  starts within one claim cycle. Test (to write): fichero-server/tests/unit/jobs/test_lanes_released_per_project.py.
- `recipes-run.restart.retry-reaches-a-kind-row` — **[GAP]** (#6203) Retry on a kind row (`waiting:thumbnail`)
  requeues that kind's set-aside and dead claims for the project; today it answers 404 (the kind row is not
  a job id), so there is no way from Activity to restart the thumbnail work. Test (to write):
  fichero-server/tests/unit/jobs/test_thumbnail_claims_requeued_after_crash.py.

### 9. One project never blocks another

- `recipes-run.isolation.one-project-never-blocks-another` — **[BROKEN]** (#6213) the lanes are shared,
  the holds are not: a project whose rows are wedged (running with no worker) never holds the thumbnail,
  model or embed lane against another project; a fresh project's import makes its first thumbnail within
  a minute whatever another project's rows say. Dogfood B12 23:50Z: a fresh project sat at 0 of 20,
  "Waiting for the thumbnail lane: work in another project is running", on the wedged project's phantom
  rows. Test (to write): fichero-server/tests/unit/jobs/test_lanes_released_per_project.py.
- `recipes-run.isolation.release-never-refused-by-a-phantom` — **[BROKEN]** (#6213) releasing a library
  refuses only for a run with a live thread of this engine, naming the run and its state; with every thread
  terminal it releases. Dogfood B12: `fichero_library_release` answered 409 "1 workflow run(s) are going"
  with `list_threads` empty and every thread terminal. Test (to write): fichero-server/tests/unit/jobs/test_lanes_released_per_project.py.

### 10. A run can be stopped, paused and resumed

- `recipes-run.control.stop` — **[OK]** (#5609; `activity.recipe-run.stop-reaches-its-step` owns it; pinned
  by `fichero-server/tests/unit/jobs/test_cancel_recipe_run_5609.py`) Stop on the run's row ends the run
  after its current unit, its waiting pages withdrawn, a page mid-read finishing and recorded; the row says
  who stopped it (`test_a_stopped_run_says_who_stopped_it.py`).
- `recipes-run.control.pause-and-resume` — **[PARTIAL]** (#5933; `activity.recipe-run.pause-reaches-its-step` (G)
  owns it) Pause on the run's row pauses the recipe at its next step and its step's run in flight, saying
  so; a paused step is waiting, never failed; Resume carries on from the checkpoint. Written, unrun:
  `fichero-server/tests/unit/recipes/test_recipe_pause_5933.py`.
- `recipes-run.control.start-again-redoes-nothing` — **[OK]** (#5390; `source.recipe.done-is-not-redone` owns
  it; pinned by `fichero-server/tests/unit/recipes/test_start_stop_restart_resumes.py` and
  `test_every_stage_resumes_after_a_stop_1134.py`) Start after a Stop or a crash skips every step and page
  it finished (lines not found again, lines not read again, pages not split again) and the run ends done.

### 11. Order of completion, and search once at the end

- `recipes-run.order.folders-then-pages-queued` — **[OK]** (#5849; `source.recipe.pages-in-finder-order` owns
  it; pinned by `fichero-server/tests/unit/recipes/test_pages_in_finder_order_5849.py`) a run queues and
  starts its pages folder by folder in sidebar order, pages in no folder first, each page in its natural
  name order.
- `recipes-run.order.done-in-order-shown` — **[GAP]** (#6186) with pages read side by side they finish out
  of order; the run's progress is shown as done-in-order: the first N consecutive pages done in sidebar
  order, so the page grid and the pages list read alphanumerically, a page finished ahead counted when
  the gap before it closes. Test (to write): fichero-server/tests/unit/recipes/test_pages_done_in_order_6186.py.
- `recipes-run.order.search-entities-once-at-the-end` — **[PARTIAL]** (#6186; `activity.run.stages-before-search-do-not-embed`
  and `activity.lane.embed-after-reading` are the built halves) for a recipe run, the search embedding and
  the names draft run ONCE after the last reading step of the batch, in batches of 64, and Activity says
  "Search and names run once at the end"; they never compete with the readers for the model lane. Built:
  inside a run no stage before Search queues a page's embed, Search embeds it once
  (`fichero-server/tests/unit/recipes/test_stages_before_search_do_not_queue_embeds_6126.py`); background
  embeds wait for the reading and run off the heavy lane (`test_embed_after_reading.py`,
  `test_embed_off_the_reading_lane.py`). Not built: the import still queues an embed and an NLP draft per
  page at import time (`derivatives.py` `EMBED_KIND`, `NLP_KIND`), before there is text, so Activity shows
  them beside every step (dogfood B12: "Embed for search 0/95" queued at import). Test (to write):
  fichero-server/tests/unit/recipes/test_embed_once_after_reading_6186.py.

### 12. Per-step timings are recorded

- `recipes-run.timing.per-step-recorded` — **[PARTIAL]** (#6215, #6178) the run's record carries, per step
  and per batch, started, ended, seconds, pages done and seconds a page (the median of its pages' own
  times), and the run's total; a page's time is its own, never the job's cumulative figure; the figures
  survive a restart; the summary names the slowest step in words. Built: job rows carry `started_at` and
  `finished_at` (`execution/jobs.py`), the run has `estimate_seconds_left` from measured pages
  (`recipes/run_view.py`). Not built: the per-step durations on the run's record, and the per-file time
  (Ann's log shows "File N/213 completed (6541168ms)", the cumulative figure). Test (to write):
  fichero-server/tests/unit/recipes/test_step_timings_recorded.py.
- `recipes-run.engine.thumbnails-cheap-and-off-the-lane` — **[GAP]** (#6193) a thumbnail of a 10.7 MP TIFF
  costs under 2 s with a reduced-size decode and a bounded peak, and thumbnails never take the model lane,
  so the thumbnails-first hold is short by construction (dogfood: 1.6 s a page alone, 60 to 120 s a page
  beside a Kraken fan-out). Test (to write): fichero-server/tests/unit/importers/test_thumbnail_cost_bounded_6193.py.

## Changes to existing behaviours

1. **Resume after a crash resumes in place.** `activity.durable.lease-not-fail` (P) and
   `compute.run.interrupted-on-start` describe a crashed workflow step flipped to failed and offered as a
   new run. This spec asks that the step resume from its checkpoint like a paused one
   (`recipes-run.journey.resume-after-crash`); the owning spec is edited on approval.
2. **The import's embed and NLP draft wait for the run.** `activity.lane.embed-after-reading` holds a
   background embed for the reading; this spec asks that a project with a started recipe queue its
   search and names once at the end of each batch (`recipes-run.order.search-entities-once-at-the-end`),
   so nothing is queued at import for a page the recipe will read.
3. **Thumbnails-first is bounded.** `activity.lane.thumbnails-first` (P) holds heavy work for a project's
   thumbnails; with `recipes-run.restart.requeues-unfinished` and `recipes-run.engine.thumbnails-cheap-and-off-the-lane`
   that hold is at most a minute after a restart and never a deadlock.

Not changed: the batch loop and its checkpoints (`source.recipe.batch-at-archive-scale`,
`source.recipe.batch-checkpoint`); the step-major order inside a batch; the one throttle rule
(`throttle.decide`); no setting is added for any of it.

## Build order

### Stage 1 — Unwedge: a restart leaves nothing held

#### Step 1.1 — Dead claims requeue and release their lanes (#6203, #6213)
- Behaviours: `recipes-run.restart.requeues-unfinished`, `recipes-run.restart.releases-lanes`, `recipes-run.isolation.one-project-never-blocks-another`, `recipes-run.isolation.release-never-refused-by-a-phantom`, `recipes-run.restart.retry-reaches-a-kind-row`
- Tests: fichero-server/tests/unit/jobs/test_thumbnail_claims_requeued_after_crash.py, fichero-server/tests/unit/jobs/test_lanes_released_per_project.py
- Size: M

#### Step 1.2 — The engine answers while a run goes (#6178)
- Behaviours: `recipes-run.engine.answers-while-a-run-goes`
- Tests: fichero-server/tests/unit/core/test_loop_lag_activity_polls.py
- Size: S

### Stage 2 — Memory bounded

#### Step 2.1 — The DuckDB cap applies (#6177)
- Behaviours: `recipes-run.memory.duckdb-cap-applies`
- Tests: fichero-server/tests/unit/core/test_duckdb_memory_cap.py
- Size: S

#### Step 2.2 — One heavy model on a small Mac; the fan-out decodes only admitted pages (#6000, #6167, #5846)
- Behaviours: `recipes-run.memory.one-heavy-model`, `recipes-run.memory.fan-out-does-not-decode-ahead`
- Tests: fichero-server/tests/unit/jobs/test_one_heavy_when_memory_tight.py, fichero-server/tests/unit/workflows/test_fan_out_decodes_only_admitted_pages_5846.py
- Size: M

#### Step 2.3 — Measure, then the ceiling and the load leg (#6076, #6212)
- Behaviours: `recipes-run.memory.peak-ceiling-per-model-kind`, `recipes-run.memory.flat-over-pages`, `recipes-run.reliability.hundred-pages-finish`
- Tests: fichero-server/tests/perf/test_recipe_run_100_pages.py
- Depends on: 1.1, 2.1, 2.2
- Size: M

### Stage 3 — Order, once-at-the-end, timings

#### Step 3.1 — Search and names once at the end; done-in-order progress (#6186)
- Behaviours: `recipes-run.order.search-entities-once-at-the-end`, `recipes-run.order.done-in-order-shown`
- Tests: fichero-server/tests/unit/recipes/test_embed_once_after_reading_6186.py, fichero-server/tests/unit/recipes/test_pages_done_in_order_6186.py
- Size: M

#### Step 3.2 — Per-step timings on the run; cheap thumbnails (#6215, #6193)
- Behaviours: `recipes-run.timing.per-step-recorded`, `recipes-run.engine.thumbnails-cheap-and-off-the-lane`
- Tests: fichero-server/tests/unit/recipes/test_step_timings_recorded.py, fichero-server/tests/unit/importers/test_thumbnail_cost_bounded_6193.py
- Size: M

### Stage 4 — The journey's ends

#### Step 4.1 — Start opens the run; the summary at the end (#5576, #5577)
- Behaviours: `recipes-run.journey.start-opens-the-run`, `recipes-run.journey.finish-summary`, `recipes-run.journey.progress-in-words`
- Tests: fichero-server/tests/unit/recipes/test_run_summary_counts_6001.py, fichero/Tests/Unit/general/Models/ActivityOpenedRunTests.swift
- Size: M

#### Step 4.2 — Resume in place after a crash; pause; run again on what was missed (#5357, #5933, #6170)
- Behaviours: `recipes-run.journey.resume-after-crash`, `recipes-run.control.pause-and-resume`, `recipes-run.journey.run-again-on-what-was-missed`, `recipes-run.journey.start-on-project-or-folder`
- Tests: fichero-server/tests/unit/jobs/test_durable_5357.py, fichero-server/tests/unit/recipes/test_recipe_pause_5933.py, fichero-server/tests/unit/recipes/test_step_rerun_on_folder.py
- Depends on: 1.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | the opened run renders the engine's stage words, done-in-order progress and timings as served; no rule in Swift | `fichero/Tests/Unit/general/Models/ActivityOpenedRunTests.swift` |
| Availability (Swift) | y | Start opens the run in Activity; Run the Recipe on This Folder… reachable | `fichero/Tests/Unit/general/Models/RecipeSetupStoreTests.swift` |
| Backend (pytest) | y | dead claims requeue and release lanes; one project never blocks another; a release refuses only a live run; the DuckDB cap applies; one heavy model; fan-out decodes only admitted pages; polls answer within 1 s; search and names once at the end; done-in-order; per-step timings; resume in place; pause | the unit files named per behaviour above (`fichero-server/tests/unit/jobs/`, `fichero-server/tests/unit/recipes/`, `fichero-server/tests/unit/core/`) |
| MCP | y | `fichero_recipes_start_project`, `fichero_recipes_run_status`, `fichero_activity_*` drive the load leg and read the timings | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | y | the load leg starts and watches the run through the CLI, never curl | `fichero-cli/tests/` |
| Click-around (XCUITest, Mac) | n | Activity's own spec owns the window's UI test | — |
| iPhone (iOS) | n | — | — |
| iPad | n | — | — |
| Load (#4634) | y | a 100-page run on a temp engine finishes; peak RSS under the ceiling; flat over pages; the engine answers throughout | fichero-server/tests/perf/test_recipe_run_100_pages.py (to write; the M4 gate's load leg, skipped on the Pro) |

Hard-gate: the cross-surface invariant (the run's status, Activity's rows and the MCP tools are one
account of the same job rows) + the load leg green on the M4 before the spec is marked finished.

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | `docs/user_manual/guide/` "Running your recipe" (TBD; the facts are the behaviour lines above) |
| Contributor | developer docs | y | `docs/contributor_manual/architecture/` recipes and jobs + this spec |
| AI / agent | MCP tool description | y | `fichero-mcp/**` (`fichero_recipes_start_project`, `fichero_recipes_run_status`, `fichero_activity_retry_job`: what Retry on a kind row does) |
| Scripter | CLI `--help` | y | `fichero-cli/**` (start, status, stop, resume of a recipe run) |
| Reference | capability/endpoint reference | y | generated (`check_capability_reference_current`) |

## Preview harness

None of its own: the run is shown by Activity's opened run (`activity.window.open-a-run`), whose preview
renders from recorded served data. This spec adds to that recording a run with per-step timings and a
done-in-order progress, so the manual's screenshot shows both.

## Accessibility identifiers

Activity's (`ui/activity-and-automatic-work.md`). This spec adds none.

## UX completeness

No new control: every behaviour is engine-side or shown through Activity's existing rows. The waiting
lines this spec names ("Search and names run once at the end", a swapped model's reason, the paging
line) are String Catalog keys of the engine's `why` text, passed through as sent.

## Open questions for the owner (with a recommendation each)

1. **The ceilings and the band.** Proposed: Kraken's ceiling is the card's `memory_gb` plus 1.5 GB a page
   in flight; the no-growth band is 10% between pages 20–40 and 80–100; the poll bound is 1 s. *Recommend:*
   approve as proposals, and let #6076's measured table replace the Kraken figure before #6212 is coded.
2. **Resume after a crash: at once, or offered?** Today an interrupted recipe run resumes itself on the
   next open and fans its pages out again (dogfood 23:26Z). *Recommend:* resume at once (the Spotlight
   rule: nothing waits for a person), but one page at a time for the first minute after a restart so a
   Mac that just recovered is not thrown back into paging; a person who wants it stopped presses Stop.
3. **Show the gate.** A person cannot see how many pages read at once or why. *Recommend:* the run's row
   says "reading 2 pages at once" in its grey line, from the engine's `pages_at_once`; no setting.
4. **Milestone name on approval.** This spec is DRAFT on `recipe-designer` beside `recipe-designer.md`;
   the guards want spec name == milestone name when APPROVED. *Recommend:* approve under a new milestone
   `recipes-run` (issues #6212, #6213, #6215, #6186, #6203, #5846, #6193 move to it), so the reliability
   work burns down on its own, visibly, apart from the designer's screens.
5. **Search and names at import.** Today an import queues an embed and a names draft per page at once.
   *Recommend:* a project with a started recipe queues neither at import (the recipe does them once at
   the end of each batch); a project with no recipe keeps today's behaviour.
