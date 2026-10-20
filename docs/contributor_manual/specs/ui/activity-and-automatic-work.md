# Activity and Automatic Work — one job model, one window — Design Spec (#5352)

> Milestone: activity
> Manual: TBD — "What Fichero is doing": the Activity window; why work runs by itself when you add
> or correct something; pausing everything, or one job; what happens when you quit, sleep or crash
> (nothing is lost, nothing is done twice); what a job cost; taking a job's work back.
> Facts for the maintainer to write it from (no user-manual page yet): `docs/contributor_manual/manual-facts/2026-10-05.md`, section 2.

> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-01 — design review, awaiting the
> maintainer.** Written read-only against the integration tree. Claims about the code are
> **VERIFIED** (file and line read), or **INFERRED** (follows from what was read, not run). Nothing
> was run.
>
> This spec owns the one place for all background work, a question `ui/workflows.md`,
> `ui/automation.md`, `compute/jobs-and-fine-tuning.md` and `source/models-chains-and-projects.md`
> each touch but none owns; it cites them rather than restating them. It absorbed `ui/activity.md`
> on 2026-10-04 (the maintainer's ruling): that spec's behaviours are section I here, with their
> ids unchanged, and that file is gone.
>
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists, partly wired or unpinned · **[BROKEN]**
> code contradicts the intent · **[GAP]** not built. `#ISSUE_<name>` marks an issue to file.

## Intent

Fichero does a great deal of work in the background: importing, making thumbnails, embedding,
finding lines with Kraken, reading pages with a vision model, extracting people and claims,
converting old geometry, downloading models, syncing with another Mac. Today each of these
reports (or does not) in its own way. The maintainer's direction is that this is far too
complicated, and that it should feel like a new Mac indexing itself with Spotlight: the work
grinds away for hours or days, never gets in the way, survives every quit, sleep and crash, and
one window says plainly what is happening.

So:

1. **One kind of thing: a job.** Every piece of background work, of every kind, is a job in one
   table in the engine, with the same fields: what it is, what it is working on, its state,
   progress, time, cost, errors, who or what started it. A job can have child jobs (a run has
   steps; a step has pages), so the same row expands from "Transcribe 400 pages" down to "page
   212, line 14 failed".
2. **One window.** The Activity window is a table of every job in every open project, now and
   recently, expandable row by row. Nothing else invents its own progress list.
3. **One pause.** A single *Pause Background Work* stops everything that runs by itself, and stays
   paused across relaunch until the person resumes it. Each job also has its own pause, resume and
   cancel.
4. **It never gets in the way.** Background jobs run at low priority, in bounded lanes,
   and slow down or wait on battery, under heat or memory pressure, and while the person is
   working hard. Work a person is waiting on goes first.
5. **It is durable.** The queue lives in the project's database. Quit mid-job, crash, or pull the
   plug: on the next launch every job is where it was, paused jobs are still paused, and no
   page is done twice.
6. **It is automatic.** When something is **added**, the project's recipe says what runs on it.
   When something is **changed**, whatever was made from it is marked out of date and remade.
   Correcting a page's text remakes its embedding, its entities and its claims, without anyone
   asking; what a person has already curated is kept and flagged, never overwritten.

### Ruled 2026-10-04 (the maintainer, after the spec audit; paraphrased)

- **One tree, one queue, one start and stop.** Every kind of work (Kraken, spaCy, models served on
  this Mac, cloud calls, Hugging Face and ACENET jobs, downloads, training) is a row in one tree,
  queued in one place, started and stopped one way. A run's tree follows the path its graph took,
  branches and sub-workflows included, and each running row says what it is doing now.
- **The measures that matter** for a run, a step and a page are time to run, cost, greenhouse gas,
  images run and steps run, rolled up the tree; they are the table's main columns. Greenhouse gas
  is an estimate from energy and grid intensity, always with its basis, never invented.
- **Times are absolute** everywhere.
- **The popover is a summary**: running, waiting and the main reason, the last three errors, and
  the Mac's state (memory pressure, heat, battery, in use); CPU and GPU figures come later.
- **The Mac's own work** (downloads, installs, model loads) is global, not a project's; the window
  can group by project, with the Mac's work as its own group.
- **A run started by hand** waits only for memory and heat, and its row says so.
- **Pins before OK:** a scheduler behaviour is re-tested through a route, an action or a real run
  before it is tagged OK (see "Pinning").
- `ui/activity.md` is folded in here (section I).

### Ruled 2026-10-09 (the maintainer, testing the Dev Embedded build; paraphrased)

- **One Start / Stop control, in two places**: a button in the main window's toolbar, next to the
  Activity indicator, and the same control in the Activity window. Start means *go ahead although I
  am using the Mac*: the holds for the person at the Mac and for battery are lifted for the waiting
  work until the control is pressed again, which goes back to automatic. Stop pauses all the work.
  The toolbar button shows at a glance which it is: running, held, or paused. One engine action
  behind both (`activity.mode.start-stop`).
- **Memory safety is never lifted**: forced work still never runs two heavy jobs at once while
  memory is tight, and the app manages that, not the person (`activity.throttle.one-heavy-when-memory-tight`).
- **The control's words and look** (later the same day): its menu is a choice with a tick beside the
  current mode, *Run Now*, *Run Automatically*, *Pause All*; the toolbar button is an icon only (play
  filled while work runs, play outline while idle, an orange hourglass while work waits, pause while
  paused), with the words in its help and accessibility label. "Held" is said *Waiting*. After
  *Pause All* the button must say paused at once and stay so (it kept showing running, #5621).
- **Clear Failed clears what is failed**, every failed row the window shows, and says what it
  cleared (#5634). **The popover's Mac state is a row of symbols**, not a column of text (#5635).

### Ruled 2026-10-19 (the maintainer, finding Activity and its logs cluttered; paraphrased)

What the person sees first, top to bottom, and how the window reads. The behaviours are in section B ("The Activity
window, ruled 2026-10-19") and the details view; where one of them replaces an older line, that line says
*superseded by Ruled 2026-10-19*.

- **What is working now comes first:** the recipe, the stage it is in and the workflow that stage runs.
- **What it acts on:** which files and folders and how many in all ("Read: 7 of 20 pages, folder X"), with the whole
  list of pages opening under it, each with its state. Not the next three rows.
- **What comes next, in run order.** Waiting things look waiting (no spinner) and say what they wait for.
- **Layout:** one live block per project at the top (Recipe › Stage › Workflow, a count of done, failed and left, the
  folders, opening to the files); background work (thumbnails, embeddings, Run automatically) in its own group below,
  one row per kind with its total; finished, stopped and interrupted runs fold into a History group, which Clear
  Finished empties.
- **Logs:** the default log is the person's: one line per page when it is done or failed, one per stage; one sentence per
  event, in local time, never repeated, never inside another job's line. The "Node … started" lines and the like go to a
  Developer level that is off by default.
- **Stop and Retry:** Stop on a page skips it and the run goes on; Stop on a run stops all of it and every row agrees
  (`activity.stop.page-skips-run-stops-children`, the bugs lane's); Retry on a page retries it within its run
  (`activity.retry.page-within-run`).
- **The toolbar popover follows the same rules** (live Recipe › Stage › Workflow with its pages and folder, one line per
  background kind, waits that look waiting, no stale or interrupted runs, Open Activity), and it and the window read ONE
  engine summary, so they always agree.

Issues: #5839 (order and rows), #5850 (logs), #5851 (layout: background and History groups), #5852 (one summary for the
popover and the window), #5853 (Stop and Retry; Stop is the bugs lane's entry). Already in flight with the bugs lane, not re-specified here: Stop on a
page or a run, Retry within a run, the embed after reading, one live run per project.

## Prior art (what we build on, and what we do differently)

- **macOS Spotlight indexing and Photos analysis.** The model for the whole feel. Both run at
  background QoS on efficiency cores, defer on battery and thermal pressure, pause while the
  person is busy, resume after reboot, and say little: a progress line in Spotlight settings,
  "Paused, will resume when connected to power" in Photos' library status. We adopt: background
  QoS, deferral on power/thermal/memory, plain-language "why it is waiting" text, resumption
  across reboot. We differ: researchers want to *see* the work (which page, which model, what it
  cost), so the table is richer than Photos' single status line.
- **Time Machine.** One global on/off, backups that resume where they stopped, and an honest
  "Preparing… / Waiting / Last backup failed because…". We adopt the single global switch and the
  waiting reasons. Time Machine's menu-bar "Skip This Backup" is the model for per-job cancel.
- **Activity Monitor.** A sortable table, one row per process, expandable trees, columns the user
  can show or hide, a selected row's details below. We adopt the table and the disclosure tree
  (SwiftUI `Table` with `children:`).
- **Xcode's activity view and Report navigator.** A small summary in the toolbar ("Indexing |
  Processing files 120 of 900"); the full log of every build and its steps in a navigator. We
  adopt the split: the toolbar island summarises, the window has the detail. The status island
  already does the first half.
- **Finder's copy window.** Each copy is a row with its own progress bar, time remaining and a
  stop button; several copies stack in one window. We adopt the per-row cancel and the "time
  remaining" estimate.
- **Celery, RQ, Sidekiq and other durable queues.** Tasks are rows; a worker *claims* a row with
  a lease, heartbeats it, and a row whose lease expires goes back to the queue; retries with
  backoff; a poison item is set aside after N tries. We adopt lease-and-heartbeat, idempotency
  keys and bounded retries. We do not adopt a broker (Redis, RabbitMQ): Fichero is one process
  per Mac and the project database is already durable, so the queue is a table in it (the same
  choice `workflows/tasks.py` already made).
- **Temporal-style durable execution.** A long workflow records each completed step, and after
  a crash it replays to the last recorded step instead of starting again. LangGraph's
  checkpointer is this idea, and Fichero already persists its checkpoints to DuckDB
  (`workflows/checkpointer.py:76`). We adopt "resume from the last checkpoint after a restart";
  today the engine throws that away (see below).
- **make, Bazel and incremental build systems.** Every output records exactly which inputs (and
  which version of the tool) produced it; a change to an input marks precisely the outputs that
  depend on it as stale, and only those are rebuilt; an output whose inputs have not changed is
  never rebuilt. We adopt this for derived data: each derived row names what it was made from
  and a fingerprint of it, and invalidation walks those edges. We differ in one important way:
  a build system overwrites its outputs, but a person may have curated a derived claim, so a
  stale output that a person has touched is **flagged**, not replaced.
- **W3C PROV** (already adopted in `safety/run-take-back.md`): a job is an `Activity`; what it made
  `wasGeneratedBy` it and `wasDerivedFrom` its inputs. The derivation edges here are PROV's
  `wasDerivedFrom`, stored.

## What exists today (verified 2026-10-01)

Server paths are relative to `fichero-server/src/fichero_server/`; app paths to `fichero/fichero/`.

### How many job and progress systems: at least twelve

| # | System | Covers | Where it is stored | Shows in Activity? | Pause / cancel | Survives quit? |
|---|---|---|---|---|---|---|
| 1 | **Workflow runs** (LangGraph) | every workflow: Kraken Detect Regions / HTR, MLX and cloud vision reading, LLM extraction, cleanup, translate… | run rows in the activity store (`workflows/activity_store.py`), checkpoints in DuckDB (`workflows/checkpointer.py:76`), live state in `execution/runner.py` `_running_workflows` | **Yes**: run list + `/api/activity/jobs` merges running/failed runs (`api/routes/system/activity.py:300-363`) | pause, resume, stop, delete per run (`Views/Activity/RunControls.swift`); cancel and pause flags are in-memory `threading.Event`s (`execution/cancellation.py:22-24`, `:107`) | **No.** On reopen every `running`, `accepted` **and `paused`** run is flipped to `failed` (`workflows/activity.py:658-707`, `activity_store.py:1456-1500`), although its checkpoints are on disk |
| 2 | **Batches** | one workflow over many items | DuckDB `batches`, `batch_items`, `batch_progress_snapshots` (`execution/batch.py:250-282`) | as tracker events (`batch_created/started/item_*`, `batch.py:336,561,759`); `BatchStore.swift` | pause, resume, cancel, retry (`api/routes/workflow/batch.py:346-408`) | rows persist; resumption after restart not verified |
| 3 | **Legacy chain executor** | `/chains/{id}/execute` | in-memory `_running_executions` (`api/routes/workflow/chains.py:301`) | **No**: "no thread ids, no SSE, no activity records" (`chains.py:814`) | none | no |
| 4 | **Chain steps** (workflow bar) | `/chains/execute-steps`: each step a real workflow run | as #1 | yes, as separate runs | as #1 | as #1 |
| 5 | **Task queue** | reindex, metrics, repair, vector repair, KG metrics, re-anchor (`workflows/task_types.py:10-20`) | DuckDB `background_tasks` (`workflows/tasks.py:83`) | as `backend.work.*` change events (`tasks.py:398-441`); **not** in `/activity/jobs` | cancel **pending only** (`tasks.py:503-515`) | **yes**: running tasks go back to pending on load (`tasks.py:153-176`). The closest thing to the design below |
| 6 | **Derivative queue** | thumbnails, embeddings, free NLP draft (spaCy NER + SVO) after import, and one embed per page a workflow saves | in-memory `ThreadPoolExecutor` (`importers/derivatives.py:52-79`); progress map `_progress` (`:208`) | yes, one coalesced row per library (`background_jobs_snapshot`, `:253`); **NLP is not counted** (`:150-157`) | none (only engine shutdown, `:879`) | partly: documents left `Status.pending` are re-queued on open (`db/manager.py:222-243`); the "queue" is the document status, not a row |
| 7 | **Re-embed after a correction** | page text changed by a reading/segment action | a raw daemon `threading.Thread` per page (`actions/page_text_cache.py:345-378`) | **No** | none | **No** (daemon thread; the page is not `pending`, so nothing re-queues it — INFERRED) |
| 8 | **Re-embed after a direct text edit** | `PATCH` of `page_content` | inline, on the request (`api/routes/document/documents.py` ~2334-2343) | No | — | — |
| 9 | **Ingest tasks** | an import's progress | in-memory `_tasks` with 15-minute TTL (`api/routes/ingest/core.py:35-39`) | its own `IngestProgressView.swift` | not found | no |
| 10 | **Project conversion on open** | geometry → page model (#5222) | daemon thread per library (`maintenance/conversion_on_open.py:32`) | its own route `/api/conversion/status` and pill (`ConversionStatusStore.swift`, `ConversionNotice.swift`) | stops at a page boundary on close | yes, carries on next open (its own resume) |
| 11 | **Search reindex** | `/api/search/reindex` | FastAPI `BackgroundTasks` (`api/routes/search/core.py:1559`); "poll /stats" | No | none | no. A **second** reindex beside task-queue `REINDEX` |
| 12 | **Model and runtime jobs** | MLX model downloads (`llm/mlx_model_store.py:197`), local catalogue installs for MLX/spaCy/Kraken/Whisper models incl. Kraken's Zenodo fetch (`llm/local_model_catalog.py:205`), MLX runtime provisioning (`llm/mlx_runtime.py:57`), legacy downloads via `BackgroundTasks` (`api/routes/ai/local_models.py:146-188`) | in-memory dicts | **No** — Settings only (`LocalInferenceStore.swift`, `LocalRuntimeModelsView.swift`) | MLX download has cancel (`tests/unit/llm/test_mlx_model_store.py::test_download_job_progress_and_cancel`) | no |

Also running on their own: **schedules** (APScheduler, SQLite, `workflows/scheduler.py:113`) and
**file-watch triggers** (`workflows/file_watcher.py:212`), which start workflow runs and keep a
second run history each (`ui/automation.md`); **migrations** with their own run/status route
(`api/routes/system/migrations.py:229,320`); **remote Slurm jobs**, described but not built
(`workflows/remote_jobs.py`, `compute/jobs-and-fine-tuning.md`); and **library sharing sync**,
whose engine side is pure building blocks plus manifest/object routes, driven from the client
(`workflows/library_sync.py:1-12`; INFERRED: no engine job). Exports and snapshots run inside
their request (INFERRED from the routes; no job found).

On the app side the same split repeats: `ActivityStore` (runs + a 5-second poll of
`/api/activity/jobs` into `backgroundJobs`, `Models/ActivityStore.swift:76-146`), the Activity
window (`Views/Activity/Window/ActivityMonitorWindow.swift`, a **List of workflow runs only**
across every open library; background jobs are not in it), the Activity sidebar mode
(`ActivityViewHelpers.swift:205-209`, which does show jobs), the toolbar popover
(`ActivityStatusToolbarItem.swift`), `BackendWorkPill`, `IngestProgressView`, `ConversionNotice`,
`BatchStore`, the workflow output log, and Settings' download bars. **No global pause exists**
anywhere (searched engine and app).

### Are Kraken and MLX jobs invisible? Partly.

- **Kraken and MLX *inference* is visible**, because it only ever runs inside a workflow tool
  (`workflows/tools/detect_regions.py`, `economy_htr.py`, `vision_base.py`), and a workflow run is a
  row. `/api/activity/jobs` even names "Kraken Detect Regions / HTR" in its docstring, and a run
  that failed on Kraken shows its reason (`test_activity_jobs.py::test_a_failed_workflow_run_shows_with_its_reason`).
  What is invisible is the inside: the row says "Detect Regions 40%", not which page, and Kraken
  calls queue silently behind one process-wide lock (`llm/kraken_runtime.py:499-556`), so a run
  waiting on another run's Kraken page looks stuck.
- **MLX and Kraken *model* work is invisible in Activity**: model downloads, the Zenodo fetch of a
  Kraken recognition model, and MLX runtime provisioning are in-memory jobs shown only in Settings
  (system 12). A multi-gigabyte download started by a workflow's first use does not appear.
- **Kraken never runs by itself at import**, although the 2026-09-04 ruling says segmentation
  should run automatically at import. No importer calls Kraken (searched `importers/`, ingest
  routes, `db/manager.py`). So the honest answer to "where is my Kraken job" is often: there is
  none, because nothing started one.
- **The NLP draft (spaCy) is invisible even when it runs**: its stage is deliberately not counted
  in the queue's progress (`importers/derivatives.py:150-157`), and it is **off by default**
  pending a Settings row and review (`importers/nlp_draft.py:53-61`, `_DEFAULT_ENABLED = False`).

### The defect: correcting a page's text does not update its entities and claims (confirmed)

What happens today when a person corrects a reading (VERIFIED):

1. Every action passes through `ActionRegistry.invoke`, which calls
   `page_text_cache.refresh_in_transaction` (`actions/registry.py:261-307`). For reading,
   working-pass, membership and order actions it re-derives `Document.page_content` in the same
   transaction (`actions/page_text_cache.py:310-342`), re-anchors text **highlights** to the new
   text (`actions/highlight_reanchor.py`), and after commit **re-embeds** the page on a background
   thread (`embed_after_commit`, `:345-378`). That is all.
2. **Nothing touches entities or claims.** There is no hook from the cache writer to extraction, no
   stale flag on any knowledge row (searched `models/knowledge.py`, `knowledge/`, `workflows/`),
   and no job is queued.
3. The only automatic extractor, the NLP draft stage, **refuses to re-run** on a page it has seen:
   "Skips a document already marked `nlp_processed_at` (re-run on corrected text is a deliberate v1
   non-goal…)" (`importers/derivatives.py:811-826`). It is also off by default and runs only from
   import or the open-time resume.
4. LLM extraction runs only when a person starts a workflow.
5. A claim cannot even tell it is out of date: `KnowledgeClaim` stores `source_document_id`,
   `source_char_start/_end` and `source_excerpt` (`models/knowledge.py:1719-1745`) but **no
   version or fingerprint of the text it was read from**. After a correction its offsets point at
   other words. Highlights are re-found by their quote; claims are not.
6. INFERRED: if extraction were simply re-run, the writer upserts by identity
   (`importers/nlp_draft.py:20-27`), so new claims would be added beside the claims read from
   the misread text, which nothing withdraws.
7. The direct `page_content` edit is a second writer that re-embeds inline on the request and
   triggers nothing else (`documents.py` ~2334-2343).

So the cause is structural, not one missing call: derived knowledge does not record what it was
derived from, so there is nothing for a change to invalidate, and there is no queue to put the
recompute on. `source.derived.recomputable` (#4925, [OK]) solved exactly this for pictures, search
entries, vectors and word analysis; entities, claims and NLP drafts were never brought under it.

### Throttling today

Background QoS is set by the derivative pool (`importers/derivatives.py:65-79`) and project
conversion (`maintenance/project_conversion.py`); Kraken runs at *utility* QoS with torch threads
capped (`llm/kraken_runtime.py:528-541`); embeds are gated by `embed_concurrency()`. **Not
throttled**: workflow runs, including unattended scheduled ones (`ui/automation.md`,
`automation.unattended-throttle`, #4740), task-queue tasks, and the correction re-embed thread
(which also bypasses the embed gate by calling `db.embed` directly, `page_text_cache.py:372`).
Nothing reacts to battery, thermal state or the person being active.

## The design (proposed)

### 1. One job model, in the engine

A **job** is one row in a `jobs` table in the project database (and, for work that belongs to the
Mac rather than a project, such as model downloads and runtime provisioning, the same table in the
engine's global library). Fields, in plain terms:

| Field | Meaning |
|---|---|
| `id`, `parent_id` | a job may have children: run → step → page (→ line, only when useful) |
| `kind` | from one registry: `import`, `thumbnail`, `embed`, `nlp-draft`, `find-lines` (Kraken), `read` (vision model: MLX, cloud, Apple), `extract` (entities and claims), `workflow`, `workflow-step`, `convert`, `reindex`, `repair`, `download-model`, `provision-runtime`, `export`, `snapshot`, `sync`, `remote` |
| `subject` | what it works on: project, folder, document, page, segment or pass ids |
| `inputs_fingerprint` | a hash of exactly what it reads (the page text's hash, the pass version, the model and prompt): the idempotency key together with `kind` and `subject` |
| `state` | `waiting` · `running` · `paused` · `done` · `failed` · `cancelled` · `skipped` (inputs unchanged) |
| `waiting_reason` | plain words: "Paused by you", "Waiting for power", "Waiting for Kraken (another page is using it)", "Waiting for the network", "Waiting for model download" |
| `lane`, `priority` | which resource it needs (below) and whether a person is waiting on it |
| `progress` | current, total, and **what it is working on now** ("page 212 of 400: f. 103r") |
| `working_on` | for a run, its current step; for a step, its current page and tool; for a page, the model it is calling or the lane it waits for |
| measures | time to run, cost, greenhouse gas (with its basis), images run, steps run; each rolled up the tree |
| `started_at`, `finished_at`, `elapsed`, `estimate` | time, and time remaining once there is a rate |
| `cost` | tokens and money from the vendored price list (`llm/model_types.py`), summed up the tree |
| `error` | the reason in words, and on which child |
| `started_by` | a person, the project's recipe ("automatic"), a schedule, a trigger, an assistant session |
| `run_id` | the one stamp from `safety/run-take-back.md` (`safety.run.one-stamp`, #5245): a job's outputs carry it, so a job can be taken back |
| `lease_owner`, `lease_until`, `attempts` | durability (below) |

**Iterate, do not replace.** The task queue (`workflows/tasks.py`, `background_tasks` table) is
already a persistent queue that resumes pending work; it grows into `jobs`. The derivative pool
keeps its bounded executor but takes its work from `jobs` rows instead of from
`Status.pending`. Workflow runs keep LangGraph for what happens inside a run; the run, its steps
and their pages are jobs, written by the progress callback that already exists for cancellation
(`builder.py`'s shared per-item callback). The legacy chain executor (system 3) is retired, as
`source.chain.is-a-workflow` (#4949) already proposes. Every other system above becomes a
producer that enqueues and reports through the one API; their private dicts, TTL maps and
status routes go.

The engine owns all of it (four architecture rules: logic in the engine). One route family,
`/api/jobs` (a tree, paged, filtered and sorted by the engine), one change event `job.updated`
naming the job ids that changed, one app store `JobsStore` that patches rows in place.

### 2. One window: the Activity table

The Activity window (`ActivityMonitorWindow.swift`) becomes a SwiftUI `Table` with disclosure rows:

- **Main columns, the measures** (ruled 2026-10-04): Time to run · Cost · Greenhouse gas · Images
  run · Steps run, each rolled up the tree. **Then:** Name · Project · State (with its lane and
  the waiting reason) · Working on · Started (an absolute time) · Started by · Errors. Columns can be
  hidden and sorted, like Activity Monitor; sorting and filtering are engine work (#5415).
- **Rows** are every job of every kind in every open project and the Mac's own work, live first,
  then recent, grouped by project when the person asks, the Mac's work as its own group. A row
  expands, with a disclosure triangle, into its children along the path its graph took
  (`activity.jobs-follow-the-graph`): a run into its steps (branches taken, branches skipped,
  sub-workflows), a step into its pages and remote jobs; a page's failed line shows its error.
- **Filters:** Now · Waiting · Failed · Done today · All; a search field.
- **Toolbar:** *Pause Background Work* / *Resume*; per-selection Pause, Resume, Cancel, Retry
  Failed, Show What It Made (opens the take-back list, `safety/run-take-back.md`), Delete from
  history.
- **Selecting a row** shows its detail: one view for a run, a step, a page or a job, read from the
  row's own job record, with its log under it ("The details view (#5561)" below). The five tabs
  of the old `ActivityDetailView` are gone (#5561).
- The **toolbar status island** stays as the summary ("Reading 212 of 400 · 3 waiting"), reading
  the same store. Its **popover is a summary, not a list** (ruled 2026-10-04): what is running, what
  is waiting and the main reason, the last three errors, and the Mac's state (memory pressure,
  heat, battery, in use), read from the engine (`activity.popover.summary`). The separate lists — `ActivityJobRow` in the sidebar mode, `IngestProgressView`,
  `ConversionNotice`, Settings' download bars, `BackendWorkPill` — become views of the same rows or
  are retired. Whether the `.activity` sidebar mode survives at all is an open question.

### 3. Pause and start: global and per job

- **Global:** one switch, *Pause Background Work* (Activity toolbar, the Fichero menu and the
  status island's menu). While paused, nothing that started by itself runs: recipe work, schedules,
  triggers, re-processing, downloads queued by automation. Running jobs stop at their next item
  boundary and say "Paused by you". The switch is stored in app settings and **survives relaunch**:
  a Mac that was paused at quit is paused at launch, and says so in the island.
- **Per job:** Pause, Resume, Cancel on any row, applying to its children. Cancel stops at the next
  item; a long single call (a 60-second vision request) is cancelled, not waited for (the open half
  of `workflows.run.controls-are-fire-and-forget`, #4402). Controls are actions in the audited
  action layer, so they are reachable from the window, MCP and the command line alike.
- **Work a person starts by hand while globally paused** runs, and the row says "Running although
  background work is paused". A run started by hand waits only for memory and heat, never for
  battery or for the person being at the Mac, and its row says which (ruled 2026-10-04,
  `activity.throttle.hand-started-waits-for-memory-and-heat`).
- **One start and stop:** every kind is started, paused, resumed, cancelled and retried through the
  job routes and actions; a kind's own routes call them or are retired (`activity.pause.one-start-stop`).

### 4. Never in the way: lanes and throttling

Jobs run in a few **lanes**, each with its own concurrency, chosen by the job kind's declared
resource:

| Lane | Kinds | Concurrency | Why |
|---|---|---|---|
| local ML | Kraken, MLX, spaCy, embeddings, Apple Vision | 1 heavy at a time (the existing Kraken lock and embed gate become this lane) | memory: a second model doubles it (#4987) |
| images | thumbnails, renditions, conversion | 2 (`MAX_CONCURRENT_DERIVATIVES`, the #1400 hazard) | window-server stability |
| network | cloud model calls, downloads, sync | a few, per provider rate limit | the limit is the provider's, not the CPU's |
| database | reindex, repair, metrics | 1 | one writer |

**Load once, use fully, one heavy model at a time** (ruled 2026-10-01). Reloading a model for
every page is waste: today Kraken reloads its segmenter and reader on each page, Whisper starts a
process per file, the Apple bridge a process per call (#5370). And running two heavy models at
once (MLX and Kraken together) is worse: on a Mac's shared memory they fight, swap, and each runs
slower than alone. So the local ML lane schedules **by model**, not by job:

- A heavy model is **loaded once and kept resident** while there is work for it, and fed in batches
  (many pages per call, many lines per call where the model takes lines).
- The lane **groups waiting work by the model it needs**: it runs all the Kraken pages that are
  ready, then switches to the MLX reader for all the lines that are ready, rather than alternating
  page by page. A switch unloads the old model first.
- **Two heavy models run together only when both fit** in this Mac's memory with room to spare
  (measured resident sizes from the model cards, `source.model.runs-here`). On an 8 GB Mac that is
  never; on a large Mac a small Kraken and a small reader can overlap, which is when pipelining
  pages between stages pays.
- A model nobody needs is unloaded after a short idle time, so the Mac gets its memory back.
- **Watch the processors, not only memory** (2026-10-01). The engine measures what each job uses
  (CPU cores, GPU, the Neural Engine, memory) and shows it in the job's row. The lane uses it to be
  efficient: two steps that compete for the **same** processor wait for each other, but a step that
  is CPU-bound (Kraken's line post-processing, measured at about 10 s a page on one core) can run
  beside one that is GPU-bound (an MLX reader) when memory allows, so neither sits idle. Busy CPU
  work is spread over the performance cores up to the lane's limit rather than left on one thread.

Priorities: a job a person is **watching** (they pressed Run, they opened the page being read) goes
to the front of its lane. The light lanes (images, database) run at background QoS on the
efficiency cores (`core/background_compute.py`). The **local ML lane does not**: Kraken measured
23 s a page at utility QoS and 426 s at background (#4959, `llm/kraken_runtime.py:527-530`), so
background QoS would turn an hour's job into a day. Heavy work runs at utility QoS with its
concurrency bounded by the lane, and yields to the person by holding the lane back, not by moving
to the efficiency cores (corrected 2026-10-01; see "Workflow runs inside the one job model").
The dispatcher **slows or waits** on the conditions Spotlight and Photos honour, and says which in
`waiting_reason`: Low Power Mode or on battery below a threshold, thermal state serious or
critical, memory pressure (the existing Kraken guard generalised), and — for the heaviest lane —
the person actively using the Mac. No setting is added for any of this (dead-simple UX).

### 5. Durable: nothing lost, nothing done twice

- **The queue is rows.** Enqueueing writes a row in the same transaction as the change that caused
  it (the transactional-outbox pattern), so a crash can never lose the "remember to re-extract"
  that a correction implies.
- **Claim with a lease.** A worker claims a `waiting` row, sets `lease_until`, and renews it while it
  works. On launch, a `running` row whose lease has lapsed goes back to `waiting` with `attempts+1`
  — never to `failed`. After three attempts on the same item, that item fails with its reason and
  the parent carries on (a poison page does not stop a 400-page run).
- **`paused` survives relaunch as `paused`.** This replaces `recover_stale_runs` flipping paused and
  running runs to `failed` (`workflows/activity.py:658`). A workflow run resumes from its DuckDB
  LangGraph checkpoint; the documents it held at `processing` stay with it rather than being
  settled as dead.
- **Exactly-once effect.** A child job writes its output and marks itself `done` in one
  transaction, so a crash between the two cannot happen. A job whose `(kind, subject,
  inputs_fingerprint)` already has a `done` row is `skipped`, not re-run: re-adding the same file,
  or reopening a project mid-import, does nothing twice. This makes today's "each stage happens to
  be idempotent" (`db/manager.py:222-228`) a property of the system.
- **Sleep and quit.** On quit the engine stops dispatching, lets running items reach their
  boundary for a few seconds, and exits; anything unfinished is simply `waiting` next time.

### 6. Automatic: added things are processed, changed things are re-processed

**Derived data names its inputs.** Every derived row — embedding, NLP draft, entity mention, claim,
extracted date, thumbnail, line geometry from Kraken, a reading from a vision model — records what
it was derived from: the input's kind and id, and the `inputs_fingerprint` it saw (for a claim: the
page, the text's hash and derivation version, the span; for an embedding: the text's hash; for a
reading: the image rendition and the model). This extends `source.derived.recomputable` (#4925)
from pictures, search entries, vectors and word analysis to the knowledge layer. Claims already
carry most of it (`source_document_id`, offsets, excerpt); what is missing is the text fingerprint
and the run that made it.

**Each job kind declares what it consumes and produces** in the engine's registry (the typed
"jobs" of `source/models-chains-and-projects.md`: `extract` consumes `page.text`, produces
`entity-mention`, `claim`; `embed` consumes `page.text`; `find-lines` consumes `page.image`,
produces `segments`; `read` consumes `segments` + `image`, produces `readings` → `page.text`). That
declaration *is* the dependency graph; nobody writes it twice.

**A change invalidates exactly its dependents.** The hook already exists: `ActionRegistry.invoke`
calls the page-text cache writer for every action. It grows into one invalidation step: when an
action changes an input, look up the rows derived from it whose fingerprint no longer matches,
mark them `stale` (with the reason, "page text changed on 1 Oct"), and enqueue one recompute job
per (kind, subject). Coalescing: a scholar correcting line after line produces one `extract` job
for the page, enqueued after a short quiet period (the debounce `embed_after_commit` already does
for embeddings, made durable). Chained effects follow naturally: a new Kraken pass → new readings
→ new page text → re-embed and re-extract.

**People's work is never overwritten.** When the recompute finishes:

- machine-made rows from the old text that a person never touched are **withdrawn** (kept in the
  record, findable, reversible — never hard-deleted) and replaced by the new ones;
- a row a person curated, confirmed or edited is **kept** and flagged "the text under this changed"
  with old and new excerpt, for the person to decide (`curation_guard`'s conflict tracking is the
  existing mechanism);
- the swap is one recorded step with the job's `run_id`, so it can be taken back like any run.

**What runs on add.** The project's recipe names the job kinds that run automatically when a
source is added (for example: thumbnail, embed, find-lines with Kraken, read with the project's
model, NLP draft, extract). What runs on *change* is not listed by hand: whatever kinds are on for
the project are kept current through the dependency graph. A kind that is off is never run
automatically, and its stale rows simply stay marked stale.

### 7. Recipes tie in

A recipe (`source.recipe.is-a-file`, #4950) already names a project's chain. It gains one short
section, `automatic`, listing which job kinds run on add (and so are kept current on change), with
whether each may use the cloud. The onboarding review in progress generates the recipe; the first
automatic run asks once and waits (`source.project.automatic-after-first-yes`, #4951); after that
the global pause is the only switch a person needs. The workflow bar and Run menu keep running any
workflow by hand: a hand run is a job like any other.

## Behaviors

### A. One job model

- `activity.one-job-model` — **[PARTIAL]** (#5353) every kind of background work, in every
  project and the app, is a row in one `jobs` table with the same fields, read through one route
  family and one change event. Built (2026-10-03, 2026-10-04): the `jobs` table in each project
  database and one engine-wide scheduler (`execution/jobs.py`); its rows are listed by
  `/api/activity/jobs` and a job and everything under it by `/api/activity/jobs/{id}`. The kinds on
  it: the correction re-embed, import stages (thumbnail, embed, NLP draft), Kraken pages, pages and
  text calls of local and cloud models, the task kinds, synced-folder writes and reads, training
  here and on Hugging Face, reading at scale, workflow runs with their steps, and batches (see
  `activity.every-worker-is-a-row` for which workers are rows and which are not). Still a gap: the
  Mac's own table for global work (`activity.global-work-is-the-macs`), the workers not yet on it,
  and one change event `job.updated`.
- `activity.jobs-are-a-tree` — **[PARTIAL]** (#5353) a job's children (steps, pages) are jobs;
  progress, time, cost and errors roll up the tree. Built (2026-10-04): a workflow run is a job row
  (its id is its thread id), each step a child, each page a step hands to a lane a grandchild;
  `GET /api/activity/jobs/{id}` returns the tree with pages done and in all rolled up; Pause and
  Stop on the run's row reach the run and its waiting pages (`fichero-server/tests/unit/jobs/test_runs_are_jobs.py`). The rows follow the
  run's own record (spec step 3, read-only). Built (2026-10-04): a text model's calls in a run
  (entity and claim extraction, summaries, every tool that calls `llm.chat` or its structured
  forms) are rows under their step, kind `ask-a-model` (`fichero-server/tests/unit/jobs/test_text_calls_on_the_lane.py`). Built (2026-10-04): time,
  cost and errors roll up: each row has its `seconds`, the pages under it that `failed` (each with
  its reason), its `tokens`, and its `cost_usd` from the vendored price list, null unless every
  call under it is priced (`fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`). Chat's model calls are rows too, outside any run
  (`fichero-server/tests/unit/jobs/test_chat_on_the_lane.py`). A batch is a job whose children are its runs (`fichero-server/tests/unit/jobs/test_batches_are_jobs.py`).
- `activity.lane.embed-after-reading` — **[OK]** (owner, 2026-10-19 16:27) Embed for search and the NLP name draft work on the text,
  so they come after the reading: a background one on the embed lane waits ("Waiting for reading to finish") while
  any Find Lines, Read or model-reading page of the library is queued or running, whatever was queued first, and
  it never takes the reading lane. A person's own (a correction's re-embed) does not wait
  (`fichero-server/tests/unit/jobs/test_embed_after_reading.py`).
- `activity.stop.page-skips-run-stops-children` — **[OK]** (owner, 2026-10-19 16:27) Stop on one page
  skips that page: its row ends `cancelled`, "Stopped by you" (not failed), and its run carries on with the
  next page. Stop on a run stops everything under it: its steps, sub-runs and every waiting or paused page end
  `cancelled`, so no child row reads running or waiting while the run says Stopped. Stop on a page that is
  mid-read answers `stopping` ("Stopping: what it reads is not kept"): the model cannot be interrupted midway, so
  the page finishes its call, its result is dropped (nothing is saved), its row ends `cancelled`, and the run goes
  on to its next page; a page a lane thread is running when its RUN is stopped likewise settles its own row (`fichero-server/tests/unit/jobs/test_stop_a_page_skips_it_stop_a_run_stops_all.py`).
- `activity.recipe-run.stop-reaches-its-step` — **[OK]** (#5609) Stop on a recipe run's row
  (`POST /api/activity/jobs/{id}/cancel`) stops the run: a waiting one ends `cancelled` at once; a running one
  answers `stopping`, its row says "Stopping at its next step", the step it is running is stopped through that
  step's own Stop (a workflow run, its pages waiting for a lane withdrawn; a check; a Find the Documents run,
  which stops before its next folder or page and keeps what it proposed for the folders it finished; a search
  step stops waiting and leaves its pages' embed jobs, which a correction may share, to finish); a step the run
  does itself stops before its next page: the entries step (its account counts the pages it split), prepare
  (its account counts the pages it looked at), and publish (the site is not finished); export only ties a
  folder or queues its rewrites, which is over at once. The stopped step says `cancelled`, "Stopped by you"; no step after it runs (each says "not run", "the run was stopped before this step"), and the row
  ends `cancelled`, "Stopped by you; N of M steps done". A run left stopping when the engine went away (or its
  project closed) is not taken up again on the next open. The list drops it and its tree says how it ended.
  Before: the cancel answered `running` and the run went on to its next step; then a Find the Documents step and
  the entries, prepare and publish steps ran to their end before the run stopped
  (`fichero-server/tests/unit/jobs/test_cancel_recipe_run_5609.py`,
  `fichero-server/tests/unit/recipes/test_stop_reaches_inline_steps_5609.py`). **(2026-10-11)** Checked live on a
  scratch engine: Stop on a running recipe run answered `stopping`, its running step's workflow run ended
  `cancelled` and the run ended `cancelled`, "Stopped by you; 1 of 2 steps done". The row now says who stopped it:
  the person's own Stop "Stopped by you"; through the MCP server or the command line "Stopped by you, through an
  agent (MCP)" or "… the command line"; another account by its name (`jobs.note_stopper`, `jobs.stopped_by`;
  `fichero-server/tests/unit/jobs/test_a_stopped_run_says_who_stopped_it.py`).
- `activity.job-tree-to-a-depth` — **[OK]** (#5605) `GET /api/activity/jobs/{id}?depth=N` returns the job
  and N levels under it (`depth=1`: a run and its steps); each row it cuts keeps its rolled-up counts and
  says how many children it left out (`children_omitted`). Without `depth`, the whole tree. An agent reads a
  large run this way: a 214-page recipe run's whole tree was 235k characters, over an MCP answer's size
  (`fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`).
- `activity.jobs-follow-the-graph` — **[PARTIAL]** (#5353, #5415) a run's tree follows the
  path its graph took: one step for every node that ran, in order; a conditional route shows the
  branch taken and the branches skipped (as skipped, not absent); parallel branches are siblings
  under their run; a fanned-out step's pages are its children; a sub-workflow is a child run under
  the step that called it, with its own steps and pages; a remote job a step sent is under that step
  (`activity.remote-under-its-step`). Every running row says what it is **working on now**: a run,
  its current step; a step, its current page and tool; a page, the model it is calling or the lane
  it waits for. Built: run → step → page, and a sub-workflow as a child run with its steps and
  pages (`fichero-server/tests/unit/jobs/test_runs_are_jobs.py`, `fichero-server/tests/unit/jobs/test_sub_workflows_are_child_runs.py`). Still a gap: routing
  nodes are dropped, so the branch taken is not recorded (`execution/jobs.py:292,299`
  `_ROUTING_NODES`); skipped branches are not shown; `working_on` is not a field of any row.
- `activity.every-worker-is-a-row` — **[PARTIAL]** (#5359) every worker the engine runs is a row
  with its state, lane and why it waits. Rows today: Kraken pages (`find-lines`, `read-a-line`),
  pages and text calls of models served on this Mac and of cloud models (`read-a-page`,
  `ask-a-model`, chat's calls included), embeddings (`embed`, `make-a-vector`, the reindex task),
  the NLP draft at import (`nlp-draft`), the task kinds, synced-folder writes and reads, training here
  and on Hugging Face (`train-on-this-mac`, `train-a-model`), reading at scale (`read-at-scale`),
  gathering reasons, converting a model, workflow runs, steps and batches, downloads of spaCy,
  Whisper and embeddings models (`download-model`; Whisper and embeddings since 2026-10-08, they ran on
  FastAPI `BackgroundTasks`, `fichero-server/tests/unit/api/test_routes_local_models.py`) and the
  link-predictor retrain after review decisions (`retrain-link-predictor`, 2026-10-08,
  `fichero-server/tests/unit/kg/test_review_queue.py`). **Not yet rows:** the
  built-in Apple calls (Vision, Foundation Models: `llm.model_call_slot` takes no slot for a
  built-in provider), spaCy, Whisper and other non-model tools inside a workflow (only their step
  is a row), ACENET jobs (not sent:
  `remote_read/slurm.py` describes them), MLX model downloads and the Kraken model fetch (in-memory
  jobs of the Mac's model stores, `llm/mlx_model_store.py`, `llm/local_model_catalog.py`), runtime
  provisioning (`llm/mlx_runtime.py`) and model loads (`activity.global-work-is-the-macs`), conversion
  on open (`maintenance/conversion_on_open.py`, a thread), ingest progress (`api/routes/ingest/core.py`,
  `BackgroundTasks`), legacy chains (`api/routes/workflow/chains.py`, → #4949), the companion thumbnail
  or display picture warmed after a picture request (`api/routes/system/storage.py`), and the inline
  re-embed of a direct text edit (`activity.auto.reembed-on-change`).
- `activity.remote-under-its-step` — **[PARTIAL]** (#5240, #5353, #5740) a remote job a run starts (a Hugging
  Face Job, a cluster job) is a child of the step that sent it, its far-side state its own row's. Built (engine):
  `ReadAtScaleRequest.parent_job_id` hangs the run under its step (`jobs.set_parent`); the Activity row (`GET
  /api/activity/jobs`, `BackgroundJob.remote`) says target, far-side state (queued / running / done / failed),
  shards done of total, pages landed, and what it offers; the Inspector's status (`GET
  /api/reading-at-scale/jobs/{id}`) lists each shard (state, tries, reason, last lines, seconds) and sets the
  estimate (pages, shards, GPU-hours from a pilot's rate) beside the actual. Not yet: the recipe step passing its
  id (the recipes lane), a "landing" state between done and landed, the Swift row and Inspector. Test:
  `fichero-server/tests/unit/api/test_remote_runs_in_activity.py`,
  `fichero-server/tests/unit/remote_read/test_read_at_scale_job.py`.
- `activity.remote.actions` — **[PARTIAL]** (#5740) Cancel (`POST /api/reading-at-scale/jobs/{id}/cancel`, cancels the
  far-side shards), Retry failed shards (`.../resend-failed`, only those) and Catch up (`.../catch-up`: a live run
  skips its next wait; a run the scheduler dropped is queued again and carries on from its recorded shards), the
  same for Hugging Face and a cluster. Not yet: the buttons (Swift). Test:
  `fichero-server/tests/unit/remote_read/test_read_at_scale_job.py`.
- `activity.jobs.failed-at` — **[OK]** (2026-10-11) every job in `GET /api/activity/jobs` (`BackgroundJob`)
  carries `failed_at`: for a failed job, when it failed (ISO 8601, UTC; a queued job's end, a workflow run's
  completion); null for any other, and null again once it is retried. So the popover's recent errors say when each
  happened rather than guess. Test: `fichero-server/tests/unit/jobs/test_failed_at_on_the_jobs_list.py`.
  **Built 2026-10-11 (app, #5666):** `ActivityJob.failedAt`; the popover's recent-errors window dates each failure
  by it (`ActivityErrorLedger.note(failed:)`), the first time the app saw it standing in only when it is null.
  Pinned by `fichero/Tests/Unit/general/Models/ActivityPopoverRunTests.swift`.
- `activity.persists-from-any-thread` — **[OK]** (2026-10-11) an Activity written from a job or timer thread
  with no event loop is kept: it is saved on that thread (`ActivityTracker._schedule_activity`,
  `ActivityStore.save_now`). Before, it was dropped with "Activity could not be persisted: no running event loop",
  as the import queue's "Processing imported pages started" and "stalled" rows were. Test:
  `fichero-server/tests/unit/workflows/test_activity_persists_from_any_thread.py`.
- `activity.global-work-is-the-macs` — **[GAP]** (#5359) downloads, installs, runtime provisioning
  and model loads belong to the Mac, not a project: they are rows in the Mac's own jobs table (the
  engine's global library), shown in the window's Global group. Today they are in-memory jobs shown
  only in Settings (system 12 above). Absorbs the request `activity.first-use-download-is-a-job`
  (`ai/local-runtimes.md`): a model fetched on first use is one of these rows, and the step that
  needs it waits on it, saying so.
- `activity.task-queue-grows-into-jobs` — **[OK]** (#5353) the task queue is already
  a persistent queue that resumes pending work (`workflows/tasks.py:153-176`); it becomes the jobs
  table rather than a thirteenth system being built beside it. Found 2026-10-03: nothing in the
  engine calls `init_task_queue`, so the task queue never starts and its routes answer 503; and its
  table lives in a file of its own, not the project's database. The `jobs` table was therefore
  started in the project database (open question 1). Built (2026-10-03): the six kinds are job
  kinds (`workflows/task_workers.py`: reindex and vector repair on the model lane as embedder
  work, metrics, repair, KG metrics and re-anchor on a one-wide database lane), and `/api/tasks`
  creates and reads job rows, so its routes work for the first time and a task is durable,
  pausable and shown in Activity (`fichero-server/tests/unit/jobs/test_tasks_on_the_lane.py`).
  The `TaskQueue` class it replaced (APScheduler, its own `background_tasks` table in a file of its
  own, never started) is deleted, with the tests that pinned it; the workers' own tests run them on
  their job host (`fichero-server/tests/unit/models/test_background_tasks.py`).
- `activity.every-kind-reports` — **[PARTIAL]** (#5359) every kind of work reports through
  `/api/activity/jobs`, not a route or list of its own. Built: everything that is a row
  (`activity.every-worker-is-a-row`) is listed there, with its state and reason
  (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`, `fichero-server/tests/unit/jobs/test_tasks_on_the_lane.py`). Still a gap: ingest
  progress, conversion on open and model downloads report elsewhere.
- `activity.kraken-mlx-inference-visible` — **[PARTIAL]** (#5359) Kraken and MLX
  inference shows as its workflow run's row, failures with their reason; which page it is on, and
  "waiting for Kraken", are not shown. Built (2026-10-03): every Kraken page a workflow reads
  (Transcribe in Kraken mode, economy HTR) is a job row (`find-lines`, `read-a-line`) naming its
  page and reader, with its state and reason (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`); a page read by a model
  served on this Mac (MLX, Ollama, LM Studio) is a `read-a-page` row named by its model
  (`fichero-server/tests/unit/jobs/test_local_model_pages_on_the_lane.py`), and under their run's step in its tree (`fichero-server/tests/unit/jobs/test_runs_are_jobs.py`).
- `activity.model-work-visible` — **[GAP]** (#5359) a model download, a Kraken
  model fetch from Zenodo and MLX runtime provisioning appear in Activity, not only in Settings.
- `activity.nlp-visible` — **[PARTIAL]** (#5359) the NLP draft stage is counted and
  shown; today it is deliberately left out of the queue's progress (`importers/derivatives.py:150-157`).
  Built (2026-10-03): each page's NLP draft is a job ("Read names (NLP draft)"), counted and
  shown in Activity with its state (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`). Still a gap: the import progress bar
  ("37 of 252 pages") still counts embeds only.
- `activity.correction-reembed-visible` — **[OK]** (#5359) the re-embed after a
  correction is a queued, visible job, not a raw daemon thread. Built (2026-10-03): kind
  `make-a-vector`, written in the correction's own transaction, shown by `/api/activity/jobs`,
  held by the pause, run by the scheduler (`fichero-server/tests/unit/jobs/test_job_queue.py`).
- `activity.one-reindex` — **[OK]** (#5363) there is one reindex: `/api/search/reindex`
  queues the task queue's `reindex` job, the same one `/api/tasks/reindex` queues, so it shows in
  Activity, obeys the pause and survives a quit, and asking twice while it waits is one job. Built
  (2026-10-08): it used to run on FastAPI `BackgroundTasks`, invisible and unresumable
  (`fichero-server/tests/unit/api/test_routes_search.py`).
- `activity.legacy-chain-retired` — **[BROKEN]** (→ #4949) `/chains/{id}/execute` runs with "no thread
  ids, no SSE, no activity records" (`chains.py:814`).

### B. The window

#### The Activity window, ruled 2026-10-19

Engine tests under `fichero-server/tests/unit/jobs/`; app tests drive the real window through the real environment
builder (not injected services) under `fichero/Tests/Unit/general/Models/`.

- `activity.window.live-block` — **[PARTIAL]** (#5851, #5839) one live block per project at the top: Recipe › Stage ›
  Workflow, a count (done, failed, left) and the folder(s), opening to the files. Supersedes the flat table of every
  job as the first thing seen (`activity.window.table` keeps the rows underneath). Engine side: `activity.live` in the jobs
  response is one `LiveBlock` per live recipe run (recipe, the stage running, its workflow, done / failed / left, folders done
  of total) and per workflow run outside a recipe (`fichero-server/tests/unit/jobs/test_activity_summary_one_source.py`).
  The window draws it above the table, in the popover's words (`ActivityLiveSection`; needs compile; `fichero/Tests/Unit/general/Models/ActivityPopoverAgreesWithWindowTests.swift`; counts use the singular for 1, and a job of a kind the summary has a line for is not also a running row). Not yet: opening it to the files (`activity.window.acts-on`).
- `activity.window.acts-on` — **[GAP]** (#5839) the live block says what it acts on with counts ("Read: 7 of 20 pages,
  folder X"), and the whole list of pages expands under it, each with its state. Supersedes the next-three-rows view in
  `activity.run.says-what-it-reads` and `activity.window.expand` for a recipe run. (Not yet written:
  `fichero/Tests/Unit/general/Models/ActivityLayoutTests.swift`.)
- `activity.window.next-in-run-order` — **[PARTIAL]** (#5839) what comes next is listed in run order; a waiting row has no
  spinner and says what it waits for (`activity.waiting-says-why`). Engine side: `GET /api/activity/jobs` ranks every row
  by its state, a live run first, then the queues beside it, then what has ended, and gives each row `group` ("live" or
  "earlier"); pinned by `fichero-server/tests/unit/api/test_activity_order_live_run_first.py`. Not yet: a run's steps in
  run order and each step's pages in reading order from the job tree, and the no-spinner row
  (`fichero/Tests/Unit/general/Models/ActivityLayoutTests.swift`).
- `activity.window.background-group` — **[PARTIAL]** (#5851) background work (thumbnails, embeddings, Run automatically) is a
  group of its own below the live blocks, one row per kind with its total. Supersedes
  `activity.window.grouped-by-project` as the way the Mac's own work is shown. Engine side: `activity.background` is one
  `BackgroundLine` per kind (state, the reason a wait gives, done, total), never a run or an ended row
  (`fichero-server/tests/unit/jobs/test_activity_summary_one_source.py`). The window draws the group under the live blocks (`ActivityLiveSection`; needs compile). Per-kind totals only; the Mac's per-project grouping toggle stays for the table.
- `activity.window.history-group` — **[PARTIAL]** (#5851) finished, stopped and interrupted runs fold into a History group;
  Clear Finished empties it (`activity.window.clear-finished`). No stale or interrupted run is in the live area or the
  popover. Engine side: every ended row, of any kind (a stopped or failed workflow, batch, recipe run, try or queue row),
  comes back with `group` = "earlier" and last, so none stays in the live area
  (`fichero-server/tests/unit/api/test_activity_order_live_run_first.py`). Swift so far (needs compile): the store splits its one read into `liveJobs` and `historyJobs` on the engine's `group` (`fichero/Tests/Unit/general/Models/ActivityHistoryGroupTests.swift`); the window lists `liveJobs` in its groups and the engine's ended job rows under a "History" heading (`ActivityMonitorWindow`, needs compile). The window's own finished, stopped and failed runs (from `store.runs`) now sit under History too, and Clear Finished clears them (needs compile). Not yet: Clear Finished does not remove the ended QUEUE rows in History (thumbnails, embeds); the engine has no clear for those but Clear Failed.
- `activity.log.persons-log` — **[PARTIAL]** (#5850) the default log is the person's: one line per page when it is done or
  failed and one per stage, one sentence per event in local time, never repeated, never nested inside another job's line.
  Supersedes `activity.details.log-filtered-newest-last` for what the log holds. Engine side: `GET /api/activity/jobs/{id}/log`
  returns only `detail` = "person" lines by default (a row's end, warnings and errors, a failed node), each sentence once
  per row (`fichero-server/tests/unit/jobs/test_person_log_levels.py`). Today this is every activity event that is not a Node start or finish, plus a row's end, deduped: the "one line per page done or failed, one per stage" is not enforced yet. The window shows each line's time in this Mac's local time (`ActivityJobLogLine.plainText`, already built).
- `activity.log.developer-level` — **[PARTIAL]** (#5850) the "Node … started" and other debug lines are a Developer level, off
  by default; the log shows the person's lines until it is switched on. Engine side: `?detail=developer` adds the debug lines
  ("Node 'x' started", "completed in", a row's start, what a row waits for now, a server's output), each line tagged
  `detail` (`fichero-server/tests/unit/jobs/test_person_log_levels.py`). The details view's log has a Developer switch (`ActivityDetailsLog`, off by default, remembered; needs compile)
  (`fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`).
- `activity.retry.page-within-run` — **[OK]** (#5853) Retry on a page retries it within its run, not as a new run
  (`activity.retry.one-row` keeps a whole failed run's Retry). Retry is for a page that failed or was stopped; a done
  page answers in words ("This page is already read") and does nothing. A run that has ended reopens for the page: the
  same run id goes back to running over all its pages with the node cache on, so only the retried page calls the model
  and the other pages keep their readings and counts; a STOPPED run, whose other pages were never read, reopens over
  the pages it read plus this one (the done pages are cache hits, the never-read ones are skipped by name, `only_doc_ids`, and are neither done nor failed nor counted by the step's
  aggregator, and the list is dropped from the snapshot before the next Retry: the
  checkpoint keeps the run's whole file list, so selecting fewer documents does not narrow it) and its checkpoint is
  never touched, since its account and its offer to read the rest are built from it. A run still going takes the page into its queue (no 409): the page row waits
  ("Retried by you; waits in its run") and the run reopens for it when its pass ends. Pinned by
  `fichero-server/tests/unit/jobs/test_retry_page_within_run.py` and, against the real graph (one model call, the run
  id and record kept, done == total), `fichero-server/tests/unit/jobs/test_retry_page_within_run_real_graph.py` (both branches), green on the M4 at `c7cc86d09` (REALGRAPH, 3-page stopped test included).
- `activity.engine.keychain-cached` — **[OK]** (owner, 2026-10-19: "Compare on These Pages" spun while `keychain.lookup_api_key` ran a
  `security` subprocess on the event loop) a key the keychain answered (found or absent) is kept 5 minutes, so a repeated lookup
  spawns no subprocess (a stale one is returned at once and re-read on a thread); a refusal is never kept; saving or deleting a key
  drops its entry, and a read begun before it never stores its old answer; at startup only the providers the person has set up (the
  app's own record, enabled and not on-device) are read, never every provider type (#4534: a Keychain dialog per unread item)
  (`fichero-server/tests/unit/core/test_keychain_and_child_counts_off_the_loop.py`).
- `activity.engine.child-counts-off-the-loop` — **[OK]** (owner, 2026-10-19) `GET /documents/{id}/children` counts each child's
  children on a worker thread, not the event loop (same test).
- `activity.engine.auth-never-hangs` — **[PARTIAL]** (owner, 2026-10-19 18:11: the engine stopped answering and was respawned; review 317:
  the dumps' holder is the `is_paused` claim thread inside `app.py` `get_setting`'s execute, with `app_db._lock` AND `_heavy_pick`
  held for 3+ minutes, one DuckDB call stuck under a Python `isinstance` (ABC) callback) the two flags every claim reads
  (`jobs.is_paused`, `is_started`) are read from the app database once, then only replaced by `set_paused` / `set_mode`; `_claim`
  warms them BEFORE it takes `_heavy_pick`, so no app-DB call happens under it. Auth's device and user lookups run on a worker
  thread (never the event loop), wait at most 5 s for the app-DB lock, and answer 503 `app_db_busy` in words, never a hang.
  A try's page in its scratch library resolves to a person through `person_waits_on` (its run row's starter, the try's job
  being in the project's database). Pinned by `fichero-server/tests/unit/jobs/test_app_db_lock_never_hangs.py`.
  [PARTIAL] until the M4 run; the stuck DuckDB call itself is not explained (see bugs-ready.md).
- `activity.engine.app-db-lock-names-its-holder` — **[PARTIAL]** (owner, 2026-10-19 18:12; `briefs/lock-holder-5d323cf97-1812.md`: a lane
  thread waited on `AppDatabase._lock` holding `_heavy_pick`, and no thread was visible inside it) every wait on the app-DB lock
  that lasts more than 5 s logs one warning per 5 s naming the thread that holds it and its stack (or that no Python thread
  holds it), and keeps waiting; the next hang names its holder. `get_setting` reads each key from the database once and then
  from memory (`set_setting` / `delete_setting`, its only writers, replace the cached value), so none of its 28 callers
  (`_use_multiuser_auth` runs on the event loop for every request) waits on the lock again
  (`fichero-server/tests/unit/jobs/test_app_db_lock_never_hangs.py`).
- `activity.throttle.person-heavy-first` — **[OK]** (owner, 2026-10-19: "Compare on These Pages" spun for ever while the
  project's thumbnails, 47-61 s each, took every heavy slot in turn) while memory is busy and only one heavy job runs at a time,
  a heavy lane's background work steps aside for a page handed in on another heavy lane whose run a PERSON started and that the
  throttle lets go now, for at most 20 s in a row (a background run's page, or a person's page that cannot start, never makes it
  yield), so that page takes the next slot (`fichero-server/tests/unit/jobs/test_person_heavy_first.py`).
- `recipes.try.says-what-it-waits-for` — **[OK]** (owner, 2026-10-19) the try's result (`GET /api/recipes/stages/{stage}/try`)
  carries `waiting_for`, in words, while its job waits or runs ("Copying the sample pages for Find Lines", "Waiting for the model
  lane: …", "Trying Read: …"), so the stage page never shows a spinner with no words (same test file). The stage page shows
  it: Set Up's Swift (r1, `briefs/r1-try-progress-2026-10-19.md`).
- `activity.popover.same-summary` — **[PARTIAL]** (#5852) the popover and the window read ONE engine summary and always
  agree (section A's one-summary rule); the popover shows the live Recipe › Stage › Workflow with "7 of 20 pages · folder
  …", one line per background kind, waits that look waiting, no stale runs, and Open Activity. Supersedes the content of
  `activity.popover.summary`. Engine side: `activity` (live blocks, background lines, the History count) is built once from the
  ordered job list and rides in the one jobs response both read
  (`fichero-server/tests/unit/jobs/test_activity_summary_one_source.py`). Swift (needs compile): the popover reads it, showing the live blocks and the background lines first
  (`fichero/Tests/Unit/general/Models/ActivityPopoverAgreesWithWindowTests.swift`). Not yet: the window reads the same
  blocks, and the old per-job popover rows are not retired.
- `activity.window.all-projects` — **[PARTIAL]** (#5354) the Activity window merges
  every open library and the global one (`ActivityMonitorWindow.swift`); unpinned.
- `activity.window.table` — **[PARTIAL]** (#5415, #5354) the window is a table of every job of
  every kind. **Built 2026-10-04:** a SwiftUI `Table` (`Views/Activity/Window/ActivityMonitorWindow.swift`)
  of every open library's runs plus each one's jobs of their own from `GET /api/activity/jobs` (a
  page under a run is not listed twice). Columns: name, state, progress, started, time, cost,
  errors, model, each sortable, and Pause or Resume and Stop on a row through the job routes
  (`activity.pause.per-job`). A run's row is updated in place: its tree is read when the row is
  first drawn and again when the change stream names its run (`ActivityStore.applyActivityEvent`),
  one key patched. Pinned by app tests through the real store and the real decoding of a run tree
  recorded from the engine's route (`fichero/Tests/Unit/general/Models/ActivityTableTests.swift`:
  `testActivityWindowTable_aChangeEventRereadsOnlyItsOwnRunsTree`,
  `testActivityWindowTable_rowsSortByAColumnAndTheirChildrenToo`,
  `testActivityWindowTable_pauseOnAStepRowSetsThatOneRowsState`,
  `testActivityWindowTable_aJobOfItsOwnIsARowAndAPageOfARunIsNot`). Not yet seen in the app: no
  test drives the real window. Still a gap: ingest progress, conversion and downloads
  (`activity.window.one-surface`), and filters.
  *Superseded by Ruled 2026-10-19 in part:* the table is no longer the first thing seen; the live block, the background group and History sit above and around it (`activity.window.live-block`, `activity.window.background-group`, `activity.window.history-group`).
- `activity.window.expand` — **[PARTIAL]** (#5415, #5354) a row expands, with a disclosure triangle,
  into its children as `activity.jobs-follow-the-graph` defines them; a failed page shows its
  reason. **Built 2026-10-04:** a run's row opens into its steps and their pages from
  `GET /api/activity/jobs/{id}`; a run the engine has no tree for keeps its row and is asked once
  (`ActivityTableTests` `testActivityWindowExpand_aRunRowOpensIntoItsStepsAndTheirPages`,
  `testActivityWindowExpand_aRunTheEngineHasNoTreeForStillHasItsRowAndIsNotAskedAgain`). Not yet
  seen in the app. Still a gap: branches skipped and remote jobs, which the tree does not carry.
  *Superseded by Ruled 2026-10-19 in part:* for a recipe run the expansion is the live block's list of pages with each page's state (`activity.window.acts-on`).
- `activity.window.working-on` — **[PARTIAL]** (#5415, #5354) a running row says what it is
  working on now (as defined in `activity.jobs-follow-the-graph`) and how long remains.
  **Built 2026-10-04:** a running row's state reads "Running: <step>" (the live run's step, or
  the tree's running node) and its progress "1 of 2, 0s left" at the pace so far
  (`ActivityTableTests` `testActivityWindowWorkingOn_aRunningRowSaysWhatItIsOnAndHowLongRemains`).
  Not yet seen in the app.
- `activity.window.cost` — **[PARTIAL]** (→ #4343, #5415) a row shows what it cost, summed up
  the tree. Built in the engine: each node of `GET /api/activity/jobs/{id}` has `cost_usd`, null
  unless every call under it is priced (`fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`).
  **Built 2026-10-04** in the window: the Cost column shows it in dollars, "Not priced" when a call
  under it has no price, and nothing when no model was called, never "$0"
  (`ActivityTableTests` `testActivityWindowMeasures_theColumnsCarryTimeCostErrorsAndModelRolledUp`).
  Not yet seen in the app.
- `activity.window.clear-finished` — **[PARTIAL]** (#5016) *Clear Finished…* in the window's toolbar,
  after one confirmation, soft-deletes every ended run (completed, failed, stopped) in every open
  project, the same delete as Delete (`deleteRuns(statuses:)`); runs still going stay. ⌘A then Delete
  already works on the table (`.onDeleteCommand`). Pinned by `ActivityClearFinishedShapeTests`. Not
  yet seen in the app. Left: the first row drawn under the title bar (needs a screen).
- `activity.jobs-added-columns` — **[OK]** (#5814) A library made by an older release reads its jobs without
  error: the columns later releases added to `jobs` (`target`, `detail`, `parent_id`, `run_after`, `watched`,
  `cleared_at`) are applied when the library opens (on the write connection, `Database._apply_added_jobs_columns`) and once per CONNECTION after that, so a connection that came back after an invalidated one, or a
  library opened afresh at the same path, is altered again. Before: once per process per path, so after a reconnect
  every poll of `GET /api/activity/jobs` failed with "column cleared_at not found" (352 times in one log). A column that cannot be added is logged once per library and statement. Only `cleared_at`, the newest, degrades: the
  list still reads (every failed job is shown, none can be marked cleared) instead of raising on every poll. The older
  columns are required: a failure that hits them all (a read-only file, a lock) would stop the job writes too, and a list
  that degraded would hide a library that cannot work.
  Test: `fichero-server/tests/unit/jobs/test_added_columns_survive_a_reconnect_5814.py`. The cause on the owner's
  library is the likeliest of the issue's suspects, not read off that file.
- `activity.window.clear-failed` — **[PARTIAL]** (#5634, ruled 2026-10-09) *Clear Failed* in the
  window's toolbar clears every failed row the window shows, in every open project and this Mac's
  own: failed workflow runs (`workflow_run.delete` with a status filter, soft-deleted as before) and
  failed jobs of their own (a recipe run, a model download, Detect Regions…), which are dismissed:
  kept in the jobs table and the record, never listed again by `GET /api/activity/jobs`, so the
  toolbar's error glyph clears too (the audited `job.clear_failed`, `POST /api/activity/jobs/clear-failed`;
  open question 8, "failed jobs stay until dismissed"). A job retried after it was dismissed is
  listed again. A run deleted while its execution is still in the app's memory does not come back on
  the next reload. The window then says what it cleared ("Cleared 2 failed runs and 3 failed jobs."),
  or that there was nothing to clear, or why it could not. Before (#5634): it deleted only workflow
  runs, so failed jobs stayed forever, a run that failed in this session came back, and a failure
  was silent. The button is enabled while any failed run or failed job is shown. Built
  (2026-10-09): engine `execution/jobs.py` `clear_failed`
  (`fichero-server/tests/unit/jobs/test_clear_failed_5634.py`); app `ActivityStore.clearFailed`
  (`ActivityTableTests` `testActivityWindowClearFailed_*`). Not yet seen in the app; the Swift is
  not compiled by the worker.
- `activity.window.started-by` — **[GAP]** (#5354) a row says who or what started
  it: a person, the recipe, a schedule, a trigger, an assistant.
- `activity.window.one-surface` — **[GAP]** (#5354) ingest progress, the conversion
  pill, Settings' download bars and the jobs list are views of the same rows or are retired; no
  surface keeps its own progress list.
- `activity.window.honest-state` — **[PARTIAL]** (→ #4346, #4384, #5431) a spinner only for a job that is
  running now. The run list's own honesty behaviours are in section I
  (`activity.spinner-reflects-process-liveness`, `activity.stale-runs-settle-across-restarts`).
  A failed load says what failed and clears itself. The refusal that used to stick was a 401
  `bootstrap_mismatch`: the app's first requests after an engine respawn still carry the previous
  token (#5431). The footer names the cause (the engine refused the app's credentials, or could not
  be reached) rather than only a library. A later successful load clears it, and it is retried on
  reconnect. **Built 2026-10-04** for the failed load: `ActivityService.listWorkflowRuns` throws a
  401/403 as a typed `AccessError`; `ActivityStore.runLoadFailureMessage` names the cause, keyed by
  library, so the next good load clears that library's line; the window's reload key carries each
  store's `refreshToken`, which the change stream's reconnect resync bumps
  (`Views/Activity/Window/ActivityMonitorWindow.swift`). Pinned by app tests
  (`fichero/Tests/Unit/general/Models/ActivityStoreRunsTests.swift`
  `testActivityWindowHonestState_aFailedLoadNamesItsCauseAndClearsOnTheNextSuccess`;
  `fichero/Tests/Unit/general/Models/ActivityWindowTimesAndStateTests.swift`
  `ActivityWindowHonestStateTests`) and by the engine test that the respawned engine's 401 names its
  branch (`fichero-server/tests/unit/security/test_auth_refusals_say_why.py`). Still to check: the
  spinner half (#4346, #4384).
- `activity.no-project-label-for-the-always-there-project` — **[PARTIAL]** (#5655) *Built 2026-10-10
  (app), not yet seen:* the always-there project has no name, so a run or job in it carries no
  project label: the sidebar's Activity row draws no project line, the details' subheading leaves the
  project out, and a failed load reads "Couldn't load activity: <cause>", never "from : …"
  (`ActivityRun.projectLabel`, `ActivityStore.projectName`, `ActivityStore.runLoadFailureMessage`;
  the Activity window's rows already drew no empty project, and its group reads This Mac). Pinned by
  `fichero/Tests/Unit/general/Models/ActivityWindowTimesAndStateTests.swift`
  (`noProjectLabelForTheUnnamedProject`, `refusedLoadForTheUnnamedProjectNamesNoProject`).
  *Not pinned: the drawn rows.*
- `activity.window.refusal-names-its-cause` — **[OK]** (#5469) a refused project says why, from
  the engine's typed error body, not a guess: a 403 coded `library_outside_allowed_locations` (the
  roots check) reads "the engine isn't allowed to open the project from where it's saved"; another
  coded refusal reads as the engine wrote it; a 401, or a 403 with no code, reads "the engine refused
  the app's credentials". The jobs poll (`GET /api/activity/jobs`) and the run list feed the same
  footer: `ActivityService.getBackgroundJobs` throws a refusal as a typed `AccessError` like
  `listWorkflowRuns`, and `ActivityStore` keeps one line per library and read (the same cause says
  it once), cleared by that read's next good load. A jobs poll that fails for any other reason (an
  engine restarting) stays quiet and recovers on the next tick. Pinned by
  `fichero/Tests/Unit/general/Models/ActivityStoreRunsTests.swift`
  (`testRunListRootsRefusalSaysTheProjectsLocation`, `testRunListCredentialsRefusalSaysCredentials`,
  `testJobsPollRefusalReachesTheFooterAndClearsOnTheNextGoodPoll`).
- `activity.window.what-it-made` — **[GAP]** (→ #5245) a finished job opens the list of what it made
  and can be taken back (`safety/run-take-back.md`).
- `activity.document.what-has-been-run` — **[PARTIAL]** (#5434) the reverse of
  `activity.window.what-it-made`: each document has a history of every step that has touched it
  (split, lines, read, names, statements, check). Each entry gives the model, the provider, the
  time (`activity.window.absolute-times`), the cost (null unless priced) and the outcome, as
  recorded when the step ran. One engine read serves two views:
  - the library table's **Done** column, one badge per step that has run with its outcome;
  - the document Inspector's "What has been run" section, newest first.
  The read is batched for the visible rows, never one call per row. It is built from job rows and
  run records, and nothing is stored only for display. Built (2026-10-08): the engine read,
  `GET /api/documents/run-history?ids=…` — for many documents in one call, each document's job rows
  (those named after it in `subject`: its pictures, embeddings, names, line finding and page reads,
  with the model the row recorded, the state, the reason and the job it ran under) and the workflow runs
  recorded on it (model and provider as recorded), newest first, with an absolute UTC time and cost
  null; a document the caller may not read is withheld and counted
  (`fichero-server/tests/unit/api/test_document_run_history.py`). No schema change: the join is on
  `subject`. Built (2026-10-08, app): the document Inspector's Source › Info shows "What has been run",
  newest first, each entry's name, outcome, model and provider, absolute time, reason and cost when
  priced, read through the project's `RunHistoryStore` in one call for many documents, each document's
  key set on its own (`fichero/Tests/Unit/general/Models/RunHistoryStoreTests.swift`; not yet seen in
  the app). Still a gap: the Done column (the library table has no batched per-visible-row read to
  mirror, so it is more than a column), cost for priced runs,
  the provider of a job row (only its model is recorded), and job rows whose subject is not a document
  id (a page read from a file with no document names the file).
- `activity.window.measures` — **[PARTIAL]** (#5415) the measures that matter, per run, step and
  page, rolled up the tree, are the table's main columns: **time to run, cost, greenhouse gas, images
  run and steps run**. Built in the engine: each node of `GET /api/activity/jobs/{id}` has `seconds`,
  `cost_usd` (null unless every call under it is priced), `tokens`, `failed`, and pages done and in
  all (`fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`). **Built 2026-10-04** in the
  window: time, cost, errors, progress (pages done of all) and model are the table's columns, read
  from each node of the tree, a run's model being the models its pages used (`ActivityTableTests`
  `testActivityWindowMeasures_theColumnsCarryTimeCostErrorsAndModelRolledUp`). Not yet seen in the
  app. Still a gap: greenhouse gas (`activity.ghg.estimate-with-its-basis`), and images run and
  steps run as counted measures of their own.
- `activity.ghg.estimate-with-its-basis` — **[PARTIAL]** (#5420) Built: the arithmetic and the roll-up (`execution/ghg.py`, pinned by `fichero-server/tests/unit/jobs/test_ghg_estimate_with_its_basis_5420.py`): power x time x grid intensity, a missing figure is unknown never 0, a roll-up sums the known parts and takes the weakest basis. Still a gap: nothing reads the Mac's power draw, a target's rated hardware or a grid-intensity table into it, and no job row or window shows it. each run, step and page carries its
  greenhouse gas, rolled up the tree: an estimate from the energy it used times the grid intensity
  where that energy was drawn. Energy on this Mac is its power draw over the job's time; on a remote
  target, the target's stated hardware over the job's time. The figure always says its basis
  (measured, estimate or unknown) and is never invented: the same rule as cost and as
  `source.onboard.routes-for-the-volume`. A cloud call whose provider publishes no figure is unknown.
- `activity.window.absolute-times` — **[PARTIAL]** (#5415, #5432) times are absolute everywhere
  (started at a clock time, finished at a clock time, elapsed and remaining as durations); no "just
  now". Every row used to say "just now", even for a run a day old: the engine sends `started_at`
  as aware UTC with microseconds (the store's row mapper attaches the zone, #4347), the app read it
  with a default `ISO8601DateFormatter`, which refuses fractional seconds, and put `Date()` in its
  place; the rows then built relative words by hand.
  The rule: every timestamp the engine returns is UTC with its zone. The app parses it with the
  one engine-date parser. A time that cannot be parsed is shown as no time, never as now.
  **Built 2026-10-04:** `ActivityStore` reads `started_at` with `parseEngineDate` and logs a time it
  cannot read; `ActivityRun.timestamp` and `SelectedActivityRun.timestamp` are optional; the rows
  write the start through `ActivityTimeText.absolute` ("14:32", "Yesterday 09:10", "28 Sep 11:15",
  "Time unknown"), and a live row adds its elapsed time as a timer. Pinned by:
  - an engine contract test
    (`fichero-server/tests/unit/api/test_activity_window_absolute_times.py`
    `test_activity_window_absolute_times__every_run_time_carries_its_zone`): `started_at` and
    `completed_at` from `GET /api/workflow-execution/runs` and `GET .../threads/{id}/run` parse
    with a UTC zone. `GET /api/activity/jobs` carries no time fields today;
  - app tests (`fichero/Tests/Unit/general/Models/ActivityWindowTimesAndStateTests.swift`
    `ActivityWindowAbsoluteTimesTests`): an engine string of today's shape, an hour old, renders
    as its clock time; and `ActivityStoreRunsTests`
    `testActivityWindowAbsoluteTimes_theEngineTimeShapeIsReadNotReplacedByNow`.
  The table (2026-10-04) shows each row's time to run (a live run's as a timer) and a running
  row's remaining time (`activity.window.working-on`). Still a gap: a finish time, which
  `GET /api/activity/jobs/{id}` does not carry.
- `activity.window.grouped-by-project` — **[PARTIAL]** (#5415) the window can group its rows by
  project; the Mac's own work (`activity.global-work-is-the-macs`) is a group of its own.
  **Built 2026-10-04:** a *Group by Project* toolbar switch (kept across launches) puts each open
  library's rows in a section of its own, the global library's titled "This Mac"
  (`ActivityTableTests` `testActivityWindowGroupedByProject_eachLibraryIsAGroupAndTheGlobalOneIsTheMacs`).
  Not yet seen in the app.
  *Superseded by Ruled 2026-10-19 in part:* the Mac's own and background work is the background group, not "This Mac" (`activity.window.background-group`).
- `activity.window.row-shows-lane-state-reason` — **[PARTIAL]** (#5415) every row shows its state,
  its lane and, while it waits, why. Built: rows carry `state` and `reason`, and waiting rows say
  why ("Paused by you", "Waiting for Kraken", "Waiting: memory is tight", "Waiting: you're using
  the Mac"). **Built 2026-10-04** in the window: the State column gives a failed row its reason and
  a waiting row what it waits for (`ActivityTableTests`
  `testActivityWindowRowShowsReason_aFailedRowSaysWhy`,
  `testActivityWindowRowShowsReason_aWaitingJobSaysWhatItWaitsFor`). Not yet seen in the app.
  Still a gap: no row carries its lane (neither the `jobs` table nor `JobTree` nor `BackgroundJob`
  has it, `api/routes/system/activity.py:127-146`).
- `activity.run.says-what-it-reads` — **[PARTIAL]** (#5685) while a recipe run's step reads its pages, the run's
  line names the step by what it does and who does it, and counts its pages, never its step ids or folders:
  "Reading the lines with Kraken: 56 of 87 pages, about 12 min left" (the step's own account's pages and time
  left, the words of Find Regions' line, #5689). A page waiting its turn behind the run's own pages is not
  something the run waits for: the run says nothing of a lane only its own pages hold ("Waiting for the model
  lane: Transcribe (Kraken) is reading" was the run waiting for itself). *Test:*
  `fichero-server/tests/unit/mcp/test_run_says_what_it_reads_5685.py`, through MCP on the real scheduler, caught
  mid-read.
  *Superseded by Ruled 2026-10-19 in part:* the run's line is the live block's count and folder (`activity.window.acts-on`).
- `activity.waiting-says-why` — **[PARTIAL]** (#5606) a waiting row says what it truly waits for
  now, and never has no reason: paused by you, when paused; the lane and what holds it, when the
  lane is full (#5622: it names what the row would still wait for if the person stepped away; rows
  read "you're using the Mac" while two heavy runs were plainly working); the throttle's reason only
  while the throttle gives it now ("Waiting: you're using the Mac" only while the Mac reads as in use, the
  same reading as `machine.in_use`, and never while the mode is *started*); one heavy job at a time
  while memory is busy (`activity.throttle.one-heavy-when-memory-tight`); thumbnails first ("Waiting:
  thumbnails are made first", #5585); the lane is named "Waiting for the model lane: Paleographer
  Review is reading", the holder named by the run it reads for, else by its kind; a reason the job recorded
  itself; else its turn on its lane. The import's "Processing imported pages" row, while none of
  its stages runs, is `waiting` with the same reason. It counts pages, each once: a page with its own text is
  one page, and only a PDF's pages add to the count (#5690: a 92-page project counted 178, each page once when
  queued and again for its embed; `fichero-server/tests/unit/importers/test_imported_pages_counted_once_5690.py`).
  Its NLP drafts are background work at spaCy's one lock: a recipe's Names step a person started waits only for
  the page in hand, and the drafts wait while it waits (#5690: Names sat at 0 of 92 for 15 minutes with no row to
  say why, the drafts taking the unfair lock again page after page; `knowledge.spacy_ner._turn`,
  `fichero-server/tests/unit/importers/test_names_step_not_starved_by_drafts_5690.py`). Before: a throttle scan's words stayed on
  the rows after the Mac went idle (embeds said "you're using the Mac" with `in_use` false while
  a recipe's reading held the lane), and the import's row sat at 100 of 406 with reason null.
  Built: one function decides every waiting row's reason when it is read (`execution/jobs.py`
  `waiting_reason`), used by the jobs list, a run's waiting reason and the import's row. Tested
  through `GET /api/activity/jobs` with the real lanes, a lane held by a real page of a run
  (`fichero-server/tests/unit/jobs/test_waiting_says_why.py`). Not yet seen in the app. The job
  tree (`GET /api/activity/jobs/{id}`) asks the same function for each waiting row it returns
  (`activity.list-and-tree-agree`).
- `activity.list-and-tree-agree` — **[PARTIAL]** (#5606) a row has one state and one reason, whichever
  surface reads it: the jobs list (`GET /api/activity/jobs`) and the job tree
  (`GET /api/activity/jobs/{id}`) give every row the same state and reason, decided in one place
  (a waiting row's reason by `waiting_reason`, as `activity.waiting-says-why` says). A recipe run
  (`run-a-recipe`) that the engine's restart interrupted reads the same in both while it waits
  (paused, or for its lane) and after it carries on. Before: after a restart a recipe run's tree
  said "waiting — Interrupted; carries on" while the list gave the same row as running with reason
  null. Built: one function gives a row's state and reason (`execution/jobs.py` `state_and_reason`:
  a waiting row's reason from `waiting_reason`, any other row's as stored); a recipe run's both
  surfaces take it from `_recipe_state` (`api/routes/system/activity.py`: that, and while it runs,
  what its running stage waits for); the tree's other waiting rows from `state_and_reason`. Tested
  through `GET /api/activity/jobs` and the tree with the real recipes lane: a run interrupted by
  the engine's own `resume`, read while paused, as it carries on and while it runs
  (`fichero-server/tests/unit/jobs/test_activity_one_truth_5606.py`). Not yet seen in the app.
- `activity.ended-run-reads-ended` — **[OK]** (#5615) a run that has ended reads ended, in words, on every
  surface, with what it offers. Seen in the MCP review of 2026-10-08: a recipe run failed "Interrupted 3 times; set
  aside" while its Correct stage still said running and its names stage waiting; the list named it
  `run-a-recipe`; the reason gave no cause, time or next step; failed rows stood at 100 % with nothing done; a
  page's `parent_id` looked like an id glued to a label; a page's run history said
  `process_died_recovered_on_library_open`, and a completed Transcribe run recorded provider and model empty.
  Now: a recipe run that has ended leaves no stage waiting or running: each says "not run" and why (the run ended
  before it, or it was stopped when the run ended, with the run's own reason; `recipes/runner.status`). Its row in
  the list is named by its recipe, "Run the recipe: <the recipe's title>", with the pages it runs over as its
  `total` and its furthest stage's pages done as `current` (`runner.name_and_pages`); every kind is named in words
  even when nothing waits, and Retry works then too (`jobs.load_kinds`: the lanes loaded the kinds only when one
  started). A job set aside after its interruptions says what interrupted it (the engine stopped: the app quit, or
  the engine or the Mac stopped), when its last try started and when it was found stopped, and the row offers
  Resume (`offer`, done by `POST /api/activity/jobs/{id}/retry`, which carries it on from where it was;
  `jobs.set_aside_reason`, `jobs.offer_for`). A row's percent is its pages done over its pages, whatever its state:
  a failed run with nothing done is at 0. A page's `parent_id` stays its step's row id, "<run id>:<step name>"
  (every step row is written under that id, and the tree and log find steps by it), and is looked up like any job;
  each row under a run also carries `run_id`, the run's own id. A run's reason recorded on its pages is words ("The
  engine stopped while this run was going …"; an old row's code is read as those words), a page's run history
  gives each recorded run's own outcome (failed, cancelled; before, every one read done), and a run records the
  provider and model it ran with: the run's own choice (a recipe step's model) before the workflow's default
  (`execution/runner._ran_with`). Tested through the routes in
  `fichero-server/tests/unit/recipes/test_ended_run_reads_ended_5615.py`. Not yet seen in the app.
- `activity.popover.summary` — **[PARTIAL]** (#5415) the toolbar popover is a summary, not a list:
  what is running, what is waiting and the main reason why, the last three errors, and the Mac's
  state (memory pressure, heat, battery, in use), read from the engine. CPU and GPU percentages
  join it with `activity.lane.measures-processors`. **Built 2026-10-04:** the popover
  (`Views/Shell/Toolbar/ActivityStatusToolbarItem.swift`, `Views/Activity/ActivityPopoverSummary.swift`)
  says what runs now, how many wait and the main reason, the last three errors with why, whether
  heavy work is held back and why (paused by you, or the throttle's reason a waiting job gives),
  the process CPU, and has Open Activity; all from `GET /api/activity/jobs` through the store the
  window reads (`ActivityTableTests` `testActivityPopoverSummary_saysWhatRunsWhatWaitsAndWhyAndTheLastThreeErrors`,
  `testActivityPopoverSummary_pausedBackgroundWorkIsSaidFirst`,
  `testActivityPopoverSummary_nothingHeldBackWhenNothingWaitsOnTheMac`). Not yet seen in the app.
  The engine serves the Mac's own state (2026-10-04): `GET /api/activity/jobs` carries `machine`
  (memory pressure normal/warn/critical, thermal state nominal/fair/serious/critical, on battery,
  in use, and `why_wait`, the throttle's current reason heavy work is held back), read through
  the same readings the throttle acts on (`execution/throttle.py` `machine_state`;
  `tests/unit/api/test_activity_machine_state.py`). The popover shows it (2026-10-04): a "This
  Mac" block (memory pressure, heat, on battery or power, in use or not), a reading the engine
  could not take (null) left out, and `why_wait` said as why heavy work is held back ahead of a
  waiting job's reason (`ActivityStore.machine`; `ActivityTableTests`
  `testActivityPopoverSummary_saysThisMacsStateAndHidesAReadingTheEngineCouldNotTake`). Not yet
  seen in the app. Still a gap (#5415): nothing reads the GPU.
  *Superseded by Ruled 2026-10-19 in part:* what the popover shows, and that it reads the window's summary, is `activity.popover.same-summary`.
- `activity.popover.mac-state-row` — **[PARTIAL]** (#5635, ruled 2026-10-09) the popover shows this
  Mac's state as one compact row of symbols with short values, not a column of text: memory
  (`memorychip`: OK, High, Critical), heat (`thermometer.medium`: OK, Warm, Hot, Critical), power
  (`battery.50percent` "Battery" or `powerplug` "Power"), the person at the Mac (`person.fill` "In
  use" or `person` "Away") and the app's CPU (`cpu`, "2%"). Each has help text and an accessibility
  label with the full reading (for the CPU, of how many cores' worth). Only a reading that is a
  problem is tinted: memory pressure high or critical, the Mac hot or critical. A reading the engine
  could not take (null) is left out. The recent errors stay, three at most, each one line (its name
  and reason, truncated), the full name and reason in its help. Built (2026-10-09):
  `ActivityPopoverSummary.macReadings` and `ActivityMacStateRow`
  (`Views/Activity/ActivityPopoverSummary.swift`), with a #Preview; `ActivityTableTests`
  `testActivityPopoverSummary_saysThisMacsStateAndHidesAReadingTheEngineCouldNotTake`,
  `testActivityPopoverSummary_aReadingIsTintedOnlyWhenItIsAProblem`. Not yet seen in the app; the
  Swift is not compiled by the worker.

### The details view (#5561)

**What was there before #5561 (verified 2026-10-06, read-only; replaced by the one view below, the files named here are deleted).** Double-clicking a row in the Activity
table, or pressing its ⓘ button (#5560), opens the Activity Details window
(`Views/Activity/Window/ActivityDetailWindow.swift`), which mounts `ActivityDetailView`
(`Views/Activity/Detail/ActivityDetailView.swift`); the same view is mounted in the Preview pane
of the `.activity` sidebar mode (`ContentView+DetailLayout.swift:285`) and in the compact flow
(`ContentView+Navigation.swift:374`). It is a stats bar and **five sections**: Overview, Console,
Progress, Trace and Log (`ActivityChildType`, `Models/SidebarViewTypes.swift:60-83`). They read
**three different records** of the same run and show the same facts several times over:

| Section | Reads | Repeats |
|---|---|---|
| Stats bar (`ActivityDetailView.swift:136-262`) | the live `WorkflowExecution` if any, else the persisted run (`GET /workflow-execution/threads/{id}/run`), else the row snapshot | status, started, finished, progress bar, "x of y files", current file, error count, controls |
| Overview (`Overview/ActivityOverviewView.swift`, `+Cards.swift`) | the live execution; the activity events (`GET /api/activity?thread_id=`) | status card (status, started, finished again), progress bar and counts again, current file again, a files × steps grid, a timing card, every activity event as a list |
| Console (`ActivityConsoleView.swift`) | the live execution's node states, else the activity events | node states with success counts and errors (the Progress tab's rows again); the current file a third time; the events the Overview already listed |
| Progress (`Progress/ActivityProgressView*.swift`) | the live execution, else seeds one from the persisted run | progress bar and counts a third time; node rows again; "Recent Files". Its historical branch is dead: `progressTimeline` is declared and never assigned (`ActivityProgressView.swift:19`, `+DataLoading.swift:19-30`), so it always falls to "Progress data not available" |
| Trace (`Trace/RunTraceView.swift`) | its own fetch of the persisted run plus the episode ledger | the steps' states, time and cost a second way (per-node `progress_timeline`, not the jobs tree) |
| Log (`ActivityLogView.swift`) | its own fetch of the persisted run; or the live `logLines` | status header with cost and time a fourth time; the log, as one string (copyable) or as streamed lines (not copyable) |

None of the five reads the one record the table reads: the run's job tree
(`GET /api/activity/jobs/{id}`, `ActivityMonitorModel.swift:215-242`). So the table and the window
can disagree: the table's Errors column is the tree's `failed` count, the window's badge is the
live node states' error count or the number of error-level events (`ActivityDetailView.swift:36-42`).

**Why it is unreliable.**

- *It freezes at open.* The window follows a `SelectedActivityRun` whose `status` and `isLive` are
  `let`s copied from the row when it was double-clicked (`SidebarViewTypes.swift:92-94`,
  `ActivityMonitorWindow.swift:271`). `isLive` means "an execution this window started"
  (`ActivityStore.swift:341-361`), so a run started from another window, the CLI or a schedule is
  treated as history: its events are fetched once (`ActivityDetailView.swift:347-389`) and never
  again, because the task is keyed on an id that does not change (`:86`). A live run is the
  opposite: the fetch is skipped (`:348-351`), so Overview and Console are empty until it is
  reopened. The Log tab decides live or done from the same frozen flag (`ActivityLogView.swift:68, 85`).
- *Three transports, none of them the table's.* The table is updated by the jobs poll and the
  change stream (`ActivityStore.swift:132, 456-458`). The window neither polls nor listens to
  either; it opens a per-thread SSE subscription of its own, only when the snapshot said running
  or paused (`ActivityDetailView.swift:334-345`), and otherwise shows what it fetched once.
- *The start time can be now.* Subscribing seeds an execution with `startTime: Date()`
  (`WorkflowExecutionStore.swift:101-115`), and seeding from the persisted run falls back to
  `Date()` when the time does not parse (`:540`); the stats bar prefers the live execution's start
  (`ActivityDetailView.swift:52-60`). This is the "just now" defect of
  `activity.window.absolute-times` (#5432), still alive in the window.
- *Which tab you open first changes what the others show.* The Progress tab seeds the shared
  store (`WorkflowExecutionStore.seedFromPersistedRun`, `:184-196`) with empty node states and
  document progress; the Console and Overview then take the live branch on an execution with no
  content (`ActivityConsoleView.swift:18-21`, `ActivityProgressView.swift:26-29`), which is the
  blank console already patched once.
- *Three cost figures.* The Log header shows the run's `run_usage` with the estimate
  (`ActivityLogView.swift:207-243`), the Trace popover shows per-node timeline cost
  (`RunTraceModel.swift:257-260`), the table shows the jobs tree's `cost_usd`
  (`execution/jobs.py:405-408`); they are summed from different records.
- *Ids where names belong.* Console and Progress rows fall back to `nodeId`
  (`ActivityConsoleView.swift:88`, `+LiveProgress.swift:72`); a page's name is whatever the job's
  `subject` holds (`ActivityMonitorModel.swift:300-309`), not the document's title, which the
  historical Progress view had to look up itself (`+HistoricalProgress.swift:197-212`).
- *It is only ever a run.* Double-clicking a step or a page row opens the run that owns it
  (`ActivityMonitorWindow.swift:130-133, 198-205`); a job of its own (an embedding queue) has no
  details at all (`runRowID` nil). The one shared selection (`ActivityWindowSelectionState.shared`,
  `ActivityViewHelpers.swift:3-21`) resolves its library from the run, else the current library,
  else the global one (`ActivityDetailWindow.swift:12-22`), so a run whose library id is missing is
  read through another library's services.
- *What the engine knows and no view shows:* the run's peak memory, the engine's and the model
  servers' (`RunUsageResponse.engine_peak_memory_bytes`, `model_server_peak_memory_bytes`,
  `api/routes/workflow_execution/threads.py:122-127`, measured since #5537); a waiting row's reason
  with the Mac's numbers (`MachineState`, `activity.py:149-160`); the failed pages under a row with
  each one's reason (`JobTree.failed`, `activity.py:192`).

**The design: one view, one record.** The details of a selected row, whatever its kind (a run, a
step, a page, a job of its own), is one scrolling view with no tabs, read from the row's own node
of the job tree (`GET /api/activity/jobs/{id}`) and one filtered read of its log. Top to bottom:

1. **Heading.** What it is, in words: "Transcribe · 40 pages", "Read a page · f. 103r of
   Diary 1918", "Find lines · page 12 of letter_0417.pdf", "Embedding queue". The project, the
   model it used (or the models under it), who or what started it (`activity.window.started-by`).
   Names, never ids or upload temp names.
2. **State, and why.** One line, the same words as the table's State column: "Running: Entities,
   page 212 of 400"; "Waiting: memory is tight (pressure warn, 1.2 GB free)"; "Paused by you";
   "Failed: the provider refused this page (429)"; "Stopped by you"; "Done". A failed row names
   the cause the engine recorded; a waiting row names the throttle's reason and the Mac's reading
   it rests on.
3. **Progress.** Pages done · failed · left, a bar, and time left at the pace so far; for a row
   with no pages (a single page, a job of its own with no total) the counts are omitted, not
   "0 of 0". Under it, the **failed pages** by name, each with its reason, and the action
   *Read the N pages that failed again* (#5555), which retries only those.
4. **Log.** Every line the engine wrote for this row and the rows under it, filtered to this row
   only, newest last, auto-following while it runs, selectable and copyable as plain text. The
   log is the only part of the view that scrolls on its own.
5. **Resources.** Started at and finished at (absolute, `activity.window.absolute-times`),
   elapsed; tokens and cost as the table shows them (null stays blank, never "$0"); the peak
   memory of the engine and of the model servers during the run, from the run's usage record; a
   figure the engine did not measure is left out.
6. **Actions.** Pause or Resume, Stop, Retry on a failed or stopped row (the row's own job routes,
   `activity.pause.per-job`);
   *Read the N pages that failed again*; *Open the page* on a page row, *Show the pages* on a step
   or run row (the Library selects them); *Show the trace* on a run row, which opens the existing
   `RunTraceSheet` as a sheet; *Show what it made* (`activity.window.what-it-made`). An action
   that does not apply is absent, not disabled.

The view follows the selected row: picking another row changes it; the table's in-place update of
that row (tree re-read on the change stream) is the view's update; it opens no stream and no poll
of its own. It is reached by the ⓘ button and by double-click (#5560), and the same view is the
detail below the table, in the Preview pane and on the compact stack.

**What is deleted.** `ActivityChildType` and the section bar; `ActivityOverviewView` and
`+Cards`; `ActivityConsoleView`; `ActivityProgressView` and its three files, including the dead
timeline branch; `ActivityLogView`'s two-headed live/persisted log; the stats bar's second copy of
status, time, progress and errors; `ActivityViewHelpers.selectedRunStatus` and the
`SelectedActivityRun` snapshot (the selection becomes a job id and its library);
`WorkflowExecutionStore.seedFromPersistedRun` and the detail's subscribe-on-select; the
"Compare Runs…" button (it moves into the trace sheet). `RunTraceView` stays, as a sheet, because
the artifact Inspector opens it too (`RunTraceSheet`, #4319).

**What the engine must carry for it** (today missing from `JobTree`, `activity.py:179-198`,
`execution/jobs.py:360-413`): `started_at` and `finished_at` on every node (only `seconds` is
rolled up now); `working_on`; the page's document id and display name beside `subject`; the
run's peak memory on the run node (it lives only in `run_usage`); `started_by`; a log read by job
id (the run log is one `execution_log` string per run, and activity events are keyed by thread
and node, not by job); a retry action for failed pages.

- `activity.details.what-it-works-on-now` — **[PARTIAL]** (#5623) a running row's details say at a
  glance that it is working: what it works on now (the page and the step: "Embed for search ·
  p12.jpg"), its stages each with its state and counts, the recent lines of its log, and its controls
  (Pause or Resume, Stop) beside the Start / Stop mode control. The import's "Processing imported
  pages" row has a tree like any job (`GET /api/activity/jobs/derivatives`): one child per
  stage (Make thumbnails, Embed for search, Read names), each with its state, why it waits, its pages
  done, failed and in all for the import in hand, and its running and most recent pages under it; its
  log (`GET /api/activity/jobs/derivatives/log`) is those pages' lines (started, done,
  failed and why, waiting and for what), newest last. A kind's counted row (`waiting:<kind>`) reads
  the same way. Before: the row showed a bar, "97 done · 0 failed · 49 left" and "Log: Nothing
  written for this row yet". Built (2026-10-09): `execution/jobs.py` `queue_tree`, tested through
  the routes (`test_start_stop_mode.py`); app: the details' "Working on" line and Stages list from
  the tree (`ActivityTableTests` `testActivityDetailsWhatItWorksOnNow_theImportRowSaysItsPageItsStagesAndOffersItsControls`; its Pause and Stop `testActivityWindowTable_pauseOnTheImportRowGoesToItsIdAndTheJobsReadFollows`). Not yet seen in the app; the Swift is not compiled by the worker.
- `activity.details.one-view` — **[OK]** (#5561) the details of a selected row, whether a run,
  a step, a page or a job of its own, is one scrolling view with no tabs or sections to choose
  between; the Overview, Console, Progress, Trace and Log sections are gone. Built: `Views/Activity/Detail/ActivityDetailsView.swift`; the five sections' files are deleted (pinned: `ActivityWindowSelectionStateTests`).
- `activity.details.one-record` — **[OK]** (#5561) everything the view shows is read from the
  row's own node of `GET /api/activity/jobs/{id}` and one filtered log read, never from a live
  `WorkflowExecution`, a persisted `WorkflowRunResponse` and the activity events side by side; the
  Errors, Progress, Cost and Model figures it shows equal the table row's. Built: `ActivityDetails` words the table's own row for the job (pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`).
- `activity.details.heading-names-not-ids` — **[PARTIAL]** (#5561) the heading says what the row is,
  on which file or page by its display name, with which model and started by whom; no thread id,
  node id or upload temp name appears anywhere on the view. Built for runs, steps and pages read by a lane (pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`, `fichero-server/tests/unit/jobs/test_activity_details_5561.py`). Left: a model call a text step makes names no page (its caller passes none; the file being read is known only in `workflows/builder.py`), so its row says its kind, not the page.
- `activity.details.state-says-why` — **[OK]** (#5561) the state line uses the table's State
  column words and adds the reason: a failed row its recorded cause, a waiting row the throttle's
  reason with the Mac reading it rests on, a running row what it is working on now. Built: the State column's words (`ActivityMonitorRow.stateText(phase:…)`), and a waiting row adds the Mac's reading (pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`).
- `activity.details.progress-counts` — **[OK]** (#5561, #5555) a row with pages shows pages
  done, failed and left with the time left at the pace so far; a row with no pages shows no counts
  rather than "0 of 0". Pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`.
  A try's row has no child rows (its pages live in a scratch copy that is deleted when it ends), so it keeps the
  pages made and tried on its own detail and the tree reads them (Fable review 2026-10-19 #3, built 2026-10-20);
  `fichero-server/tests/unit/jobs/test_a_try_row_counts_its_pages_2026_10_20.py`.
- `activity.details.failed-pages-by-name` — **[OK]** (#5561, #5555) the failed pages under the
  row are listed by display name, each with its own reason, and *Read the N pages that failed
  again* enqueues only those pages and nothing else. Pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`; the retry is the run's `read-again` (#5555).
- `activity.details.log-filtered-newest-last` — **[OK]** (#5561) the log shows only the lines the
  engine wrote for this row and the rows under it, newest last, following the end while the row
  runs, and copies as plain text with one command. Built: `GET /api/activity/jobs/{id}/log` (pinned: `fichero-server/tests/unit/jobs/test_activity_details_5561.py`, `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`).
  *Superseded by Ruled 2026-10-19 in part:* what the log holds is the person's log, with debug lines at a Developer level (`activity.log.persons-log`, `activity.log.developer-level`).
- `activity.details.resources` — **[OK]** (#5561, #5555, #5537) the view shows started at and
  finished at as absolute times, elapsed, tokens and cost as the table does, and the engine's and
  model servers' peak memory during the run; a figure the engine did not measure is omitted, never
  shown as zero or as now. Pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`.
- `activity.details.actions-are-the-rows` — **[OK]** (#5561) Pause, Resume and Stop on the view
  are the same job routes the row's buttons call, and an action that does not apply to this row's
  kind or state is absent. Pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`.
- `activity.details.open-in-the-app` — **[PARTIAL]** (#5561, #5560) a page row offers *Open the page*
  and a step or run row *Show the pages*, which select those documents in the Library window. Built: *Open the page* (`UIVerbs.openNode`) and *Show the pages* (`UIVerbs.selectNodes`); their presence is pinned, the Library's selection after them is not.
- `activity.details.follows-the-row` — **[OK]** (#5561) the view follows the selected row: it
  changes when another row is selected, updates when the table's tree re-read updates that row,
  and opens no stream, poll or fetch of its own beyond the log read. Pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift` (a tree re-read on the change stream updates the same selection; no other read).
- `activity.details.one-mount` — **[OK]** (#5561, #5560) the ⓘ button, double-click, the detail
  below the table, the Preview pane of the `.activity` mode and the compact stack all mount this
  one view for the row's job id and library, and a job of its own has details like any run. Built: the details window, the detail below the table, the Preview pane, the compact stack, and the Reader (its log alone); a job of its own has details (pinned: `fichero/Tests/Unit/general/Models/ActivityDetailsTests.swift`, `ActivityTableTests`).
- `activity.details.engine-carries-what-it-shows` — **[OK]** (#5561) every node of
  `GET /api/activity/jobs/{id}` carries `started_at`, `finished_at`, `working_on`, `started_by`,
  the page's document id and display name, and the run node its peak memory; the engine serves a
  log filtered by job id and a retry action for a row's failed pages; the view adds nothing the
  engine does not record. Pinned: `fichero-server/tests/unit/jobs/test_activity_details_5561.py`; the run node's peak memory rides on its `account` (#5537), the retry is `read-again`.

### C. Pause and start

- `activity.pause.global` — **[PARTIAL]** (#5355) one *Pause Background Work* stops every
  job that started by itself, at its next boundary, and the island says so. Built (2026-10-03):
  `PUT /api/activity/jobs/paused`; while paused the scheduler starts nothing and a waiting job says
  "Paused by you"; `/api/activity/jobs` reports `paused` (`fichero-server/tests/unit/jobs/test_job_queue.py`). The derivative stages
  are held too (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`). The engine starts no workflow run
  by itself outside the queue (2026-10-08): a recipe run is a `recipes` job, held like any other, and
  the schedule and file-trigger managers are never started (`init_scheduler`, `init_file_watcher`
  have no caller). Still a gap: the Mac control and the island.
- `activity.pause.global-survives-relaunch` — **[PARTIAL]** (#5355) a Mac paused at quit is
  paused at launch. Built: the switch is an app setting (`background_work_paused`), read by the
  scheduler before every job (`fichero-server/tests/unit/jobs/test_job_queue.py`). Pinned (2026-10-08): after a
  relaunch the open's resume puts interrupted jobs back to waiting without starting them, and
  `/api/activity/jobs` says `paused` and "Paused by you" until the switch is turned off
  (`test_job_queue.py::TestPause::test_pause_survives_a_relaunch_and_activity_says_so`). Still a gap:
  the click-around leg.
- `activity.pause.per-job` — **[PARTIAL]** (#5356) Pause, Resume and Cancel on any row, applying
  to its children. Built (2026-10-03, 2026-10-04): any row in the `jobs` table can be paused,
  resumed and cancelled (`PUT /api/activity/jobs/{id}/paused`, `POST /api/activity/jobs/{id}/cancel`);
  a run's row reaches the run and its waiting pages and its sub-workflows; a training Job is
  cancelled on Hugging Face (`fichero-server/tests/unit/jobs/test_job_queue.py`, `fichero-server/tests/unit/jobs/test_runs_are_jobs.py`,
  `fichero-server/tests/unit/jobs/test_sub_workflows_are_child_runs.py`). The window's rows carry
  Pause or Resume and Stop through these routes (2026-10-04, `ActivityTableTests`
  `testActivityWindowTable_pauseOnAStepRowSetsThatOneRowsState`; not yet seen in the app); a job of
  its own from the jobs read has them too (2026-10-09, #5621, `activity.pause.per-queue`). Built (2026-10-08): retry, `POST /api/activity/jobs/{id}/retry`
  (`job.retry`): a failed or stopped job goes back to waiting with its attempts cleared and carries on from
  its own checkpoint; refused, with the reason, for work a run hands in (retry the run), a training on
  Hugging Face (start a new one) and work already waiting again. Stop on its row now reaches a running
  check, line check, tie-text, reading at scale and gathering of reasons. Every kind is pinned to the four
  controls (`fichero-server/tests/unit/jobs/test_every_kind_has_its_controls.py`). Built (2026-10-08,
  app): a failed or stopped row in the window, a job of its own too, offers Retry through this route; the
  engine's answer is set on that one row in place, and a refusal is shown in the engine's words
  (`ActivityTableTests` `testActivityWindowTable_retryOnAFailedPageRowSetsThatOneRowsState`,
  `testActivityWindowTable_aRefusedRetrySaysTheEnginesWordsAndChangesNothing`,
  `testActivityWindowTable_aStoppedJobOfItsOwnOffersRetryButARunningOneDoesNot`; not yet seen in the
  app). Still a gap: pausing
  every waiting job of one kind at once; a running reasons A/B cannot be stopped; and kinds keep stop
  routes of their own beside it (`activity.pause.one-start-stop`).
- `activity.mode.start-stop` — **[PARTIAL]** (#5621, ruled 2026-10-09) one control says how
  background work runs on this Mac, in one of three modes: **automatic** (the throttle holds heavy
  work while the person uses the Mac or it is on battery, and lets it go the moment that clears),
  **started** (*Start*: those two holds are lifted for all waiting work until the control is pressed
  again; memory and heat still hold), and **paused** (*Stop*: Pause Background Work, nothing that
  runs by itself starts and running work stops at its next boundary). The mode is an app setting, so
  it survives relaunch like the pause. One audited, undoable action (`background.mode`,
  `PUT /api/activity/jobs/mode`) behind the main window's toolbar button and the Activity window's
  toolbar; `GET /api/activity/jobs` reports `mode`, and `machine.why_wait` is null while started
  unless memory or heat holds. The control's menu is an inline choice with the current mode ticked:
  *Run Now* (started), *Run Automatically* (automatic), *Pause All* (paused); a click on the button
  itself runs now from automatic and goes back to automatic otherwise. The toolbar button is an icon
  only, its words in its help and accessibility label (`Background work: <state>`): *Running* (play
  filled, work runs now), *Idle* (play outline, nothing runs), *Waiting* (orange hourglass:
  automatic or run now, and the throttle holds waiting work now, with why in its help), *Paused*
  (pause). The mode the button shows is the one the engine last answered: a jobs read that began
  before a mode was set is older than the engine's answer to it and never puts the old mode back
  (`ActivityStore.refreshBackgroundJobs`; #5621, where after Stop the button kept saying running).
  The Activity window's button reads a project's store that polls the jobs read, so it follows a
  change made elsewhere. Built (2026-10-09): engine (`execution/jobs.py` `set_mode`, `execution/throttle.py`
  `why_wait`), tested through the route with the real lanes (`fichero-server/tests/unit/jobs/test_start_stop_mode.py`);
  app: `ActivityModeButton` in the main toolbar and the Activity window, driven by
  `ActivityStore.setBackgroundMode` (`ActivityTableTests` `testActivityMode_*`, and
  `testActivityMode_aJobsReadBegunBeforePauseAllDoesNotPutTheOldModeBack` for the stale read). Not yet seen in the app; the Swift is not compiled by the worker.
- `activity.throttle.recheck-when-it-clears` — **[PARTIAL]** (#5621) work held for battery, for the
  person at the Mac, or for memory or heat starts by itself once the hold clears, with no new work
  queued and nothing pressed: the model lane looks again every few seconds while it holds work, and
  the battery reading is trusted for at most 10 s. Tested (`test_start_stop_mode.py`
  `test_work_held_for_battery_starts_when_power_returns`). Not yet seen in the app.
- `activity.pause.per-queue` — **[PARTIAL]** (#5621) a row that stands for many jobs (the import's
  "Processing imported pages", or one kind's waiting jobs counted on one row) has Pause, Resume and
  Stop like any other row: they apply to every job it stands for that has not started (running ones
  finish their item). Paused jobs are counted on one row per kind too, so pausing 137 pages does not
  list 137 rows. Built (2026-10-09): `pause_job` / `cancel_job` take the row's id
  (`derivatives`, the import's row in the project the request names; `waiting:<kind>`, `paused:<kind>`), through `job.pause` / `job.cancel`
  (`test_start_stop_mode.py`). Not yet seen in the app.
- `activity.pause.cancel-long-call` — **[PARTIAL]** (→ #4402) cancel is checked at every per-item
  boundary (`execution/cancellation.py`, `builder.py`); a single long call is still waited for. Owned
  by `activity.run.stop-reaches-in-flight-calls`; this line points there.
- `activity.pause.controls-are-actions` — **[PARTIAL]** (#5356) pause, resume, cancel
  and retry are audited actions, reachable from the window, MCP and the command line. Built: the
  global pause is the audited, undoable action `background.pause` (`fichero-server/tests/unit/jobs/test_job_queue.py`); per job, `job.pause`
  (undoable) and `job.cancel`; MCP tools `fichero_jobs`, `fichero_pause_background_work`,
  `fichero_job_pause`, `fichero_job_cancel` (`fichero-mcp/tests/test_mcp_server.py`); retry is the
  action `job.retry` (2026-10-08), reachable from MCP and the command line through the tools generated
  from its route, and from the window's Retry on a failed or stopped row (2026-10-08).
- `activity.pause.one-start-stop` — **[PARTIAL]** (#5356) every kind of job is started, paused,
  resumed, cancelled and retried through one pair of routes and actions (`/api/activity/jobs/{id}/…`,
  `job.pause`, `job.cancel`); a kind's own routes are callers of it or are retired. Built: pause and
  cancel on every row (`fichero-server/tests/unit/jobs/test_job_queue.py`, `fichero-server/tests/unit/jobs/test_runs_are_jobs.py`). Still a gap: runs keep their
  own pause and stop routes (`/api/workflow-execution/…`), training its own cancel
  (`/api/training/jobs/{id}/cancel`), gathering reasons its own (`/api/training/reasons/{id}/cancel`),
  batches their own (`/api/batches/{id}/pause|cancel`), each beside the job route; and there is no
  start on it (retry is, 2026-10-08).

### D. Throttling

- `activity.throttle.background-qos` — **[PARTIAL]** (#5358) background work runs at background
  QoS on the efficiency cores, and heavy local work at utility QoS bounded by its lane. Built: every
  job kind declares its QoS (background by default, `execution/jobs.py` `Kind.qos`); the derivative
  stages, the correction re-embed, the task kinds and synced-folder work are background; Kraken
  pages, local-model pages and training are utility, bounded by the local-model lane; a job a
  person waits on runs at utility (`activity.throttle.watched-first`). Still a gap: workflow runs
  started by themselves (schedules, triggers) are held by nothing of their own beyond the lanes
  their model calls take (→ #4740).
- `activity.throttle.lanes` — **[PARTIAL]** (#5358) jobs run in lanes by resource with bounded
  concurrency, and a waiting job says what it is waiting for. Built: the local-model lane (one heavy
  model at a time), images (two), network (four, with a share per provider), database (one),
  remote, and recipes (`execution/jobs.py` `LANES`); a waiting job says why ("Waiting for Kraken",
  "Paused by you", the throttle's reasons) (`fichero-server/tests/unit/jobs/test_job_queue.py`, `fichero-server/tests/unit/jobs/test_provider_share.py`).
  Still a gap: the row does not show its lane (`activity.window.row-shows-lane-state-reason`), and
  the scheduler behaviours are pinned below the public surface (see "Pinning").
- `activity.lane.load-once` — **[PARTIAL]** (#5358, #5370) a heavy model is loaded once and kept resident
  while work for it remains, fed in batches; it is never reloaded per page or per call. Built for
  Kraken: its line finder and reader stay resident (`llm/kraken_runtime.py` `_resident`), and the
  lane runs a folder's pages for one reader together (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). Still a gap: batching, and
  the other runtimes.
- `activity.lane.group-by-model` — **[PARTIAL]** (#5358) the local ML lane runs ready work grouped by the model it
  needs, switching models only between groups and unloading the old one only when the next does not fit beside it (`activity.lane.one-model-at-a-time`, the later ruling; Apple and spaCy never evict). Built: queued jobs
  for the model last used run before any other model's (`fichero-server/tests/unit/jobs/test_job_queue.py`), Kraken pages
  included, named by reader (`kraken:<reader id>`); leaving Kraken for another heavy model frees
  Kraken's resident models first, and leaving the embedder for Kraken frees the embedder; a
  background job for another heavy model waits for 20 s of quiet on the loaded one, so bursts do
  not swap models page by page, while work a person waits for switches at once
  (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). The quiet spell is not the only hold (#5846,
  `fichero-server/tests/unit/jobs/test_model_lane_affinity_5846.py`): while Kraken is loaded and a Kraken page
  waits in any open project, or a run has one at the page gate, no other heavy model takes the lane, so Kraken loads
  once for a run. Over a whole Kraken run that means the embeds for search (an import's, or one a person starts
  without waiting on it) wait for the run's pages; they go ahead 5 minutes after Kraken last ran, so queued Kraken
  work that cannot run never holds them for good. Work a person waits for, and a try a step hands in, switch at
  once. Every model load and unload is one engine log line, `model-lane: load …` or `model-lane: unload … (why)`,
  so reloads can be counted. Pages read by a model served on this Mac hold the same lane
  (`fichero-server/tests/unit/jobs/test_local_model_pages_on_the_lane.py`). Still a gap: stopping a local model server on a switch (its restart costs
  30-300 s). A text model served on this Mac holds the lane like a page, called in a run
  (`fichero-server/tests/unit/jobs/test_text_calls_on_the_lane.py`) or by chat (`fichero-server/tests/unit/jobs/test_chat_on_the_lane.py`).
- `activity.lane.co-run-only-if-it-fits` — **[PARTIAL]** (#5358) two heavy models run at once only when their
  measured resident sizes fit this Mac's memory with headroom; on an 8 GB Mac, never. Built: never,
  for now: queued heavy jobs run one at a time and wait while a Kraken page holds Kraken's lock
  (`fichero-server/tests/unit/jobs/test_job_queue.py`); a workflow's Kraken pages are on the same lane, and a vision
  model reading Kraken's lines waits on the network off it (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). Still a gap:
  measuring, and co-running when both fit. One model is not two (#5654): several reads of the one model the
  engine's model server has loaded run at once, as many as `compute.memory.reads-follow-memory` allows, and
  nothing else runs beside them (`fichero-server/tests/unit/jobs/test_model_lane_reads_what_the_plan_says_5654.py`).
- `activity.lane.embed-off-the-heavy-lane` — **[OK]** (speed review 2026-10-19, #5847) the search embedder is a child
  process, so its jobs (Embed for search and the like) run on a lane of their own, "the small-model lane" (`embed`, one
  at a time), not on the model lane (`local-ml`). An embed beside a Kraken page neither waits for the model lane nor
  unloads Kraken's models, so a step followed by an embed keeps Kraken resident and the next step does not reload the line
  finder and the reader. Only battery, memory and heat hold the lane, as they hold the model lane; a build or the person
  using the Mac slows its jobs and never holds them (`activity.throttle.use-means-slower`), and they stay background work. Pinned by
  `fichero-server/tests/unit/jobs/test_embed_off_the_reading_lane.py` (a step followed by an embed keeps Kraken resident;
  an embed runs beside a Kraken page; the real embed kinds are on the embed lane and stay background).
- `activity.lane.each-unit-its-own-lane` — **[PARTIAL]** (speed round 2, `briefs/bugs-vision-alongside-2026-10-19.md`) each compute unit has its
  own lane and they run at once: Kraken on the CPU, Apple Vision on the Neural Engine, MLX on the GPU, hosted readers on the
  network. Apple Vision runs beside Kraken: an Apple page takes no model-lane job, does not count as a "local page in flight"
  against Kraken's memory fan-out (`kraken_runtime.page_fan_out`), and never waits for a Kraken page; its own gate
  (`vision_base._APPLE_VISION_GATE`, at most 2, one when memory is short) bounds it. Already true, pinned by reading the code:
  the Vision bundle and its locales load once per engine at startup, off the loop (`warm_supported_locales`), and one
  `VNRecognizeTextRequest` per page carries the lines and the words (a per-line Apple read is a different feature, and gap
  escalation adds a request only for a band Vision missed)
  (`fichero-server/tests/unit/workflows/test_apple_vision_runs_beside_kraken.py`; the job lane already runs a Vision page beside a Kraken page, `tests/unit/jobs/test_one_model_at_a_time_on_the_lane.py`).
- `activity.lane.same-model-pages-together` — **[PARTIAL]** (speed round 2 (b); r1's measurement: two Kraken pages at once with five
  threads each took 6.3 s a page against 9.7-10.2 s one after the other) built in two halves, merged together; not yet run on the
  M4. The lane: `_Lane.may_start` admits a second page of the SAME model on the model lane when a person started its run
  (`person_waits_on`) and `kraken_runtime.pages_at_once(True)` (fast priority, cores, memory for both) says two; never while
  memory is busy (`one-heavy-when-memory-tight` stands); a third page waits, a different model waits, background stays at one
  (`fichero-server/tests/unit/jobs/test_same_model_pages_together.py`, work faked). The gate (r1, `source.read.two-pages-at-once`):
  `kraken_runtime._INFERENCE_LOCK` is a page gate that lets `pages_at_once` pages read together and, taken whole
  (`_release_kraken`, `local_inference.release_idle_engine_models`), waits for them all. `locked()` is true while ANY page reads, so
  a queued page's "is a page outside the queue reading" check is `_kraken_busy(queued)`, which does not count the lane's own other
  Kraken pages (same test file).
- `activity.reconnects-after-engine-restart` — **[PARTIAL]** (owner, 2026-10-19 20:14, P1: Activity could not load after Sharing was
  turned on; `briefs/activity-after-sharing-restart-2026-10-19.md`) after the engine restarts, Activity loads again without the
  person doing anything: a jobs read that finds the engine not there (a `URLError`, or the socket layer's `NIOCore.IOError`,
  "error 1") says so in the footer in words ("Couldn't load activity: the engine could not be reached"), never the raw socket
  text; reads again after 2, 4, 8, 16, then every 30 s; and when one answers, the footer line clears and the run list is
  read again (`ActivityStore.jobsPollFailed` / `jobsPollSucceeded`, the window reloads on `refreshToken`); and each failed read re-resolves the endpoint (`FicheroClient.reconfigure(baseURL:transportMode:)` from `EngineConfig`: a changed socket path, or a move between the socket and the https listener, gets a new transport and pool instead of redialling the first connect's) (`fichero/fichero-api-client/Tests/FicheroAPIClientTests/TransportModeTests.swift`)
  (`fichero/Tests/Unit/general/Models/ActivityReconnectTests.swift`; needs compile). NOT shown to be the cause: why the
  requests never reached the engine at all (the log has none after the restart); this makes the app keep trying and say so, it does
  not explain an `EPERM` on a stale or sandboxed dial. Open: should turning Sharing on restart the engine (its graceful shutdown
  timed out and cancelled work in flight)? That is the owner's call. WHY THE ENDPOINT WAS STALE (read from the code, 2026-10-19; NOT reproduced): the two paths that rebind the clients when the host
  changes, `AppState.reconfigureGeneratedClientsForCurrentHost` and `LibraryManager`'s `reconfigureBackendHost`, passed only the
  base URL (`reconfigure(baseURL:)`), which returns early when the URL is unchanged and never rebuilds the transport. A change in HOW
  the engine is dialled (its socket path, or the socket against its https listener, as turning Sharing on does) was therefore
  never applied to the clients built at the first connect; Activity kept the old one while a store built afterwards got the new
  one. Fixed: every host-change rebind now passes `EngineConfig.transportMode` too (AppState, LibraryManager, KnownLibraryRegistryStore, AppleScriptSupport, IntegrationsService, ModelComparisonService, LooveCoverageService), and the host-only `reconfigure(baseURL:)` is DELETED from `FicheroClient` and `APIClient`, so a new rebind that forgets the mode does not compile; pinned by the `transportMode == EngineConfig.transportMode` expectations in `ServiceHostReconfigurationTests`. Not proven: that this is the EPERM (macOS answers a refused
  sandbox connect with EPERM, and the engine log showed the same socket path), which needs the M4 repro: turn Sharing on with
  Activity open, then read the app log for `endpoint re-resolved … (was …)`, which now names the old and the new mode.

- `activity.read.page-read-once` — **[PARTIAL]** (owner, 2026-10-19 20:29, `briefs/kraken-slow-respawn-2026-10-19.md`) a page is read ONCE. A
  GET never runs a model: `GET /api/segments/document/{id}/text` (`document_text`) only derives the text from the passes the page
  already has, so opening a page's text while a run reads it starts no recognise (`fichero-server/tests/unit/api/test_document_text_never_reads.py`).
  The 20:24 dumps show ONE recognise (the lane's job, `jobs._work` -> `recognize_to_geometry`; the second `recognize_to_geometry`
  frames are the same job's waiting thread), and the request thread in `working_pass` only deriving text; what held the loop
  8-10 s was the route being `async def` and running that derivation (library DB queries, the library lock behind the lane's
  writes) ON the event loop; it runs on a worker thread now, one derivation at a time, and callers asking for the same page's text at once share one (`single_flight`): three GETs beside a Kraken read starved the GIL (blla is mostly single-threaded; r1's profile). Same test file, with the loop's longest stall measured beside the call. NOT built: the owner's "the view shows the page as
  waiting or reading in that run, and a page nothing covers queues one de-duplicated job on the model lane". The text view has no
  such state today (a page with no pass answers an empty text); it needs the product shape first.
- `activity.read.get-runs-no-model` — **[PARTIAL]** (manager ruling, 2026-10-19) a GET never runs a model, at any depth: it never starts a
  read, an embedding or any derivation that loads one. It returns what is stored, or says it isn't ready (503, in words). Two
  guards. The scan: it fails when a GET handler's own body calls a model entry point (`recognize_*`, `segment_to_geometry`,
  `apple_vision_ocr*`, `_embed_text*`, `get_embedder`, `run_on_lane`, a model's `.encode(`)
  (`fichero-server/tests/unit/api/test_no_model_work_in_gets.py`). The runtime guard, for what two calls down the scan cannot
  see: a middleware marks every GET/HEAD request (`core/no_model_in_get.py`, a `ContextVar` that threads started with
  `asyncio.to_thread` or the threadpool inherit), and `kraken_runtime._kraken_call`, the embedder (`_embed_text`, `_embed_texts`)
  and `jobs.run_on_lane` / `run_on_lane_blocking` raise `ModelWorkInGet` there, answered 503 with the words
  (`fichero-server/tests/unit/api/test_no_model_work_in_gets_at_any_depth.py`). Built: `GET /api/claims/{id}/similar` reads the
  claim's stored vector. The mark ends when the response's last byte is sent, so a `BackgroundTasks` function or a task the GET left running runs free after it (work awaited inside the request, `asyncio.to_thread` included, is the GET). LIMITS: a thread started with `run_in_executor` or `threading.Thread` does not inherit the mark (the
  scan and review cover those); Apple Vision and the MLX servers are not guarded yet; the bench (GETs firing during a read, on
  the M4, `briefs/tester-gets-bench-2026-10-19.md`) is pending. What the request awaits (its tasks, a `single_flight` flight, a `gather` branch, `asyncio.to_thread`) keeps the mark; the three
  fire-and-forget sites (the auto-embed `create_task`, the activity tracker's recovery, `on_background_loop` at a library open)
  are spawned with a fresh context (`spawn_free`) and run their model call. Pinned by
  `test_what_the_request_awaits_keeps_the_mark_and_the_known_spawn_sites_run_free` and
  `test_on_background_loop_is_spawned_free`.
- `activity.read.get-embeds-its-own-query` — **[PARTIAL]** (manager ruling on review 361, 2026-10-19) a GET may embed its OWN
  query text, one short vector, and nothing else: `GET /api/kg/claim-search?q=`, `GET /api/kg/entities/semantic?q=` (and
  `/api/search`) answer with a query embedding. The embed is bounded (`QUERY_EMBED_SECONDS`, 5 s): if the embedder is busy
  or cold past the bound the GET answers 503 in words ("The search model is busy …, try again"), never hangs; the late embed
  finishes on its own thread and the next GET finds the model loaded. It never loads, unloads or waits on a heavy model
  (Kraken, MLX, a VLM): the embedder is the small model that runs beside them. A passage embed (`role="passage"`, the batch
  `_embed_texts`) stays refused. Pinned by `fichero-server/tests/unit/api/test_get_embeds_its_own_query.py` (a answers,
  b busy answers in words within the bound, c the loaded heavy model is still loaded).
- `activity.read.get-keeps-kraken-and-lane-refused` — **[OK]** Kraken, recognise and `run_on_lane` stay refused in every GET
  (the indirect-call test above stays).
- `activity.read.claims-backfill-is-a-lane-job` — **[PARTIAL]** a GET never embeds the claims that lack a vector. It
  searches the vectors that exist, says how many claims are not embedded yet (`not_embedded` on the response, absent when
  none), and queues ONE background job (kind `embed-knowledge`, subject `claims` or `entities`, the embed lane, so the throttle applies); a second GET while
  that job waits or runs queues nothing. An auto-embed that finds no event loop inside a GET (a `to_thread`) queues the same job for the
  kind it was asked to embed (claims or entities), so no vectors are lost. Pinned by `test_a_get_with_unembedded_claims_queues_the_backfill_once` and `test_auto_embed_with_no_loop_inside_a_get_queues_the_backfill_instead_of_losing_the_vectors` (claims and entities). NOTE:
  no GET embedded claims before this (the reindex action is a POST), so this is the count and the queue, not a move.
- `activity.engine.restart-says-why` — **[PARTIAL]** (overnight P1, 2026-10-19) when the app restarts its engine because its
  health checks went unanswered, the connection detail says why in words: how many seconds were missed, and that an import was
  running, then "Reconnecting…" (`AppState.restartSentence`, `ConnectionPresentation.lastRestartReason`, cleared when the
  engine answers). Pinned by `fichero/Tests/Unit/general/App/EngineRestartSaysWhyTests.swift` (needs compile). LIMIT: it says
  the engine did not answer, not what held the loop (the engine log's `loop_lag` dump names that).
- `activity.jobs-poll-off-the-loop` — **[PARTIAL]** (Fable runner review #2, 2026-10-19; the app polls `GET /api/activity/jobs` every 2 s) the poll never holds the
  event loop. Already so on the chain head: the app-DB flag reads are cached (`is_paused`, `is_started`, the settings), auth waits off the
  loop, `snapshot`, `waiting_reason_of`, `read_again_runs` and the summary run on threads. Added: the per-row reads (`name_and_pages`,
  `_remote_row`), the process-tree walk (`ps`) and the machine readings run on threads too, and a battery reading taken on an event loop
  serves the last value and refreshes on a thread, so `pmset` is never waited for there. Pinned by
  `fichero-server/tests/unit/jobs/test_activity_jobs_get_off_the_loop.py` (an AST check that no blocking reading is called in the
  handler's own body; a slow-`pmset` loop test). NOT covered: `_recipe_state` (async, reads the run's tree) and the one DuckDB read inside
  `run_account`; a measured loop stall under a 50-row queue is the M4 bench.
- `activity.lane.pick-holds-no-lock-across-slow-probes` — **[PARTIAL]** (Fable runner review #11, 2026-10-19; the lock-P1 family) a heavy
  lane's pick holds neither `_heavy_pick` nor its own lock across a slow probe. The flags (`is_paused`, `is_started`) were already
  read before the lock; the battery reading (`pmset`, up to 5 s) is now taken there too, so the pick reads a fresh cache; and the
  held reason is written to the waiting rows once per change (again after 30 s), not once per scan per open project. Pinned by
  `fichero-server/tests/unit/jobs/test_pick_holds_no_lock_across_slow_probes.py`. NOT done: the held-reason write still happens
  inside the lane's pick when it does happen, and the thermal and memory probes are read in place (cheap sysctls).
- `activity.lane.hung-call-says-so` — **[PARTIAL]** (Fable runner review #16) a model call that holds the lane's slot and does not
  answer says so on its row after 60 s and at each minute after ("Waiting for the model to answer (2 min so far)"), instead of the last
  reason for up to 15 minutes. Pinned by `test_a_model_call_that_does_not_answer_says_so_on_its_row` (same file). NOT done: the 15-minute
  hold limit is not yet the call's own timeout plus a margin (no per-call timeout is traced for the local servers), and Stop does not
  reach a call already in flight (`activity.run.stop-reaches-in-flight-calls` [BROKEN]).
- `activity.runner.review-p2-p3` — **[PARTIAL]** (Fable runner review, 2026-10-19; each pinned in `fichero-server/tests/unit/jobs/test_fable_runner_p2.py`)
  #7 reopening a project no longer words a killed batch's row like a page (it reads "The engine stopped before this batch finished";
  runs are settled by `mark_interrupted_runs`); #20 `snapshot` lists a batch once (its own record), as it already did a workflow run;
  #21 a lane thread that dies on an error wakes the lane again after half a second, so waiting jobs do not sit until the next
  enqueue; #8 and #14 a job ends, or is deferred, on the connection its project has NOW, so a reopen no longer leaves a phantom
  `running` row or counts a deferral as an attempt; #15 the stale-run sweep runs on the engine's background loop, not on whichever
  loop made the tracker, and is no longer skipped when none runs. NOT done in this entry: #18 (`_wait_for_lane` polling), #19 (the
  lane's reason before Kraken's lock), #23 (an embed timeout kills a healthy child), #10 (Swift, its own entry).
- `activity.lane.one-model-at-a-time` — **[OK]** (owner rulings 2026-10-19, speed review) the model lane loads one heavy
  model at a time. Its next background job is the oldest for the model already loaded; it switches to another heavy
  model only when the loaded one has nothing queued (a short grace after its last page covers a run's next page, and a
  page a run has taken up but not yet queued counts as queued). Work a person started or watches goes first, at a page
  boundary, and its own model then becomes the loaded one, so its queued pages follow it. The loaded model is unloaded
  only when the next one does not fit beside it (the throttle's one memory rule: Kraken's need is its small working need
  while its models are resident, else the cold figure, a served model's own size); when both fit they stay loaded
  together, and the engine log says which (`model-lane: keep … loaded beside …`, or the unload with the memory it
  needed). Small models (the embedder, spaCy) run beside the big ones and are never "the loaded model"; Apple Vision is
  built in, takes no lane and evicts nothing. Pinned by
  `fichero-server/tests/unit/jobs/test_one_model_at_a_time_on_the_lane.py` (vision work and an embed during a Kraken run
  unload nothing; a VLM and Kraken that both fit stay loaded; when they do not, ten interleaved pages cause at most two
  swaps; embed, Kraken and a VLM interleaved load each heavy model once; a person's job for another model goes at the
  next page boundary and its pages follow it). Find Regions' Kraken segmenter is a lane job too (`find-regions` for `kraken:blla`, one per page, hanging under the recipe run's own row so the run's tree, its starter and its Stop are the page's: an automatic run's segmenter pages do not rank or hold as a person's; a job already running on the lane runs such a call in place), not work on the recipes lane's own thread beside whatever the lane has loaded (Fable runner review #5, 2026-10-19; `test_the_segmenter_runs_through_the_model_lane_not_beside_it` in `fichero-server/tests/unit/recipes/test_regions_one_pass_5689.py`). The bookkeeping half of #5 (loaded model set only by heavy families, a switch releasing only on memory need) was ALREADY on the chain: see this entry.
- `activity.lane.memory-look-again-follows-the-throttle` — **[OK]** (speed review 3c) a page held for memory goes on the
  moment the throttle's one decision (`decide`) lets it, asked again every quarter second inside the look-again time, not
  after a fixed five seconds; a resident model's page, sized by its small working need, does not wait at all, and one
  really held goes the moment it fits. Under *warn* memory pressure a Kraken page no longer waits for an embed (the embed
  lane is not a heavy lane). Pinned by `fichero-server/tests/unit/jobs/test_embed_off_the_reading_lane.py` (a resident
  models' page does not pay the five-second look-again; a page held for memory goes the moment it fits; under warn
  pressure a Kraken page runs while an embed runs).
- `activity.lane.thumbnails-first` — **[PARTIAL]** (#5585) a new import's thumbnails are made before
  heavy local work queued after them: they are cheap, and they are what the person sees. The local
  ML lane takes no job of a library while a thumbnail job of that library queued at or before it is
  still waiting or running, so a reading started on a new box and the import's own embeds wait for
  the box's thumbnails; work queued earlier keeps its place. While Background Work is paused the hold
  is off (paused thumbnails never run, and a page a person waits for still does). A held row says
  "Waiting: thumbnails are made first". Built as the smallest change on the existing lanes: the
  thumbnail kind is `first` (`execution/jobs.py` `Kind.first`); thumbnails already had their own
  images lane, but nothing ordered the heavy lane behind them, and the reading took the Mac while
  the box stayed blank (2026-10-07, 100 of 251 after 30 minutes). Tested through the real
  `import.folder` action, thumbnail stage and lanes (`fichero-server/tests/unit/jobs/test_thumbnails_first.py`);
  not yet seen in the app. Still a gap: a reading on a cloud model (the network lane) is not held,
  and the small display image is made on first view, not at import.
- `activity.lane.measures-processors` — **[PARTIAL]** (#5358) each job's row shows what it uses (CPU, GPU, Neural
  Engine, memory), measured by the engine. Built: the engine's CPU %, memory and energy (watts) are measured
  process-wide, the last two summed over its child processes (`process_tree_rusage`), the last two from `proc_pid_rusage` RUSAGE_INFO_V6, which needs no root (probed on the M4), and
  ride on `GET /api/activity/jobs` (`fichero-server/tests/unit/jobs/test_process_rusage_5358.py`). Still a gap:
  per-job attribution, and GPU and Neural Engine use (the OS gives no per-process figure without root).
- `activity.lane.overlap-different-processors` — **[GAP]** (#5358, #5370) a CPU-bound step and a GPU-bound
  step can run at the same time when memory allows; two steps on the same processor do not.
- `activity.lane.idle-unload` — **[OK]** (#5358, #5529) a resident model with no work is unloaded after a short idle
  time. Kraken's line finder, reader and the reader's two line-extraction processes are let go after 120 s without a
  page (`llm/kraken_runtime.py` `IDLE_RELEASE_SECONDS`, `_release_if_idle`); an embedding model no embed holds after
  600 s (`db/embeddings.py` `EMBEDDER_IDLE_SECONDS`, `release_idle_embedders`); an engine-started local model server
  after 600 s (`api/routes/ai/local_inference.py` `IDLE_STOP_SECONDS`). Tests: `fichero-server/tests/unit/jobs/test_engine_memory.py`,
  `fichero-server/tests/unit/db/test_embedding_model_only_while_needed.py`.
- `activity.throttle.watched-first` — **[PARTIAL]** (#5358) a job a person is waiting
  on goes first in its lane at utility QoS. Built (2026-10-04): handed-in work (a page of a run a
  person started) is ordered first on the local-model lane, and a long background job (training)
  steps aside for it at its next batch (`fichero-server/tests/unit/jobs/test_training_on_this_mac.py`). Built (2026-10-04): a
  queued job can be marked watched, and goes first in its lane at utility QoS; a person's own small change marks its
  synced-folder rewrite so (`fichero-server/tests/unit/jobs/test_synced_folder.py`). Still a gap: other work a person
  waits for that is not handed in (an opened page).
- `activity.throttle.person-started-first` — **[BUILT]** (#5820) on a shared lane the order is: work a person
- `activity.throttle.try-ahead-of-bulk` — **[BUILT]** (#5839) a person's stage try is watched, and so are the model-lane rows its steps hand in (`jobs.person_is_waiting()`: its Kraken pages were `started_by` "workflow", equal to the bulk recipe run's, so they queued behind it in creation order). The pick order is three-ranked: watched, then a person's started work, then background, each oldest first; the waiting rows in Activity are listed in that rank, then oldest first (a library's share, the attached-first rule and the loaded model, which the lane also weighs, aside), not by creation. While a try's page waits for the lane the try's own row says "Waiting: <the page's reason>" and is listed as waiting, reading running only once the page starts (`jobs.person_is_waiting(db, job_id)`). A job already running is never preempted. Pinned by `test_person_started_work_goes_first_5820.py`.
- `activity.window.waiting-looks-waiting` — **[PARTIAL]** (#5839) **Built 2026-10-19 (app), not yet seen:** a row that has not started looks it: a grey clock and grey "Waiting: <reason>", no progress count and no ticking timer (`ActivityMonitorRow.looksWaiting`: the engine lists the row as waiting; a running job that waits for the lane, Kraken or memory is listed so by its `waiting_on`, set when the wait starts and cleared when it ends, never by the words of its reason). The table's default order is running work first, then waiting work in the engine's list order, which is the lane's pick order (`activity.throttle.try-ahead-of-bulk`), then the rest newest first. Pinned by `ActivityWaitingLooksWaitingTests`.
- `activity.lane.no-wait-on-a-job-that-will-not-run` — **[BUILT]** (#5845) heavy work queued after thumbnails waits for them (`activity.lane.thumbnails-first`), so a thumbnail job that will never run must not hold it: on opening a project every thumbnail job waiting or set aside whose thumbnail file already exists ends `done` (`settle_made_thumbnails`), and Stop on a failed or set-aside job ends it `cancelled` (Delete and Stop work on it; it stops offering Resume). A restart is all it needs. The false "queue stalled" alarm is #5807. `test_stuck_thumbnail_waiters_5845.py`.
- `activity.window.one-row-per-kind` — **[BUILT]** (#5839) Activity lists ONE row per kind of queued work per project (a recipe run and a try keep a row each), with the whole queue's total and what is done of it ("Make thumbnails: 12 of 41", `done` since its oldest queued job was queued); the row reads Running only while a job of the kind is really going (not waiting on the lane, Kraken or memory), else Waiting. `test_person_started_work_goes_first_5820.py`.
- `activity.window.queue-summary` — **[PARTIAL]** (#5839) **Built 2026-10-19 (engine; the app's line waits on the route regen):** `GET /api/activity/jobs` carries `summary`: what is done, what is left across every kind's row, and about how long is left, from each kind's measured median time per item (its latest 50 finished); the time is absent when nothing queued has been measured, never guessed. `activity.window.expands-to-pages`: `GET /api/activity/jobs/kind/{kind}/items` lists a row's queued jobs in the order the lane picks them, running first, paged. `test_queue_summary_and_items_5839.py`.
- `activity.set-aside-said-once` — **[BUILT]** (#5844) a job set aside after its interruptions says it once and short, with no clock: "Stopped 3 times by the engine stopping; set aside. Resume to carry on." (a row stored before reads "Interrupted 3 times: …" and still offers Resume); a job held behind a set-aside thumbnail says "Waiting for thumbnails (set aside)" and does not repeat the reason. `test_set_aside_said_once_5844.py`.
  started (a run, a try, a Start; any starter but the engine, a synced folder or a kept export) or marked watched,
  then background work (embedding, derivatives, indexing). A queued person-started job never waits behind
  queued background work; behind a RUNNING background job it waits only for that one item (a job is one page's
  embed), then it is the next pick, before the background work queued after it; background work resumes after.
  Its waiting line names the holder ("Waiting for the model lane: Embed for search is running")
  (`fichero-server/tests/unit/jobs/test_person_started_work_goes_first_5820.py`).
- `activity.throttle.hand-started-waits-for-memory-and-heat` — **[PARTIAL]** (#5358) a run a person
  started by hand waits only for memory and heat, never for battery or for the person being at
  the Mac, and its row says which it waits for. Built: a page a person waits for is held only by
  memory pressure and a serious thermal state (`fichero-server/tests/unit/jobs/test_throttle.py`); Find Regions in a hand-started
  run and in a Set Up try holds the same way (`fichero-server/tests/unit/recipes/test_a_hand_started_regions_run_waits_only_for_memory_and_heat_2026_10_20.py`). Still a gap: it is pinned
  below the public surface (see "Pinning"), and the window shows no waiting reason.
- `activity.throttle.one-heavy-when-memory-tight` — **[PARTIAL]** (#5622) while this Mac's memory
  pressure is at warn or above, the heavy lanes (the model lane and the images lane) run **one job at
  a time between them**, whatever started it and in whichever project: the images lane drops to one,
  and neither lane starts a job while the other runs one. A row held so says "Waiting: memory is
  busy, so heavy work runs one job at a time: <what runs> is running". Work started with *Start*
  obeys it too. Before: two projects' "Processing imported pages" ran together (thumbnails on the
  images lane, embeds on the model lane) at pressure warn and 312% CPU. Pressure warn does not hold
  work outright (#5524); it only stops heavy work running side by side. Built (2026-10-09):
  `execution/jobs.py` `_Scheduler._claim`, tested with the real lanes (`fichero-server/tests/unit/jobs/test_one_heavy_when_memory_tight.py`).
  Not yet seen in the app.
- `activity.throttle.use-means-slower` — **[BUILT]** (#5819, owner rulings 2026-10-19) ONE rule for the Mac being used, a
  build, battery, memory and heat, taken by every caller from `throttle.decide` (Find Lines, the lane scheduler,
  derivatives, embeddings, training, Kraken's threads, the machine state; `why_wait` is its holds). *Run
  automatically* keeps working while the person uses the Mac **or a build runs** (`throttle.a_build_is_running`:
  xcodebuild, swift-build, swift-frontend, clang, what runs only while compiling, one `pgrep`, never Xcode merely being
  open): slower, at the lowest priority (background QoS, few threads), never held. Background work holds fully only on
  the Mac on battery or in Low Power Mode, memory pressure, or a serious thermal state, and the waiting line says which
  ("Waiting: the Mac is on battery", "Waiting: memory is tight", "Waiting: the Mac is hot"). Work a person started (a run
  they Started, a try, a watched job; the RUN's starter decides, not each page's own row: an import's own recipe run,
  a synced folder and a kept export are background) goes flat out: fast priority, every core, no waits for use or a
  build; memory and heat hold it, and the Mac on battery slows it (balanced) and says so ("The Mac is on battery:
  going slower"). Leaving the hold resumes. This supersedes the "input in the last 30 s" hold below
  (`fichero-server/tests/unit/jobs/test_using_the_mac_means_slower_5819.py`, `test_one_throttle_rule_5819.py`,
  `test_kraken_never_waits_on_use_or_build_5819.py`).
- `activity.throttle.power-heat-memory` — **[PARTIAL]** (#5358) background lanes slow
  or wait in Low Power Mode, on low battery, under serious thermal state or memory pressure, and
  say so; no setting. Built (2026-10-04): the local-model lane holds a background job while
  macOS's memory pressure is at warn or above, the thermal state is serious, the Mac is on battery
  or in Low Power Mode, or there was input in the last 30 s; the row says which ("Waiting: memory
  is tight", "Waiting: you're using the Mac") and the job runs when it clears. A page a person is
  waiting for waits only for memory and heat (`execution/throttle.py`,
  `fichero-server/tests/unit/jobs/test_throttle.py`). A long job checks at its own boundaries: training on this Mac holds
  at every batch while the Mac is in use, hot or on battery, and lets memory go when it is tight
  (`fichero-server/tests/unit/jobs/test_training_on_this_mac.py`). Still a gap: slowing rather than waiting, and the other lanes.
  **[OK]** (#5685) a recipe step that reads pages inside the run (Find Regions) checks before each page: while
  the throttle holds it, the run's row says so and holds, Stop still heard. What holds is the RUN's starter's (not the
  page row's): a run a person started by hand (and a Set Up try, which a person presses and watches) waits only for memory and heat,
  and on battery goes on slower and says so (#5819); a background run is also held by battery ("Waiting: the Mac is
  on battery") and slowed while the Mac is used (Fable review 2026-10-19 #4, ruled by the manager;
  `fichero-server/tests/unit/recipes/test_a_hand_started_regions_run_waits_only_for_memory_and_heat_2026_10_20.py`); between pages it counts pages, not folders ("Finding regions: 3 of 92 pages"). Before, the row said
  "Running step find-regions: 0 of 1 folder done" while `machine.why_wait` said wait (the 2026-10-11 MCP walk);
  `fichero-server/tests/unit/recipes/test_regions_step_waits_and_counts_pages_5685.py`.
  **[OK]** (#5702) a long job that stops to wait (memory tight, the Mac in use) is always looked at again: its
  project stays on its lane though a scan while the job ran (its row `running`, nothing else waiting) had
  forgotten the project as idle. Before, the lane's thread then ended and the job waited for an unrelated wake;
  training on this Mac failed to resume about 1 run in 5
  (`fichero-server/tests/unit/jobs/test_training_on_this_mac.py`).
  **[OK]** (#5654) a job waiting for memory on the model lane names its own model and that model's own need:
  a call to a model on this Mac's model server its need ("Qwen2.5-VL 3B (OCR) needs about 3.9 GB …"), or,
  with that model already loaded, one more read's margin; a Kraken page "Kraken needs about 2.5 GB …". Before,
  every job said Kraken's floor ("Kraken and the other local models need about 2.5 GB", seen during an MLX
  step on the 2026-10-10 demo). `throttle.model_need`; tests:
  `fichero-server/tests/unit/jobs/test_memory_wait_names_its_model_5654.py`.
  **[OK]** (2026-10-11) a deliberate wait is not a stall: the import queue's watchdog ("Processing imported pages
  stalled at N of M") says nothing while the throttle holds background work, whose rows already say why, and looks
  again a minute later (`derivatives._arm_stall_watchdog`; seen when the queue sat at "Waiting: you're using the
  Mac" and was called stalled every minute). Test: `fichero-server/tests/unit/jobs/test_deliberate_wait_is_not_a_stall.py`.

### E. Durability

- `activity.durable.reopen-leaves-live-jobs` — **[OK]** (review 278) a job a lane thread is running ends only when the
  engine does. Opening a library again (`resume`) leaves every job a lane thread of this engine is running alone: its
  row stays running, an attached Kraken page is not cancelled and no row is reset to waiting or set aside; only an engine
  restart ends them, and the next open then settles them (`activity.durable.queue-is-rows`). The release of a stale
  lane holder is gone, as it could free a lane under a running thread; a lane's holder in the waiting words is named
  only while its row is running. Pinned by
  `fichero-server/tests/unit/jobs/test_only_a_running_job_holds_a_lane.py` (reopening during a live attached page leaves it
  running and the lane held; the waiting words name only a running holder).
- `activity.durable.queue-is-rows` — **[PARTIAL]** (#5357) the task queue and batches
  persist rows; the derivative queue uses `Status.pending` as its queue (`db/manager.py:222-243`);
  ingest, chains, downloads, the re-embed thread and reindex are in memory. Built (2026-10-03):
  the derivative stages and the correction re-embed are rows in `jobs`, and an import's stages
  survive a quit (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`). The open-time `Status.pending` re-queue stays for libraries
  imported before; it no longer runs anything twice. Still a gap: ingest tasks, chains, downloads,
  reindex.
- `activity.durable.enqueue-with-the-change` — **[PARTIAL]** (#5357) the job a change
  implies is written in the change's own transaction. Built for the correction re-embed
  (`ActionRegistry.invoke`, `fichero-server/tests/unit/jobs/test_job_queue.py`) and an import's derivative stages, which commit or roll
  back with the documents (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`).
- `activity.durable.lease-not-fail` — **[PARTIAL]** (#5357) after a crash or quit, an
  interrupted job goes back to waiting and resumes. *Quit — built 2026-10-18:* a quit records each live run that has a checkpoint
  `paused` and the next open resumes it (`activity.run.quit-pauses`); a paused run is not swept on reopen
  (`activity.durable.paused-stays-paused`). *Crash — not built:* a run that was `running` or `accepted` when the engine died
  (no quit to pause it) is still flipped to `failed` on the next open (`workflows/activity.py` `_recover_stale_runs_bg`),
  although its checkpoints are on disk (`workflows/checkpointer.py`). The flip says so — "Interrupted: the engine stopped at HH:MM" —
  and the run offers to read its pages not done as a new run (`compute.run.interrupted-on-start`, #5555); it is not resumed in
  place.
- `activity.durable.dies-with-the-engine` — **[OK]** (2026-10-11) when the engine dies mid-job (killed, not closed),
  nothing reads "running" after it starts again: on the project's open a queued job (an import's page, a model
  download, a recipe run) goes back to waiting, "Interrupted; carries on", and is taken up again from its own
  checkpoint; one interrupted three times is set aside, failed, saying what interrupted it and when, with
  `failed_at` and Resume (`POST /api/activity/jobs/{id}/retry`, which puts the same row back to waiting: one row,
  no `failed_at`); a workflow run reads failed, "Interrupted: the engine stopped at HH:MM, before this run
  finished", and offers its pages not done. Checked live on a scratch engine killed during an import, a recipe run
  and its workflow step (the recipe run carried on and could then be stopped). Fixed with it: the model download's
  and Find the Documents' runners were not registered when the queue first looked after a restart, so their rows
  waited with no runner, named by their id and with no Resume (`jobs._KIND_MODULES`, guarded). Pinned by
  `fichero-server/tests/unit/jobs/test_a_job_that_dies_with_the_engine.py`.
- `activity.retry.one-row` — **[OK]** (2026-10-11) Retry on a failed row (`POST /api/activity/jobs/{id}/retry`) runs it
  again and Activity still shows one row: a queued job's row goes back to waiting with the same work, its
  `failed_at` cleared; a failed or stopped workflow run is run again over the pages it did not do, with the same
  workflow and model, as a new run (the answer's `id`, with `replaces` naming the old run) that takes the old one's
  place in the list (`workflow_execution.core.read_again`, shared with Read Again). Before, Retry on an interrupted
  workflow run's row was refused as "work a workflow run handed in", though the row was the run. Pinned by
  `fichero-server/tests/unit/jobs/test_retry_is_one_row.py` and `test_a_job_that_dies_with_the_engine.py`.
  A retried run reads with the nodes (their settings, provider and model) the original run ran with, kept on its
  record, not with the workflow as it is stored now: a workflow edited after the failure is not what Retry runs, and a
  recipe step's settings carry over, so the retry has the same reader as the recipe and joins a live read of the same
  pages rather than reading them again (`activity.run.one-live-read-per-page`, #5848). The record keeps a node's id,
  tool, label, settings, inputs and provider and model names; anything else on a node is not carried.
- `activity.run.one-live-read-per-page` — **[OK]** (#5848) A page is read by one live run at a time. A run of the same
  workflow with the same reader (every node's settings, the provider and the model) on pages a live run reads
  joins that run for those pages: a Start, a Retry or a resumed recipe step does not read them again, and reads
  only the rest if the live run covers some of them; a start that is wholly covered answers with the live run.
  A recipe step waits for the run it joined, then reports its outcome, naming the run by its workflow. A paused run
  is not live (Pause then Start reads), and a different model or setting is a different read, never joined. Matched
  by the page ids each run recorded: a run started on a folder and one on its pages do not match.
  Pinned by `fichero-server/tests/unit/recipes/test_one_live_read_per_page_5848.py`.
- `activity.durable.paused-stays-paused` — **[OK]** (#5357) a paused job is still
  paused after relaunch. Holds for rows in the `jobs` table (`fichero-server/tests/unit/jobs/test_job_queue.py`) and,
  since 2026-10-08, for workflow runs: the reopen sweep and the interrupted-run marking take only
  running and accepted runs, a paused run is listed in Activity as paused, and its Resume carries on
  from its checkpoint (`fichero-server/tests/unit/jobs/test_durable_5357.py`).
- `activity.durable.run-deletable-after-a-crash` — **[OK]** (#5644) a failed run from a session the engine did not close cleanly can be deleted or cleared, and the project stays usable. Deleting it used to raise DuckDB's FATAL "Failed to delete all rows from index" on a stale index and shut the database for the session. Pinned by `fichero-server/tests/unit/db/test_saved_is_found_after_a_crash.py::test_a_failed_run_can_be_deleted_after_the_engine_was_killed`.
- `activity.durable.poison-item` — **[PARTIAL]** (#5357) an item that fails three times is
  set aside with its reason and the job carries on. Built: a queued job interrupted by a quit or
  crash goes back to waiting and is set aside after three (`fichero-server/tests/unit/jobs/test_job_queue.py`); a job that raises fails
  at once, with its reason.
- `activity.durable.nothing-twice` — **[PARTIAL]** (#5357) a job whose kind, subject and
  inputs fingerprint already finished is skipped; today the derivative stages happen to be
  idempotent and the NLP stage skips marked pages, while re-running a workflow has three different
  behaviours (`safety/run-take-back.md`). Built: queuing a page whose stage is already waiting
  reuses that job (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`); a paused run resumed after a
  relaunch does not read again the page it read before the pause (`fichero-server/tests/unit/jobs/test_durable_5357.py`).
  Still a gap: the inputs fingerprint, and a per-kind check that each queued kind is safe to run twice.

### F. Automatic processing

- `activity.auto.on-add` — **[PARTIAL]** (#5362) on import, thumbnails and
  embeddings always run; the NLP draft only behind a setting that is off by default
  (`nlp_draft.py:61`); Kraken never runs at import despite the 2026-09-04 ruling. Since 2026-10-07
  the project's recipe runs on an import after Start (`activity.auto.on-add-from-recipe`).
- `activity.auto.on-add-from-recipe` — **[OK]** (→ #4950, #4951) what runs when a source is added is
  what the project's recipe lists, after the first yes. Built by `runner.material_arrived`:
  `source.onboard.just-do-it`, `source.onboard.auto.runs-by-itself-honoured`,
  `source.onboard.auto.on-add-refusal-said` (`source/models-chains-and-projects.md`), tested in
  `fichero-server/tests/unit/recipes/test_every_step_runs_to_spec.py` and `test_run_visible_to_spec.py`.
- `activity.auto.what-runs-by-itself` — **[PARTIAL]** (#5362) the project says, in one engine
  read the app and MCP can show, what runs by itself on an import and on a correction, each kind of
  work with whether it runs and why. Built (2026-10-08, engine): `GET /api/recipes/project/automatic`
  (`runner.what_runs_by_itself`), read from the same gates the import and the correction use
  (pictures and search always; the NLP draft and the re-read of names by the Ingestion setting; the
  recipe's steps by its first yes, purposes, What runs by itself and the Start plan, a skipped step
  with the plan's why); an import after Start runs exactly the steps it names
  (`fichero-server/tests/unit/recipes/test_what_runs_by_itself_5362.py`). Still a gap: the app's setup
  and Activity do not show it.
- `activity.auto.reembed-on-change` — **[OK]** (#5360) a reading or segment change
  re-derives the page text and re-embeds it. Built: the re-embed is a queued job written in the
  change's own transaction (`activity.correction-reembed-visible`, `actions/page_text_cache.py:366-376`).
  A direct text edit (`PUT` of `page_content`) queues the same job instead of embedding on the request
  (`fichero-server/tests/unit/jobs/test_text_edit_reembed_is_a_job_5360.py`).
- `activity.auto.reextract-on-change` — **[PARTIAL]** (#5361) after a person
  corrects a page's text, its entities and claims are remade from the corrected text. Built
  (2026-10-03): where the library reads names automatically, a correction takes back the page's
  untouched NLP draft through the audited purge and reads it again; the draft records the text it
  read (`nlp_text_sha`), so unchanged pages and the open-time resume never re-read; a re-run
  extraction workflow misses the cache on changed text
  (`fichero-server/tests/unit/api/test_names_follow_a_correction.py`,
  `fichero-server/tests/unit/workflows/test_cache_key_follows_the_page_text.py`). Built
  (2026-10-08): the re-read is a job of its own, `read-names-again`, queued in the change's own
  transaction by a reading correction and by a direct text edit (no more daemon thread), one
  waiting job per page, shown in Activity and held by the pause; nothing is queued where the
  library does not read names (`fichero-server/tests/unit/api/test_names_follow_a_correction.py`).
  Still a gap: claims from LLM workflows are not withdrawn when the workflow re-runs.
- `activity.derived.names-its-inputs` — **[PARTIAL]** (→ #4925, #5360) pictures,
  search entries, vectors and word analysis name what they were made from (`source.derived.recomputable`);
  claims name their page and offsets but not the text version; entity mentions and NLP drafts name
  nothing.
- `activity.derived.stale-is-marked` — **[PARTIAL]** (#5360) a change marks exactly
  the rows derived from it stale, with the reason, and the Inspector shows "out of date" on them
  until they are remade. Built: the engine reports which stored vectors are stale and why
  (`text-changed`, `model-changed`, `not-embedded`) from the stored text and model
  (`fichero-server/tests/unit/db/test_stale_vectors_marked_5360.py`). The entity Inspector response carries it as `stale_reason`
  (`fichero-server/tests/unit/api/test_routes_entity_inspector.py`). Still a gap: the Mac Inspector does not show
  "out of date" yet, and other derived rows (claims, mentions) have no marker.
- `activity.derived.coalesced` — **[PARTIAL]** (#5360) many corrections to one page
  make one recompute job after a short quiet period. Built: one waiting job per kind and page
  (`fichero-server/tests/unit/jobs/test_job_queue.py`); the page's re-embed waits QUIET_SECONDS and each correction pushes it later
  (`fichero-server/tests/unit/jobs/test_reembed_waits_for_a_quiet_period_5360.py`). Still a gap: the names re-read job does not wait yet.
- `activity.derived.person-work-kept` — **[PARTIAL]** (#5361) a recompute withdraws
  only untouched machine rows; a row a person curated is kept and flagged with old and new excerpt.
  Built: the purge removes only draft rows nobody checked, linked or annotated (and keeps an entity
  another page's claims name); every surviving claim is marked `text_changed_at`. Still a gap: the
  old and new excerpt, and showing the flag in the Inspector. Ruling (2026-10-03): machine rows
  are deleted through the audited purge for now; a reversible `withdrawn` claim state is an option
  to add later.
- `activity.derived.recompute-is-one-step` — **[GAP]** (→ #5245) a recompute's swap is one recorded
  step with its run id and can be taken back.
- `activity.recipe.declares-automatic` — **[GAP]** (→ #4950) a recipe lists the job kinds that run on
  add; the dependency graph comes from the job kinds' declared inputs, never written twice.

## Workflow runs inside the one job model

A review of the workflow runner on 2026-10-01 read it end to end, ran the scheduled path, and
timed Kraken on this Mac. This section says what a workflow run becomes in the job model, lists the
runner's defects as behaviours that must hold, and gives the order to fix them in. Server paths
are relative to `fichero-server/src/fichero_server/`.

### What a workflow run becomes

- **A run is a parent job** (`kind = workflow`). It carries what `workflow_runs` carries today: the
  definition snapshot, the resolved scope, the chosen model, the estimate and the usage.
- **Each step is a child job** (`kind = workflow-step`), one per graph node.
- **Each page in a fanned-out step is a grandchild job** (`kind = page`, or the step's own kind
  such as `find-lines` or `read`), with `(kind, subject, inputs_fingerprint)` as its key. A page
  job writes its output and marks itself `done` in one transaction. On resume a `done` page is
  skipped. This key replaces the node cache, so it is keyed on the text and image the page reads,
  not on the file's path and time or on the workflow and node ids.
- **The jobs table, not LangGraph, is the record** of progress, state and resumption. LangGraph
  stays inside a run as the graph engine: `build_graph`, `Send` fan-out, cross-step state in the
  DuckDB checkpointer, and `interrupt()` for review steps. Because finished pages are rows, the
  checkpointer only needs cross-step state: keep the last checkpoint per run, delete them all when
  the run is done.
- **Leases, not a sweep.** The run job holds a lease while its worker lives. On launch a run whose
  lease has lapsed goes back to `waiting` and re-enters through the resume path, with its snapshot
  and its chosen model; a `paused` run stays `paused` (section 5).
- **Progress is written on purpose.** The per-item callback that today checks pause and cancel
  becomes "update the page job, renew the lease, check pause and cancel". The Activity row, the
  trace and the SSE stream are views of job rows and `job.updated`, not of a replay buffer.
- **Pages flow between steps.** A page goes on to the next step as soon as its last step is done,
  within the residency rules of section 4: the model is loaded once, work is grouped by model, two
  heavy models run together only if both fit, and steps overlap only when they use different
  processors.

**What is deleted.** Six ways to execute a workflow become one, the runner, entered through one
enqueue:

| Today | Becomes |
|---|---|
| the runner (`execution/runner.py`) | **kept**: the one path, writing jobs |
| batch items (`execution/batch.py`, its own `astream` loop) | a batch is a parent job whose children are run jobs; its tables stay only as a migration source |
| the legacy chain executor (`execution/chaining.py` → `workflows/executor.py`, and `/chains/{id}/execute`) | deleted; a chain is a workflow (#4949) |
| chain steps run one after another through the runner (`api/routes/workflow/chains.py`) | a chain is a workflow, so a step is a step job |
| `builder.execute_workflow` (`workflows/builder.py`), used by schedules and triggers | deleted; a schedule or trigger enqueues a run job |
| a sub-workflow's `ainvoke` with no checkpointer (`workflows/subworkflow.py:466-468`) | a child run job of the step that called it, so pause, cancel and the record reach it |

Also deleted or folded: the three cancel registries and two pause registries (the runner's
`_running_workflows` flag, `execution/cancellation.py`, the batch's own events) become job rows and
one in-process wake event; `_generate_workflow_python_code` and the mermaid diagram built per run
go (the diagram is drawn on demand from the snapshot); `recover_stale_runs` failing runs is
replaced by lease expiry; the app's client-side chain loop `runStagedChainClientSide`
(`ContentView+WorkflowBar.swift:166-242`) goes, since it is logic outside the engine and a second
code path.

### G. Workflow runs: defects

- `activity.run.review-step-pauses` — **[PARTIAL]** (#5371, #5429) a review step pauses the run and
  waits for the person's answer, and the answer reaches the tool when the run resumes. Built
  (426fd3e8f): LangGraph's interrupt passes the node wrapper untouched, the runner settles a run
  whose stream ends on an interrupt or a breakpoint as paused ("awaiting_review", with the
  question), and resuming with the answer continues from the checkpoint
  (`fichero-server/tests/unit/workflows/test_review_step_pauses_the_run.py`). Still a gap: the test
  builds the graph by hand. Pinned through the routes too: a run started with `POST /execute` settles `paused`,
  and `POST /threads/{id}/resume` with an answer delivers it to the tool and completes
  (`fichero-server/tests/unit/workflows/test_review_step_pauses_through_the_routes_5429.py`). Still a gap: the
  question reaching the app on the stream's `pause` event is not pinned (#5429).
  (Corrected 2026-10-04: this line said BROKEN after #5371 had landed.)
- `activity.run.scheduled-runs-execute` — **[OK]** (#5372) *Built (2026-10-04): a schedule's run and a file
  trigger's runs start through `runner.start_run` (`runner.run_and_wait`), the way a run by hand
  does, with their record, steps, usage and job row (`started_by` schedule or trigger), on the
  engine's background loop rather than the request's; and a file trigger fires at all (its
  watcher's thread asked for an event loop it did not have, which ended the watcher, and an
  extension named with its dot matched nothing) (`fichero-server/tests/unit/jobs/test_scheduled_and_triggered_runs.py`).* a scheduled or file-triggered run
  executes through the same path as a run started by hand.
- `activity.run.resume-once` — **[OK]** (#5373) resuming a run that is already running is
  refused with 409, so two clicks never start two workers on one checkpoint thread; pinned by
  `fichero-server/tests/unit/workflows/test_resume_once_5373.py`.
- `activity.run.resume-default-workflow` — **[OK]** (#5373) a paused run of a shipped default
  workflow resumes: resume finds the workflow as `/execute` does, falling back to the default; pinned by
  `fichero-server/tests/unit/workflows/test_resume_default_workflow_5373.py`.
- `activity.run.resume-from-snapshot` — **[OK]** (#5373) a run resumes on the graph it started
  with, built from its own snapshot (`workflows/resume_snapshot.as_started`: the snapshot's nodes and edges over the stored
  workflow, so an edit made while paused changes nothing under the checkpoint); pinned by
  `fichero-server/tests/unit/workflows/test_resume_from_snapshot_5373.py`.
- `activity.run.resume-keeps-model` — **[OK]** (#5373) a resumed run uses the provider and model the person chose when it started, read from the run's own snapshot; pinned by
  `fichero-server/tests/unit/workflows/test_resume_keeps_model_5373.py`.
- `activity.run.batch-off-the-request` — **[OK]** (#5374) *Built (2026-10-04): a batch runs on a worker
  thread of its own and its event stream follows it, so a client that disconnects stops listening, not
  the batch; each item is a run started by `runner.start_run`, the way every run by hand starts, with its
  run record, steps, usage and timeline; the batch is a job whose children are its runs; and the
  batch routes use the library's own database (they used the app's, where no workflow is) (`fichero-server/tests/unit/jobs/test_batches_are_jobs.py`).* a batch runs on the engine's work
  path, not on the API's event loop, survives the client disconnecting, and writes a run record per
  item.
- `activity.run.stop-reaches-sub-workflows` — **[OK]** (#5375) *Built (2026-10-04): a sub-workflow's run is
  linked to the run that called it (`cancellation.link_child`), so the parent's Stop and Pause reach
  the child's checks; a page of the child waiting for a lane is held by its parent's row too; and
  the child is a run row under the step that called it, its steps and pages under it (`fichero-server/tests/unit/jobs/test_sub_workflows_are_child_runs.py`).* Stop and Pause reach a
  sub-workflow.
- `activity.run.stop-reaches-economy-htr` — **[OK]** (#5375) Stop (and Pause) take effect between
  files in economy HTR: each file is read off the run's event loop and the step checks for a stop or pause before the next
  (`workflows/tools/economy_htr.py`); pinned by `fichero-server/tests/unit/workflows/test_economy_htr_stops_5375.py`.
- `activity.run.stop-reaches-in-flight-calls` — **[BROKEN]** (#5392, #5375, → #4402) Stop ends an
  in-flight Kraken page or model call rather than waiting for it. Today nothing passes cancellation
  into Kraken's lock and joined thread (`llm/kraken_runtime.py:499-556`) or into a model's HTTP call.
  Built (2026-10-03): Stop reaches a Kraken page still waiting for the lane: its row is cancelled
  ("Stopped by you") and the step ends as stopped, not as a file error
  (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). Still broken: a page already running is waited for, and
  economy HTR's pages are not reached.
- `activity.run.record-keeps-all-history` — **[OK]** (#5376) a long run's record keeps every
  step and page from the start: the event hub keeps every event but the log lines for the saved timeline
  (`WorkflowEventHub.record`), while a late viewer's replay stays the newest 2,000; pinned by
  `fichero-server/tests/unit/execution/test_record_keeps_all_history_5376.py`.
- `activity.run.log-is-bounded` — **[OK]** (#5376) a run's log is bounded in memory and
  appended, not rewritten. *Built 2026-10-18:* the log is a `BoundedLog` (`execution/run_log.py`: the first 200 and the latest
  1,800 lines held, the middle counted; a node boundary appends only the lines since its last flush; the final text says
  how many it leaves out); the node-boundary append was built in #5645; pinned by `test_run_log_bounded_5376.py`.
  The `complete` frame carries each final-state value only when its JSON is within 2,000 characters, else its size
  (`run_log.bounded_final_state`; the same test file). The full state stays on the run's checkpoint. **[OK]** once the
  M4 run is green.
- `activity.run.checkpoints-pruned` — **[PARTIAL]** (#5376) only the last checkpoint per run is
  kept, and all are deleted when the run is done. *Built 2026-10-18:* the run path's checkpointer is built with
  `keep_last_only`, so a save drops the thread's earlier checkpoints and their writes (`workflows/checkpointer.py`;
  `test_checkpoints_pruned_5376.py`); thread history then lists one checkpoint. *Not built, and not safe to build yet:*
  deleting the last one when the run is done. Tried and reverted 2026-10-18: the last checkpoint is the run's final state, and
  it is read after the run is done, by the status route's `current_state` (the review-step test checks the answer reached the
  tool through it, `test_review_step_pauses_through_the_routes_5429.py`), by the run's account (pages done, failures) and by a
  group run's member pages (`test_run_on_any_level_5604.py`). Deleting it needs each of those to read the saved final state
  instead; until then one checkpoint per run is what is kept (it is what bounds the growth). Resume reads the last checkpoint
  of a paused run (#5373).
- `activity.run.live-run-never-evicted` — **[OK]** (#5376) a live run is never dropped from
  the engine's run registry: the cap evicts only runs that have exited (`execution/runner.py`
  `_cap_workflow_state_registry`); pinned by `fichero-server/tests/unit/workflows/test_live_run_never_evicted_5376.py`.
- `activity.run.quit-pauses` — **[PARTIAL]** (#5357) quitting pauses running runs at their next
  boundary, and they carry on at the next launch. *Built 2026-10-18 (engine):* on shutdown each live run with a checkpoint on
  disk is recorded `paused` (`runner.pause_live_runs_for_shutdown`, before the streams close), and a paused run is not swept on
  reopen (`activity.durable.paused-stays-paused`), so it waits for Resume; pinned by `test_quit_pauses_runs_5357.py`.
  *Built (engine):* the quit records the reason (`runner.QUIT_PAUSED_ERROR`) and the library's next open resumes the runs that
  carry it, clearing the reason first so a later pause by a person is left for Resume; a resume that fails leaves the run paused
  with why (`activity.resume_quit_paused_runs`; `fichero-server/tests/unit/workflows/test_quit_paused_runs_resume_5357.py`).
  The quit then waits up to `runner.BOUNDARY_GRACE_SECONDS` (1 s; the app kills the engine soon after) for each asked run to reach
  its boundary and settle `paused`; one that does not is covered by the `paused` record (`test_quit_paused_runs_resume_5357.py`).
  *Not built:* a step that runs longer than the grace is still cut at exit, so its checkpoint is the last one written.
- `activity.run.cache-keyed-on-content` — **[PARTIAL]** (#5360, #5361) a step re-runs when the
  text or image it reads has changed, and is reused when it has not, in any workflow. Built
  (2026-10-03): a text-reading step's key carries a fingerprint of the page's current text, so a
  correction re-runs extraction; image readers keep the file key
  (`fichero-server/tests/unit/workflows/test_cache_key_follows_the_page_text.py`). Still a gap: the
  key includes the workflow and node ids, so the same page and model in another workflow is never
  reused.
- `activity.run.one-way-to-run` — **[BROKEN]** (#5374, → #4949) every run, whether by hand, batch,
  chain, schedule, trigger or sub-workflow, goes through the runner and writes jobs. Built
  (2026-10-04): by hand, a batch's items, a schedule and a file trigger all start through
  `runner.start_run` (`fichero-server/tests/unit/jobs/test_batches_are_jobs.py`, `fichero-server/tests/unit/jobs/test_scheduled_and_triggered_runs.py`); a sub-workflow runs inside the
  step that called it, as a child run of it in the job table, reached by its Stop and Pause
  (`fichero-server/tests/unit/jobs/test_sub_workflows_are_child_runs.py`). Still broken: chains have their own path, and the app has a client-side chain loop
  (#4949).
- `activity.run.where-and-estimate` — **[GAP]** (#5240) before a run starts, the person can see where
  it can run (this Mac, Hugging Face, ACENET, a cloud model) and, for each, its time to run, cost
  and greenhouse gas, each measured, estimated or unknown, never invented. For a whole volume the
  same figures come from `source.onboard.routes-for-the-volume`; `compute.job.choose-where` is the
  chooser and cites this line.
- `activity.run.account` — **[OK]** (#5555, #5498 ruling: Activity is the run's account) a run's status
  and its row in Activity read one account (`workflows/run_account.py`): pages done, failed and left;
  each failed page with its reason (and whether it was read twice); what a page is waiting for (a memory
  wait says "Waiting: memory is tight: … needs about X GB, this Mac has about Y GB free"); the time left
  at the run's own pace; the engine's and the model servers' peak memory (so far, while it runs);
  interrupted, with when the engine stopped; and the offer "Read the N pages that failed". The run's
  node in `GET /api/activity/jobs/{run}` counts its pages from it, and `GET /api/activity/jobs` lists a
  running or failed run with it; the run's status (`/threads/{id}/status`) carries the same `account`.
  Before, Activity read the run's saved timeline and showed a ten-page run as "running, total 0" while
  only the status counted pages. The Activity row shows the failures, the wait, the estimate, the peak
  memory and a *Read the N pages that failed* button (`compute.run.read-failed-again`).
  Tests: `fichero-server/tests/unit/jobs/test_run_account_5555.py`; the row's words,
  `ActivityTableTests` (Swift, `testActivityRunAccount_*`).
  **[OK]** (#5654) one count of failed pages: the account and the job tree said pages_failed 0 and failed 1
  for one run (2026-10-10 demo). In the tree a page's row read again (after a passing cause) counts once, by
  its last attempt, as the account counts it; and the account reads the per-page results of a step that read
  all its pages in one call (not fanned out), so a page that step failed is counted and listed. Tests:
  `fichero-server/tests/unit/jobs/test_run_failures_one_truth_5654.py`.
  **[OK]** (#5654) a recipe run's status points at the step it is running: while a step runs, its
  `child_id` is the step's own job (the recipe run's newest job not yet ended) and a workflow step carries
  that run's account (before, both were null until the step ended). Tests:
  `fichero-server/tests/unit/jobs/test_recipe_status_points_at_running_step_5654.py`.
- `activity.window.icons-names-info` — **[OK]** (#5560) every row of the table shows an SF Symbol for its kind
  (a run, a step, a page, a model load, training, other work) beside its name and one for its state
  (running, waiting, paused, failed, stopped, done) beside its state; a page is named by its file
  (`SM_NPQ_C01_004.jpg`), from the `display_name` (with its `document_id`) the engine's tree gives each page's node (#5561's fields), never by its id (the id
  stays in the details); double-click opens the row's run log and details, and an ⓘ (`info.circle`) button at
  the far right of each row of a run opens the same. Tests: `fichero-server/tests/unit/jobs/test_run_account_5555.py`
  (the page's `display_name`); `ActivityTableTests` (Swift, `testActivityWindowIcons_*`). Not covered: the drawn table
  (no mounted-view harness).

### H. Workflow runs: efficiency

These follow the residency rules of section 4 (load once, group by model, co-run only if it fits,
measure the processors). The timings are from the 2026-10-01 review on this Mac: Kraken segmenting
took 17–20 s a page on the CPU and was no faster on the GPU; about 10 s of that is single-threaded
line post-processing. For 200 handwritten pages the stages today add up rather than overlap.

- `activity.run.pipeline-pages` — **[GAP]** (#5370, #5358) a page moves to the next step as soon
  as its last step is done, so a CPU-bound Kraken step runs under a GPU-bound reading step and the
  first page is readable in about a minute. Today every step waits for all pages, because per-page
  streaming is built but behind a flag that is off (`workflows/builder.py:383-395`). Estimated
  saving on 200 pages: about an hour, 30–45% of the run.
- `activity.run.kraken-workers` — **[GAP]** (#5370) Kraken runs in two or three worker
  processes, each gated by the memory guard and each loading its models once. Today one process
  lock serialises every Kraken page (`llm/kraken_runtime.py:496`), and the segmenter and reader are
  reloaded on every page (`llm/kraken_runtime.py:579-588`, `:599`).
- `activity.run.lines-batched-per-call` — **[GAP]** (#5370) when a recipe reads Kraken lines with
  a vision model, several line crops (or the page with its line boxes) go in one call, with the
  local model server kept warm between steps. One call per line would be 25 calls a page.
- `activity.run.lane-cap-per-mac` — **[PARTIAL]** (#5358) *Built (2026-10-04) for vision pages: every page a cloud model
  reads is a job on the network lane, four at once for the whole Mac, shared by every run (`fichero-server/tests/unit/jobs/test_runs_are_jobs.py`);
  a local model's page holds the local-model lane. Built (2026-10-04) for text-model calls in a
  run too: each holds the same lane, cloud on the network lane, a model served on this Mac on the
  local-model lane (`fichero-server/tests/unit/jobs/test_text_calls_on_the_lane.py`). Built (2026-10-04): a share per provider: while another provider's
  call waits, one provider's calls hold at most all but one of the network lane's slots, so a
  provider stuck on a rate limit gives a slot to another's as soon as one of its calls ends; with
  no other provider waiting, it keeps the whole lane (`fichero-server/tests/unit/jobs/test_provider_share.py`). Its ceiling: a newcomer
  that arrives while one provider holds every slot waits for that provider's next call to end, which
  for a stuck call is as long as its timeout. Chat's calls take the same lanes and share the same cap
  (`fichero-server/tests/unit/jobs/test_chat_on_the_lane.py`). Still a gap: a provider's own stated rate limit.* the cap on concurrent model calls is one per
  Mac, shared by every run. Today it is per run: the semaphore is rebound to each run's event loop
  (`workflows/builder.py:91-127`), and three runs measured 12 calls at once against a cap of 4.
- `activity.run.utility-qos-bounded` — **[GAP]** (#5358) heavy local work runs at utility QoS in
  a bounded lane, and yields to the person by holding the lane back. It never drops to background
  QoS, which measured about 18 times slower for Kraken (`llm/kraken_runtime.py:527-530`).
- `activity.run.progress-on-purpose` — **[GAP]** (#5376) a run reports progress it writes on
  purpose (graph updates and explicit progress), not by translating LangGraph's every internal
  event (`execution/runner.py:305-316`, `:1677-1683`).

### I. The run list (folded from `ui/activity.md`, 2026-10-04)

`ui/activity.md` owned the run list's honesty. It is folded in here and deleted; its behaviours keep
their ids. The run list is `ActivityStore.rebuildRuns` (`fichero/fichero/Models/ActivityStore.swift`),
which merges live executions with each library's history and collects a library's load failure in
`runLoadFailures`; `ActivityViewHelpers.swift` renders it.

How the list is laid out (a live block per project, a background group, finished and interrupted runs in History) is
*Ruled 2026-10-19* (`activity.window.live-block`, `activity.window.history-group`); the assembly rules below stand.

- `activity.store-owns-run-assembly` — **[PARTIAL]** (#3231, #493) `ActivityStore.rebuildRuns` merges live
  and historical runs, sorts and dedupes; the view only renders `runs` and `runLoadFailures`. Pinned
  by fichero/Tests/Unit/general/Models/ActivityStoreRunsTests.swift (testRebuildRunsPatchesEachFreshRowIntoRuns,
  testLoadMoreRunsAppendsWithoutDisturbingExistingRows); the live-over-historical dedupe has no test of its own yet.
- `activity.load-failures-are-honest` — **[OK]** (#3231) a library's failure to load its history
  is collected into `runLoadFailures` and shown as a warning row naming the library, never dropped;
  pinned by fichero/Tests/Unit/general/Models/ActivityStoreRunsTests.swift
  (testActivityWindowHonestState_aFailedLoadNamesItsCauseAndClearsOnTheNextSuccess,
  testJobsPollRefusalReachesTheFooterAndClearsOnTheNextGoodPoll).
- `activity.change-events-patch-not-reload` — **[OK]** an activity change event updates the affected
  row in place; only a real domain mutation goes to the domain stores; neither bumps
  `refreshToken`. Pinned: `ActivityStoreTests.swift`, "folded change frame does NOT bump
  refreshToken (no wholesale run reload)" (`fichero/Tests/Unit/general/Models/ActivityStoreTests.swift:177`).
- `activity.spinner-reflects-process-liveness` — **[BROKEN]** (#4346) a spinner means the run is
  alive and working now; after a run stops, its row has been seen keeping a spinner.
- `activity.stale-runs-settle-across-restarts` — **[PARTIAL]** (#4384, #5357) a run that died with its
  process is settled at the next launch, and a paused or resumable run is not. Built (2026-10-08): a
  paused run is not settled (`fichero-server/tests/unit/jobs/test_durable_5357.py`). Still a gap: a running run is
  still turned into a failed (interrupted) one on reopen, although its checkpoints are on disk.
- `activity.cancellation-boundary-generalized` — **[PARTIAL]** (→ #4402) Stop's check covers every
  per-item tool loop, and Pause shares it. Owned by `activity.run.stop-reaches-in-flight-calls`.
- `activity.standalone-window` — **[PARTIAL]** (#1264, #1559) a standalone Activity window, opened from
  the Window menu, independent of the library window. Built: the window exists
  (`Views/Activity/Window/ActivityMonitorWindow.swift`), a list of workflow runs across every open
  library. What it shows is `activity.window.table` and the behaviours under it (#5415).
- `activity.delete-by-workflow-run` — **[GAP]** (#1830) a run's outputs can be taken back without
  touching sources or other runs. Owned by `safety/run-take-back.md`, reached from the window as
  `activity.window.what-it-made`.
- `activity.columns-move-into-activity-view` — **[GAP]** (#2277) a run's progress and state
  columns live in the Activity window, not in the workflow node editor. Answered by
  `activity.window.measures` and `activity.window.table` (#5415).
- `activity.step-click-jumps-to-comparison` — **[GAP]** (#2277) clicking a step opens a comparison of
  what it made. Undecided: comparison is now panes and a diff lens (`modes-to-panes.md`), so whether
  a step opens that is open question 11.

### Migration order

Each step lands with the tests that pin it, under a new `jobs` test folder in the engine's unit
tests or beside the module.

1. **Fix the independent defects first.** None of these needs the job model. Let LangGraph's
   interrupt pass through the node wrapper and record the run as paused awaiting an answer; skip the
   missing-exit check when the last checkpoint has a pending interrupt. Stop the reopen sweep
   touching paused runs. Make resume refuse a live run, fall back to shipped defaults, rebuild from
   the snapshot and carry the model. Send schedules and triggers through the runner. Move batches
   off the request. Pins: `test_interrupt_pauses_not_fails`, `test_paused_survives_relaunch`,
   `test_resume_twice_is_refused`, `test_resume_default_workflow`,
   `test_resume_keeps_model_override`, `test_resume_uses_snapshot_not_edited_workflow`,
   `test_scheduled_single_run_executes` (a real `_run_single` on a stored workflow; it fails today),
   `test_batch_survives_client_disconnect`, `test_cancel_reaches_subworkflow_child`,
   `test_cancel_reaches_economy_htr_between_files`.
2. **Key the cache on content.** The input's text or image hash, the tool, the model, the prompt
   and the config; not the file's time, not the workflow or node. Pins:
   `test_cache_misses_on_corrected_text`, `test_cache_hits_across_workflows_same_inputs`.
3. **Add the jobs table** by growing `workflows/tasks.py`. The runner writes the run and step jobs;
   the per-item callback writes page jobs. Read-only at first: Activity reads it. Pin:
   `test_run_record_keeps_all_page_steps_beyond_2000_events`.
4. **Leases and resume on launch.** At start-up a run whose lease has lapsed re-enters through the
   resume path; done pages are skipped; checkpoints are pruned. Pins:
   `test_sigkill_mid_run_resumes`, `test_checkpoints_pruned_after_done`.
5. **Lanes.** One lane per resource for the whole Mac in place of per-run semaphores; Kraken worker
   processes; per-page streaming on and its flag deleted. Pins: `test_global_lane_cap_across_runs`
   (three runs never exceed the cap), `test_kraken_model_loaded_once_per_worker`, and a 20-page
   pipelined run with fake tools whose time is close to the slowest step, not the sum.
6. **Fold batch, chains and automation into jobs** and delete the dead executors. Pin: each entry
   point (hand, batch, chain, schedule, trigger, sub-workflow) produces the same job tree for the
   same workflow.
7. **Replace the event firehose** (`astream_events`) with graph updates and explicit progress.
   Pin: the job tree and the SSE stream match for one run, before and after.

**The test that matters most** is `test_sigkill_mid_run_resumes`: start a run over many pages in an
engine subprocess, kill it with `SIGKILL` mid-run, relaunch, and assert the run resumes, every page
is done exactly once, and no artifact is written twice.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | job rows, lease recovery, paused-stays-paused, nothing-twice, invalidation edges, re-extract on correction | `fichero-server/tests/unit/jobs/**` (new), extending `test_page_content_is_a_cache.py`, `test_activity_jobs.py`, `test_run_lifecycle_vocabulary.py` |
| Pure rule (Swift) | y | table row model, roll-up, column formatting off-main | a new `JobsStoreTests.swift` under `fichero/Tests/Unit/general/` |
| MCP / CLI | y | list jobs, pause all, pause/cancel one | `fichero-mcp/tests/test_mcp_generated.py`; CLI generated from OpenAPI |
| Click-around (Mac) | y | pause all → island says paused → relaunch → still paused | `fichero/Tests/UI/…` |
| Load (#4634) | y | 10,000 queued pages: bounded memory, no CPU peg, table pages | `fichero-server/tests/perf/…` |
| iPhone / iPad | n | jobs are seen on the Mac first | — |

The crash leg is the one that matters most: kill the engine mid-run with `SIGKILL`, relaunch, and
assert every job resumed, none failed for being interrupted, none produced a duplicate row.

### Pinning (ruled 2026-10-04)

A behaviour here is tagged **[OK]** only when a test proves it through the public surface: a route,
an audited action, an MCP tool, or a real run started the way the app starts one. Several
scheduler behaviours are pinned today only by tests that drive the queue directly with made-up job
kinds (`fichero-server/tests/unit/jobs/test_job_queue.py`: lanes, group-by-model, two heavy jobs
never together, the poison item, a waiting job surviving a restart; `test_throttle.py`: the
throttle's signals). They stay **[PARTIAL]** until the first slice after this spec's edit re-tests
each one through a route, an action or a real run (#5429).

## Accessibility identifiers

Identifiers: `activity.window` · `activity.table` · `activity.row.<jobId>` · `activity.row.<jobId>.disclosure`
  `activity.toolbar.pauseAll` · `activity.toolbar.resumeAll` · `activity.filter.<name>`
  `activity.mode.button` (main toolbar and Activity window: Run Now / Run Automatically / Pause All) · `activity.toolbar.clearFailed` · `activity.details.workingOn`
  `activity.row.<jobId>.pause` · `.resume` · `.cancel` · `.retry` · `.whatItMade`
  `activity.group.<projectId>` · `activity.group.mac` · `activity.popover` · `activity.popover.macState` (the row) · `activity.popover.macState.<reading>` · `activity.popover.errors`
  `activity.row.<jobId>.details` · `activity.details` · `activity.details.heading` · `activity.details.state`
  `activity.details.progress` · `activity.details.failedPages` · `activity.details.log` · `activity.details.log.copy`
  `activity.details.resources` · `activity.details.retryFailed` · `activity.details.openPage` · `activity.details.showPages`

## Open questions (with recommendations)

1. **Answered** (this spec, ruled 2026-10-04): The Mac's own work is global; the window groups by project with the Mac's work as its own group. **One table for the whole Mac, or one per project?** *Ruled 2026-10-04:* the Mac's own work
   (downloads, installs, model loads) is global, in the Mac's table, and the window groups by
   project with the Mac's work as its own group. *Recommended before:* one `jobs` table per project
   database plus the same table in the global library for Mac-level work (downloads, runtimes);
   the window merges them, as it already merges libraries. A project carries its own queue when it
   moves to another Mac.
2. **Answered** (this spec, ruled 2026-10-04): A hand-started run waits only for memory and heat, and says so. **Does a hand-started run obey the global pause?** *Ruled 2026-10-04:* a run started by hand
   waits only for memory and heat, and says so. *Recommended before:* no. Pausing means "stop working
   by yourself"; a run the person just pressed is what they asked for. The row says it is running
   although background work is paused.
3. **Re-extract after every correction, or only after the person leaves the page?** *Recommend:*
   a quiet period (a minute after the last change to that page) or leaving the page, whichever is
   first; cheap NLP immediately, LLM extraction only if the recipe has it on and the project allows
   the cost.
4. **What happens to a claim a person confirmed when the text under it changes?** *Recommend:* keep
   it, re-find its excerpt in the new text the way highlights are re-found (`highlight_reanchor.py`),
   and flag it only if it cannot be found. Never withdraw a person's claim automatically.
5. **Is the `.activity` sidebar mode kept?** *Recommend:* retire it once the window has the table;
   the island and the window are enough (modes → panes ruling: nodes, not modes).
6. **Kraken at import: on by default?** The 2026-09-04 ruling says yes; the code never wired it.
   *Recommend:* it becomes one line of the starter recipes for handwritten material, so the
   decision is per project, not a global toggle.
7. **Answered** (design lead 2026-10-04, applying the spec's lean): Yes, for the local-ML lane only. **Should throttling yield to the person actively typing?** Spotlight does; it costs a little
   throughput. *Recommend:* yes for the local-ML lane only.
8. **How long is history kept?** *Recommend:* done jobs collapse to their top row after a day and
   are kept for 30 days; failed jobs stay until dismissed; the record (audit log) keeps everything
   regardless.
9. **Answered** (this spec, ruled 2026-10-01): One global queue for everything; remote jobs are rows with lane remote. **Remote jobs: a cluster, a Docker server, a GPU service.** *Ruled 2026-10-01 (the
   maintainer): one global queue for everything, tied into HPC and Docker.* A job sent to a Slurm
   cluster (ACENET), to Fichero's own server image running in Docker on another machine, or to a
   GPU service (Hugging Face Jobs) is a row in the same queue with `lane = remote` and its target
   named; the states `compute/jobs-and-fine-tuning.md` defines map onto `waiting_reason`; no second
   job model. Global pause stops new submissions and polling; it never kills a job already running
   on a cluster (that costs allocation). Cancel on the row cancels it there. Its errors (the
   cluster's own message, the log tail) show in the row like any other. Its result lands through
   the one landing path (`compute.land.*`). The same inputs fingerprint stops a training or
   inference job being sent twice for unchanged inputs.
10. **Answered** (design lead 2026-10-04, applying the spec's lean): The graph, fan-out, cross-step state and interrupt for review steps stay, and nothing else. **How much of LangGraph stays once runs are jobs?** *Recommend:* the graph, `Send` fan-out,
    cross-step state and `interrupt()` for review steps; nothing else. Page jobs carry durability
    and idempotency, so checkpoints shrink to the last one per run. If review steps are rare in the
    shipped recipes, a later review can ask whether a review step could itself be a job that waits
    on a person, which would leave LangGraph as the graph alone.
11. **Does clicking a step open a comparison of what it made?** (from `ui/activity.md`, #2277)
    Comparison is now panes and a diff lens (`modes-to-panes.md`), not the chat tab the issue was
    written for. *Recommend:* a step's row offers "Show what it made", which opens the take-back list
    (`activity.window.what-it-made`); comparing two runs' outputs is the panes' diff lens, opened
    from there, not a second path.
12. **Answered** (this spec, 2026-10-06, #5561): one details view for any row, read from the row's
    job record, with the log under it; a page's row offers *Open the page*. **What does clicking a
    row open?** (from `ui/activity.md`, #1264, #1559) *Recommended before:* its detail below the
    table (§2); a page's row also offers "Open the page".

## Requests to other specs (for the manager to route)

- `ui/workflows.md`: `workflows.run.pause-is-dead-end` and `.stuck-processing-on-cancel-fail` are
  answered by section E; `workflows.defaults.chains-not-persisted` (#3181) by retiring the legacy
  chain executor.
- `ui/automation.md`: schedules and triggers enqueue jobs; their own run histories become filters
  on the one table; `automation.unattended-throttle` (#4740) is answered by section D.
- `source/models-chains-and-projects.md`: recipes gain an `automatic` section; job kinds declare
  inputs and outputs (already proposed there as typed jobs).
- `source/segments-and-geometry.md`: `source.derived.recomputable` widens to the knowledge layer.
- `safety/run-take-back.md`: a job is a run; `run_id` is the one stamp.

Stale tags found by the 2026-10-01 workflow-runner review (corrections for those specs' owners):

- `ui/workflows.md`, `workflows.run.provenance-run-id-on-artifacts` is tagged GAP but is mostly
  built: the run id is set as the task id (`execution/runner.py:1561-1565`, #4313) and fan-out
  carries it. Retag PARTIAL; the gaps are sub-workflow children (their own task id) and the
  scheduled path (#5372).
- `ui/workflows.md`, `workflows.run.pause-is-dead-end` is stale wording: a paused run can be
  cancelled, deleted (`workflows/run_status.py:57-62`) and resumed within one engine lifetime. The
  dead ends now are relaunch (#5357) and review steps (#5371).
- `ui/workflows.md`, `workflows.run.stuck-processing-on-cancel-fail` is tagged GAP but is built for
  the runner and batches (#4315, #4379); still open for schedules and triggers (#5372).
- `ui/workflows.md`, `workflows.run.trace-view` is tagged GAP; `RunTraceModel.swift` exists, so it
  is at least PARTIAL.
- `ui/workflows.md`, `workflows.run.cost-tracking-per-node` is tagged GAP; per-node usage is
  recorded at each step's end (`execution/runner.py:1640-1658`) with a run usage column, so it is
  PARTIAL.
- `ui/workflows.md`, `workflows.run.controls-are-fire-and-forget`, and
  `activity.cancellation-boundary-generalized` (section I; both PARTIAL): accurate but understated; Stop does
  not reach sub-workflows or economy HTR (#5375).
- `ui/workflows.md`, `workflows.defaults.chains-not-persisted`: accurate. The app comment in
  `ContentView+WorkflowChainEngine.swift:9-12` that says chains persist is wrong; the engine's chain
  store is in memory (`execution/chaining.py:831-868`).
- `ui/automation.md`, `automation.run-now`, `automation.run-history.backend` and
  `automation.schedule.crud` are tagged OK, but a scheduled or triggered single run crashes at graph
  build (#5372); only the routes are pinned. Retag `automation.run-now` BROKEN citing #5372.
- Section I, the stale-runs behaviour: BROKEN for a new reason (the settle now exists, and it
  settles too much, failing paused and resumable runs, #5357). Done in the fold.

## Sources

Code read 2026-10-01: `api/routes/system/activity.py`, `importers/derivatives.py`,
`importers/nlp_draft.py`, `actions/page_text_cache.py`, `actions/highlight_reanchor.py`,
`actions/registry.py:255-310`, `db/manager.py:205-260`, `workflows/activity.py:655-760`,
`workflows/activity_store.py:1456-1500`, `workflows/run_status.py`, `workflows/tasks.py`,
`workflows/task_types.py`, `execution/cancellation.py`, `execution/batch.py`,
`api/routes/workflow/chains.py`, `api/routes/ingest/core.py`, `maintenance/conversion_on_open.py`,
`api/routes/search/core.py`, `llm/kraken_runtime.py`, `llm/mlx_model_store.py`,
`llm/local_model_catalog.py`, `api/routes/ai/local_models.py`, `api/routes/ai/local_inference.py`,
`models/knowledge.py:1719-1900`, `core/background_compute.py`; app: `Models/ActivityStore.swift`,
`Views/Activity/Window/ActivityMonitorWindow.swift`, `Views/Activity/ActivityJobsView.swift`,
`Views/Activity/RunControls.swift`, `Views/Components/LiveUpdatesPausedPill.swift`,
`App/FicheroApp.swift:646-690`. Specs: `ui/workflows.md`, `ui/automation.md`,
`safety/run-take-back.md`, `compute/jobs-and-fine-tuning.md`,
`source/models-chains-and-projects.md`, `source/segments-and-geometry.md`.

Workflow-runner review, 2026-10-01 (read, one scheduled run reproduced, Kraken timed on this Mac):
`execution/runner.py`, `workflows/builder.py`, `workflows/cache.py`, `workflows/checkpointer.py`,
`workflows/scheduler.py`, `workflows/file_watcher.py`, `workflows/subworkflow.py`,
`workflows/executor.py`, `execution/chaining.py`, `api/routes/workflow_execution/core.py`,
`api/routes/workflow_execution/threads.py`, `api/routes/workflow/batch.py`,
`workflows/tools/economy_htr.py`, `workflows/tools/catalogue.py`, `api/main.py:1015-1025`.

## Future (ideas, not scheduled)
- (#4044) A bottom Xcode-debug-area style strip showing multiple running agents' progress and tool calls; new chrome, not current work.
- (#5021) a spec-first 'ready to run' review: one pre-run check (sources, model, language, machine, cost) replacing the one-offs; parked by the maintainer, nearest existing line `activity.run.where-and-estimate`.

## Triaged from the backlog (2026-10-04)
- `activity.voiceover-announcements` — **[PARTIAL]** (#3724) import, indexing and workflow runs post an AccessibilityNotification announcement on started, completed and failed. Built: the jobs read every kind of work reports through says it, at the transitions only (a job of its own starting, failing with its reason, finishing or leaving the list; never a progress tick, a page's step, or what was running when the app first looked), several in one read as one announcement (`ActivityStore.announcement(from:to:)`, `ActivityAnnouncementTests`). Owed: hearing it with VoiceOver, and `.accessibilityValue` on the progress views.
- `activity.run-control-is-global` — **[GAP]** (#5116) one global start, stop and pause over every file's steps, with per-file step tracking, for a library left running for days.
- `activity.simple-for-its-reader` — **[GAP]** (#5117) Activity is redesigned from who reads it, not from the existing views.
- `activity.window.newest-first-and-clear-all` **[PARTIAL]** (#5016): the engine lists finished jobs newest first (pinned by fichero-server/tests/unit/jobs/test_activity_newest_first_5016.py); still owed on the Swift side, which needs a screen check: the window lists the newest run at the top, offers a way to delete every run at once, and its first row is never drawn under the title bar. (The 'just now' half is `activity.window.absolute-times`, built 2026-10-04.)
