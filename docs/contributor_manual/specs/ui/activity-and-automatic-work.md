# Activity and Automatic Work — one job model, one window — Design Spec (#5352)

> Milestone: activity
> Manual: TBD — "What Fichero is doing": the Activity window; why work runs by itself when you add
> or correct something; pausing everything, or one job; what happens when you quit, sleep or crash
> (nothing is lost, nothing is done twice); what a job cost; taking a job's work back.

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
- **Selecting a row** shows its detail below the table (the run trace, the log, the model and
  prompt, cost by step), reusing `ActivityDetailView`/`RunTraceView`.
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
  gathering reasons, converting a model, workflow runs, steps and batches. **Not yet rows:** the
  built-in Apple calls (Vision, Foundation Models: `llm.model_call_slot` takes no slot for a
  built-in provider), spaCy, Whisper and other non-model tools inside a workflow (only their step
  is a row), the NLP re-read after a correction (inside the re-embed row), ACENET jobs (not sent:
  `remote_read/slurm.py` describes them), model downloads, installs, runtime provisioning and model
  loads (`activity.global-work-is-the-macs`), conversion on open, ingest progress and
  `/api/search/reindex`.
- `activity.remote-under-its-step` — **[GAP]** (#5240, #5353) a remote job a run starts (a Hugging
  Face Job, a cluster job) is a child of the step that sent it, its far-side state its own row's;
  today reading at scale and training are top-level rows of their own.
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
  progress, conversion on open, `/api/search/reindex` and model downloads report elsewhere.
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
- `activity.one-reindex` — **[BROKEN]** (#5363) there are two reindexes: task-queue
  `REINDEX` and `/api/search/reindex` on FastAPI `BackgroundTasks` (`search/core.py:1559`), the
  second invisible and unresumable.
- `activity.legacy-chain-retired` — **[BROKEN]** (→ #4949) `/chains/{id}/execute` runs with "no thread
  ids, no SSE, no activity records" (`chains.py:814`).

### B. The window

- `activity.window.all-projects` — **[PARTIAL]** (#5354) the Activity window merges
  every open library and the global one (`ActivityMonitorWindow.swift`); unpinned.
- `activity.window.table` — **[GAP]** (#5415, #5354) the window is a table of every job of
  every kind; today it is a list of workflow runs only (`Views/Activity/Window/ActivityMonitorWindow.swift:67`),
  and background jobs appear only in the sidebar mode and the toolbar popover.
- `activity.window.expand` — **[GAP]** (#5415, #5354) a row expands, with a disclosure triangle,
  into its children as `activity.jobs-follow-the-graph` defines them; a failed page shows its
  reason. The engine serves the tree (`GET /api/activity/jobs/{id}`); the app does not read it.
- `activity.window.working-on` — **[GAP]** (#5415, #5354) a running row says what it is
  working on now (as defined in `activity.jobs-follow-the-graph`) and how long remains.
- `activity.window.cost` — **[PARTIAL]** (→ #4343, #5415) a row shows what it cost, summed up
  the tree. Built in the engine: each node of `GET /api/activity/jobs/{id}` has `cost_usd`, null
  unless every call under it is priced (`fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`).
  Still a gap: the window shows it (`activity.window.measures`).
- `activity.window.started-by` — **[GAP]** (#5354) a row says who or what started
  it: a person, the recipe, a schedule, a trigger, an assistant.
- `activity.window.one-surface` — **[GAP]** (#5354) ingest progress, the conversion
  pill, Settings' download bars and the jobs list are views of the same rows or are retired; no
  surface keeps its own progress list.
- `activity.window.honest-state` — **[BROKEN]** (→ #4346, #4384, #5431) a spinner only for a job that is
  running now. The run list's own honesty behaviours are in section I
  (`activity.spinner-reflects-process-liveness`, `activity.stale-runs-settle-across-restarts`).
  A failed load says what failed and clears itself. Today one refused load of a library's runs
  leaves "Couldn't load activity from Local" up for good: the window reloads only when the set of
  libraries or their live run counts change (`Views/Activity/Window/ActivityMonitorWindow.swift:149`,
  `:211`). The refusal it reports was a 401 `bootstrap_mismatch`: the app's first requests after an
  engine respawn still carry the previous token (#5431). The footer names the cause (the engine
  refused the app's credentials, or could not be reached) rather than only a library. A later
  successful load clears it, and it is retried on reconnect. Pinned by an app test: a store whose
  first load fails and whose next succeeds shows no failure. An engine test pins the respawned
  engine's 401 so that it names the branch.
- `activity.window.what-it-made` — **[GAP]** (→ #5245) a finished job opens the list of what it made
  and can be taken back (`safety/run-take-back.md`).
- `activity.document.what-has-been-run` — **[GAP]** (#5434) the reverse of
  `activity.window.what-it-made`: each document has a history of every step that has touched it
  (split, lines, read, names, statements, check). Each entry gives the model, the provider, the
  time (`activity.window.absolute-times`), the cost (null unless priced) and the outcome, as
  recorded when the step ran. One engine read serves two views:
  - the library table's **Done** column, one badge per step that has run with its outcome;
  - the document Inspector's "What has been run" section, newest first.
  The read is batched for the visible rows, never one call per row. It is built from job rows and
  run records, and nothing is stored only for display. Gap: the `jobs` table has no document key
  (`execution/jobs.py:85-111`); a page job names its document only in `subject`.
- `activity.window.measures` — **[PARTIAL]** (#5415) the measures that matter, per run, step and
  page, rolled up the tree, are the table's main columns: **time to run, cost, greenhouse gas, images
  run and steps run**. Built in the engine: each node of `GET /api/activity/jobs/{id}` has `seconds`,
  `cost_usd` (null unless every call under it is priced), `tokens`, `failed`, and pages done and in
  all (`fichero-server/tests/unit/jobs/test_run_tree_rolls_up.py`). Still a gap: greenhouse gas
  (`activity.ghg.estimate-with-its-basis`), images run and steps run as counted measures, and the
  window's columns.
- `activity.ghg.estimate-with-its-basis` — **[GAP]** (#5420) each run, step and page carries its
  greenhouse gas, rolled up the tree: an estimate from the energy it used times the grid intensity
  where that energy was drawn. Energy on this Mac is its power draw over the job's time; on a remote
  target, the target's stated hardware over the job's time. The figure always says its basis
  (measured, estimate or unknown) and is never invented: the same rule as cost and as
  `source.onboard.routes-for-the-volume`. A cloud call whose provider publishes no figure is unknown.
- `activity.window.absolute-times` — **[BROKEN]** (#5415, #5432) times are absolute everywhere
  (started at a clock time, finished at a clock time, elapsed and remaining as durations); no "just
  now". Today every row says "just now", even for a run a day old:
  - the engine sends `started_at` with no time zone and with microseconds (a DuckDB `TIMESTAMP`
    through `isoformat()`, `api/routes/workflow_execution/threads.py:262`);
  - the app's default `ISO8601DateFormatter` cannot parse that, and falls back to `Date()`
    (`Models/ActivityStore.swift:287`);
  - the rows then build relative words by hand (`Views/Activity/UnifiedActivityRow.swift:132`,
    `Views/Activity/ActivityBrowserRow.swift:68`).
  The rule: every timestamp the engine returns is UTC with its zone. The app parses it with the
  one engine-date parser. A time that cannot be parsed is shown as no time, never as now. Pinned by
  two tests:
  - an engine contract test (`test_activity_window_absolute_times__every_run_time_carries_its_zone`):
    every `started_at` and `finished_at` from `GET /api/workflow-execution/runs` and
    `GET /api/activity/jobs` parses with a zone;
  - an app pure-rule test: an engine string of today's shape, an hour old, renders as its clock
    time, not as "just now".
- `activity.window.grouped-by-project` — **[GAP]** (#5415) the window can group its rows by
  project; the Mac's own work (`activity.global-work-is-the-macs`) is a group of its own.
- `activity.window.row-shows-lane-state-reason` — **[PARTIAL]** (#5415) every row shows its state,
  its lane and, while it waits, why. Built: rows carry `state` and `reason`, and waiting rows say
  why ("Paused by you", "Waiting for Kraken", "Waiting: memory is tight", "Waiting: you're using
  the Mac"). Still a gap: no row carries its lane (neither the `jobs` table nor `JobTree` nor
  `BackgroundJob` has it, `api/routes/system/activity.py:127-146`), and the app shows a reason only
  on a failed row (`Views/Activity/ActivityJobsView.swift:64-81`).
- `activity.popover.summary` — **[GAP]** (#5415) the toolbar popover is a summary, not a list:
  what is running, what is waiting and the main reason why, the last three errors, and the Mac's
  state (memory pressure, heat, battery, in use), read from the engine. CPU and GPU percentages
  join it with `activity.lane.measures-processors`.

### C. Pause and start

- `activity.pause.global` — **[PARTIAL]** (#5355) one *Pause Background Work* stops every
  job that started by itself, at its next boundary, and the island says so. Built (2026-10-03):
  `PUT /api/activity/jobs/paused`; while paused the scheduler starts nothing and a waiting job says
  "Paused by you"; `/api/activity/jobs` reports `paused` (`fichero-server/tests/unit/jobs/test_job_queue.py`). The derivative stages
  are held too (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`). Still a gap: the Mac control and the island, and the work not
  yet on the queue (workflow runs started by themselves).
- `activity.pause.global-survives-relaunch` — **[PARTIAL]** (#5355) a Mac paused at quit is
  paused at launch. Built: the switch is an app setting (`background_work_paused`), read by the
  scheduler before every job (`fichero-server/tests/unit/jobs/test_job_queue.py`). Still a gap: the click-around leg.
- `activity.pause.per-job` — **[PARTIAL]** (#5356) Pause, Resume and Cancel on any row, applying
  to its children. Built (2026-10-03, 2026-10-04): any row in the `jobs` table can be paused,
  resumed and cancelled (`PUT /api/activity/jobs/{id}/paused`, `POST /api/activity/jobs/{id}/cancel`);
  a run's row reaches the run and its waiting pages and its sub-workflows; a training Job is
  cancelled on Hugging Face (`fichero-server/tests/unit/jobs/test_job_queue.py`, `fichero-server/tests/unit/jobs/test_runs_are_jobs.py`,
  `fichero-server/tests/unit/jobs/test_sub_workflows_are_child_runs.py`). Still a gap: the window's per-row controls (#5415),
  retry, and pausing every waiting job of one kind at once; and kinds keep stop routes of their own
  beside it (`activity.pause.one-start-stop`).
- `activity.pause.cancel-long-call` — **[PARTIAL]** (→ #4402) cancel is checked at every per-item
  boundary (`execution/cancellation.py`, `builder.py`); a single long call is still waited for. Owned
  by `activity.run.stop-reaches-in-flight-calls`; this line points there.
- `activity.pause.controls-are-actions` — **[PARTIAL]** (#5356) pause, resume, cancel
  and retry are audited actions, reachable from the window, MCP and the command line. Built: the
  global pause is the audited, undoable action `background.pause` (`fichero-server/tests/unit/jobs/test_job_queue.py`); per job, `job.pause`
  (undoable) and `job.cancel`; MCP tools `fichero_jobs`, `fichero_pause_background_work`,
  `fichero_job_pause`, `fichero_job_cancel` (`fichero-mcp/tests/test_mcp_server.py`). Still a gap:
  retry.
- `activity.pause.one-start-stop` — **[PARTIAL]** (#5356) every kind of job is started, paused,
  resumed, cancelled and retried through one pair of routes and actions (`/api/activity/jobs/{id}/…`,
  `job.pause`, `job.cancel`); a kind's own routes are callers of it or are retired. Built: pause and
  cancel on every row (`fichero-server/tests/unit/jobs/test_job_queue.py`, `fichero-server/tests/unit/jobs/test_runs_are_jobs.py`). Still a gap: runs keep their
  own pause and stop routes (`/api/workflow-execution/…`), training its own cancel
  (`/api/training/jobs/{id}/cancel`), gathering reasons its own (`/api/training/reasons/{id}/cancel`),
  batches their own (`/api/batches/{id}/pause|cancel`), each beside the job route; and there is no
  start or retry on it.

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
  needs, switching models only between groups and unloading the old one first. Built: queued jobs
  for the model last used run before any other model's (`fichero-server/tests/unit/jobs/test_job_queue.py`), Kraken pages
  included, named by reader (`kraken:<reader id>`); leaving Kraken for another heavy model frees
  Kraken's resident models first, and leaving the embedder for Kraken frees the embedder; a
  background job for another heavy model waits for 20 s of quiet on the loaded one, so bursts do
  not swap models page by page, while work a person waits for switches at once
  (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). Pages read by a model served on this Mac hold the same lane
  (`fichero-server/tests/unit/jobs/test_local_model_pages_on_the_lane.py`). Still a gap: stopping a local model server on a switch (its restart costs
  30-300 s). A text model served on this Mac holds the lane like a page, called in a run
  (`fichero-server/tests/unit/jobs/test_text_calls_on_the_lane.py`) or by chat (`fichero-server/tests/unit/jobs/test_chat_on_the_lane.py`).
- `activity.lane.co-run-only-if-it-fits` — **[PARTIAL]** (#5358) two heavy models run at once only when their
  measured resident sizes fit this Mac's memory with headroom; on an 8 GB Mac, never. Built: never,
  for now: queued heavy jobs run one at a time and wait while a Kraken page holds Kraken's lock
  (`fichero-server/tests/unit/jobs/test_job_queue.py`); a workflow's Kraken pages are on the same lane, and a vision
  model reading Kraken's lines waits on the network off it (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). Still a gap:
  measuring, and co-running when both fit.
- `activity.lane.measures-processors` — **[GAP]** (#5358) each job's row shows what it uses (CPU, GPU, Neural
  Engine, memory), measured by the engine.
- `activity.lane.overlap-different-processors` — **[GAP]** (#5358, #5370) a CPU-bound step and a GPU-bound
  step can run at the same time when memory allows; two steps on the same processor do not.
- `activity.lane.idle-unload` — **[GAP]** (#5358) a resident model with no work is unloaded after a short idle
  time.
- `activity.throttle.watched-first` — **[PARTIAL]** (#5358) a job a person is waiting
  on goes first in its lane at utility QoS. Built (2026-10-04): handed-in work (a page of a run a
  person started) is ordered first on the local-model lane, and a long background job (training)
  steps aside for it at its next batch (`fichero-server/tests/unit/jobs/test_training_on_this_mac.py`). Built (2026-10-04): a
  queued job can be marked watched, and goes first in its lane at utility QoS; a person's own small change marks its
  synced-folder rewrite so (`fichero-server/tests/unit/jobs/test_synced_folder.py`). Still a gap: other work a person
  waits for that is not handed in (an opened page).
- `activity.throttle.hand-started-waits-for-memory-and-heat` — **[PARTIAL]** (#5358) a run a person
  started by hand waits only for memory and heat, never for battery or for the person being at
  the Mac, and its row says which it waits for. Built: a page a person waits for is held only by
  memory pressure and a serious thermal state (`fichero-server/tests/unit/jobs/test_throttle.py`). Still a gap: it is pinned
  below the public surface (see "Pinning"), and the window shows no waiting reason.
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

### E. Durability

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
- `activity.durable.lease-not-fail` — **[BROKEN]** (#5357) after a crash or quit, an
  interrupted job goes back to waiting and resumes; today every running, accepted **and paused**
  workflow run is flipped to `failed` on reopen (`workflows/activity.py:658-707`), although its
  checkpoints are on disk (`workflows/checkpointer.py`).
- `activity.durable.paused-stays-paused` — **[BROKEN]** (#5357) a paused job is still
  paused after relaunch. Holds for rows in the `jobs` table (`fichero-server/tests/unit/jobs/test_job_queue.py`). Broken for
  workflow runs: their rows are jobs now, but on reopen the run sweep still turns every running,
  accepted and paused run into a failed one (`workflows/activity_store.py:1469-1472`).
- `activity.durable.poison-item` — **[PARTIAL]** (#5357) an item that fails three times is
  set aside with its reason and the job carries on. Built: a queued job interrupted by a quit or
  crash goes back to waiting and is set aside after three (`fichero-server/tests/unit/jobs/test_job_queue.py`); a job that raises fails
  at once, with its reason.
- `activity.durable.nothing-twice` — **[PARTIAL]** (#5357) a job whose kind, subject and
  inputs fingerprint already finished is skipped; today the derivative stages happen to be
  idempotent and the NLP stage skips marked pages, while re-running a workflow has three different
  behaviours (`safety/run-take-back.md`). Built: queuing a page whose stage is already waiting
  reuses that job (`fichero-server/tests/unit/jobs/test_derivatives_on_the_lane.py`). Still a gap: the inputs fingerprint.

### F. Automatic processing

- `activity.auto.on-add` — **[PARTIAL]** (#5362) on import, thumbnails and
  embeddings always run; the NLP draft only behind a setting that is off by default
  (`nlp_draft.py:61`); Kraken never runs at import despite the 2026-09-04 ruling; the project's
  chain never runs by itself.
- `activity.auto.on-add-from-recipe` — **[GAP]** (→ #4950, #4951) what runs when a source is added is
  what the project's recipe lists, after the first yes.
- `activity.auto.reembed-on-change` — **[PARTIAL]** (#5360) a reading or segment change
  re-derives the page text and re-embeds it. Built: the re-embed is a queued job written in the
  change's own transaction (`activity.correction-reembed-visible`, `actions/page_text_cache.py:366-376`).
  Still a gap: a direct text edit (`PATCH` of `page_content`) re-embeds inline on the request.
- `activity.auto.reextract-on-change` — **[PARTIAL]** (#5361) after a person
  corrects a page's text, its entities and claims are remade from the corrected text. Built
  (2026-10-03): where the library reads names automatically, a correction takes back the page's
  untouched NLP draft through the audited purge and reads it again; the draft records the text it
  read (`nlp_text_sha`), so unchanged pages and the open-time resume never re-read; a re-run
  extraction workflow misses the cache on changed text
  (`fichero-server/tests/unit/api/test_names_follow_a_correction.py`,
  `fichero-server/tests/unit/workflows/test_cache_key_follows_the_page_text.py`). The re-read runs
  inside the correction's queued re-embed job (`actions/page_text_cache.py:380-391`). Still a gap:
  it is not a row of its own, and claims from LLM workflows are not withdrawn when the workflow
  re-runs.
- `activity.derived.names-its-inputs` — **[PARTIAL]** (→ #4925, #5360) pictures,
  search entries, vectors and word analysis name what they were made from (`source.derived.recomputable`);
  claims name their page and offsets but not the text version; entity mentions and NLP drafts name
  nothing.
- `activity.derived.stale-is-marked` — **[GAP]** (#5360) a change marks exactly
  the rows derived from it stale, with the reason, and the Inspector shows "out of date" on them
  until they are remade.
- `activity.derived.coalesced` — **[PARTIAL]** (#5360) many corrections to one page
  make one recompute job after a short quiet period. Built: one waiting job per kind and page
  (`fichero-server/tests/unit/jobs/test_job_queue.py`). Still a gap: the quiet period.
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
  builds the graph by hand; the run through the execute and resume routes is not pinned (#5429).
  (Corrected 2026-10-04: this line said BROKEN after #5371 had landed.)
- `activity.run.scheduled-runs-execute` — **[OK]** (#5372) *Built (2026-10-04): a schedule's run and a file
  trigger's runs start through `runner.start_run` (`runner.run_and_wait`), the way a run by hand
  does, with their record, steps, usage and job row (`started_by` schedule or trigger), on the
  engine's background loop rather than the request's; and a file trigger fires at all (its
  watcher's thread asked for an event loop it did not have, which ended the watcher, and an
  extension named with its dot matched nothing) (`fichero-server/tests/unit/jobs/test_scheduled_and_triggered_runs.py`).* a scheduled or file-triggered run
  executes through the same path as a run started by hand.
- `activity.run.resume-once` — **[BROKEN]** (#5373) resuming a run that is already running is
  refused. Today `/threads/{id}/resume` never checks, so two clicks start two workers on one
  checkpoint thread (`api/routes/workflow_execution/core.py:452-570`).
- `activity.run.resume-default-workflow` — **[BROKEN]** (#5373) a paused run of a shipped default
  workflow resumes. Today resume loads the workflow from the store only, with no default fallback,
  and answers 404 (`core.py:452-570`; compare `/execute` at `core.py:311-318`).
- `activity.run.resume-from-snapshot` — **[BROKEN]** (#5373) a run resumes on the graph it started
  with, built from its own snapshot. Today resume rebuilds the graph from the current definition,
  so an edit made while paused changes the graph under the checkpoint.
- `activity.run.resume-keeps-model` — **[BROKEN]** (#5373) a resumed run uses the model the person
  chose. Today resume builds a fresh request and drops the provider and model override
  (`core.py:542-546`).
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
- `activity.run.stop-reaches-economy-htr` — **[BROKEN]** (#5375) Stop takes effect between
  files in economy HTR. Today it runs a synchronous loop on the run's event loop with no progress
  callback (`workflows/tools/economy_htr.py:296`), so Stop waits for the whole step and the log goes
  quiet.
- `activity.run.stop-reaches-in-flight-calls` — **[BROKEN]** (#5375, → #4402) Stop ends an
  in-flight Kraken page or model call rather than waiting for it. Today nothing passes cancellation
  into Kraken's lock and joined thread (`llm/kraken_runtime.py:499-556`) or into a model's HTTP call.
  Built (2026-10-03): Stop reaches a Kraken page still waiting for the lane: its row is cancelled
  ("Stopped by you") and the step ends as stopped, not as a file error
  (`fichero-server/tests/unit/jobs/test_kraken_on_the_lane.py`). Still broken: a page already running is waited for, and
  economy HTR's pages are not reached.
- `activity.run.record-keeps-all-history` — **[BROKEN]** (#5376) a long run's record keeps every
  step and page from the start. Today the saved timeline is the newest 2,000 events of the replay
  buffer (`execution/runner.py:144-171`, `:257-264`), so a 200-page run loses its early history.
- `activity.run.log-is-bounded` — **[BROKEN]** (#5376) a run's log is bounded in memory and
  appended, not rewritten. Today `execution_log_lines` grows without limit and is rewritten in full
  at every step (`execution/runner.py:1984-1988`), and the `complete` frame ships the whole final
  state (`execution/runner.py:2161-2184`).
- `activity.run.checkpoints-pruned` — **[BROKEN]** (#5376) only the last checkpoint per run is
  kept, and all are deleted when the run is done. Today every superstep's full state is stored
  (`workflows/checkpointer.py:39-57`) and rows go only when a thread is deleted
  (`api/routes/workflow_execution/threads.py:1002`).
- `activity.run.live-run-never-evicted` — **[BROKEN]** (#5376) a live run is never dropped from
  the engine's run registry. Today the registry cap evicts the first entry when none has finished
  (`execution/runner.py:273-284`), and the reopen sweep then fails the evicted run
  (`workflows/activity.py:681-689`).
- `activity.run.quit-pauses` — **[BROKEN]** (#5357) quitting pauses running runs at their next
  boundary, and they carry on at the next launch. Today engine shutdown only closes the SSE hubs
  (`api/main.py:1020-1022`), so quit is a crash, and on reopen every running, accepted and paused
  run is failed (`workflows/activity_store.py:76-78`, `workflows/activity.py:658-707`).
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

- `activity.store-owns-run-assembly` — **[PARTIAL]** (#3231, #493) `ActivityStore.rebuildRuns` merges live
  and historical runs, sorts and dedupes; the view only renders `runs` and `runLoadFailures`. No
  pinning test for `rebuildRuns` itself.
- `activity.load-failures-are-honest` — **[PARTIAL]** (#3231) a library's failure to load its history
  is collected into `runLoadFailures` and shown as a warning row naming the library, never dropped.
  No pinning test.
- `activity.change-events-patch-not-reload` — **[OK]** an activity change event updates the affected
  row in place; only a real domain mutation goes to the domain stores; neither bumps
  `refreshToken`. Pinned: `ActivityStoreTests.swift`, "folded change frame does NOT bump
  refreshToken (no wholesale run reload)" (`fichero/Tests/Unit/general/Models/ActivityStoreTests.swift:177`).
- `activity.spinner-reflects-process-liveness` — **[BROKEN]** (#4346) a spinner means the run is
  alive and working now; after a run stops, its row has been seen keeping a spinner.
- `activity.stale-runs-settle-across-restarts` — **[BROKEN]** (#4384, #5357) a run that died with its
  process is settled at the next launch, and a paused or resumable run is not. The settle now
  exists and settles too much: on reopen every running, accepted and paused run is turned into a
  failed one (`workflows/activity_store.py:1469-1472`), although its checkpoints are on disk.
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
| MCP / CLI | y | list jobs, pause all, pause/cancel one | `fichero-mcp/tests/test_mcp_full.py`; CLI generated from OpenAPI |
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
  `activity.row.<jobId>.pause` · `.resume` · `.cancel` · `.retry` · `.whatItMade`
  `activity.group.<projectId>` · `activity.group.mac` · `activity.popover` · `activity.popover.macState`

## Open questions (with recommendations)

1. **One table for the whole Mac, or one per project?** *Ruled 2026-10-04:* the Mac's own work
   (downloads, installs, model loads) is global, in the Mac's table, and the window groups by
   project with the Mac's work as its own group. *Recommended before:* one `jobs` table per project
   database plus the same table in the global library for Mac-level work (downloads, runtimes);
   the window merges them, as it already merges libraries. A project carries its own queue when it
   moves to another Mac.
2. **Does a hand-started run obey the global pause?** *Ruled 2026-10-04:* a run started by hand
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
7. **Should throttling yield to the person actively typing?** Spotlight does; it costs a little
   throughput. *Recommend:* yes for the local-ML lane only.
8. **How long is history kept?** *Recommend:* done jobs collapse to their top row after a day and
   are kept for 30 days; failed jobs stay until dismissed; the record (audit log) keeps everything
   regardless.
9. **Remote jobs: a cluster, a Docker server, a GPU service.** *Ruled 2026-10-01 (the
   maintainer): one global queue for everything, tied into HPC and Docker.* A job sent to a Slurm
   cluster (ACENET), to Fichero's own server image running in Docker on another machine, or to a
   GPU service (Hugging Face Jobs) is a row in the same queue with `lane = remote` and its target
   named; the states `compute/jobs-and-fine-tuning.md` defines map onto `waiting_reason`; no second
   job model. Global pause stops new submissions and polling; it never kills a job already running
   on a cluster (that costs allocation). Cancel on the row cancels it there. Its errors (the
   cluster's own message, the log tail) show in the row like any other. Its result lands through
   the one landing path (`compute.land.*`). The same inputs fingerprint stops a training or
   inference job being sent twice for unchanged inputs.
10. **How much of LangGraph stays once runs are jobs?** *Recommend:* the graph, `Send` fan-out,
    cross-step state and `interrupt()` for review steps; nothing else. Page jobs carry durability
    and idempotency, so checkpoints shrink to the last one per run. If review steps are rare in the
    shipped recipes, a later review can ask whether a review step could itself be a job that waits
    on a person, which would leave LangGraph as the graph alone.
11. **Does clicking a step open a comparison of what it made?** (from `ui/activity.md`, #2277)
    Comparison is now panes and a diff lens (`modes-to-panes.md`), not the chat tab the issue was
    written for. *Recommend:* a step's row offers "Show what it made", which opens the take-back list
    (`activity.window.what-it-made`); comparing two runs' outputs is the panes' diff lens, opened
    from there, not a second path.
12. **What does clicking a row open?** (from `ui/activity.md`, #1264, #1559) *Recommend:* its detail
    below the table (§2); a page's row also offers "Open the page".

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
