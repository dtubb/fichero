# Dev Workflows on the App Engine — Design Spec

> Milestone: dev-workflows
> Manual: TBD — a contributor section ("How Fichero is built", the page Stage 1 of the Dev Pipeline spec writes)
> saying that the dev pipeline is a Fichero workflow you can open on the canvas, and how to run one on a scratch
> path.

> **Status: DRAFT, proposed, not approved.** Written 2026-10-26 from the maintainer's direction of the same day.
> Nothing here is built or ruled until the maintainer approves it. Tags: [OK] built · [PARTIAL] exists, not wired ·
> [GAP] not built · [PROPOSED] decided here, not yet ruled.
>
> Revised 2026-10-26 from the owner's correction of the same day: Fichero already has tasks and task lists in the
> Research workspace, but no spec layer, no plan layer and no GitHub tie-in. This spec now COMBINES them into one model
> of project work (§ One model of project work), synced two ways with GitHub, which the dev pipeline uses first and
> the Research workspace uses for every other project. Further owner additions of the same day: retire chains
> (recipes do what chains did), the folder importer joins the one activity system, a code project is a
> **workspace** source indexed lazily in place, the pipeline acts as a GitHub App bot identity, invited users can
> contribute through the same model, and the release becomes a dev workflow with the owner's yes before anything
> public. Every behaviour names its test (§ Behaviour tests). Later the same day: shared projects (several Ficheros on
> one project, `dev-workflows.shared.*`), GitHub's names in the app (`dev-workflows.combined.github-names`), and the
> owner's rulings on Q1, Q3, Q4, Q6, Q7 and Q8 (§ Rulings).
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
- **GitHub** (`gh`, REST): issues, milestones and PRs are the system of record for a project's work *state*
  (open/closed, labels, milestone, assignee); Fichero keeps a synced mirror keyed by issue URL so it works offline and
  links each issue to its spec behaviour and plan step, which GitHub has no field for
  (`dev-workflows.combined.sync-two-way`).

Deliberately different: the runner keeps its journal and GitHub as truth for state; a workflow run is a *view and a
driver* of that state, and Fichero's mirror never wins a disagreement about state
(`dev-workflows.run.state-stays-in-github`).

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
- Research data (the in-app issues and milestones): `models/research.py` holds `ResearchProject`
  (`ProjectStatus` active/paused/completed/archived, `library_destination_folder_id`), `ResearchPlan` (`project_id`,
  `PlanStatus` draft/active/completed/cancelled, `order_index`: a named, ordered, closable group of tasks, which is
  what a milestone is), `ResearchTask` (`plan_id`, `TaskStatus` pending/in_progress/completed/blocked/cancelled,
  `priority`, `assigned_to`, `completed_at`, free `metadata`: what an issue is), `ResearchStep` (`task_id`, a
  `StepTool` call: web_search, browser_navigate, document_fetch, local_search, with result and error: a run step,
  not a plan step), `ResearchChecklist`/`ChecklistItem`, `ResearchNote` and `SearchSource`. Routes:
  `api/routes/research/crud.py` (projects :135-189, plans :393-440, tasks :534-587, steps :681-706),
  `notes.py` (sources, notes, checklists), `tools.py` (web search, browse, fetch, save). Client mirror
  `fichero/fichero/Models/ResearchModels.swift`; UI `fichero/fichero/Views/Chat/Research/ResearchTasksPane.swift`
  (tabs Tasks, Checklists, Sources, Notes; a plan picker and a plan composer sheet) with `+Actions`, `+Tabs`,
  `+Views`, inside `ResearchWorkspaceView.swift`. No record is called a milestone: the word appears in the server
  only for TEI/KG/bookmark fields and in the client only for `LaunchProfile.milestone` timing.
- Questions to a person: `workflows/human_review.py` `HumanReviewRequest` / `ask_human()`, used by
  `workflows/tools/catalogue.py` and `execution/runner.py`; no Research task or plan carries a question or an
  approval state today.
- Adding a folder: `POST /api/ingest/folder` (`api/routes/ingest/core.py:962`), cancel at `:1304`, status at
  `:1261`. Tying a project to a folder on the engine's disk: `api/routes/sync_folders.py` (`POST ""`, the audited
  `sync.tie`; modes `index` or `keep-arranged`; `specs/source/synced-folder.md`, #4952). Watching a folder:
  `workflows/file_watcher.py`.
- GitHub today: no code reads issues, milestones or PRs. The only GitHub touchpoints are downloads
  (`recipes/htr_united.py` `CATALOG_URL` on raw.githubusercontent.com, `llm/local_models.py` spaCy release URLs) and
  About/onboarding links in the client. The dev pipeline reads and writes GitHub itself, outside the app:
  `pipeline/gh.py` (`read`, and `write(..., dry_run=True)`, every write journaled), `pipeline/feeder.py`
  (`approved_ids` reads spec status lines, `pick`, `order`, `blocked`, `milestone_order`), `pipeline/core.py`
  (`next_issues` queues `write-up` and `triage` items, `ask`/`answer` the maintainer queue, `approve_checks`,
  `close_landed` the closer: landed sha + checks green, residue leaves the issue open, a milestone closes with its
  last issue), and `scripts/close_fixed_issues.py`. `plan <spec>` and `plan-approve <spec> [--apply]` (dry run by
  default; one issue per step, stage labels, `(#N)` on headings, the milestone made) are **in review on runner/b4**
  (2858dbb68, unmerged); on this spec's base, spec approval is
  only the status line `feeder.approved_ids` reads.

- Chains (to be retired): `execution/chaining.py` (868 lines; `WorkflowChain` :143; `ChainStore` :831 keeps chains
  **in memory only**, "could be extended to persist to database"), `api/routes/workflow/chains.py` (1,280 lines:
  CRUD :497-618, paleography preset :626-643, legacy `execute_chain` :666 with no thread, #4949, `stop_chain` :825,
  the step helpers `_load_step_workflow` :846, `_validate_step_workflow` :856, `_record_step_run_accepted` :866,
  `_run_step_workflow` :883, `_step_run_outcome` :895, `execute_chain_steps` :1196 for the Workflow Bar).
  Dependants: `recipes/runner.py` imports the four step helpers (:274-279) and `_step_run_outcome` (:382, :393, :525);
  `execution/jobs.py` registers kind `chain` with `_cancel_chain` → `stop_chain` (:447-458) and `record_chain`
  (:540); the client has `Models/ChainStore.swift`, `Models/WorkflowChain.swift`, `Services/ChainService.swift`
  (+`StepExecution`), `Views/Shell/Toolbar/WorkflowBarChainPersistence.swift` (the bar's one shared chain named
  "Workflow Bar"), `ContentView+WorkflowChainEngine.swift`/`+WorkflowChainActualCost.swift`,
  `Views/Workflow/Library/WorkflowChainListView.swift` and its parts, `Views/Workflow/Editor/ChainEditorView.swift`,
  sidebar entries (`SidebarItem.swift`, `SidebarItem+MoreFactories.swift`, `SidebarItemBuilder+Sections.swift`,
  `SidebarViewTypes.swift`, `AddItemMenu.swift`), `AppState+Readiness.swift` (:60, the chains fetch), the feature
  `workflowChains` (`features.yaml` → `FeatureTiers.generated.swift`, `api/feature_tiers_generated.py`,
  `FeatureManager+Tiers.swift`), the AppleScript class `workflow chain` (`Fichero.sdef`), the CLI's generated
  surface (`fichero-cli/src/fichero_cli/openapi_surface_generated.py`, `client.py`, `__main__.py`) and their tests.
  Not chains, and staying: `ImageEditChain` (`db/storage.py`, `workflows/tools/image_edit_chains.py`) and the
  builder's "chain Sends" (`workflows/builder.py:740`).
- Code indexing: none in the app. No symbol, outline or code search exists in the engine (no tree-sitter, no symbol
  table; `api/routes/document/inspector.py` `document_outline` outlines a document). `training/bakeoff_lines.py:123`
  finds the enclosing git work tree. The pipeline's worktrees come from `pipeline/core.py` `_worktree` (:412) under
  the profile's `repo.worktrees` (`pipeline/config.py:12`). The external precedent is jcodemunch (outline, symbol,
  text search, files read on demand).
- Identity and contributors: the pipeline calls `gh` as the maintainer's login (`pipeline/gh.py` `sh`), authors
  agent commits with `github.agent_email`, and admits work only from `github.allowed_authors`
  (`pipeline/config.py:12`, `pipeline/core.py:394,542,892`); there is no bot identity and no contributor tier.
- Release: `scripts/release-all.sh` (Developer ID DMG, Mac and iOS TestFlight, `--github --draft`),
  `set-release-version.sh`, `stamp_engine_version_into_app.sh` + `check_engine_version_stamp.py`,
  `release-notes-gen.sh`, `build-release-dmg.sh`, `notarize.sh`, `check_release_staples_app.py`, `appcast_upsert.py`
  + `check_sparkle_update_ready.py`, `create-github-release.sh`, `deploy-site.sh`, `publish-release.sh`,
  `nightly-release.sh`; the contract and OpenAPI regeneration is a release commit (274f9af19). The owner runs them by
  hand; #6142 moves them to a PR flow.

What is missing, stated plainly: (1) a **spec layer**: no record holds a spec, its behaviour ids or their tags; specs
are Markdown files only the pipeline's regexes read. (2) a **plan layer**: no record holds a build order of steps
sized for one worker session with dependencies; `ResearchPlan` is a task list, not an ordered, approved build order.
(3) a **GitHub tie-in**: no Research record links to an issue, milestone or PR, and nothing syncs. (4) an **approval
state** on a spec or plan and a question attached to a task.
- Scratch isolation: `db/paths.py` and `db/storage.py` read `FICHERO_BASE_PATH`; `security/real_data_guard.py`
  guards against touching real data. Memory rule `bare-engine-calls-open-real-app-db`: a bare engine call opens the
  real app DB; a scratch path is mandatory for any headless run.

## Behaviours

### One model of project work (combined; spec → plan → milestones → tasks → runs → checks → landing)

One model serves the Fichero dev project, any user's code project and any Research project. It extends the records
that exist (`ResearchProject`, `ResearchPlan`, `ResearchTask`, `HumanReviewRequest`, the jobs table) and adds two
layers above them (spec, plan); GitHub is synced two ways where a project has a repo. The dev pipeline is its first
user, not a parallel system.

| Name (app, API, docs, pipeline, GitHub) | Stored today as | Today | GitHub side | Wins on conflict |
|------------------------------------------|-----------------|-------|-------------|------------------|
| **Project** | `ResearchProject` | [PARTIAL] | the repo (a project may link one) | Fichero on the link |
| **Spec** (ours; GitHub has none): path, title, milestone, status (DRAFT/APPROVED), behaviours `{id, tag, issue}` | Markdown only | [GAP] | the spec file in the repo; a behaviour id appears in the issue body's `Behaviours:` line and the label `stage:<spec>-<n>` (`pipeline.spec-to-issues`); no label per behaviour | Fichero (the repo file as Fichero reads it) |
| **Plan** (ours; GitHub has none): the spec's ordered build order; each **step** `{N.M, title, behaviours, tests, depends_on, size, issue}` | Markdown only | [GAP] | step heading `#### Step N.M — title (#N)` ↔ issue `#N` | Fichero (order, dependencies, links) |
| **Milestone** | `ResearchPlan` | [PARTIAL] | milestone (title, open/closed, due, counts) | GitHub on state; Fichero on `order_index` |
| **Issue** (+ plan step, behaviour ids) | `ResearchTask` | [PARTIAL] | issue (state, state_reason, title, body) | GitHub on state; Fichero on links |
| **Label** | `ResearchTask.metadata` (free) | [GAP] | label | GitHub |
| **Assignee** | `ResearchTask.assigned_to` (free text) | [PARTIAL] | assignee | GitHub |
| **Comment** | `ResearchNote` on an issue | [PARTIAL] | issue comment | GitHub (Fichero appends, never edits another's) |
| **Run** (ours) = a job row (`execution/jobs.py`); a Research tool call stays a `ResearchStep` | job row | [PARTIAL] | a marker comment `<!-- pipeline:<event>:<task> -->` | Fichero |
| **Check / Review** = the run's verdict and findings | pipeline journal | [PARTIAL] | PR checks, PR review | GitHub on PR checks |
| **Pull Request** (landing) = sha on the base branch, or PR merged | pipeline journal | [PARTIAL] | pull request, `Fixes #N` | GitHub |
| **Release** | release scripts | [PARTIAL] | GitHub release | GitHub |
| **Question / Approval** (ours) = `HumanReviewRequest` attached to a spec, plan or issue | `workflows/human_review.py` | [PARTIAL] | optional comment once answered | Fichero |

`TaskStatus` ↔ issue state: open and unclaimed → `pending`; open with `claimed` → `in_progress`; open with an open
dependency or a `blocked` label → `blocked`; closed `completed` → `completed`; closed `not_planned` → `cancelled`.
`ResearchStep` is not a plan step: it is one tool call inside a task's run.

- `dev-workflows.combined.github-names` [GAP] (#6116) — one vocabulary across the app, the API, the docs, the specs,
  the pipeline and GitHub (owner ruling 2026-10-26, Q6): **Project, Milestone, Issue, Pull Request, Label, Comment,
  Release, Assignee**, plus our own **Spec** and **Plan** (GitHub has neither). `ResearchPlan` is shown and named
  Milestone and `ResearchTask` Issue in the UI (`ResearchTasksPane`'s plan picker and composer become the milestone
  picker), in the API (new `/milestones` and `/issues` routes beside `/plans` and `/tasks` in
  `api/routes/research/crud.py`, the old routes kept as aliases for one release and then removed) and in docs; the
  stored records keep their tables and are migrated by renaming with a copy-then-verify step, so no record is lost.
  Pass: every record readable under the old route is readable under the new one with the same id, and a guard fails
  a new UI string or route that says task or plan for an issue or milestone.
- `dev-workflows.combined.entities` [GAP] (#2072) — the records and links in the table above exist, typed (not in
  the free `metadata` dict) so a task can be found by issue URL and a step by spec and number; `ResearchPlan` gains a
  milestone link, `ResearchTask` gains `github_issue {repo, number, url, updated_at}`, `plan_step` and
  `behaviour_ids`; a project with no repo leaves them empty and loses nothing. One record per thing: no dev-only
  task, milestone or question table (`dev-workflows.research.one-task-model`).
- `dev-workflows.combined.spec-layer` [GAP] (#6116) — a project's specs are records read from its spec folder (the
  profile's `repo.specs`; for Fichero `docs/contributor_manual/specs`): status line, milestone, behaviour ids and
  their tags, parsed by the same rules the pipeline and guards use (`pipeline/feeder.py` `approved_ids`,
  `scripts/check_spec_behaviors_are_tagged.py`), so the app and the pipeline never disagree about what is approved.
  The file stays the source; Fichero changes a spec only as a commit on a branch for review.
- `dev-workflows.combined.plan-layer` [GAP] (#6116) — a plan is a spec's build order as records: ordered steps, each
  sized for one worker session (`Size S|M`, at most five behaviours, Tests named; `pipeline.build-order-shape`,
  `scripts/check_spec_build_order_shape.py`), with dependencies. "What is next" is the first open step whose
  dependencies are closed. A plan has its own approval (`dev-workflows.combined.approvals`); changing an approved
  plan asks again. With no repo, the plan lives in Fichero's records only.
- `dev-workflows.combined.github-mapping` [GAP] (#6116) — a project linked to a GitHub repo maps issue ↔ task,
  milestone ↔ `ResearchPlan`, behaviour id ↔ the issue body's `Behaviours:` line and `stage:` label, step heading
  `(#N)` ↔ plan step, PR ↔ landing, as in the table; an issue with no step is a task in its milestone with no plan
  step (a bug, a write-up), never dropped.
- `dev-workflows.combined.read-only-first` [GAP] (#6116) — Stage 1: the mapping is proven **read-only** against the
  real GitHub repo on a scratch `FICHERO_BASE_PATH` (`dev-workflows.run.headless-on-scratch`): every open issue,
  milestone and PR of this repo lands as a task, milestone or landing with the right status and links, the
  pipeline's `next_issues` pick equals the model's "what is next", and no write reaches GitHub (the `gh` node in
  dry-run; a write attempt fails the test).
- `dev-workflows.combined.sync-two-way` [GAP] (#6116) — sync **pulls** every 5 minutes per project and when a project
  is opened (owner ruling 2026-10-26: pull only, no webhooks; the engine is usually not reachable from the internet),
  using conditional reads (`If-None-Match` / `since`) so an unchanged repo costs no quota; it pushes only
  through the `gh` node (`pipeline/gh.py` `write` is the model: one function, journaled, dry-run in tests). Conflict
  rules: **GitHub wins for state** (open/closed, state_reason, labels, assignee, milestone membership, title, body);
  **Fichero wins for plan and spec links** (step, behaviour ids, order, approvals). A Fichero edit to a state field
  is a pending write stamped with the `updated_at` it was made against; if GitHub changed since, the write becomes a
  question, it does not overwrite. If a human strips the behaviour ids from an issue body, Fichero keeps its link and
  raises the drift in the queue rather than rewriting the body. Each sync is one job row
  (`dev-workflows.one-activity-system.dev-uses-it`), one per repo at a time.
- `dev-workflows.combined.close-only-by-closer` [PROPOSED] — Fichero never closes an issue or milestone except by the
  closer's rule (`pipeline.closes-issues`, `scripts/close_fixed_issues.py`): the commit **landed** on the base
  branch, its checks **green**, and **no residue** reported; a residue updates the body with what is left and keeps
  it open; a milestone closes when its last issue closes; a dry-run line is journaled before each close. An issue
  closed on GitHub by anyone else is mirrored closed (GitHub wins); a reopened one reopens its task.
- `dev-workflows.combined.offline` [GAP] (#6116) — with no network or no `gh` login the model works from the mirror:
  every view reads, the age of the last sync is shown, edits queue as pending writes that survive a restart (they are
  rows), and nothing claims to be synced. On reconnect it pulls first, then pushes pending writes in order, each
  re-checked under `dev-workflows.combined.sync-two-way`. A project with no repo is always "offline" and needs none
  of this.
- `dev-workflows.combined.rate-limits` [GAP] (#6116) — sync stays inside GitHub's REST limits for the user's token:
  conditional reads first, back off on 403/429 until `Retry-After` / `X-RateLimit-Reset`, space content-creating
  writes (comments, issues) to respect secondary limits, and show "rate limited until HH:MM" instead of failing a
  run. The remaining quota is recorded on the sync job row.
- `dev-workflows.combined.writes-need-approval` [PROPOSED] — who may write what (owner ruling 2026-10-26, Q4). **A
  model node** (a worker, the Research agent, any node whose output a model wrote) does **bookkeeping only**: a
  comment, a label, moving an issue between milestones. **Committing, landing, closing and pushing** are done only by
  the runner's gated script steps (the verify-all and commit gates, the closer's rule in
  `dev-workflows.combined.close-only-by-closer`), never by a model node; the `gh` and `git` nodes refuse those
  operations when called from a model node. Filing a plan's issues needs **the approved plan**
  (`pipeline.spec-to-issues`); every other write a model proposes (a new issue outside a plan, a new or closed
  milestone, a body edit, a reopen) needs **an owner answer**. A push to `main` or a `v*` tag is never a sync write
  (`dev-workflows.node.git`). Reads need nothing.
- `dev-workflows.combined.approvals` [GAP] (#2067) — three human-in-the-middle approvals, each a
  `HumanReviewRequest` attached to its record and shown in the one queue (`dev-workflows.research.one-question-queue`):
  **approve spec** (DRAFT → APPROVED, the status line flipped by a reviewed commit), **approve plan** (the build
  order is accepted and its steps may be filed; owner ruling 2026-10-26, Q8: first as the runner's `plan-approve
  <spec> [--apply]`, dry run by default, in review on runner/b4, then in the app with this model), **answer question** (a parked run or a write-up resumes). Each
  records who and when; a model never approves or answers (`pipeline/core.py` `WORKER_FORBIDDEN`,
  `pipeline.three-faces`: approve and answer are never over MCP).
- `dev-workflows.combined.repo-as-project-source` [GAP] (#6116) — a repo becomes a project by adding it as a
  **workspace** (`dev-workflows.workspace.source-kind`) and attaching that workspace to a Research project; Fichero
  reads the `origin` remote and proposes the GitHub link, which the owner confirms; then the spec folder is read into
  the spec and plan layers and the first pull runs. Detaching keeps the records and stops sync. A synced folder
  (`api/routes/sync_folders.py`, `sync.tie`) is NOT the carrier: `sync_folder.py` writes exports and corrections back
  into the tied folder, and Fichero must never write into a working tree.
- `dev-workflows.combined.research-projects` [GAP] (#2070) — the same records serve a non-dev Research project: a
  brief in place of a spec (optional), a plan of ordered steps, milestones, tasks, runs (the agent's tool calls as
  `ResearchStep`s under a job row), checks (a checklist or a reviewer verdict) and closing, with the same three
  approvals; linking a GitHub repo is optional and uses any repo the user's `gh` login can see. `ResearchTasksPane`
  shows them; no second task UI is built.
- `dev-workflows.combined.pipeline-is-first-user` [GAP] (#6116) — Stage 3: the pipeline reads and writes through this
  model, not beside it: the feeder's pick (`pipeline/core.py` `next_issues`, `feeder.pick`) reads the pointed
  milestone's tasks; spec approval is the spec layer's (`feeder.approved_ids` today); `pipeline.spec-to-issues` is
  the approved plan's filing (`plan-approve`, in review on runner/b4); `write-up`, `triage` and `ask` items and `approve-checks` are questions and approvals
  in the one queue; `answer` resolves one; `close-landed` is `dev-workflows.combined.close-only-by-closer`. The
  runner's own `gh` reads are retired only after a run of the same items gives the same picks and closes
  (`dev-workflows.rollout.stdlib-runner-stays`).

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
  pipeline records the pinned engine id in each run; a run on an engine other than the pinned one is refused. Owner
  ruling 2026-10-26 (Q1): first a **separate pinned build** kept next to the checkout; only once the pipeline is
  proven on it does it move onto the app's own engine (dogfooding, Stage 3,
  `dev-workflows.combined.pipeline-is-first-user`).
- `dev-workflows.run.state-stays-in-github` [PROPOSED] — a workflow run holds item state only as GitHub issue/label/
  milestone state plus the runner's JSONL journal, which stays the source of truth (owner ruling
  2026-10-26, Q2); the run log and the activity rows are a view built from it, and the Fichero issue mirror
  (`dev-workflows.combined.sync-two-way`) is a cache of it, never a second truth. A workflow that disagrees with the
  journal or with GitHub stops with a question, it does not win.
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
  (the GitHub link and the plan-step and behaviour links of `dev-workflows.combined.entities`) rather than a second
  table. A workflow node can read and update tasks through the audited action layer (`actions/registry.py`), as the
  in-app agent does.
- `dev-workflows.research.one-question-queue` [GAP] (#2067) — a human-question from a workflow and a question from the
  Research agent are one typed `HumanReviewRequest` (`workflows/human_review.py`) shown in one queue, with options
  and the artifact it concerns; the pipeline's `pipeline.maintainer-queue` reads the same queue. Answering from any
  surface resumes the parked run.
- `dev-workflows.research.proposals-are-reviewable` [GAP] (#2067) — a proposed plan (milestone, task list, spec-to-plan) is
  a typed proposal the human accepts, edits or rejects before any `gh` write happens; it carries the approval state of
  `dev-workflows.combined.approvals` (the three approvals are defined there, once), and the accept step is a
  human-question node. This is the "human in the middle" the Research spec's
  `research.manager-with-workers-orchestration` [GAP] and `research.future.agent-operates-projects` [GAP] name.
- `dev-workflows.research.same-node-types` [PROPOSED] — the Research agent's tool list and the dev workflow palette
  draw from one registry (`workflows/registry.py`); a node added for the pipeline (gh, git read-only, script with an
  allow-listed argv) is available to a researcher workflow with no second implementation.

### A repo and GitHub as sources

- `dev-workflows.source.repo-folder-and-index` [PARTIAL] (#6116) — adding the repository to Fichero as a folder works and
  is indexed (superseded for code projects by the workspace source, `dev-workflows.workspace.*`, which imports no
  file; this behaviour now pins only that the folder importer refuses or warns on a git work tree and that its ignore
  rules are the workspace's): `POST /api/ingest/folder` imports it, `file_watcher.py` keeps it current, and code navigation for
  a researcher uses the same search. Today the import path is built for documents and images; a repo (thousands of
  `.py`/`.swift`/`.md` files, `.venv`, build output) needs ignore rules (`.gitignore` + an explicit deny list), a
  text-only file kind, and a cancel that works (`/folder/{task_id}/cancel` exists). Pass: the Fichero repo itself
  adds in under a stated time on the M4, ignores `.venv*`/`build/`, and search finds a symbol name.
- `dev-workflows.source.github-as-source` [GAP] (#6116) — a GitHub repo is a **source** (`source/source-model.md` kinds):
  its issues, milestones and PRs appear as nodes in the library with number, state, labels, milestone and body,
  refreshed by a poll or `gh api` read, read-only in Stage 1. Writes come in Stage 2 under
  `dev-workflows.combined.sync-two-way` and `dev-workflows.combined.writes-need-approval`, and only through the `gh`
  node (`dev-workflows.node.gh`). Auth for a user's project is the user's `gh` login and Fichero stores no token;
  the dev pipeline acts as the bot identity (`dev-workflows.identity.github-app-bot`). Evidence of the gap: no
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
- `dev-workflows.one-activity-system.folder-import-is-a-job` [GAP] (#5359) — the folder importer runs as a job row
  (a new kind, e.g. `import-folder`, with one child per file batch) instead of the in-memory `_tasks` dict
  (`api/routes/ingest/core.py:38`): `GET /folder/{task_id}/status` (:1261) and `POST /folder/{task_id}/cancel`
  (:1304) read and cancel through `execution/jobs.py` (the routes stay, as thin readers, so clients do not break),
  progress and the log go to the one run log, the import shows in Activity, Pause Background Work pauses it, and an
  import interrupted by an engine restart shows as stopped with what it took in, not vanished.
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
  with the spec behaviour each cites; they are the synced mirror, and GitHub wins on state
  (`dev-workflows.run.state-stays-in-github`, `dev-workflows.combined.sync-two-way`).
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
  (`dev-workflows.research.proposals-are-reviewable`, `dev-workflows.combined.approvals`): approval flips the spec's
  status line by a reviewed commit and files the Step issues (`pipeline.spec-to-issues`); nothing flips on a model's
  word. This behaviour is the project view's button for it; the rule lives in `combined.approvals`.
- `dev-workflows.project-view.answer-and-control` [GAP] (#6116) — the owner answers a question (resumes the parked
  run) and starts, pauses or stops work (the milestone to run next, Pause All, a run's Stop) from the same view,
  through `pipeline.pause-all` and the activity layer's one pause and cancel.
- `dev-workflows.project-view.no-parallel-surface` [PROPOSED] — the view is composed of existing panes (library,
  Inspector, Research tasks, Activity) and adds a source kind and a project node, not a new window or a second task
  or activity list; `pipeline/web.py` is retired only by `pipeline.retire-fs-skills`-style owner decision after parity.

### A code project without importing its files (the workspace source)

A **workspace** is a source kind: one live git repository and its worktrees (a repo can have several), indexed lazily
in place. Nothing is copied into the library, no document is made per file, and Fichero never writes into a working
tree. It is what a code project (Fichero's own, or a user's) is attached by (`dev-workflows.combined.repo-as-project-source`).
Today none of it exists (§ What exists today, "Code indexing").

- `dev-workflows.workspace.source-kind` [GAP] (#6116) — the owner adds a workspace by picking a folder inside a git
  repo; Fichero resolves the repo root (as `training/bakeoff_lines.py:123` does), lists its worktrees
  (`git worktree list --porcelain`) and shows the workspace in the sidebar as a source with its worktrees beneath,
  each with branch, head sha and dirty state. Adding is read-only: no file is imported, moved or written, and
  removing the workspace deletes only Fichero's index. Owner ruling 2026-10-26 (Q3): the Fichero repo is a
  **separate dev library** holding this workspace, not shown to a user unless they are told how to open it; once it
  is good it is shared so people can connect and help (`dev-workflows.shared.*`, `dev-workflows.contrib.*`).
- `dev-workflows.workspace.lazy-index` [GAP] (#6116) — outline, symbol lookup and text search over a worktree, built
  per file on first need and cached by `(path, blob sha)`, refreshed by `workflows/file_watcher.py` events; file
  contents are read on demand by line range, never stored whole; ignore rules are `.gitignore` plus a deny list
  (`.venv*`, `build/`, `DerivedData/`, `node_modules/`, binaries over a size cap). Pass: on this repo, the first symbol
  query answers without indexing the whole tree, a second answers from cache, and `.venv*` is never read.
- `dev-workflows.workspace.context-for-agents` [GAP] (#2072) — Research agents, workflow nodes and the MCP read-only
  tools use a workspace as context through read-only tools in the one registry (outline, symbol, search, read a line
  range; `dev-workflows.research.same-node-types`); none can write a file through them.
- `dev-workflows.workspace.worktrees-map-to-tasks` [GAP] (#6116) — the pipeline's worktrees (`pipeline/core.py`
  `_worktree`, profile `repo.worktrees`) appear as worktrees of the Fichero workspace, each linked to the task (issue)
  it works on through the combined model, so the project view shows which worktree holds which item.
- `dev-workflows.workspace.github-tie` [GAP] (#6116) — a workspace's `origin` remote gives the GitHub repo of
  `dev-workflows.combined.github-mapping`: its issues, milestones and PRs attach to the workspace's project, and a
  PR's head branch is matched to the worktree that has it checked out.

### Identity: who acts on GitHub

- `dev-workflows.identity.github-app-bot` [GAP] (#6116) — the dev pipeline acts on GitHub as a **GitHub App** (a bot
  identity), not as the maintainer: permissions issues and pull requests read/write, contents write on non-protected
  branches only, metadata read; never administration, never a bypass of the branch rules, so `main` stays PR + merge
  and `v*` tags stay locked for it like anyone. It uses short-lived installation tokens minted on the build machine
  from a private key held in the owner's keychain; no agent or workflow sees the key. Every agent comment, branch and
  PR is attributable to the bot, and the owner reviews and approves the bot's PRs. Today: the maintainer's `gh`
  login (`pipeline/gh.py`) with `github.agent_email`.
- `dev-workflows.identity.owner-creates-accounts` [PROPOSED] — creating the App, installing it, creating any account,
  team or token is the owner's act, done by hand; an agent may write the instructions, never perform them.
- `dev-workflows.identity.contributors-own-accounts` [GAP] (#6116) — a contributor acts as themself: a fork and a PR
  from their own GitHub account, or an issue that the maintainer's agent picks up (`feeder.pick`'s
  `allowed_authors` and `triage` path). Fichero never acts on GitHub as a contributor except through that
  contributor's own login.

### Retire chains (recipes do what chains did)

Chains are retired; a recipe run is the one way to run workflows in order (`recipes/runner.py`, one
`run-a-recipe` job with its workflow cards as runs beneath it). The chain code cannot be deleted blindly: the recipe
runner borrows its step helpers (§ What exists today, "Chains").

- `dev-workflows.chains.helpers-move` [GAP] (#4949) — `_load_step_workflow`, `_validate_step_workflow`,
  `_record_step_run_accepted`, `_run_step_workflow` and `_step_run_outcome` move from `api/routes/workflow/chains.py`
  into `execution/runner.py` (the one runner, which `recipes/runner.py` already imports `LIVE_CHECK_LOCK` from) as
  public functions, unchanged in behaviour; `recipes/runner.py` imports them from there and no longer imports an API
  route module.
- `dev-workflows.chains.workflow-bar-runs-a-recipe` [GAP] (#4949) — the Workflow Bar's "run these in order" starts a
  recipe run, not `/chains/execute-steps`; the bar's staged steps (today the one shared chain "Workflow Bar",
  `WorkflowBarChainPersistence.swift`) persist as that library's bar recipe, so they survive an engine restart,
  which today they do not (the engine's `ChainStore` is in memory).
- `dev-workflows.chains.user-chains-become-recipes` [GAP] (#4949) — no user's saved chain is lost. What is
  persisted: the engine's `ChainStore` is in memory (`execution/chaining.py:831`), so no chain is on disk; a
  chain lives only while the engine runs, plus the bar's chain the client re-creates by name. The release before
  removal converts every chain present in the running engine (and the bar's) into a recipe with the same workflows in
  the same order and the same inputs mapping, reports each conversion, and leaves a chain it cannot convert in the
  queue as a question with its definition as JSON; a test proves no table or file holds chain definitions before
  removal. The paleography chain preset (`api/routes/workflow/chains.py` `_build_paleography_chain` :412, the
  preset routes :626-643) becomes a **recipe template** with the same workflows and order (owner ruling 2026-10-26,
  Q9).
- `dev-workflows.chains.removed` [GAP] (#4949) — removed: the `/chains/*` routes (CRUD, paleography preset, the
  legacy `/chains/{id}/execute`, `/chains/execute-steps`), `execution/chaining.py`, the job kind `chain`
  (`register_kind`, `_cancel_chain`, `record_chain`, the `RUN_KINDS` entry), the feature `workflowChains` in
  `features.yaml` and its generated files, the AppleScript `workflow chain` class (`Fichero.sdef`; removed with no replacement, owner ruling 2026-10-26, Q11:
  no script uses it), the CLI's chain commands
  (regenerated surface), the Swift chain files and sidebar, menu and readiness entries listed above, and the chain
  tests. The paleography preset is removed only after its recipe template exists
  (`dev-workflows.chains.user-chains-become-recipes`).
- `dev-workflows.chains.nothing-depends` [GAP] (#4949) — a guard test fails if any source, Swift file, generated
  surface or spec outside history names `execution.chaining`, `routes.workflow.chains`, `/chains`, `WorkflowChain`,
  `ChainService` or `ChainStore` (the `ImageEditChain` and builder chain-Send names excepted by exact name).

### User contributions (late; through the same model)

A Fichero user can help develop Fichero through the same model: an issue with context they chose, a spec line, a
fix proposed by their own model in a scratch worktree, checks, and a PR. `main` stays PR + merge only, the
maintainer reviews every PR, and nothing auto-merges. All of it is [GAP].

- `dev-workflows.contrib.tier-off-by-default` [GAP] (#6116) — the contributor tier is off for every user and every
  build until the user turns it on and passes the allow-list check (`dev-workflows.contrib.invite-only`); with it
  off, no contributor menu, route or tool exists. Owner ruling 2026-10-26 (Q5): the dev workflows ship **only** in
  this tier, off by default; this spec promises no release of the combined or shared-project model to all users
  (that would be a separate decision).
- `dev-workflows.contrib.invite-only` [GAP] (#6116) — contributions are limited to people the maintainer invites
  (owner ruling 2026-10-26, Q10: a **signed invite**, no GitHub org needed). The maintainer issues an invite naming
  one GitHub login, an expiry and the per-person limits, signed with a maintainer key whose public half is kept in
  the repo; the person enters it in the app, which verifies the signature and expiry, then checks through the
  person's own `gh` login that they are that GitHub user. The tier stays locked without a valid invite. The app
  re-checks before each contribution, and a revocation list in the repo (read on each pull) ends an invite at the
  next check. The account invites in `api/routes/auth/accounts.py` (:549-681: mint, redeem, revoke) are the nearest
  existing piece and are reused for minting and revoking where they fit. Noted alternatives, not the default: a list
  of named GitHub logins, or membership of a GitHub team.
- `dev-workflows.contrib.maintainer-manages-people` [GAP] (#6116) — the maintainer adds and removes people by a
  signed invite and removes them by revoking it, sets a per-person rate limit (open PRs at once, proposals per day) and revokes a
  person; a revoked person's open proposals are closed with a comment, never merged.
- `dev-workflows.contrib.library-stays-local` [GAP] (#6116) — a contributor's library never leaves their machine:
  the contributor model is bound only to the repo workspace's read-only tools and the scratch worktree, never to the
  library, documents, transcriptions or the KG, and the egress gate refuses library content on the contribution
  path. Pass: a contribution run with a library open makes no call that reads a library record.
- `dev-workflows.contrib.consented-context` [GAP] (#6116) — an issue is drafted with only the context the user picks
  (app and engine versions, a log excerpt, steps, a screenshot they choose), shown in full before it is sent, and
  sent from their own account; nothing from the library is offered by default.
- `dev-workflows.contrib.own-compute-and-caps` [GAP] (#6116) — the proposed fix runs on the user's own local model or
  their own API key, with a per-proposal and per-day budget cap they set, the running cost shown, and a stop at the
  cap.
- `dev-workflows.contrib.scratch-worktree` [GAP] (#6116) — the fix is made in a scratch worktree of the user's clone
  and checked on a scratch `FICHERO_BASE_PATH` (`security/real_data_guard.py`), so neither touches the user's
  library or real app data; the worktree is removed after the PR is opened or abandoned.
- `dev-workflows.contrib.quality-bar-and-pr` [GAP] (#6116) — a PR opens only when the pinned checks are green, the
  change cites the spec behaviour it serves (a new spec line is marked proposed), and the per-person limit allows;
  the PR is labelled proposed, goes from the contributor's fork, and is reviewed by the maintainer; nothing merges
  automatically.

### Shared projects (several Ficheros on one project)

Several people, each with their own Fichero, work on one project. Two carriers exist or are planned, and a project
may use either or both. What exists: Fichero's own sharing hosts **one library** on one Mac that other Macs connect
to (`transport/library-sharing.md`: `sharing.edits-both-ways` [PARTIAL] over `/api/changes`, `sharing.who-did-it`
[OK], `sharing.revoke` [PARTIAL], `sharing.device-chooses-person` [PARTIAL]; `transport/multiuser-always-on.md`
DRAFT), Multi-user accounts with roles owner, editor, viewer and scoped (`security/authz.py:64-69`, `can_read`,
`can_write`, `require_owner`), and account invites (`api/routes/auth/accounts.py`: `GET/POST /invites` :549-560,
`/invites/redeem` :603, `/invites/{id}/revoke` :681). What is missing: sharing a **project** without sharing the
whole library, any lease on an issue (`ResearchTask.assigned_to` is free text; the pipeline's `claimed` label has no
expiry), any addressee on a question (`HumanReviewRequest`, `workflows/human_review.py:27-48`, has question,
options, context and node only), and project-level permissions for approving, answering, running and spending.

- `dev-workflows.shared.via-github` [GAP] (#6116) — any project, dev or research, can live in a GitHub repo: its
  issues, milestones and comments through `dev-workflows.combined.sync-two-way`, its specs and plans as files, and
  its project notes as Markdown files in the repo changed by pull request; every Fichero that links the repo sees the
  same project after a pull.
- `dev-workflows.shared.via-fichero-host` [PARTIAL] (#5049) — a project can be shared from a host Fichero to people
  with accounts on it (Multi-user, invites, the change stream above); what is missing is sharing the project's
  records (issues, milestones, plans, approved results) without the host's library, which is a project-scoped grant
  on top of `security/authz.py`, not a second account system.
- `dev-workflows.shared.issue-leases` [GAP] (#6116) — one holder works an issue at a time: a lease `{person, device,
  taken_at, expires_at}` taken before work starts, renewed at each run boundary while the work runs, released on
  done, failure or stop, and taken over by someone else only after it expired, recorded with who took it. On GitHub
  the lease is the assignee plus the `claimed` label plus a marker comment carrying the expiry
  (`<!-- fichero:lease:<person>:<expires> -->`); taking it is assign, then re-read: if two holders appear, the
  earlier marker wins and the later one releases at once. The pipeline's `claimed` label becomes this lease. Two
  workers never run the same issue.
- `dev-workflows.shared.question-routing` [GAP] (#6116) — a question names who must answer: the issue's assignee, the
  spec's or plan's approver, or the project owner, in that order of default; it shows first in that person's queue,
  others see it read-only, and one unanswered past the project's wait time is raised to the project owner.
- `dev-workflows.shared.permissions` [GAP] (#6116) — per project: approving a spec or plan is the owner's or a named
  approver's; answering is the addressee's or the owner's; running workers and spending budget is an editor's,
  within a per-person budget the owner sets; viewers read. Checked through `security/authz.py`, mapped to GitHub
  repo permissions when the project lives on GitHub (a person without write there cannot take a lease).
- `dev-workflows.shared.conflicts-follow-combined` [PROPOSED] — conflicts between Ficheros follow the combined model:
  GitHub wins on state, Fichero (the repo's spec and plan files) on links; two edits to one spec or plan meet in a
  pull request, never a silent merge; on a host-shared project the host's records are the source.
- `dev-workflows.shared.library-stays-local` [GAP] (#6116) — each person's library stays on their machine; only
  issues, milestones, plans, comments and **approved** results sync, and a result is shared only as the file or
  record its owner picked when approving it. Pass: a sync of a shared project sends no library record that was not
  approved for sharing.
- `dev-workflows.shared.offline` [GAP] (#6116) — offline, a person keeps working on the issues they hold and on the
  mirror (`dev-workflows.combined.offline`); a lease that expires while they are offline may be taken over, and on
  reconnect work done under a lease someone else now holds becomes a question to both, never an overwrite.

### Release as a dev workflow (late; the end state)

Fichero, with its agent, integrates and pushes releases through the same model, as a workflow of script nodes over
the existing release scripts; the owner says yes to everything public.

- `dev-workflows.release.stamp-and-notes` [PARTIAL] (#6142) — the workflow stamps the version
  (`set-release-version.sh`, `stamp_engine_version_into_app.sh`, checked by `check_engine_version_stamp.py`),
  regenerates the contract and OpenAPI files, and drafts the notes (`release-notes-gen.sh`) as a proposal the owner
  edits before anything is built. Today the scripts exist and are run by hand.
- `dev-workflows.release.gate-build-notarize-testflight` [PARTIAL] (#6142) — it runs the gate, builds the DMGs,
  notarizes and staples (`build-release-dmg.sh`, `notarize.sh`, `check_release_staples_app.py`) and uploads Mac and
  iOS TestFlight, each a script node calling the existing scripts (`release-all.sh` broken into its lanes); no build
  logic is rewritten.
- `dev-workflows.release.credentials-stay-put` [PROPOSED] — signing, notarization and App Store Connect credentials
  stay in the owner's keychain on the build machine and are used only by the existing scripts; no agent or workflow
  types, reads, logs or stores one, and the workflow passes no secret as an input.
- `dev-workflows.release.failure-is-a-question` [GAP] (#6142) — a failed step (for example the Xcode 27.0 `altool`
  crash on upload) parks the run with a question to the owner carrying the log tail and the options (retry, skip
  this lane, stop); it is never retried silently.
- `dev-workflows.release.activity-row` [GAP] (#6142) — every release run is a job row with a child per step and its
  stored log (`dev-workflows.one-activity-system.dev-uses-it`), so a release is replayable from Activity.
- `dev-workflows.release.pr-as-bot` [GAP] (#6142) — when the build is good the workflow opens the PR integration →
  main as the bot identity (`dev-workflows.identity.github-app-bot`) with the notes and the check results.
- `dev-workflows.release.owner-yes-gate` [GAP] (#6142) — the merge, the GitHub release (`create-github-release.sh`),
  the Sparkle feed (`appcast_upsert.py`, `check_sparkle_update_ready.py`) and the site (`deploy-site.sh`) each wait
  for the owner's explicit yes at a human-question node that survives a restart
  (`dev-workflows.run.pause-resume-durable`); no yes, nothing public changes.
- `dev-workflows.release.main-and-tags-locked` [PROPOSED] — the workflow never pushes `main` or a `v*` tag; `main`
  changes only by the merged PR, and the tag is made by the release step the owner said yes to.

## Rulings

Owner rulings of 2026-10-26 on this spec's open questions (the spec as a whole stays proposed, not approved):

- Q1 pinned engine: a separate pinned build first; onto the app's own engine once proven (Stage 3).
  (`dev-workflows.run.pinned-engine`)
- Q3 library: the Fichero repo is a separate dev library (a workspace source), not obvious to users; shared once
  good. (`dev-workflows.workspace.source-kind`)
- Q4 GitHub writes: model nodes do bookkeeping only (comment, label, milestone move); committing, landing, closing
  and pushing are the runner's gated steps. (`dev-workflows.combined.writes-need-approval`)
- Q6 names: GitHub's names in the app (Project, Milestone, Issue, Pull Request, Label, Comment, Release, Assignee);
  Spec and Plan are ours. (`dev-workflows.combined.github-names`)
- Q7 sync: pull only, every 5 minutes and on open; no webhooks. (`dev-workflows.combined.sync-two-way`)
- Q8 plan approval: the runner's `plan-approve` first (dry run by default; in review on runner/b4, 2858dbb68,
  reviewed READY with the caveat #6161), the app's approval with the combined model. (`dev-workflows.combined.approvals`)
- Q2 journal: the pipeline's JSONL journal stays the source of truth; workflow and activity rows are a view built
  from it. (`dev-workflows.run.state-stays-in-github`)
- Q5 ship scope: the dev workflows ship only in the contributor tier, off by default; nothing here promises the
  combined or shared-project model to all users. (`dev-workflows.contrib.tier-off-by-default`)
- Q9 paleography chain preset: becomes a recipe template. (`dev-workflows.chains.user-chains-become-recipes`)
- Q10 contributor check: a signed invite issued by the maintainer; named logins or team membership are noted
  alternatives only. (`dev-workflows.contrib.invite-only`)
- Q11 AppleScript `workflow chain` class: removed with chains, no replacement; no script uses it.
  (`dev-workflows.chains.removed`)

## Build order

Stage 1 proves the combined model **read-only** against GitHub on a scratch base path, with a repo added as a
workspace and one item through by hand. Stage 2 adds two-way sync, the bot identity, GitHub names, the spec and
plan layers, the node types and pause/resume work, one activity system, and retires chains. Stage 3 moves the
pipeline onto the model (onto the app's own engine once proven on the pinned build). Stage 4 opens it to invited
contributors, Stage 5 to shared projects, and Stage 6 makes the release a dev workflow. Each step is one coder
context's worth.

### Stage 1 — prove it read-only against GitHub on a scratch base path

#### Step 1.1 — headless run on a scratch base path
- Behaviours: `dev-workflows.run.headless-on-scratch`, `dev-workflows.run.pinned-engine`
- Tests: fichero-server/tests/unit/workflows/test_headless_scratch_run.py
- Size: M

#### Step 1.2 — the combined records and the GitHub mapping, read-only
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-mapping`, `dev-workflows.source.github-as-source`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — read this repo into the model on scratch, no writes
- Behaviours: `dev-workflows.combined.read-only-first`
- Tests: fichero-server/tests/unit/research/test_github_read_only_mirror.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — a repo as a workspace, read-only and lazily indexed
- Behaviours: `dev-workflows.workspace.source-kind`, `dev-workflows.workspace.lazy-index`, `dev-workflows.workspace.worktrees-map-to-tasks`, `dev-workflows.combined.repo-as-project-source`, `dev-workflows.source.repo-folder-and-index`
- Tests: fichero-server/tests/unit/sources/test_workspace_source.py
- Depends on: 1.2
- Size: M

#### Step 1.5 — script node and the exit-code router
- Behaviours: `dev-workflows.node.script`, `dev-workflows.node.validate-before-run`
- Tests: fichero-server/tests/unit/workflows/test_script_node.py
- Depends on: 1.1
- Size: M

#### Step 1.6 — one item through, scratch only
- Behaviours: `dev-workflows.rollout.prove-one-item`, `dev-workflows.rollout.stdlib-runner-stays`
- Tests: fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py
- Depends on: 1.3, 1.5
- Size: M

### Stage 2 — two-way sync, the spec and plan layers, GitHub names, one activity system, chains retired

#### Step 2.1 — git and gh nodes with their allow-lists
- Behaviours: `dev-workflows.node.git`, `dev-workflows.node.gh`
- Tests: fichero-server/tests/unit/workflows/test_git_gh_nodes.py
- Size: M

#### Step 2.2 — the bot identity
- Behaviours: `dev-workflows.identity.github-app-bot`, `dev-workflows.identity.owner-creates-accounts`, `dev-workflows.identity.contributors-own-accounts`
- Tests: fichero-server/tests/unit/workflows/test_github_app_identity.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — GitHub names: Milestone and Issue in the app and API, with aliases
- Behaviours: `dev-workflows.combined.github-names`
- Tests: fichero-server/tests/unit/research/test_github_names_and_aliases.py
- Size: M

#### Step 2.4 — the spec and plan layers
- Behaviours: `dev-workflows.combined.spec-layer`, `dev-workflows.combined.plan-layer`
- Tests: fichero-server/tests/unit/research/test_spec_and_plan_layers.py
- Depends on: 2.3
- Size: M

#### Step 2.5 — durable pause and resume
- Behaviours: `dev-workflows.run.pause-resume-durable`
- Tests: fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py
- Size: M

#### Step 2.6 — the human-question node
- Behaviours: `dev-workflows.node.human-question`
- Tests: fichero-server/tests/unit/workflows/test_human_question_node.py
- Depends on: 2.5
- Size: M

#### Step 2.7 — one issue model, one question queue, the three approvals
- Behaviours: `dev-workflows.research.one-task-model`, `dev-workflows.research.one-question-queue`, `dev-workflows.research.proposals-are-reviewable`, `dev-workflows.research.same-node-types`, `dev-workflows.combined.approvals`
- Tests: fichero-server/tests/unit/research/test_dev_task_and_question_model.py
- Depends on: 2.4, 2.6
- Size: M

#### Step 2.8 — two-way sync with its conflict, close and write rules
- Behaviours: `dev-workflows.combined.sync-two-way`, `dev-workflows.combined.close-only-by-closer`, `dev-workflows.combined.writes-need-approval`
- Tests: fichero-server/tests/unit/research/test_github_two_way_sync.py
- Depends on: 2.2, 2.7
- Size: M

#### Step 2.9 — offline and rate limits
- Behaviours: `dev-workflows.combined.offline`, `dev-workflows.combined.rate-limits`
- Tests: fichero-server/tests/unit/research/test_sync_offline_and_rate_limited.py
- Depends on: 2.8
- Size: M

#### Step 2.10 — Research projects on the same model
- Behaviours: `dev-workflows.combined.research-projects`
- Tests: fichero-server/tests/unit/research/test_research_project_uses_combined_model.py
- Depends on: 2.7
- Size: M

#### Step 2.11 — a workspace as agent context, tied to GitHub
- Behaviours: `dev-workflows.workspace.context-for-agents`, `dev-workflows.workspace.github-tie`
- Tests: fichero-server/tests/unit/sources/test_workspace_context_and_github.py
- Depends on: 1.4, 2.8
- Size: M

#### Step 2.12 — worker node with role, model alias and cap
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.run.small-models-only`, `dev-workflows.run.no-model-rerun`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py
- Size: M

#### Step 2.13 — unify the activity bypasses
- Behaviours: `dev-workflows.one-activity-system.one-job-table`, `dev-workflows.one-activity-system.bypasses`, `dev-workflows.one-activity-system.one-cancel`, `dev-workflows.one-activity-system.one-pause`, `dev-workflows.one-activity-system.one-run-log`
- Tests: fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py
- Depends on: 2.5
- Size: M

#### Step 2.14 — the folder importer is a job
- Behaviours: `dev-workflows.one-activity-system.folder-import-is-a-job`
- Tests: fichero-server/tests/unit/ingest/test_folder_import_is_a_job_row.py
- Depends on: 2.13
- Size: M

#### Step 2.15 — chain helpers move to the runner; the Workflow Bar runs a recipe
- Behaviours: `dev-workflows.chains.helpers-move`, `dev-workflows.chains.workflow-bar-runs-a-recipe`
- Tests: fichero-server/tests/unit/recipes/test_recipe_runner_without_chains.py
- Size: M

#### Step 2.16 — saved chains become recipes
- Behaviours: `dev-workflows.chains.user-chains-become-recipes`
- Tests: fichero-server/tests/unit/recipes/test_chains_become_recipes.py
- Depends on: 2.15
- Size: M

#### Step 2.17 — remove chains
- Behaviours: `dev-workflows.chains.removed`, `dev-workflows.chains.nothing-depends`
- Tests: fichero-server/tests/unit/seams/test_nothing_names_chains.py
- Depends on: 2.16
- Size: M

### Stage 3 — move the pipeline onto the model

#### Step 3.1 — see the pipeline on the canvas
- Behaviours: `dev-workflows.visibility.canvas-and-log`, `dev-workflows.visibility.runs-from-the-pipeline-page`, `dev-workflows.run.state-stays-in-github`
- Tests: fichero-server/tests/unit/workflows/test_dev_run_log_events.py, pipeline/tests/test_page_links_workflow_runs.py
- Size: M

#### Step 3.2 — dev workflows are ordinary activity rows
- Behaviours: `dev-workflows.one-activity-system.dev-uses-it`
- Tests: fichero-server/tests/unit/workflows/test_dev_run_is_a_job_row.py
- Depends on: 3.1
- Size: S

#### Step 3.3 — the pipeline reads and writes through the model
- Behaviours: `dev-workflows.combined.pipeline-is-first-user`
- Tests: pipeline/tests/test_pipeline_uses_combined_model.py
- Depends on: 3.2
- Size: M

#### Step 3.4 — the project view, read-only
- Behaviours: `dev-workflows.project-view.overview`, `dev-workflows.project-view.specs-and-build-order`, `dev-workflows.project-view.issues-and-bugs`, `dev-workflows.project-view.runs-turns-tokens-cost`, `dev-workflows.project-view.tests-and-reviews`
- Tests: fichero-server/tests/unit/workflows/test_project_view_read.py
- Depends on: 3.3
- Size: M

#### Step 3.5 — owner actions in the project view
- Behaviours: `dev-workflows.project-view.owner-queue`, `dev-workflows.project-view.issue-actions`, `dev-workflows.project-view.approve`, `dev-workflows.project-view.answer-and-control`, `dev-workflows.project-view.no-parallel-surface`
- Tests: fichero-server/tests/unit/workflows/test_project_view_actions.py
- Depends on: 3.4
- Size: M

### Stage 4 — user contributions

#### Step 4.1 — the contributor tier, invite-only
- Behaviours: `dev-workflows.contrib.tier-off-by-default`, `dev-workflows.contrib.invite-only`, `dev-workflows.contrib.maintainer-manages-people`
- Tests: fichero-server/tests/unit/contrib/test_contributor_allow_list.py
- Size: M

#### Step 4.2 — private, on the contributor's own compute, in scratch
- Behaviours: `dev-workflows.contrib.library-stays-local`, `dev-workflows.contrib.own-compute-and-caps`, `dev-workflows.contrib.scratch-worktree`
- Tests: fichero-server/tests/unit/contrib/test_contribution_isolation.py
- Depends on: 4.1
- Size: M

#### Step 4.3 — from a consented issue to a reviewed PR
- Behaviours: `dev-workflows.contrib.consented-context`, `dev-workflows.contrib.quality-bar-and-pr`
- Tests: fichero-server/tests/unit/contrib/test_contribution_to_pr.py
- Depends on: 4.2
- Size: M

### Stage 5 — shared projects

#### Step 5.1 — shared state, carriers and leases
- Behaviours: `dev-workflows.shared.via-github`, `dev-workflows.shared.via-fichero-host`, `dev-workflows.shared.issue-leases`, `dev-workflows.shared.conflicts-follow-combined`
- Tests: fichero-server/tests/unit/research/test_shared_project_leases.py
- Size: M

#### Step 5.2 — people: routing, permissions, privacy, offline
- Behaviours: `dev-workflows.shared.question-routing`, `dev-workflows.shared.permissions`, `dev-workflows.shared.library-stays-local`, `dev-workflows.shared.offline`
- Tests: fichero-server/tests/unit/research/test_shared_project_people.py
- Depends on: 5.1
- Size: M

### Stage 6 — release as a dev workflow

#### Step 6.1 — stamp, notes, gate, build and upload
- Behaviours: `dev-workflows.release.stamp-and-notes`, `dev-workflows.release.gate-build-notarize-testflight`, `dev-workflows.release.credentials-stay-put`, `dev-workflows.release.failure-is-a-question`, `dev-workflows.release.activity-row`
- Tests: fichero-server/tests/unit/workflows/test_release_workflow_build.py
- Size: M

#### Step 6.2 — the PR and the owner's yes
- Behaviours: `dev-workflows.release.pr-as-bot`, `dev-workflows.release.owner-yes-gate`, `dev-workflows.release.main-and-tags-locked`
- Tests: fichero-server/tests/unit/workflows/test_release_workflow_owner_gate.py
- Depends on: 6.1
- Size: M

## Behaviour tests

Every behaviour names the test that pins it (the step's test file, one test per behaviour; a [PROPOSED] rule's test
pins the rule once it is ruled). None of these tests exists yet; each is written in its step.

| Behaviour | Step | Test |
|-----------|------|------|
| `dev-workflows.run.headless-on-scratch` | 1.1 | `fichero-server/tests/unit/workflows/test_headless_scratch_run.py::test_headless_on_scratch` |
| `dev-workflows.run.pinned-engine` | 1.1 | `fichero-server/tests/unit/workflows/test_headless_scratch_run.py::test_pinned_engine` |
| `dev-workflows.combined.entities` | 1.2 | `fichero-server/tests/unit/research/test_combined_model_records.py::test_entities` |
| `dev-workflows.combined.github-mapping` | 1.2 | `fichero-server/tests/unit/research/test_combined_model_records.py::test_github_mapping` |
| `dev-workflows.source.github-as-source` | 1.2 | `fichero-server/tests/unit/research/test_combined_model_records.py::test_github_as_source` |
| `dev-workflows.combined.read-only-first` | 1.3 | `fichero-server/tests/unit/research/test_github_read_only_mirror.py::test_read_only_first` |
| `dev-workflows.workspace.source-kind` | 1.4 | `fichero-server/tests/unit/sources/test_workspace_source.py::test_source_kind` |
| `dev-workflows.workspace.lazy-index` | 1.4 | `fichero-server/tests/unit/sources/test_workspace_source.py::test_lazy_index` |
| `dev-workflows.workspace.worktrees-map-to-tasks` | 1.4 | `fichero-server/tests/unit/sources/test_workspace_source.py::test_worktrees_map_to_tasks` |
| `dev-workflows.combined.repo-as-project-source` | 1.4 | `fichero-server/tests/unit/sources/test_workspace_source.py::test_repo_as_project_source` |
| `dev-workflows.source.repo-folder-and-index` | 1.4 | `fichero-server/tests/unit/sources/test_workspace_source.py::test_repo_folder_and_index` |
| `dev-workflows.node.script` | 1.5 | `fichero-server/tests/unit/workflows/test_script_node.py::test_script` |
| `dev-workflows.node.validate-before-run` | 1.5 | `fichero-server/tests/unit/workflows/test_script_node.py::test_validate_before_run` |
| `dev-workflows.rollout.prove-one-item` | 1.6 | `fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py::test_prove_one_item` |
| `dev-workflows.rollout.stdlib-runner-stays` | 1.6 | `fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py::test_stdlib_runner_stays` |
| `dev-workflows.node.git` | 2.1 | `fichero-server/tests/unit/workflows/test_git_gh_nodes.py::test_git` |
| `dev-workflows.node.gh` | 2.1 | `fichero-server/tests/unit/workflows/test_git_gh_nodes.py::test_gh` |
| `dev-workflows.identity.github-app-bot` | 2.2 | `fichero-server/tests/unit/workflows/test_github_app_identity.py::test_github_app_bot` |
| `dev-workflows.identity.owner-creates-accounts` | 2.2 | `fichero-server/tests/unit/workflows/test_github_app_identity.py::test_owner_creates_accounts` |
| `dev-workflows.identity.contributors-own-accounts` | 2.2 | `fichero-server/tests/unit/workflows/test_github_app_identity.py::test_contributors_own_accounts` |
| `dev-workflows.combined.github-names` | 2.3 | `fichero-server/tests/unit/research/test_github_names_and_aliases.py::test_github_names` |
| `dev-workflows.combined.spec-layer` | 2.4 | `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_spec_layer` |
| `dev-workflows.combined.plan-layer` | 2.4 | `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_plan_layer` |
| `dev-workflows.run.pause-resume-durable` | 2.5 | `fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py::test_pause_resume_durable` |
| `dev-workflows.node.human-question` | 2.6 | `fichero-server/tests/unit/workflows/test_human_question_node.py::test_human_question` |
| `dev-workflows.research.one-task-model` | 2.7 | `fichero-server/tests/unit/research/test_dev_task_and_question_model.py::test_one_task_model` |
| `dev-workflows.research.one-question-queue` | 2.7 | `fichero-server/tests/unit/research/test_dev_task_and_question_model.py::test_one_question_queue` |
| `dev-workflows.research.proposals-are-reviewable` | 2.7 | `fichero-server/tests/unit/research/test_dev_task_and_question_model.py::test_proposals_are_reviewable` |
| `dev-workflows.research.same-node-types` | 2.7 | `fichero-server/tests/unit/research/test_dev_task_and_question_model.py::test_same_node_types` |
| `dev-workflows.combined.approvals` | 2.7 | `fichero-server/tests/unit/research/test_dev_task_and_question_model.py::test_approvals` |
| `dev-workflows.combined.sync-two-way` | 2.8 | `fichero-server/tests/unit/research/test_github_two_way_sync.py::test_sync_two_way` |
| `dev-workflows.combined.close-only-by-closer` | 2.8 | `fichero-server/tests/unit/research/test_github_two_way_sync.py::test_close_only_by_closer` |
| `dev-workflows.combined.writes-need-approval` | 2.8 | `fichero-server/tests/unit/research/test_github_two_way_sync.py::test_writes_need_approval` |
| `dev-workflows.combined.offline` | 2.9 | `fichero-server/tests/unit/research/test_sync_offline_and_rate_limited.py::test_offline` |
| `dev-workflows.combined.rate-limits` | 2.9 | `fichero-server/tests/unit/research/test_sync_offline_and_rate_limited.py::test_rate_limits` |
| `dev-workflows.combined.research-projects` | 2.10 | `fichero-server/tests/unit/research/test_research_project_uses_combined_model.py::test_research_projects` |
| `dev-workflows.workspace.context-for-agents` | 2.11 | `fichero-server/tests/unit/sources/test_workspace_context_and_github.py::test_context_for_agents` |
| `dev-workflows.workspace.github-tie` | 2.11 | `fichero-server/tests/unit/sources/test_workspace_context_and_github.py::test_github_tie` |
| `dev-workflows.node.worker` | 2.12 | `fichero-server/tests/unit/workflows/test_worker_node.py::test_worker` |
| `dev-workflows.run.small-models-only` | 2.12 | `fichero-server/tests/unit/workflows/test_worker_node.py::test_small_models_only` |
| `dev-workflows.run.no-model-rerun` | 2.12 | `fichero-server/tests/unit/workflows/test_worker_node.py::test_no_model_rerun` |
| `dev-workflows.one-activity-system.one-job-table` | 2.13 | `fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py::test_one_job_table` |
| `dev-workflows.one-activity-system.bypasses` | 2.13 | `fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py::test_bypasses` |
| `dev-workflows.one-activity-system.one-cancel` | 2.13 | `fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py::test_one_cancel` |
| `dev-workflows.one-activity-system.one-pause` | 2.13 | `fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py::test_one_pause` |
| `dev-workflows.one-activity-system.one-run-log` | 2.13 | `fichero-server/tests/unit/execution/test_every_path_is_a_job_row.py::test_one_run_log` |
| `dev-workflows.one-activity-system.folder-import-is-a-job` | 2.14 | `fichero-server/tests/unit/ingest/test_folder_import_is_a_job_row.py::test_folder_import_is_a_job` |
| `dev-workflows.chains.helpers-move` | 2.15 | `fichero-server/tests/unit/recipes/test_recipe_runner_without_chains.py::test_helpers_move` |
| `dev-workflows.chains.workflow-bar-runs-a-recipe` | 2.15 | `fichero-server/tests/unit/recipes/test_recipe_runner_without_chains.py::test_workflow_bar_runs_a_recipe` |
| `dev-workflows.chains.user-chains-become-recipes` | 2.16 | `fichero-server/tests/unit/recipes/test_chains_become_recipes.py::test_user_chains_become_recipes` |
| `dev-workflows.chains.removed` | 2.17 | `fichero-server/tests/unit/seams/test_nothing_names_chains.py::test_removed` |
| `dev-workflows.chains.nothing-depends` | 2.17 | `fichero-server/tests/unit/seams/test_nothing_names_chains.py::test_nothing_depends` |
| `dev-workflows.visibility.canvas-and-log` | 3.1 | `fichero-server/tests/unit/workflows/test_dev_run_log_events.py::test_canvas_and_log` |
| `dev-workflows.visibility.runs-from-the-pipeline-page` | 3.1 | `fichero-server/tests/unit/workflows/test_dev_run_log_events.py::test_runs_from_the_pipeline_page` |
| `dev-workflows.run.state-stays-in-github` | 3.1 | `fichero-server/tests/unit/workflows/test_dev_run_log_events.py::test_state_stays_in_github` |
| `dev-workflows.one-activity-system.dev-uses-it` | 3.2 | `fichero-server/tests/unit/workflows/test_dev_run_is_a_job_row.py::test_dev_uses_it` |
| `dev-workflows.combined.pipeline-is-first-user` | 3.3 | `pipeline/tests/test_pipeline_uses_combined_model.py::test_pipeline_is_first_user` |
| `dev-workflows.project-view.overview` | 3.4 | `fichero-server/tests/unit/workflows/test_project_view_read.py::test_overview` |
| `dev-workflows.project-view.specs-and-build-order` | 3.4 | `fichero-server/tests/unit/workflows/test_project_view_read.py::test_specs_and_build_order` |
| `dev-workflows.project-view.issues-and-bugs` | 3.4 | `fichero-server/tests/unit/workflows/test_project_view_read.py::test_issues_and_bugs` |
| `dev-workflows.project-view.runs-turns-tokens-cost` | 3.4 | `fichero-server/tests/unit/workflows/test_project_view_read.py::test_runs_turns_tokens_cost` |
| `dev-workflows.project-view.tests-and-reviews` | 3.4 | `fichero-server/tests/unit/workflows/test_project_view_read.py::test_tests_and_reviews` |
| `dev-workflows.project-view.owner-queue` | 3.5 | `fichero-server/tests/unit/workflows/test_project_view_actions.py::test_owner_queue` |
| `dev-workflows.project-view.issue-actions` | 3.5 | `fichero-server/tests/unit/workflows/test_project_view_actions.py::test_issue_actions` |
| `dev-workflows.project-view.approve` | 3.5 | `fichero-server/tests/unit/workflows/test_project_view_actions.py::test_approve` |
| `dev-workflows.project-view.answer-and-control` | 3.5 | `fichero-server/tests/unit/workflows/test_project_view_actions.py::test_answer_and_control` |
| `dev-workflows.project-view.no-parallel-surface` | 3.5 | `fichero-server/tests/unit/workflows/test_project_view_actions.py::test_no_parallel_surface` |
| `dev-workflows.contrib.tier-off-by-default` | 4.1 | `fichero-server/tests/unit/contrib/test_contributor_allow_list.py::test_tier_off_by_default` |
| `dev-workflows.contrib.invite-only` | 4.1 | `fichero-server/tests/unit/contrib/test_contributor_allow_list.py::test_invite_only` |
| `dev-workflows.contrib.maintainer-manages-people` | 4.1 | `fichero-server/tests/unit/contrib/test_contributor_allow_list.py::test_maintainer_manages_people` |
| `dev-workflows.contrib.library-stays-local` | 4.2 | `fichero-server/tests/unit/contrib/test_contribution_isolation.py::test_library_stays_local` |
| `dev-workflows.contrib.own-compute-and-caps` | 4.2 | `fichero-server/tests/unit/contrib/test_contribution_isolation.py::test_own_compute_and_caps` |
| `dev-workflows.contrib.scratch-worktree` | 4.2 | `fichero-server/tests/unit/contrib/test_contribution_isolation.py::test_scratch_worktree` |
| `dev-workflows.contrib.consented-context` | 4.3 | `fichero-server/tests/unit/contrib/test_contribution_to_pr.py::test_consented_context` |
| `dev-workflows.contrib.quality-bar-and-pr` | 4.3 | `fichero-server/tests/unit/contrib/test_contribution_to_pr.py::test_quality_bar_and_pr` |
| `dev-workflows.shared.via-github` | 5.1 | `fichero-server/tests/unit/research/test_shared_project_leases.py::test_via_github` |
| `dev-workflows.shared.via-fichero-host` | 5.1 | `fichero-server/tests/unit/research/test_shared_project_leases.py::test_via_fichero_host` |
| `dev-workflows.shared.issue-leases` | 5.1 | `fichero-server/tests/unit/research/test_shared_project_leases.py::test_issue_leases` |
| `dev-workflows.shared.conflicts-follow-combined` | 5.1 | `fichero-server/tests/unit/research/test_shared_project_leases.py::test_conflicts_follow_combined` |
| `dev-workflows.shared.question-routing` | 5.2 | `fichero-server/tests/unit/research/test_shared_project_people.py::test_question_routing` |
| `dev-workflows.shared.permissions` | 5.2 | `fichero-server/tests/unit/research/test_shared_project_people.py::test_permissions` |
| `dev-workflows.shared.library-stays-local` | 5.2 | `fichero-server/tests/unit/research/test_shared_project_people.py::test_library_stays_local` |
| `dev-workflows.shared.offline` | 5.2 | `fichero-server/tests/unit/research/test_shared_project_people.py::test_offline` |
| `dev-workflows.release.stamp-and-notes` | 6.1 | `fichero-server/tests/unit/workflows/test_release_workflow_build.py::test_stamp_and_notes` |
| `dev-workflows.release.gate-build-notarize-testflight` | 6.1 | `fichero-server/tests/unit/workflows/test_release_workflow_build.py::test_gate_build_notarize_testflight` |
| `dev-workflows.release.credentials-stay-put` | 6.1 | `fichero-server/tests/unit/workflows/test_release_workflow_build.py::test_credentials_stay_put` |
| `dev-workflows.release.failure-is-a-question` | 6.1 | `fichero-server/tests/unit/workflows/test_release_workflow_build.py::test_failure_is_a_question` |
| `dev-workflows.release.activity-row` | 6.1 | `fichero-server/tests/unit/workflows/test_release_workflow_build.py::test_activity_row` |
| `dev-workflows.release.pr-as-bot` | 6.2 | `fichero-server/tests/unit/workflows/test_release_workflow_owner_gate.py::test_pr_as_bot` |
| `dev-workflows.release.owner-yes-gate` | 6.2 | `fichero-server/tests/unit/workflows/test_release_workflow_owner_gate.py::test_owner_yes_gate` |
| `dev-workflows.release.main-and-tags-locked` | 6.2 | `fichero-server/tests/unit/workflows/test_release_workflow_owner_gate.py::test_main_and_tags_locked` |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | dev-node log rows use the existing renderer | — |
| Availability (Swift) | n | — | — |
| Backend (pytest) | y | node contracts, restart survival, scratch guard, sync rules, workspace index, chains gone, contributor isolation, release gates | `fichero-server/tests/unit/{workflows,research,sources,execution,ingest,recipes,seams,contrib}/`, `pipeline/tests/` (§ Behaviour tests) |
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

None open. Q1 to Q11 were decided by the owner on 2026-10-26 (§ Rulings).
