# Dev Workflows on the App Engine — Design Spec

> Milestone: dev-workflows
> Manual: TBD — a contributor section ("How Fichero is built", the page Stage 1 of the Dev Pipeline spec writes)
> saying that the dev pipeline is a Fichero workflow you can open on the canvas, and how to run one on a scratch
> path.

> **Status: DRAFT, proposed, not approved.** Written 2026-10-26 from the maintainer's direction of the same day.
> Nothing here is built or ruled until the maintainer approves it. Tags: [OK] built · [PARTIAL] exists, not wired ·
> [GAP] not built · [PROPOSED] decided here, not yet ruled.
>
> Related, not edited here: `harness/deterministic-conductor.md` (the stdlib runner, `pipeline/`),
> `ui/workflows.md` (the canvas and run log), `ui/workflow-node-config.md` (node popover), `ui/research.md` (the
> Research workspace).

## Intent (the design)

The dev pipeline (issue → code → check → review → land → close, plus bug triage, issue reconcile, spec to plan and
the release steps) is expressed as Fichero **workflows**, run by the same LangGraph engine
(`fichero-server/src/fichero_server/workflows/**`) that runs archival work. Fichero workflows are for more than
archives; dev work is the first non-archival use. The maintainer then watches the pipeline on the workflow canvas
and its live, replayable run log, and the in-app Research workspace (tasks, milestones, issues, a human in the
middle) uses the same node types, the same question queue and the same task model, so the app's own agent is
dogfooded the way the pipeline is. Both are built and run with SMALL models: Sonnet and Haiku first, then Qwen big
and small on a Mac Studio (oMLX). A model never moves an item between states; a script step's exit code does.

The stdlib runner (`pipeline/`) stays the engine of record until a workflow has run the same items to the same
result (stage 3). This spec adds nothing to what the runner does; it moves where the steps are declared and
watched.

## Prior art (adopt, don't invent)

- **Microsoft Conductor** (github.com/microsoft/conductor): declared steps in a file; **script steps** routed on
  exit codes; explicit inputs and outputs per step; caps (timeouts, max iterations); **validate before run**. We
  adopt all four. `pipeline.pipeline-as-data` (`deterministic-conductor.md`) already has the same shape in the
  profile's `[[steps]]`; this spec makes a workflow graph the carrier of it instead of a second format.
- **LangGraph** (what the engine already is): `interrupt()` + checkpointer is the pause/park/resume primitive. We
  reuse it; we do not write a second one.
- **Our own runner** (`pipeline/`): the behaviour to reproduce, and the oracle for stage 3 (same inputs, same
  verdicts).
- **GitHub** (`gh`, REST): issues, milestones and PRs are the system of record for work; Fichero reads them as a
  source and does not copy them into a private store.

Deliberately different: the runner keeps its journal and GitHub as truth; a workflow run is a *view and a driver*
of that state, never a second copy of it (`dev-workflows.state-stays-in-github`).

## What exists today (grounded; paths under `fichero-server/src/fichero_server/` unless stated)

- Engine: `workflows/builder.py` builds a LangGraph graph from a `WorkflowDef`; `workflows/registry.py` and
  `registry_builtins.py` hold the tool catalogue; `workflows/tools/*.py` are the node kinds (about 150 modules, all
  archival or text work). `workflows/safe_condition.py` + `resolver.evaluate_condition` give a safe expression
  evaluator for conditions; `workflows/subworkflow.py` has typed sub-workflows.
- Existing dev-shaped nodes: `workflows/tools/cli_agent.py` runs a local CLI agent (Claude/Codex) and returns
  stdout/stderr (#341); `workflows/tools/agent.py` is a ReAct agent node (`create_react_agent`);
  `workflows/tools/mcp.py` exposes external MCP tools as nodes (#5760); `workflows/tools/multi_agent.py` exists.
- Pause/park: `workflows/human_review.py` defines the typed `HumanReviewRequest` and `ask_human()` (LangGraph
  `interrupt()`); `api/routes/workflow_execution/core.py` has `POST /threads/{thread_id}/resume` and
  `_resume_argument`, which delivers `Command(resume=answer)`. `workflows/checkpointer.py` persists state in
  DuckDB. The one caller of `ask_human` today is `workflows/tools/catalogue.py:581`.
  `builder.py` honours `pause_requested(run_id)` and `cancellation_requested(run_id)` at the per-item progress
  boundary (#4402 partial; `ui/workflows.md` `workflows.run.controls-are-fire-and-forget` stays [GAP]).
- Schedules and triggers: `workflows/scheduler.py` (cron, interval, one-time) and `workflows/file_watcher.py`.
- Research data: `models/research.py` (`ResearchProject`, `ResearchPlan`, `ResearchTask` with `TaskStatus`,
  `ResearchNote`, `ResearchChecklist`, `ResearchStep` with `StepTool`) and `api/routes/research/*`; the client
  mirror is `fichero/fichero/Models/ResearchModels.swift`; `ResearchTasksPane` is the surviving task UI.
- Adding a folder: `POST /api/ingest/folder` (`api/routes/ingest/core.py:962`), cancel at `:1304`, status at
  `:1261`. Watching a folder: `workflows/file_watcher.py`. No code reads GitHub: `grep -il github` over the
  engine source finds nothing.
- Scratch isolation: `db/paths.py` and `db/storage.py` read `FICHERO_BASE_PATH`; `security/real_data_guard.py`
  guards against touching real data. Memory rule `bare-engine-calls-open-real-app-db`: a bare engine call opens the
  real app DB; a scratch path is mandatory for any headless run.

## Behaviours

### Node types for dev work

- `dev-workflows.node.script` [GAP] (#6116) — a **script** node runs one argv (no shell string) in a named working
  directory with a `timeout_s`, captures stdout, stderr and the exit code as typed outputs, and routes on the exit
  code (`on_ok`, `on_fail`, optional per-code routes) with no model call. A node with no timeout is refused at
  validation. Reuse: the condition router (`workflows/safe_condition.py`) for routing; `cli_agent.py` is the nearest
  existing node (stdout/stderr only, no exit-code route) and is not changed.
- `dev-workflows.node.git` [GAP] (#6116) — a **git** node offers a closed list of operations (worktree add/remove,
  status, diff stat, rebase onto, merge --no-ff, range-diff, log of a range) as typed inputs, and refuses any
  push to `main` or to a tag matching `v*` (memory rule `main-is-protected-2026-10-25`). Push is its own node, never
  chained after a verdict.
- `dev-workflows.node.gh` [GAP] (#6116) — a **gh** node wraps the read and write calls the pipeline needs (issue list/view/
  edit/comment/close, milestone list/edit, PR create/view/merge, label edit) as typed operations returning JSON.
  Writes go only through this node; it carries an allow-list per workflow, so a triage workflow cannot merge.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — a **worker** (coder/agent) node runs one model session with a role
  (coder, coder-small, reviewer), a model alias (`$small`, `$large`, or Sonnet/Haiku/Qwen ids), a brief and a
  cost/turn cap. Today `workflows/tools/agent.py` (ReAct) and `cli_agent.py` run an agent but have no role, no cap
  and no exit-style result; those are what this node extends. Results are a typed `{verdict|diff|text, cost}`.
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — a **human-question** node parks the run with a typed question
  (text, options, the artifact it is about) and resumes with the answer, **durably**: the run survives an engine
  restart and the answer can come minutes or days later from the Activity surface, the Research workspace, the CLI
  or a page. Today `ask_human()` + `POST /threads/{id}/resume` exist and the catalogue node uses them; there is no
  general node, no queue view and no restart test (see `dev-workflows.run.pause-resume-durable`).
- `dev-workflows.node.validate-before-run` [GAP] (#6116) — saving or running a dev workflow first validates the graph, as
  Conductor does: a step that is not reachable, an input no step writes, a loop without a cap, a script without a
  timeout, a gh write outside the allow-list all refuse the run with a message naming the node. Today
  `workflows/validation.py` validates the archival graph only; it is extended, not duplicated.

### Running them

- `dev-workflows.run.pause-resume-durable` [GAP] (#4402) — pause, resume and stop on a parked run are honest and survive an
  engine restart: the buttons update local state (`workflows.run.controls-are-fire-and-forget`, #4402), a paused
  run can be cancelled or deleted (`workflows.run.pause-is-dead-end`), and a run parked on a human question is
  resumed by `Command(resume=answer)` after the engine restarts (`workflows/activity.py:726`
  `resume_quit_paused_runs` is the existing restart hook). This spec **depends on** those two `ui/workflows.md`
  behaviours and does not restate them as its own; it adds the restart test and the human-question park case.
- `dev-workflows.run.headless-on-scratch` [GAP] (#6116) — `fichero workflow run <id>` (and the equivalent script) runs a
  workflow with no app open, against a **scratch** `FICHERO_BASE_PATH` the runner creates per run; it refuses to
  start if the base path is unset or equals the real app's, via `security/real_data_guard.py`. A headless run opens
  the engine through the same entrypoint the app does (`main()`), not a bare module import, and never opens the real
  app DB. Prints the thread id and exits non-zero on a failed run.
- `dev-workflows.run.pinned-engine` [GAP] (#6116) — the pipeline's workflows run on a **pinned stable engine**, not on the
  engine of the checkout being worked on: a built engine at a recorded version (release-channels spec,
  `harness/release-channels-and-feature-tiers.md`) that a coder's half-edited `fichero_server/**` cannot break. The
  pipeline records the pinned engine id in each run; a run on an engine other than the pinned one is refused.
- `dev-workflows.run.state-stays-in-github` [PROPOSED] — a workflow run holds item state only as GitHub issue/label/
  milestone state plus the runner's journal; the run log is a view of it. A workflow that disagrees with the journal
  stops with a question, it does not win.
- `dev-workflows.run.small-models-only` [GAP] (#6116) — every dev workflow runs with a model alias at Sonnet or Haiku
  tier, then Qwen big and small through the local runtime (oMLX) on the Mac Studio; no node names a frontier model.
  Cost per run is recorded (`workflows.run.cost-tracking-per-node`, #4343 is the shared GAP). The reviewer node's
  verdict agreement with the Claude reviewer is measured over 30 items before Qwen is binding
  (`deterministic-conductor.md` Rulings).
- `dev-workflows.run.no-model-rerun` [PROPOSED] — a node whose input and model match an existing result reuses it
  (memory rule `never-rerun-a-model-pass`); the engine's cache (`workflows/cache.py`) is the carrier.

### Seeing them

- `dev-workflows.visibility.canvas-and-log` [PARTIAL] (#6116) — the maintainer opens a dev workflow on the canvas
  (`ui/workflows.md` §A) and sees the run live: each node's state, its exit code or verdict, the current item, and
  the replayable run log (`WorkflowOutputLog`). Today the canvas and live log exist for archival nodes
  (`workflows.run.output-log-live` [PARTIAL]); dev nodes need only their node-config views
  (`ui/workflow-node-config.md` schema-driven fallback already renders their fields) and a log renderer for
  non-file events.
- `dev-workflows.visibility.runs-from-the-pipeline-page` [GAP] (#6116) — the local pipeline page (`pipeline.dashboard-pages`)
  links each item to its workflow run (thread id) and back; no second dashboard is built.

### Shared with the Research workspace

- `dev-workflows.research.one-task-model` [GAP] (#2067) — a dev **task** (an issue, a build-order step) and a Research
  **task** are one record shape: the existing `ResearchTask` + `TaskStatus` in `models/research.py` is extended
  (a `source` ref such as a GitHub issue URL, a `step` id) rather than a second table. A workflow node can read and
  update tasks through the audited action layer (`actions/registry.py`), as the in-app agent does.
- `dev-workflows.research.one-question-queue` [GAP] (#2067) — a human-question from a workflow and a question from the
  Research agent are one typed `HumanReviewRequest` (`workflows/human_review.py`) shown in one queue, with options
  and the artifact it concerns; the pipeline's `pipeline.maintainer-queue` reads the same queue. Answering from any
  surface resumes the parked run.
- `dev-workflows.research.proposals-are-reviewable` [GAP] (#2067) — a proposed plan (milestone, task list, spec-to-plan) is
  a typed proposal the human accepts, edits or rejects before any `gh` write happens; it reuses `ResearchPlan` and
  its status, and the accept step is a human-question node. This is the "human in the middle" the Research spec's
  `research.manager-with-workers-orchestration` [GAP] and `research.future.agent-operates-projects` [GAP] name.
- `dev-workflows.research.same-node-types` [PROPOSED] — the Research agent's tool list and the dev workflow palette
  draw from one registry (`workflows/registry.py`); a node added for the pipeline (gh, git read-only, script with an
  allow-listed argv) is available to a researcher workflow with no second implementation.

### A repo and GitHub as sources

- `dev-workflows.source.repo-folder-and-index` [PARTIAL] (#6116) — adding the repository to Fichero as a folder works and
  is indexed: `POST /api/ingest/folder` imports it, `file_watcher.py` keeps it current, and code navigation for
  a researcher uses the same search. Today the import path is built for documents and images; a repo (thousands of
  `.py`/`.swift`/`.md` files, `.venv`, build output) needs ignore rules (`.gitignore` + an explicit deny list), a
  text-only file kind, and a cancel that works (`/folder/{task_id}/cancel` exists). Pass: the Fichero repo itself
  adds in under a stated time on the M4, ignores `.venv*`/`build/`, and search finds a symbol name.
- `dev-workflows.source.github-as-source` [GAP] (#6116) — a GitHub repo is a **source** (`source/source-model.md` kinds):
  its issues, milestones and PRs appear as nodes in the library with number, state, labels, milestone and body,
  refreshed by a poll or `gh api` read, read-only by default. The write path is only the `gh` node
  (`dev-workflows.node.gh`). Auth is the user's `gh` login; Fichero stores no token. Evidence of the gap: no
  GitHub reader exists in the engine.

### Rollout

- `dev-workflows.rollout.stdlib-runner-stays` [PROPOSED] — `pipeline/` is not removed or edited to depend on this
  work until stage 3 passes; both can run the same item and a script compares their verdicts and journal rows.
- `dev-workflows.rollout.prove-one-item` [GAP] (#6116) — stage 1: one real item (a docs-guard issue) goes
  brief → code → checks → review → land (to a scratch branch, never pushed) as a workflow on a scratch base path,
  with the runner's checks as script nodes, and produces the same verdict as the runner.

### One activity system (audit 2026-10-26, from the code; no code changed)

Rule: workflows, recipes, the recipe designer and dev workflows all run on the SAME job/activity layer, so one list,
one run log, one Stop and one Pause serve them. The layer is the `jobs` table and scheduler
(`fichero_server/execution/jobs.py`, `activity.one-job-model` in `ui/activity-and-automatic-work.md`), with run rows
and timelines in `workflows/activity_store.py` + `workflows/activity.py`.

- `dev-workflows.one-activity-system.one-job-table` [PARTIAL] (#5353) — rows through the one layer today: workflow
  runs, batches, chains and steps (`jobs.record_run`/`record_batch`/`record_chain`/`record_step`, `execution/jobs.py`
  :485-552); a recipe start is one `run-a-recipe` job (`recipes/runner.py` `enqueue` → `jobs.enqueue_remote`), whose
  workflow cards run as ordinary workflow runs beneath it ("the one job tree the activity spec draws", same file's
  docstring); the six task kinds (`workflows/tasks.py`, `task_workers.TASK_JOB_KINDS`); training
  (`training/job.py`, `local.py`, `reasons_job.py`), IIIF/derivative importers, local-model work (`llm/*`), reindex
  (`jobs.enqueue(db, "reindex", ...)` in `api/routes/search/core.py`). Dev workflows add only job kinds, never a
  second table. The recipe job registry (`recipes/jobs.py`) is a vocabulary of what a step asks for, not a runner: it
  holds no run state, and its job names are the `kind` vocabulary of the jobs table.
- `dev-workflows.one-activity-system.bypasses` [GAP] (#5359) — paths that keep their own state outside the one
  layer: folder import keeps an in-memory `_tasks` dict with its own status and cancel routes
  (`api/routes/ingest/core.py:38,1261,1304`; no `jobs.` call in that file), lost on restart; `workflows/executor.py`
  is test-only dead code per `ui/workflows.md`; the legacy `/chains/{id}/execute` runs with no thread
  (`activity.legacy-chain-retired`, BROKEN, #4949); model downloads and runtime provisioning are not rows
  (`activity.model-work-visible` [GAP], `activity.global-work-is-the-macs` [GAP], #5359); `cli_agent.py` runs a local
  agent with no job row of its own. Each is named so the unify step can close it.
- `dev-workflows.one-activity-system.one-cancel` [PARTIAL] (#4317) — cancel is one primitive for single runs and
  batches (`execution/cancellation.py`) and `jobs._cancel_run` / `_cancel_chain` reach children; a recipe run's Stop
  reaches its step (`activity.recipe-run.stop-reaches-its-step` [OK]). Not reaching: ingest's own cancel route (above).
- `dev-workflows.one-activity-system.one-pause` [GAP] (#5933) — Pause Background Work is one setting
  (`execution/jobs.py` docstring) and `_pause_run` pauses a run, but a recipe run's pause does not reach its running
  step (`activity.recipe-run.pause-reaches-its-step` [GAP]) and a run parked on a human question is not shown as
  waiting for a person in the same list; dev workflows need both.
- `dev-workflows.one-activity-system.one-run-log` [PARTIAL] (#5376) — every run's log is bounded and streamed
  (`execution/run_log.py` `BoundedLog`, appended per node boundary into `workflows/activity_store.py`); script/git/gh/
  worker nodes write through `jobs.note_call_log`/`note_usage` (`execution/jobs.py:361-388`) so tokens and cost land
  in the same rows. Ingest's `_tasks` has its own progress and no stored log.
- `dev-workflows.one-activity-system.dev-uses-it` [PROPOSED] — a dev workflow run is a normal `workflow` job row with
  steps beneath it: it appears in Activity, is stopped and paused there, and is replayed from the same stored log; no
  dev-only run list exists (`dev-workflows.visibility.canvas-and-log` reads these rows).

### The project view (Fichero as the place to manage the Fichero project)

The repository is a library source (`dev-workflows.source.repo-folder-and-index`, `dev-workflows.source.github-as-source`);
a **Project** view over it shows and manages the project from inside the app. It reuses the surfaces that exist and
adds no parallel one: the library tree/browse and Inspector for specs and milestones as nodes
(`ui/sidebar-crud.md`, `ui/modes-to-panes.md`: a project is a sidebar node like a workflow or research project), the
Research workspace's task views for the build order and issue lists (`fichero/fichero/Views/Chat/Research/ResearchTasksPane.swift`,
backed by `models/research.py`), the Activity window for runs
(`fichero/fichero/Views/Activity/ActivityJobsView.swift`, `ProjectRunStrip.swift`), and the one question queue for the
owner's decisions (`dev-workflows.research.one-question-queue`). The pipeline page (`pipeline/web.py`, 142 lines,
`pipeline.dashboard-pages`) stays until this view replaces it and a comparison shows nothing it shows is missing.

- `dev-workflows.project-view.overview` [GAP] (#6116) — one place shows the project at a glance: milestones with
  open/closed counts, what is next (the runner's feeder pick, `pipeline.point-at-a-milestone`), what is running, and
  what waits for the owner. Today the only such view is `pipeline/web.py`.
- `dev-workflows.project-view.specs-and-build-order` [GAP] (#6116) — specs under `docs/contributor_manual/specs` are
  nodes with their status (DRAFT/APPROVED), behaviour tag counts and build order; each Step shows its issue, state
  and dependencies, drawn with the Research task list (`ResearchTask`), so "what is next" is the first open step
  whose dependencies are closed (`pipeline.build-order-shape`).
- `dev-workflows.project-view.issues-and-bugs` [GAP] (#6116) — issues (open and closed), bugs and PRs are browsable
  and filterable by milestone, label, from-user and claimed, from the GitHub source (`dev-workflows.source.github-as-source`),
  with the spec behaviour each cites; no copy is kept (`dev-workflows.run.state-stays-in-github`).
- `dev-workflows.project-view.runs-turns-tokens-cost` [PARTIAL] (#5359) — each item's runs show turns, tokens and
  cost, from the jobs rows (`jobs.note_usage`) and the pipeline's cost sums (`pipeline/budget.py`,
  `pipeline.cost-cap`); Activity already shows runs, and the project view links to them.
- `dev-workflows.project-view.tests-and-reviews` [GAP] (#6116) — each item shows its check results (the pinned
  checks), the review verdict and findings (`pipeline.review`), the shas, and the gate result of the night.
- `dev-workflows.project-view.owner-queue` [GAP] (#2067) — questions waiting for the owner and proposals to approve
  (plans, specs, spec changes) are one list with their options, the same queue as `pipeline.maintainer-queue` and
  `dev-workflows.research.one-question-queue`.
- `dev-workflows.project-view.issue-actions` [GAP] (#6116) — from an issue the owner can comment, label, close with
  a commit sha, or reopen; each is a `gh` node call (`dev-workflows.node.gh`) through the audited action layer, recorded
  with who asked, and never a direct token use by the view.
- `dev-workflows.project-view.approve` [GAP] (#6116) — the owner approves or rejects a spec or a plan in place
  (`dev-workflows.research.proposals-are-reviewable`): approval flips the spec's status line by a reviewed commit
  and files the Step issues (`pipeline.spec-to-issues`); nothing flips on a model's word.
- `dev-workflows.project-view.answer-and-control` [GAP] (#6116) — the owner answers a question (resumes the parked
  run) and starts, pauses or stops work (the milestone to run next, Pause All, a run's Stop) from the same view,
  through `pipeline.pause-all` and the activity layer's one pause and cancel.
- `dev-workflows.project-view.no-parallel-surface` [PROPOSED] — the view is composed of existing panes (library,
  Inspector, Research tasks, Activity) and adds a source kind and a project node, not a new window or a second task
  or activity list; `pipeline/web.py` is retired only by `pipeline.retire-fs-skills`-style owner decision after parity.

## Rulings

None yet. Everything above is proposed.

## Build order

Stage 1 proves one item with nodes built by hand. Stage 2 builds the node types and the pause/resume work. Stage 3
moves the pipeline over, the runner staying until it is proven. Each step is one coder context's worth.

### Stage 1 — prove one item on a scratch path

#### Step 1.1 — headless run on a scratch base path
- Behaviours: `dev-workflows.run.headless-on-scratch`, `dev-workflows.run.pinned-engine`
- Tests: fichero-server/tests/unit/workflows/test_headless_scratch_run.py
- Size: M

#### Step 1.2 — script node and the exit-code router
- Behaviours: `dev-workflows.node.script`, `dev-workflows.node.validate-before-run`
- Tests: fichero-server/tests/unit/workflows/test_script_node.py
- Size: M

#### Step 1.3 — one item through, scratch only
- Behaviours: `dev-workflows.rollout.prove-one-item`, `dev-workflows.rollout.stdlib-runner-stays`
- Tests: fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py
- Depends on: 1.1, 1.2
- Size: M

### Stage 2 — node types and the pause/resume gap

#### Step 2.1 — git and gh nodes with their allow-lists
- Behaviours: `dev-workflows.node.git`, `dev-workflows.node.gh`
- Tests: fichero-server/tests/unit/workflows/test_git_gh_nodes.py
- Size: M

#### Step 2.2 — worker node with role, model alias and cap
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.run.small-models-only`, `dev-workflows.run.no-model-rerun`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py
- Size: M

#### Step 2.3 — durable pause and resume (#4402)
- Behaviours: `dev-workflows.run.pause-resume-durable`
- Tests: fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py
- Size: M

#### Step 2.4 — the human-question node
- Behaviours: `dev-workflows.node.human-question`
- Tests: fichero-server/tests/unit/workflows/test_human_question_node.py
- Depends on: 2.3
- Size: M

#### Step 2.5 — one task model and one question queue with Research
- Behaviours: `dev-workflows.research.one-task-model`, `dev-workflows.research.one-question-queue`, `dev-workflows.research.proposals-are-reviewable`, `dev-workflows.research.same-node-types`
- Tests: fichero-server/tests/unit/research/test_dev_task_and_question_model.py
- Depends on: 2.4
- Size: M

#### Step 2.6 — a repo as a folder
- Behaviours: `dev-workflows.source.repo-folder-and-index`
- Tests: fichero-server/tests/unit/ingest/test_repo_folder_ingest.py
- Depends on: 2.1
- Size: M

#### Step 2.7 — GitHub as a source
- Behaviours: `dev-workflows.source.github-as-source`
- Tests: fichero-server/tests/unit/sources/test_github_source.py
- Depends on: 2.1
- Size: M

#### Step 2.8 — unify the activity bypasses
- Behaviours: `dev-workflows.one-activity-system.one-job-table`, `dev-workflows.one-activity-system.bypasses`, `dev-workflows.one-activity-system.one-cancel`, `dev-workflows.one-activity-system.one-pause`, `dev-workflows.one-activity-system.one-run-log`
- Tests: fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py
- Depends on: 2.3
- Size: M

### Stage 3 — move the pipeline over

#### Step 3.1 — see the pipeline on the canvas
- Behaviours: `dev-workflows.visibility.canvas-and-log`, `dev-workflows.visibility.runs-from-the-pipeline-page`, `dev-workflows.run.state-stays-in-github`
- Tests: fichero-server/tests/unit/workflows/test_dev_run_log_events.py, pipeline/tests/test_page_links_workflow_runs.py
- Depends on: 2.4, 2.5
- Size: M

#### Step 3.2 — dev workflows are ordinary activity rows
- Behaviours: `dev-workflows.one-activity-system.dev-uses-it`
- Tests: fichero-server/tests/unit/workflows/test_dev_run_is_a_job_row.py
- Depends on: 2.8, 3.1
- Size: S

#### Step 3.3 — the project view, read-only
- Behaviours: `dev-workflows.project-view.overview`, `dev-workflows.project-view.specs-and-build-order`, `dev-workflows.project-view.issues-and-bugs`, `dev-workflows.project-view.runs-turns-tokens-cost`, `dev-workflows.project-view.tests-and-reviews`
- Tests: fichero-server/tests/unit/workflows/test_project_view_read.py
- Depends on: 2.6, 2.7, 3.2
- Size: M

#### Step 3.4 — owner actions in the project view
- Behaviours: `dev-workflows.project-view.owner-queue`, `dev-workflows.project-view.issue-actions`, `dev-workflows.project-view.approve`, `dev-workflows.project-view.answer-and-control`, `dev-workflows.project-view.no-parallel-surface`
- Tests: fichero-server/tests/unit/workflows/test_project_view_actions.py
- Depends on: 3.3, 2.5
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | dev-node log rows use the existing renderer | — |
| Availability (Swift) | n | — | — |
| Backend (pytest) | y | node contracts, restart survival, scratch guard | `fichero-server/tests/unit/workflows/` |
| MCP | n | tools are generated from the contract | — |
| CLI | y | `fichero workflow run` headless | `fichero-cli/tests/` |
| Click-around (XCUITest, Mac) | n | not before stage 3 | — |
| iPhone / iPad | n | — | — |
| Load (#4634) | n | — | — |

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual | n | — |
| Contributor | developer docs | y | this spec |
| AI / agent | MCP tool description | y | generated from the new routes |
| Scripter | CLI `--help` | y | `fichero-cli/**` |
| Reference | endpoint reference | y | generated |

## Open questions for the maintainer

1. Is a **pinned engine** the Mac's installed release, or a separate build kept next to the checkout? (Affects
   `dev-workflows.run.pinned-engine` and where scratch runs get Kraken/MLX.)
2. Should the pipeline's journal move into the engine's DuckDB (one store) or stay JSONL with the workflow as a
   view? This spec assumes the second (`state-stays-in-github`).
3. Is a repo imported as a **library source** (visible in the sidebar next to archives) or in a separate dev
   library, so the real archive library never shows 6,000 code files?
4. Which of the `gh` writes may a Haiku-tier node ever make without a human-question first (comment, label, close)?
5. Do dev workflows ship in the app for every user, or behind a contributor tier (`release-channels-and-feature-tiers.md`)?
