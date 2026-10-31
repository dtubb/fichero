# Fichero Builder and Fichero Researcher — one harness, two uses — Design Spec

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — a contributor section ("How Fichero is built") saying that
> Fichero builds itself through its own workflows, how to run a cluster on a scratch path, and how the same harness
> runs a research project.

> **Status: PROPOSED 2026-10-31 (rewrite 2), for the maintainer's approval.** Replaces the text approved on 2026-10-26
> (c9c24dfbf, 739ad4ba4) with the maintainer's rulings of 2026-10-31 and what the trials and the runner's journal
> taught (evidence: `agent-work/status/briefs/studio-harness-report.md`). Tags: [OK] built · [PARTIAL] exists, not
> wired · [GAP] not built · [BROKEN] fails today · [PROPOSED] decided here, not yet ruled. Issues: #6116 (the
> pipeline), #2067 (Research), #4402 (controls).
>
> What merges and retires: `pipeline/` is **frozen** (maintainer, 2026-10-31): no further investment; its ideas, the
> check ladder and the `scripts/` guards are reused where the engine can call them directly; it retires once the engine
> runs real clusters (§ Rollout). `harness/deterministic-conductor.md` stays as its record and retires with it. `ui/research.md` keeps the Research surface (chat, panes,
> workspace); its orchestration lines (`research.manager-with-workers-orchestration`,
> `research.future.agent-operates-projects`, `research.per-model-tool-grants`) are owned here.
> `ui/activity-and-automatic-work.md` (approved 2026-10-27) keeps the one job model, lanes, throttling and durability;
> § UX below overrides its window columns and adds workers, handoffs and reviews as rows, and says so where it does.
> `ui/workflows.md` keeps the canvas and run log. Thin engine (2026-10-31): the worker's loop is the agent harness's; no
> LangGraph graph drives it (`agent-work/status/briefs/thin-harness-answer.md`).

## Intent

One harness, two uses. **Fichero Builder** builds Fichero: a long-running worker takes a cluster of issues from one
spec, builds them in build order, one commit per issue, checks, asks for review, lands the cluster, updates the
issues, hands off at 85 % of its context and a successor carries on. **Fichero Researcher** does a person's research
project with the same harness: finds sources on the web, searches the person's own libraries, reads and summarises,
files tasks under milestones, asks when it is unsure, and hands off the same way. The harness is projects,
milestones, issues and specs; long-running workers with handoff; review; a runner; models by configuration; one
question queue; one Activity table where everything is seen. What differs between the two uses is the worker's
tools, permissions and data, granted per step. The maintainer and the user see and steer it in the app or a CLI chat
over one audited action layer. Scripts decide wherever a rule can; models do the judgement inside a task; the person
approves specs, plans and anything public or paid. Every bug the Builder meets is a bug in the Researcher's own
machinery, so both get stronger together. Target: Builder and Researcher standing by the end of November 2026, on
Sonnet through Claude Code agents first, other models through OpenRouter next, local models later and by
configuration only.

## Prior art (adopt, don't invent)

Microsoft Conductor (declared steps, script steps routed on exit codes, caps, validate before run); LangGraph
(`interrupt()` + checkpointer: already the engine); our runner (`pipeline/`, frozen: the ideas and the ladder to reuse); GitHub (`gh`, REST) as the public record of work state; macOS Activity Monitor (a dense sortable table with
disclosure rows, a few toolbar icons, a search field, a small summary strip); operators who run coding agents on
128 GB Macs for weeks (several small models at once, one pinned per role, a session per task on a cached prefix, a
tool-call repair layer). Not adopted: a second orchestrator, a second task store, a second question queue, a second
activity list.

## What exists today (grounded; paths under `fichero-server/src/fichero_server/` unless stated)

- Engine: `workflows/builder.py` builds a `StateGraph` compiled with the DuckDB checkpointer (`workflows/checkpointer.py`);
  `workflows/human_review.py` `ask_human()` = `interrupt()`, resumed by `POST /threads/{thread_id}/resume`;
  `workflows/scheduler.py`, `workflows/file_watcher.py`, `workflows/validation.py`, `workflows/safe_condition.py`.
  `pause_requested()` is honoured only at the per-item boundary (`builder.py:1176`; #4402's open half).
- Dev-shaped nodes: `workflows/tools/cli_agent.py` runs a local agent CLI (`claude -p`) in its own process group with a
  timeout (#341); `tools/agent.py` ReAct; `tools/mcp.py` (#5760); `tools/multi_agent.py`. No script, git or gh node.
- Recipes: `recipes/runner.py` runs a plan's cards in order as child jobs of one Activity row, parks on a step run,
  pauses and cancels; a failed card stops only the cards that need its output. This is the shape of a cluster run.
- Jobs: one `jobs` table with `parent_id` (#5353) and `_record`, `record_run`, `settle_stopped_children`
  (`execution/jobs.py`); the Activity spec's 2026-10-27 review lists the four forks (a workflow run's state in three
  places, a recipe's own status, no lane for a workflow run, spaCy in a step not a row).
- Research data: `models/research.py` `ResearchProject` (Project), `ResearchPlan` (Milestone), `ResearchTask` (Issue),
  `ResearchStep` (a tool call: web_search, browser_navigate, document_fetch, local_search), `ResearchNote`,
  `SearchSource`, `ResearchChecklist`; routes `api/routes/research/crud.py` (17), `notes.py`, `tools.py` (DuckDuckGo-HTML
  search, browse, fetch, behind SSRF and size guards); `workflows/tools/research.py` the same as LangChain tools. No
  library-catalogue connector exists; "local_search" is the library's own search. The chat tool loop runs over the
  audited action layer (`actions/chat_tools.py`, `actions/registry.py`: every mutation writes an `ActionAudit` row,
  role-gated; per-model grants are #4721, GAP).
- Apple Intelligence: the engine reaches Foundation Models through the bundled Swift `fm-bridge` binary
  (`llm/__init__.py:2229`, provider `apple`, model `apple-text`; `local_model_choice.apple_intelligence_in_this_build()`
  gates the defaults on the binary and the device); Apple Translation rides the same bridge (`llm/apple_translation.py`);
  Apple Vision and Speech are system frameworks. No tool calling or guided generation is used through the bridge today.
- Activity window: `Views/Activity/Window/ActivityMonitorWindow.swift`, `ActivityGroupsView`, `ActivityStageBar`,
  `Monitor/ActivityMonitorModel` + `ActivityMonitorRow+Build`, `RunControls.swift` (pause/resume/stop per run status).
  The approved spec's Stage 3 (the `Table` with disclosure rows, started-by, what-it-made) is not built.
- CLI and MCP: `fichero workflow …`, `fichero workflow-execution …`, the generated OpenAPI surface; `fichero-mcp`
  exposes the same routes (`fichero_research_*`, …). No chat verb lists specs, milestones or issues; no GitHub code
  in the engine.
- The runner (`pipeline/`, frozen 2026-10-31): journal and state machine, tmux Pi/API workers behind a key wrapper, model-free brief
  localisation, feeder and brief lint, the check ladder (ready, red-on-base, fast guards, contract-current; the trial
  branch adds diff-bound and failing-run-pasted), verdicts bound to a sha, `land` (fast-forward to integration only),
  closer, `plan`/`plan-approve`, budgets in turns and dollars, a batch session with a handoff and park/wake, `gh.py`
  the one journaled GitHub writer. Live: 6 READY / 11 NOT_READY verdicts, 7 of the 11 spec-diff findings; long-running
  builders with a `## Log` handoff did better on larger items.
- Measured so far (`agent-work/status/briefs/local-small-log.tsv`, `trial2/LOCAL-REQUIREMENTS.md`): Qwen3.5-4B 4-bit
  on a 24 GB M4: 2.7 GB resident, 29 tok/s, 340 tok/s prefill under load, tool calls 5/5, triage 8/11; small hosted
  models (gpt-oss-20b, qwen3.5-9b, qwen3.5-35b-a3b, granite-4.2-8b) all 7/7 on clear triage items and all over-call the
  unclear ones; a 30B coder printed its tool call as text; a 35B hit the compaction crash; a 9B ran out of time: small
  models fit triage and routing, not yet a coding task. Qwen3.8-27B hosted: tests 6/6, review 3/3, lead 7.5/8.
  Small-model trial (`briefs/local-small-report.md`, 2026-10-31): no open small model finished the exact edit (a 30B
  coder's tool call came back as text and ran nothing; a 35B ended in Pi's "Cannot continue from message role:
  assistant"; a 9B timed out); triage models guessed on the four unclear items unless offered an explicit UNKNOWN.
  Pi's error appears with a 35B through OpenRouter, so it is a harness fault to fix at the OpenRouter stage, before any
  local model is judged.

## Decisions

- **This repo's issues are managed in Fichero, and Fichero syncs them to GitHub** (maintainer, 2026-10-31). GitHub stays
  the public record of work state (open/closed, labels, milestone, assignee, PRs, releases): contributors and users
  look there and it survives any Fichero bug; `gh` by hand is the exception. Fichero holds the records plus what GitHub
  has no field for (spec, behaviour ids, plan step, run, question, approval, cost), keyed by issue URL, and writes to
  GitHub only through one guarded sync step with a public-repo check at the boundary and a visible log of every write.
  Specs stay Markdown in the repo, bound by the guards. A Researcher project with no repo has the same records and no
  sync.
- **The engine's own records are the truth for runs from the start** (maintainer, 2026-10-31): the checkpointer and the
  jobs table; the pipeline journal becomes a log. This runs **supervised**: the Lead session and the Sonnet builders
  stay in charge, and a plain supervision rule says what they can stop, inspect and repair.
- **Thin engine; the loop lives in the agent harness** (maintainer's question, answered 2026-10-31 in
  `agent-work/status/briefs/thin-harness-answer.md`). A long-running worker owns one task (a Builder cluster, a
  Researcher task); its loop is the harness's own (Claude Code now, Pi as a kind, the engine's existing tool-call loop
  for the Researcher), its handoff and successor are a harness hook, and it calls a few tools (brief, check, ask, hand
  off, land, and the research tools). The engine holds the records, starts and stops workers, shows them in
  Activity, carries questions and grants, and keeps the run log; LangGraph graphs stay where a fixed sequence earns
  them (recipes). Scripts choose between tasks, wake, re-send, budget, bind verdicts to shas, land and close. A model
  never moves an item.
- **Land per cluster** (maintainer, 2026-10-31).
- **One worker kind, two capability sets** (Builder: worktree, shell, git, step tools, scratch base path, contributor
  tier; Researcher: read-only library actions, web search and fetch, note/source/task writes through the audited layer
  as the user's account, no shell). A session never holds both.
- **`pipeline/` is frozen.** Claude Code workers and the Lead carry the real work, as today, until the engine runs real
  clusters; the engine calls the `scripts/` guards and `lane_ready_check.sh` directly, ports the brief builder's
  localisation and the ladder's rungs where it needs them, and never waits on parity with the runner; a comparison is
  made only where a cheap one already exists (the same scenario's events). Its open issues are closed or retargeted
  to this spec's steps (the list is in the plan).
- **Models by configuration, picked by results, profiles per machine.** Nothing in code names a model. Two worker
  kinds, Claude Code and Pi (maintainer, 2026-10-31); `fake` is the test double.
- **Fixed steps are scripts.** Testing, building, landing and closing stay the scripts that exist (`lane_ready_check.sh`,
  `check_*.py`, `scripts/gate`, `verify_all.sh`, `build-and-validate.sh`, the `land` guard, `close_fixed_issues.py`),
  each one Activity row with a progress count and a Stop where it runs long. Only the **release** (`release-all.sh`'s
  steps: long, must resume at the step it died, stops for the maintainer's yes, shown step by step) earns a workflow,
  and stays deferred as the spec's release lane (inventory: `agent-work/status/briefs/thin-harness-answer.md`).
- **Small-context handoff is a core requirement**, not a compromise: the Researcher's normal machine is a 24 GB
  laptop with one small local model beside the engine, so every worker must do real work at a 16-32k context with
  handoffs, and the same mechanism gives the Builder its 85 % line.

### Deployment profiles (configuration over one harness; a role picks from what the machine has)

| Profile | Machine | Models | What runs |
|---|---|---|---|
| Builder, now | M1 Pro 16 GB | Claude Code agents (Sonnet) as the worker kind; then OpenRouter models | clusters, reviews, the dry run; the engine on a scratch base path |
| Builder, end state | M5 Studio 128 GB | several small local models pinned at once under a memory cap (a fast MoE builder, a reviewer, a helper, an embedder; measured roster in the report), served locally with a prefix cache; cloud by exception | 2-3 builder sessions + a reviewer + research at once; headroom for the gate and a build |
| Researcher and a person's local tasks | M5 MacBook Pro 24 GB | one small local model at a time beside the engine (a 4B-9B class at 4-bit: 2.7-6 GB measured/estimated), Apple Intelligence on-device for small typed jobs, Apple Vision/Speech/Translation, MLX readers when the person chooses; cloud models only where the person allows them, cost shown first | one research task at a time, 16-32k context, handoff per task; the engine's own work (import, embed, Kraken) and the model alternate under the machine budget |

On 24 GB the engine itself (DuckDB, LanceDB, spaCy, a reader) takes 2-6 GB at rest and 10-40 GB when a vision reader
or Kraken runs (measured in the Activity spec's review), so a research model runs only when no heavy engine step does,
and a task that needs a larger model than fits (a 27B-class judgement, a long synthesis over many sources) goes to a
cloud model the person allowed or is refused plainly with the reason, never degraded silently.

### Apple Intelligence in the profiles (researched 2026-10-31; numbers reported unless said)

The on-device Foundation Models model is about 3 B parameters, 2-bit quantised, about 1.2 GB resident, about 40 tok/s on
an Apple Silicon Mac (one developer's measurement), with a 4,096-token window on macOS 26 and 8,192 reported for the
macOS 27 rebuild (read `contextSize` at run time, never hard-code), nine languages, guided generation (`@Generable`
typed outputs with enum choices, constrained decoding: zero schema errors in one developer's 200 runs), a `Tool`
protocol, non-disableable guardrails with documented false positives, and typed errors (`exceededContextWindowSize`,
`guardrailViolation`, `rateLimited`, `refusal`). Private Cloud Compute's larger model (32k window) opens to third-party
apps on macOS 27 behind an entitlement. Apple's own task list is summarisation, extraction, classification, tagging,
composition, revision over text the app holds; not code, long reasoning, or world knowledge. In this harness it fits
the **decider** role (`dev-workflows.models.decider`) and small clerk jobs (a failure's category, a note's tags, a
source's one-line why, the words for a row's Why column), through the existing `fm-bridge` once it passes a typed
output and a choice list; never a coding or research-synthesis role. Where Apple Intelligence is off, the role falls
back along its list and says so.

## Behaviours

### A. The harness: project work records, GitHub as the record

- `dev-workflows.combined.entities` [GAP] (#6116) — one model of project work extends the existing records: Project =
  `ResearchProject`, Milestone = `ResearchPlan`, Issue = `ResearchTask` (+ GitHub URL, plan step, behaviour ids),
  Comment = `ResearchNote` on an issue, Run = a job row, Question/Approval = `HumanReviewRequest` on a spec, plan or
  issue; two layers above them: **Spec** (path, title, milestone, status, behaviours `{id, tag, issue}`) and **Plan**
  (the spec's build order; steps `{N.M, title, behaviours, tests, depends_on, size, issue}`). Test:
  `fichero-server/tests/unit/research/test_combined_model_records.py::test_entities`.
- `dev-workflows.combined.github-names` [GAP] (#6116) — Project, Milestone, Issue, Pull Request, Label, Comment, Release,
  Assignee are the words in the app, API and CLI; the storage names stay behind aliases. Test:
  `fichero-server/tests/unit/research/test_github_names_and_aliases.py::test_github_names`.
- `dev-workflows.combined.github-sync` [GAP] (#6116) — for a project with a repo, issues, milestones, labels, comments and
  PR state are pulled with `gh` every five minutes and on open and stored by URL; Fichero's edits (create, title, body,
  comment, label, milestone, close, reopen) go out through **one guarded sync step**: a typed operation with a grant
  (`dev-workflows.security.capability-grants`), the public-repo check of `dev-workflows.combined.public-boundary`, then
  the engine's journaled writer; the first stage pulls only, against this repo on a scratch base path.
  **Conflict rule:** on work state (open/closed, labels, milestone, assignee) GitHub wins when both sides changed since
  the last sync; on Fichero's own fields (spec, plan step, behaviour ids, run, cost) Fichero wins; on text (title,
  body, a comment) a conflict is a question in the queue showing both versions, never resolved by itself. Test:
  `fichero-server/tests/unit/research/test_github_sync.py::test_pull_push_and_conflict_rule`.
- `dev-workflows.combined.public-boundary` [PROPOSED] — every text that leaves for GitHub (title, body, comment, label,
  commit message) passes a boundary check first: no personal names from the project's people list, no local paths, no
  manuscript or source text from a private library, no secret shapes; a hit refuses the write naming the field and
  parks it as a question; every write, refused or made, is one row in Activity and one line in the log with the
  operation, the target URL and who or what asked. Test:
  `fichero-server/tests/unit/security/test_public_boundary.py::test_private_text_is_refused_and_every_write_is_logged`.
- `dev-workflows.run.engine-records-are-truth` [PROPOSED] (maintainer 2026-10-31) — a run's truth is the engine's own
  records, the checkpointer and the jobs table, from the first slice; a run log (TSV and rows) is written from them;
  work state is GitHub's after the sync; Activity rows are views of the records. Test:
  `fichero-server/tests/unit/workflows/test_engine_records_are_truth.py::test_run_state_reads_from_records_not_the_journal`.
- `dev-workflows.run.supervision` [PROPOSED] (maintainer 2026-10-31) — the harness runs supervised: a supervisor (the Lead
  session, a Sonnet builder, or the maintainer) can **stop** any run, worker or the whole harness (a hold, during which
  nothing lands or closes), **inspect** a run's checkpoints, job rows, log rows, handoff files and worktree from the
  Activity row or the CLI chat, and **repair**: resume from the last checkpoint, re-brief a worker from its handoff,
  rebuild job rows from the log when the engine has lost history, or set an item aside as needs-maintainer; every
  repair is a row with who did it and why. Test:
  `fichero-server/tests/unit/workflows/test_supervision.py::test_stop_inspect_repair_and_hold_blocks_landing`.
- `dev-workflows.combined.spec-layer` [GAP] (#6116) — a spec is read from the repo file (status, behaviour ids with tags
  and issues, cited tests); the guards stay the binding; the app and CLI list specs with tag counts. Test:
  `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_spec_layer`.
- `dev-workflows.combined.plan-layer` [GAP] (#6116) — a plan is the spec's build order as steps with dependencies and
  issues; a plan step (ported from the runner's `plan`/`plan-approve`, dry run by default) proposes and files it; a plan is a typed proposal the
  person accepts before any `gh` write. Test: `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_plan_layer`.
- `dev-workflows.combined.approvals` [GAP] (#6116) — three approvals, each a `HumanReviewRequest` in the one queue: a
  spec's status flip, a plan (issues filed), a check-file or acceptance-line change; everything else runs without a
  person. Test: `fichero-server/tests/unit/research/test_approvals.py::test_three_approvals`.
- `dev-workflows.workspace.source-kind` [GAP] (#6116) — a code repository is a workspace source: a folder tied in place,
  indexed lazily (outline, symbols, text search on demand), never imported as pages; the Fichero repo is a separate
  dev library (ruling Q3). Test: `fichero-server/tests/unit/sources/test_workspace_source.py::test_workspace_source`.
- `dev-workflows.workspace.worktrees-map-to-issues` [GAP] (#6116) — a cluster's worktree and branch derive from the spec
  and numeric issue ids, never titles, and are recorded on the issues' records. Test:
  `fichero-server/tests/unit/sources/test_workspace_worktrees_and_github.py::test_worktrees_map`.

### B. The harness: workers

- `dev-workflows.worker.steers` [PROPOSED] — a worker session owns one task's judgement; its loop is the harness's own,
  and it calls the steps as tools (`brief`, `check`, `request-review`, `land`, `close`, `update-issue`, `file-bug`,
  `ask`, `hand-off`, and for research `search`, `fetch`, `save-source`, `note`), each an audited engine action with its
  check; scripts and hooks act between tasks and as guards (wake, ack re-send within ten minutes, budgets, verdict
  bound to a sha, the ladder before any land). Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_worker_steers_through_step_tools`.
- `dev-workflows.worker.handoff` [PROPOSED] — at 85 % of the context window, or at a task boundary, a harness hook (the
  successor hook that runs today, one per harness kind) writes the handoff from the engine's rows and git or the task's notes — the spec or question and its sections; the ordered items
  with state; one line per commit or saved source; commands run and results; the current failing command or open
  lead and its last output; decisions taken and alternatives rejected; files or sources touched; the do-not list;
  budget used; under two thousand tokens, one paragraph the worker may add — and starts the successor at once; a
  successor result already on the task (`git patch-id`, or a source URL) is refused as re-done work. On a 16-32k
  context the same handoff fires per item, so a long research run is a chain of short sessions on a cached prefix.
  Test: `fichero-server/tests/unit/workflows/test_cluster_run.py::test_handoff_and_successor`.
- `dev-workflows.worker.stop-and-ask` [PROPOSED] — a worker stops and asks, parking only its item, when an acceptance
  line would change, a pinned check trips, the diff bound trips twice, the same test fails twice, a step needs a paid
  or irreversible action, a source contradicts the question's premise, the spec contradicts the code, or the turn or
  dollar budget is hit; it never stops for context. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_stop_and_ask_cases`.
- `dev-workflows.worker.two-capability-sets` [PROPOSED] — the Builder set (worktree, shell, git, step tools, scratch base
  path, contributor tier) and the Researcher set (read-only library actions, web search and fetch, source/note/task
  writes through the audited layer as the user's account, no shell) are granted per step; one session never holds
  both; a research session never holds a GitHub token. Test:
  `fichero-server/tests/unit/workflows/test_capability_sets.py::test_dev_and_research_sets_never_mix`.

### C. The harness: worker start and stop, and the tools

- `dev-workflows.tool.check` [PROPOSED] — a `check` tool runs the ladder for the worker: `scripts/lane_ready_check.sh`, the
  named pytest, `scripts/check_*.py` (with the skip list and per-guard time budgets carried over from the frozen
  runner), diff-bound and failing-run-pasted; argv lists only, a cwd and a timeout per command, stdout, stderr and exit
  code returned as typed results; the same command set is what the land step re-runs on the rebased head. Test:
  `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — the engine starts a worker of one of two kinds (maintainer, 2026-10-31):
  `claude` (Claude Code, `claude -p` as `cli_agent.py` runs it today, unchanged) and `pi` (headless `pi -p`, a session
  directory, the role's rules appended, provider and model from the role; returns usage, tool errors, the reported
  sha); `fake` is the test double that replays a scenario, never a kind a person starts; the decider role's Apple Intelligence call is not a worker. The Researcher's in-app loop is the
  engine's existing chat tool loop over the audited action layer, under the same records, so a 24 GB laptop needs no
  terminal. Each worker has a role, a model from the profile, a brief and a cost/turn cap; result typed
  `{sha|verdict|text, usage}`. Test: `fichero-server/tests/unit/workflows/test_worker_node.py::test_worker_kinds`.
- `dev-workflows.tool.git` [GAP] (#6116) — a `git` tool offers a closed list of operations as typed inputs (worktree
  add/remove, status, diff stat, rebase onto, merge --no-ff, range-diff, log of a range, push to the integration branch);
  refuses any push to `main` or a `v*` tag; push needs a land grant. Test:
  `fichero-server/tests/unit/workflows/test_git_gh_tools.py::test_git_tool`.
- `dev-workflows.tool.gh` [GAP] (#6116) — a `gh` tool: reads and writes as typed operations through the engine's one
  journaled writer (ported from `pipeline/gh.py`: dry run by default, every write logged), with an allow-list per role.
  Test: `fichero-server/tests/unit/workflows/test_git_gh_tools.py::test_gh_tool`.
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — `ask_human()` + resume exist; the `ask` tool parks the task with a
  typed question (text, options, the artifact) and resumes durably across an engine restart from Activity, the
  Research workspace, the CLI chat or a page. Test:
  `fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py::test_human_question_survives_restart`.

### D. The harness: runs, review, landing, recovery, models

- `dev-workflows.run.worker-start-stop` [PROPOSED] — the engine starts a worker for a task (a Builder cluster, headless on a
  scratch base path with a pinned dev engine, ruling Q1; a Researcher task, in-app on the person's engine, no terminal),
  with its brief, kind, model and grants, records it as one Activity row with a child row per tool call and report,
  stops it on Stop, a budget hit or a hold, and starts its successor when the hook hands off; no LangGraph graph drives
  the loop. Test: `fichero-server/tests/unit/workflows/test_worker_start_stop.py::test_start_record_stop_and_successor`.
- `dev-workflows.run.review-per-issue` [PROPOSED] — the `request-review` tool starts a fresh reviewer-role worker on the
  issue's commit, its verdict bound to the sha, with findings; NOT_READY returns the findings to the same session (two
  rounds, then the queue). A
  research task's review is the person's: sources and notes are proposals until accepted. Test:
  `fichero-server/tests/unit/workflows/test_review_and_land.py::test_review_per_issue`.
- `dev-workflows.run.land-per-cluster` [PROPOSED] (maintainer 2026-10-31) — the `land` tool is a guard script: it lands a
  cluster as one fast-forward to the integration branch only when every issue is READY and the ladder is green on the
  rebased head (`patch-id` reuse of reviews); never `main`; enforced by `dev-workflows.run.land-gate`; each issue is then closed with its sha or left open with its residue. Test:
  `fichero-server/tests/unit/workflows/test_review_and_land.py::test_land_per_cluster`.
- `dev-workflows.run.recovery` [PROPOSED] — on restart every task whose worker is gone is restarted from its handoff; a
  stuck worker is told once, then replaced by a successor from the handoff; a budget stop parks the item with a
  question; the machine budget refuses to start a worker when memory, disk or load is short; every recovery is a row.
  Keeping the harness awake is the harness's own duty: a scheduled tick (`workflows/scheduler.py`) wakes it every
  twenty to thirty minutes to re-send briefs, start successors and surface questions, so an unattended night never
  depends on a person's session being awake.
  Test: `fichero-server/tests/unit/workflows/test_recovery.py::test_restart_stuck_budget_and_machine`.
- `dev-workflows.run.land-gate` [PROPOSED] — landing is enforced outside the model: a worker's worktree has no push
  right (its `origin` push URL is disabled and it holds no GitHub token), so `git push` from a worker fails whatever it
  is told; only the engine's `land` step, running with the harness's own credential, pushes `integration`, and only for
  a head whose every issue has a READY verdict bound to that exact sha and whose ladder is green on it; a GitHub
  ruleset on `integration` requires that verdict status, written by the land step, so a push around the engine is
  refused by GitHub too. `main` stays PR-and-merge only (#6142), unchanged. Test:
  `fichero-server/tests/unit/workflows/test_land_gate.py::test_worker_push_fails_and_only_the_land_step_pushes`.
- `dev-workflows.run.watch-tick` [PROPOSED] — the scheduled tick (every twenty to thirty minutes, the harness's own wake)
  looks at every task and acts or asks: a worker process gone with its task unfinished → a successor from the handoff,
  or a question when there is no handoff; a handoff written with no successor after twenty minutes → the successor is
  started; a cluster READY and unlanded after thirty minutes → `land`, or the refusal as a question; a worker with no
  row written for `stuck_minutes` → told once, then replaced; each action is a row. The two scenarios that failed on
  2026-10-31 (a READY item unlanded for two hours; a builder stalled with no successor) are the dry run's cases. Test:
  `fichero-server/tests/unit/workflows/test_watch_tick.py::test_gone_worker_orphan_handoff_and_unlanded_ready`.
- `dev-workflows.run.machine-watch` [PROPOSED] — the tick also reads load, free memory and free disk on every machine the
  harness uses (this Mac; the test Macs over ssh) and, past the limits (load above twice the cores, disk under 20 GiB,
  memory pressure critical: `execution/throttle.py`'s readings), refuses new starts, tells running workers to finish the
  current step and park, and writes an alert row and a question; it resumes when the machine has been under the limits
  for five minutes; a run already under way is paused, not only new work refused. Test:
  `fichero-server/tests/unit/workflows/test_machine_watch.py::test_overload_pauses_running_work_and_refuses_new`.
- `dev-workflows.run.log` [PROPOSED] — one row per item attempt: model, provider, precision, context cap, prompt/cached/
  output tokens, tool calls and errors, diff lines or sources saved, wall time, cost, ladder, verdicts, rework rounds,
  false done; shown in Activity and written as TSV. Test: `fichero-server/tests/unit/workflows/test_run_log.py::test_run_log_row`.
- `dev-workflows.run.feeder` [PROPOSED] — scripts choose the next task: the person's pointed milestone, then urgent, then
  bugs, then the plan's build order; claimed, blocked and running items skipped; a brief that fails lint goes to the
  queue as a write-up, never to a worker. Test: `fichero-server/tests/unit/workflows/test_feeder.py::test_feeder_order_and_lint`.
- `dev-workflows.models.role-config` [PROPOSED] — a profile names a model per role (builder, reviewer, lead-model, helper,
  researcher, manager, decider): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`, `apple`, `claude-code`), model
  id, precision, context cap, resident memory; the loader refuses a roster whose resident models exceed the machine's
  cap; a role falls back along its list when a provider is absent (no Apple Intelligence, no key, no server). Test:
  `fichero-server/tests/unit/workflows/test_model_config.py::test_roles_name_models_and_fit_the_cap`.
- `dev-workflows.models.results-pick` [PROPOSED] — a role moves to a cheaper model only on the run log: twenty items with
  READY rate within fifteen points of the current model's, no false done, no write outside the worktree; a reviewer
  also agrees with the binding reviewer on ninety percent and is never READY where it said NOT_READY. Test:
  `fichero-server/tests/unit/workflows/test_model_config.py::test_role_moves_only_on_the_log`.
- `dev-workflows.models.decider` [PROPOSED] — small fixed-choice decisions (which model suits a step, is this failure
  environment or real, is this item exact enough for a small model, what runs next among the ready items) are made by
  a rule where one exists, else by the `decider` role: a typed output over a fixed choice list (Apple Intelligence
  guided generation on a Mac that has it, else the helper model), with the evidence it used; a decision with no
  evidence line is refused and falls to the rule or the queue; every decision is logged and the log is scored against
  outcomes, so a decider that trails the rule is turned off. Test:
  `fichero-server/tests/unit/workflows/test_decider.py::test_decider_fixed_choices_with_evidence`.

### E. The Builder layer

- `dev-workflows.builder.cluster` [PROPOSED] — the Builder's unit of work is a cluster: one spec and its build-order issues,
  worked in order, one commit per issue with its test in the same commit; the cluster record (issue states and shas,
  written by the runner) lives on the plan. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_cluster_in_build_order_one_commit_each`.
- `dev-workflows.builder.bug-narrowing` [PROPOSED] — before a bug's brief reaches a model, a script reproduces and narrows
  it (runs the failing command, localises symbols and tests, searches the base's history, pastes the failing tail); a
  bug it cannot reproduce goes to the thinker role marked so. Test:
  `fichero-server/tests/unit/workflows/test_bug_narrowing.py::test_reproduced_or_marked`.

### F. The Researcher layer

- `dev-workflows.researcher.find-sources` [PROPOSED] — a task "find sources on X" runs the search provider, fetches the
  candidates through the existing guards, and saves each as a `SearchSource` with title, URL, date seen, a one-line
  why, and the quote it rests on; nothing is saved without a quote; duplicates by URL are refused; the person accepts
  or discards sources in the Sources tab. Test:
  `fichero-server/tests/unit/research/test_find_sources_task.py::test_sources_saved_with_quotes_and_no_duplicates`.
- `dev-workflows.researcher.search-libraries` [PROPOSED] — a task "search the libraries for X" runs the library's own
  search and KG queries (`local_search`) over the person's open libraries and files what it finds as sources linked to
  the documents and segments, with the matching words; an external catalogue (a library's OPAC or an aggregator) is a
  later connector behind the same tool, not a scrape. Test:
  `fichero-server/tests/unit/research/test_search_libraries_task.py::test_library_hits_are_sources_with_segments`.
- `dev-workflows.researcher.read-and-note` [PROPOSED] — a task "read these sources and tell me what they say about X"
  produces notes that cite the source and quote, and proposes follow-up tasks under the milestone; at a 16-32k context
  it reads one source per session and hands off; a synthesis needing more than fits goes to a cloud model the person
  allowed or is refused with the reason. Test:
  `fichero-server/tests/unit/research/test_read_and_note_task.py::test_notes_cite_and_handoff_per_source`.
- `dev-workflows.research.one-task-model` [GAP] (#2067) — a research task and a dev issue are one record shape (`ResearchTask`
  extended). Test: `fichero-server/tests/unit/research/test_combined_model_records.py::test_one_task_model`.
- `dev-workflows.research.one-question-queue` [GAP] (#2067) — a workflow's question and the Researcher's are one
  `HumanReviewRequest` in one queue; answering from any surface resumes the parked run. Test:
  `fichero-server/tests/unit/research/test_one_question_queue.py::test_one_queue`.
- `dev-workflows.research.web-search` [PROPOSED] — search is a configured provider behind the existing SSRF and size
  guards: a self-hosted SearXNG JSON endpoint by default, a paid API as a fallback, the DuckDuckGo HTML scrape last;
  every URL fetched is logged on the task. Test:
  `fichero-server/tests/unit/research/test_web_search_provider.py::test_provider_order_and_url_log`.

### G. Surfaces and UX

- `dev-workflows.surface.cli-chat` [PROPOSED] — `fichero chat` (and the MCP tools) lists specs, milestones, issues and
  tasks, points a milestone, starts a cluster or a research task, shows runs, workers and questions, answers a
  question, approves a plan; every verb is an audited action, the same one the app and the workers call. Test:
  `fichero-cli/tests/test_chat_dev_verbs.py::test_dev_verbs_are_audited_actions`.
- `dev-workflows.surface.app` [GAP] (#2067) — the Research workspace's Plan tab shows milestones, issues or tasks and
  questions for any project; the workflow canvas and run log show a run; the question queue is one list. Test:
  `fichero-server/tests/unit/api/test_dev_project_view.py::test_app_surface_reads_the_same_records`.
- `dev-workflows.ux.activity-table` [PROPOSED] — the Activity window is one native sortable `Table` with disclosure
  rows (SwiftUI `Table` with `children:`, as the approved Activity spec says) over one data shape from the engine with
  a stored parent id: run › stage › step › batch › item for recipes, task › session › step for the Researcher, cluster ›
  issue › session › step for the Builder. Columns, in this order and these words: Name · Working on (the current file,
  page or issue) · Progress (a bar with a count, a spinner while the count is unknown) · Time · Cost · State · Why (one
  short plain reason on failure or waiting); more columns (Started, Started by, Images, Steps, Greenhouse gas) are
  hidden by default and shown like Activity Monitor's. Toolbar: a few icon controls and a search field; a small summary
  strip at the bottom (load graph, totals). Rows update one at a time in place, never a wholesale re-render; children
  load lazily and parents carry summaries, so the table holds on 100k pages. Overrides the approved spec's
  measures-first column order and its stage bar (the bar becomes rows); keeps its three groups, detail view and the
  status island. Test: `fichero/Tests/Unit/general/Models/ActivityTableTests.swift`.
- `dev-workflows.ux.controls-work` [BROKEN] (#4402) — Pause, Resume and Stop are three distinct controls with distinct
  icons and words, each shows the state it put the row in, and each reaches the work: a Stop cancels a long single call
  rather than waiting for its item boundary (today `pause_requested()` is read only at the per-item boundary,
  `builder.py:1176`; the Activity spec's `workflows.run.controls-are-fire-and-forget` is the open half); a control that
  has not acted within ten seconds says so on the row. Test:
  `fichero-server/tests/unit/workflows/test_controls_reach_the_call.py::test_stop_cancels_a_running_call`.
- `dev-workflows.ux.workers-are-rows` [PROPOSED] — every Builder worker, handoff, review, question and landing, and every
  Researcher session, source saved and question, is a row under its task in the same table, with Working on, Progress,
  Time, Cost, State and Why filled. What lacks parent links or a current item today and must gain them: a workflow run's spaCy step (no row), a
  recipe run's own status beside its row, the runner's items (no job row). Test:
  `fichero-server/tests/unit/api/test_workers_are_rows.py::test_worker_handoff_review_rows_under_task`.

### H. Security

- `dev-workflows.security.untrusted-text` [GAP] (#6116) — issue bodies, comments, spec text and fetched pages reach a model
  only as fenced, labelled data; the turn that reads them has no write tool; anything proposed is acted on by a later
  script step with a fixed argv and a grant. Test: `fichero-server/tests/unit/security/test_untrusted_text.py::test_injected_text_makes_no_write`.
- `dev-workflows.security.argv-injection` [GAP] (#6116) — script, git and gh nodes take typed inputs; free text goes in a
  file or stdin; each argv value matches `^[A-Za-z0-9._/-]+$`, no leading `-`, no `..`; names come from numeric ids.
  Test: `fichero-server/tests/unit/workflows/test_git_gh_tools.py::test_argv_injection_refused`.
- `dev-workflows.security.capability-grants` [GAP] (#6116) — a per-step grant (operation set + target) held by the engine;
  gh and git nodes refuse a write without one; model-reachable steps get bookkeeping grants only. Test:
  `fichero-server/tests/unit/workflows/test_capability_grants.py::test_model_output_cannot_close`.
- `dev-workflows.security.builder-kind-gated` [GAP] (#6116) — the Builder worker kind and the `git`, `gh` and `check`
  tools exist only in the contributor tier, off by default; a Researcher worker can never be started with them. Test:
  `fichero-server/tests/unit/workflows/test_capability_sets.py::test_builder_kind_gated`.
- `dev-workflows.security.tokens-and-redaction` [GAP] (#6116) — a GitHub token lives in one `gh` subprocess's environment
  per call; no token, key or credential reaches workflow state, the checkpointer, the journal, the run log or captured
  output. Test: `fichero-server/tests/unit/security/test_no_secret_persists_after_a_run.py::test_tokens_and_redaction`.

### I. Dry runs and rollout

- `dev-workflows.rollout.dry-run` [PROPOSED] — the `fake` worker kind replays a scenario (scripted tool calls and reports plus
  the Activity rows and log expected) through the engine's start/stop and tools with no model and no money, covering every tool-call shape
  including a malformed one, one commit per issue over a three-issue cluster, the handoff and the successor, ask-park-
  answer-resume across a restart, NOT_READY and a rework round, the ladder rungs tripping, a dead worker and an
  unbriefed one, a 429, a 5xx and a context overflow, a false done, the budget stop, land and close against a fake
  `gh`, a research task saving three sources with quotes, and a complete log row. Test: `fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py::test_scenario_matches_the_runner`.
- `dev-workflows.rollout.pipeline-frozen` [PROPOSED] (maintainer 2026-10-31) — `pipeline/` takes no new code; what the engine
  needs from it is ported, not called: the brief localisation (`localise.py`), the ladder's rungs as script-node
  commands over `scripts/check_*.py` and `lane_ready_check.sh`, the closer's residue rule, the `gh` writer, the run-log
  columns; it is removed once the engine has landed real clusters for two weeks; no step of this spec waits on parity
  with it. Test: `fichero-server/tests/unit/workflows/test_pipeline_frozen.py::test_engine_calls_scripts_not_pipeline`.

## Rulings

- 2026-10-26 (kept): pinned separate dev engine first (Q1); the repo is a separate dev library (Q3); model nodes do
  bookkeeping only (Q4); GitHub names (Q6); `plan-approve` first (Q8); contributor tier off by default (Q5); chains retire into recipes (Q9); invites for contributors (Q10).
- 2026-10-27 (Activity, kept): one window and one job model; lanes sized from the machine; cloud by default per recipe
  step with cost shown; the embedder's own lane.
- 2026-10-31 (paraphrased): one harness, two uses, Fichero Builder and Fichero Researcher; built in Fichero as part of the
  agent area; a long-running builder, Claude Code agents first, judged by use, no shape comparison first; land per
  cluster; models by configuration and results; Pi is a worker kind; the Researcher's machine is a 24 GB laptop; the
  deployment profiles above; the Activity window follows Activity Monitor with a hierarchy; Builder and Researcher
  standing by the end of November. Later the same day: this repo's issues are managed in Fichero and synced to GitHub
  through a guarded step (replaces Q7 pull-only); the engine's records are the truth for runs from the start and the journal
  is a log (replaces Q2), under supervision by the Lead session and the Sonnet builders.
- Deferred as text, no behaviours yet: invited contributors; shared projects (task leases); the release as a dev workflow (the one fixed sequence that earns one: long, resumable at the failed step, a yes before anything public, step by step in Activity).

## Build order

Thin slices through November 2026, each one a Claude Code builder can take from its heading; dogfooding starts at 1.1.
`Depends on` defaults to the step before within the stage.

### Stage 1 — a Claude Code builder runs one cluster with the hook and tools, the engine recording it; one Researcher task (weeks 1-2)

#### Step 1.1 — the engine starts and stops a worker; the check tool
- Behaviours: `dev-workflows.tool.check`, `dev-workflows.run.worker-start-stop`
- Tests: fichero-server/tests/unit/workflows/test_worker_start_stop.py, fichero-server/tests/unit/workflows/test_check_tool.py
- Size: M

#### Step 1.2 — worker kinds: claude today, fake for the dry run
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.rollout.dry-run`, `dev-workflows.rollout.pipeline-frozen`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py, fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py, fichero-server/tests/unit/workflows/test_pipeline_frozen.py
- Size: M

#### Step 1.3 — the Builder cluster: order, one commit per issue, the worker steers
- Behaviours: `dev-workflows.builder.cluster`, `dev-workflows.worker.steers`, `dev-workflows.worker.stop-and-ask`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py
- Size: M

#### Step 1.4 — the first Researcher task: find sources, with quotes
- Behaviours: `dev-workflows.researcher.find-sources`, `dev-workflows.research.web-search`, `dev-workflows.worker.two-capability-sets`
- Tests: fichero-server/tests/unit/research/test_find_sources_task.py, fichero-server/tests/unit/research/test_web_search_provider.py, fichero-server/tests/unit/workflows/test_capability_sets.py
- Depends on: 1.2
- Size: M

#### Step 1.5 — the review, land and git tools; the question survives a restart
- Behaviours: `dev-workflows.run.review-per-issue`, `dev-workflows.run.land-per-cluster`, `dev-workflows.node.human-question`, `dev-workflows.tool.git`
- Tests: fichero-server/tests/unit/workflows/test_review_and_land.py, fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py, fichero-server/tests/unit/workflows/test_git_gh_tools.py
- Depends on: 1.3
- Size: M

#### Step 1.6 — the handoff hook and successor, recovery, the log; the engine's records are the truth, supervised
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.recovery`, `dev-workflows.run.log`, `dev-workflows.run.engine-records-are-truth`, `dev-workflows.run.supervision`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_recovery.py, fichero-server/tests/unit/workflows/test_run_log.py, fichero-server/tests/unit/workflows/test_engine_records_are_truth.py, fichero-server/tests/unit/workflows/test_supervision.py
- Size: M

#### Step 1.7 — secrets never persist
- Behaviours: `dev-workflows.security.tokens-and-redaction`
- Tests: fichero-server/tests/unit/security/test_no_secret_persists_after_a_run.py
- Depends on: 1.2
- Size: S

#### Step 1.8 — the land gate, the watch tick and the machine watch
- Behaviours: `dev-workflows.run.land-gate`, `dev-workflows.run.watch-tick`, `dev-workflows.run.machine-watch`
- Tests: fichero-server/tests/unit/workflows/test_land_gate.py, fichero-server/tests/unit/workflows/test_watch_tick.py, fichero-server/tests/unit/workflows/test_machine_watch.py
- Depends on: 1.6
- Size: M

### Stage 2 — seen in the app: the Activity table, the records, the sync, the surfaces (weeks 2-3)

#### Step 2.1 — the Activity table with a hierarchy, and controls that work
- Behaviours: `dev-workflows.ux.activity-table`, `dev-workflows.ux.controls-work`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero-server/tests/unit/workflows/test_controls_reach_the_call.py
- Depends on: 1.1
- Size: M

#### Step 2.2 — workers, handoffs and reviews are rows
- Behaviours: `dev-workflows.ux.workers-are-rows`
- Tests: fichero-server/tests/unit/api/test_workers_are_rows.py
- Size: M

#### Step 2.3 — the records and GitHub names
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-names`, `dev-workflows.research.one-task-model`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py, fichero-server/tests/unit/research/test_github_names_and_aliases.py
- Depends on: 1.7
- Size: M

#### Step 2.4 — the guarded GitHub sync and the public boundary
- Behaviours: `dev-workflows.combined.github-sync`, `dev-workflows.combined.public-boundary`
- Tests: fichero-server/tests/unit/research/test_github_sync.py, fichero-server/tests/unit/security/test_public_boundary.py
- Size: M

#### Step 2.5 — spec and plan layers, approvals
- Behaviours: `dev-workflows.combined.spec-layer`, `dev-workflows.combined.plan-layer`, `dev-workflows.combined.approvals`
- Tests: fichero-server/tests/unit/research/test_spec_and_plan_layers.py, fichero-server/tests/unit/research/test_approvals.py
- Size: M

#### Step 2.6 — the CLI chat verbs, the feeder, one question queue
- Behaviours: `dev-workflows.surface.cli-chat`, `dev-workflows.run.feeder`, `dev-workflows.research.one-question-queue`
- Tests: fichero-cli/tests/test_chat_dev_verbs.py, fichero-server/tests/unit/workflows/test_feeder.py, fichero-server/tests/unit/research/test_one_question_queue.py
- Size: M

#### Step 2.7 — the repo as a workspace source
- Behaviours: `dev-workflows.workspace.source-kind`, `dev-workflows.workspace.worktrees-map-to-issues`
- Tests: fichero-server/tests/unit/sources/test_workspace_source.py, fichero-server/tests/unit/sources/test_workspace_worktrees_and_github.py
- Depends on: 2.3
- Size: M

### Stage 3 — models by configuration, the Researcher's next tasks, the gates (weeks 3-4)

#### Step 3.1 — the gh tool, argv jail, grants
- Behaviours: `dev-workflows.tool.gh`, `dev-workflows.security.argv-injection`, `dev-workflows.security.capability-grants`
- Tests: fichero-server/tests/unit/workflows/test_git_gh_tools.py, fichero-server/tests/unit/workflows/test_capability_grants.py
- Depends on: 2.7
- Size: M

#### Step 3.2 — models in configuration, picked by results; the decider
- Behaviours: `dev-workflows.models.role-config`, `dev-workflows.models.results-pick`, `dev-workflows.models.decider`
- Tests: fichero-server/tests/unit/workflows/test_model_config.py, fichero-server/tests/unit/workflows/test_decider.py
- Depends on: 1.6
- Size: M

#### Step 3.3 — the Researcher reads, notes and searches the libraries
- Behaviours: `dev-workflows.researcher.read-and-note`, `dev-workflows.researcher.search-libraries`, `dev-workflows.security.untrusted-text`
- Tests: fichero-server/tests/unit/research/test_read_and_note_task.py, fichero-server/tests/unit/research/test_search_libraries_task.py, fichero-server/tests/unit/security/test_untrusted_text.py
- Depends on: 1.4
- Size: M

#### Step 3.4 — bug narrowing, the Builder kind gated, the app surface
- Behaviours: `dev-workflows.builder.bug-narrowing`, `dev-workflows.security.builder-kind-gated`, `dev-workflows.surface.app`
- Tests: fichero-server/tests/unit/workflows/test_bug_narrowing.py, fichero-server/tests/unit/workflows/test_capability_sets.py, fichero-server/tests/unit/api/test_dev_project_view.py
- Depends on: 3.1
- Size: M

## Behaviour tests

Every behaviour names its test above, one test per behaviour, written in its step; each `security.*` test includes its
failing case. The table is the pinning the guard reads.

| Behaviour | Step |
|-----------|------|
| `dev-workflows.tool.check` | 1.1 |
| `dev-workflows.run.worker-start-stop` | 1.1 |
| `dev-workflows.node.worker` | 1.2 |
| `dev-workflows.rollout.dry-run` | 1.2 |
| `dev-workflows.rollout.pipeline-frozen` | 1.2 |
| `dev-workflows.builder.cluster` | 1.3 |
| `dev-workflows.worker.steers` | 1.3 |
| `dev-workflows.worker.stop-and-ask` | 1.3 |
| `dev-workflows.researcher.find-sources` | 1.4 |
| `dev-workflows.research.web-search` | 1.4 |
| `dev-workflows.worker.two-capability-sets` | 1.4 |
| `dev-workflows.run.review-per-issue` | 1.5 |
| `dev-workflows.run.land-per-cluster` | 1.5 |
| `dev-workflows.node.human-question` | 1.5 |
| `dev-workflows.worker.handoff` | 1.6 |
| `dev-workflows.run.recovery` | 1.6 |
| `dev-workflows.run.log` | 1.6 |
| `dev-workflows.security.tokens-and-redaction` | 1.7 |
| `dev-workflows.run.land-gate` | 1.8 |
| `dev-workflows.run.watch-tick` | 1.8 |
| `dev-workflows.run.machine-watch` | 1.8 |
| `dev-workflows.ux.activity-table` | 2.1 |
| `dev-workflows.ux.controls-work` | 2.1 |
| `dev-workflows.ux.workers-are-rows` | 2.2 |
| `dev-workflows.combined.entities` | 2.3 |
| `dev-workflows.combined.github-names` | 2.3 |
| `dev-workflows.research.one-task-model` | 2.3 |
| `dev-workflows.combined.github-sync` | 2.4 |
| `dev-workflows.run.engine-records-are-truth` | 1.6 |
| `dev-workflows.run.supervision` | 1.6 |
| `dev-workflows.combined.public-boundary` | 2.4 |
| `dev-workflows.combined.spec-layer` | 2.5 |
| `dev-workflows.combined.plan-layer` | 2.5 |
| `dev-workflows.combined.approvals` | 2.5 |
| `dev-workflows.surface.cli-chat` | 2.6 |
| `dev-workflows.run.feeder` | 2.6 |
| `dev-workflows.research.one-question-queue` | 2.6 |
| `dev-workflows.workspace.source-kind` | 2.7 |
| `dev-workflows.workspace.worktrees-map-to-issues` | 2.7 |
| `dev-workflows.tool.git` | 1.5 |
| `dev-workflows.tool.gh` | 3.1 |
| `dev-workflows.security.argv-injection` | 3.1 |
| `dev-workflows.security.capability-grants` | 3.1 |
| `dev-workflows.models.role-config` | 3.2 |
| `dev-workflows.models.results-pick` | 3.2 |
| `dev-workflows.models.decider` | 3.2 |
| `dev-workflows.researcher.read-and-note` | 3.3 |
| `dev-workflows.researcher.search-libraries` | 3.3 |
| `dev-workflows.security.untrusted-text` | 3.3 |
| `dev-workflows.builder.bug-narrowing` | 3.4 |
| `dev-workflows.security.builder-kind-gated` | 3.4 |
| `dev-workflows.surface.app` | 3.4 |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | worker start/stop, tools, review and land, recovery, sync, layers, grants, secrets, researcher tasks, the decider | `fichero-server/tests/unit/workflows/`, `tests/unit/research/`, `tests/unit/security/`, `tests/unit/sources/`, `tests/unit/api/` |
| CLI (pytest) | y | chat verbs are audited actions | `fichero-cli/tests/test_chat_dev_verbs.py` |
| Swift unit | y | the table's rows, columns, in-place update, lazy children | `fichero/Tests/Unit/general/Models/ActivityTableTests.swift` |
| UI (XCUITest) | later | the table on a 100k-page library | Stage 2 follow-up |

## Documentation matrix

| Doc | Says |
|-----|------|
| `docs/contributor_manual/how-fichero-is-built.md` | Fichero builds itself through its workflows; how to run a cluster on a scratch path; the Researcher as the same harness |
| `ui/research.md` | the surface; points here for orchestration and tasks |
| `ui/activity-and-automatic-work.md` | the job model, lanes, throttling; points here for the window's columns and worker rows |
| `harness/deterministic-conductor.md` | the frozen runner's record; retires with it |

## Open questions for the maintainer

1. The external catalogue connector for `researcher.search-libraries`: proposed none until a person asks; the first
   Researcher tasks run over the person's own libraries plus web search, which is what exists today (`local_search`
   and the web tools) and what the two trial tasks need.
