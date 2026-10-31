# Fichero Builder and Fichero Researcher — one harness, two uses — Design Spec

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — a contributor section ("How Fichero is built") saying that
> Fichero builds itself through its own harness, how to run a cluster on a scratch path, and how the same harness runs
> a research project.

> **Status: PROPOSED 2026-10-31 (rewrite 3, cut to the thin design), for the maintainer's approval.** Replaces the text
> approved on 2026-10-26 (c9c24dfbf, 739ad4ba4). Evidence, trial numbers and the thin-harness argument live in
> `agent-work/status/briefs/studio-harness-report.md` and `thin-harness-answer.md`, not here. Tags: [OK] built ·
> [PARTIAL] exists, not wired · [GAP] not built · [BROKEN] fails today · [PROPOSED] decided here, not yet ruled.
> Issues: #6116 (the pipeline), #2067 (Research), #4402 (controls).
>
> Scope with other specs: `pipeline/` is **frozen** (no new code; ideas and the ladder ported; removed once the engine has
> landed real clusters for two weeks) and `harness/deterministic-conductor.md` is its record. `ui/research.md` keeps the
> Research surface; its orchestration lines (`research.manager-with-workers-orchestration`,
> `research.future.agent-operates-projects`, `research.per-model-tool-grants`) are owned here.
> `ui/activity-and-automatic-work.md` keeps the job model, lanes, throttling and durability; § E overrides its window
> columns and adds workers as rows. `ui/workflows.md` keeps the canvas; no graph drives a worker's loop.

## Intent

One harness, two uses. **Fichero Builder** builds Fichero: a long-running worker takes a cluster of issues from one spec,
builds them in order, one commit per issue, checks, asks for review, lands the cluster, updates the issues, hands off
at 85 % of its context and a successor carries on. **Fichero Researcher** does a person's research with the same
harness: finds sources on the web, searches the person's own libraries, reads and notes, files tasks under milestones,
asks when unsure, hands off the same way. The harness is: projects, milestones, issues and specs as Fichero records
synced to GitHub; long-running workers whose loop is the agent harness's own; handoff; review; scripts for every fixed
step; models by configuration; one question queue; one Activity table. What differs between the uses is the worker's
tools, permissions and data, granted per step. The maintainer and the user see and steer it in the app or a CLI chat
over one audited action layer. Scripts decide wherever a rule can; models judge inside a task; the person approves
specs, plans and anything public or paid. Target: Builder and Researcher standing by the end of November 2026 on Claude
Code agents, then other models through OpenRouter, local models later and by configuration only.

## Prior art (adopt, don't invent)

Conductor-style script steps routed on exit codes; LangGraph where a fixed sequence earns it (recipes; `interrupt()` as the
question primitive); GitHub as the public record; macOS Activity Monitor for the window; operators who run coding
agents on 128 GB Macs for weeks (several small models pinned, a session per task on a cached prefix, a tool-call repair
layer). Not adopted: a graph that drives a model turn by turn (the shape that lost here), a second task store, a second
question queue, a second activity list.

## What exists today (paths under `fichero-server/src/fichero_server/`)

- Engine: `workflows/builder.py` + `checkpointer.py` (DuckDB), `human_review.ask_human()` = `interrupt()` with `POST
  /threads/{id}/resume`, `scheduler.py`, `execution/throttle.py` (load, battery, memory, heat readings), one `jobs` table
  with `parent_id` (`execution/jobs.py`), `pause_requested()` read only at the item boundary (`builder.py:1176`, #4402).
- Agent pieces: `workflows/tools/cli_agent.py` runs a local agent CLI (`claude -p`) in its own process group with a
  timeout; `tools/agent.py`; `tools/mcp.py`; the chat tool loop over the audited action layer (`actions/chat_tools.py`,
  `actions/registry.py`: every mutation an `ActionAudit` row, role-gated; per-model grants #4721 GAP).
- Research: `models/research.py` `ResearchProject`/`ResearchPlan`/`ResearchTask`/`ResearchStep`/`ResearchNote`/`SearchSource`;
  `api/routes/research/{crud,notes,tools}.py` (DuckDuckGo-HTML search, browse, fetch behind SSRF and size guards);
  `workflows/tools/research.py`. No catalogue connector; no GitHub code anywhere.
- Apple Intelligence: Foundation Models through the bundled `fm-bridge` (`llm/__init__.py:2229`, provider `apple`); text
  only today, no typed output or tool.
- Activity: `Views/Activity/Window/*`, `Monitor/*`, `RunControls.swift`; the approved spec's `Table` with disclosure rows
  (its Stage 3) is not built.
- CLI/MCP: `fichero workflow …`, `fichero workflow-execution …`, the generated surface; `fichero-mcp` exposes the routes.
  No chat verb lists specs, milestones or issues.
- `pipeline/` (frozen): journal, Pi/API workers, `localise.py`, feeder and lint, the ladder (`checks.py`, `fichero.toml`),
  verdicts bound to a sha, `land`, closer, `plan`/`plan-approve`, budgets, handoff, `gh.py`. What to port is named below.
- Measured so far: in `agent-work/status/briefs/studio-harness-report.md` (servers, models, trials) and
  `local-small-report.md` (small models fit triage and routing; none finished an exact edit; Pi's compaction error is a
  harness fault to fix at the OpenRouter stage).

## Decisions

- **Issues are managed in Fichero and synced to GitHub** (maintainer 2026-10-31): GitHub stays the public record of work
  state; `gh` by hand is the exception; every write goes through one guarded step with a public-repo check and a
  visible log. Specs stay Markdown in the repo, bound by the guards.
- **The engine's records are the truth for runs** (maintainer 2026-10-31): the checkpointer and jobs table; the old
  journal is a log; the Lead session and Sonnet builders supervise.
- **Thin engine; the loop lives in the agent harness** (`thin-harness-answer.md`): the engine holds records, starts and
  stops workers, shows them in Activity, carries questions and grants, keeps the log; a hook does handoff and
  successor; a few tools do brief, check, ask, hand off, land, git. LangGraph graphs only for recipes and the release.
- **Two worker kinds** (maintainer 2026-10-31): Claude Code and Pi; `fake` is the test double; the Researcher's in-app
  loop is the engine's existing chat tool loop under the same records, so a 24 GB laptop needs no terminal.
- **Land per cluster** (maintainer 2026-10-31), enforced outside the model.
- **Fixed steps are scripts** (`lane_ready_check.sh`, `check_*.py`, `scripts/gate`, `verify_all.sh`, `build-and-validate.sh`,
  `close_fixed_issues.py`, the `land` guard), each one Activity row with a count and a Stop where it runs long; only the
  release earns a workflow, deferred.
- **Enforce, don't ask**: every standing rule names its layer (credential or OS, hook, guard at landing, prose only).
- **One worker kind, two capability sets**; **models by configuration, picked by results**; **small-context handoff is a
  core requirement** (the Researcher's machine is a 24 GB laptop).

### Deployment profiles (configuration over one harness)

| Profile | Machine | Models | Runs |
|---|---|---|---|
| Builder, now | M1 Pro 16 GB | Claude Code agents; then OpenRouter models | clusters, reviews, dry runs; engine on a scratch base path |
| Builder, end state | M5 Studio 128 GB | several small local models pinned under a memory cap (a fast MoE builder, a reviewer, a helper, an embedder), a local server with a prefix cache; cloud by exception | 2-3 builder sessions + reviewer + research; headroom for the gate and a build |
| Researcher | M5 MacBook Pro 24 GB | one small local model at a time (4B-9B 4-bit, 2.7-6 GB), Apple Intelligence for typed small jobs, Apple Vision/Speech/Translation, MLX readers when chosen; cloud only where the person allows, cost shown first | one research task at a time, 16-32k context, handoff per source; the engine's heavy steps (import, embed, Kraken: 10-40 GB) and the model alternate under the machine budget; what needs more goes to an allowed cloud model or is refused plainly |

Apple Intelligence (reported, 2026-10-31): a ~3 B on-device model, ~1.2 GB, 4k window on macOS 26 and 8k reported for 27
(read `contextSize` at run time), guided generation with typed enum outputs that developers find reliable, a `Tool`
protocol, non-disableable guardrails with false positives. It fits the **decider** role and clerk jobs, never coding,
review or synthesis; where it is off, the role falls back along its list.

## Behaviours

### A. Workers (the loop is the harness's)

- `dev-workflows.run.worker-start-stop` [PROPOSED] — the engine starts a worker for a task (a Builder cluster, headless on
  a scratch base path with a pinned dev engine, ruling Q1; a Researcher task, in-app) with its brief, kind, model and
  grants, installs its hooks, records one Activity row with a child row per tool call and report, stops it on Stop, a
  budget hit or a hold by killing the process group (never a message), and starts the successor when the hook hands
  off. Test: `fichero-server/tests/unit/workflows/test_worker_start_stop.py::test_start_record_stop_and_successor`.
- `dev-workflows.run.worker-address` [PROPOSED] — per task, the current generation's address (pane or process group,
  session directory, kind, started-at) is registered, rewritten at each handoff, cleared when gone; a supervisor's
  `tell` goes only there (today `tell.sh <pane>`, under 800 characters) and a tell to a stale generation is refused
  naming the current one, so a handoff never leaves two workers in one worktree. Test:
  `fichero-server/tests/unit/workflows/test_worker_address.py::test_tell_reaches_only_the_current_generation`.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — kinds `claude` (`claude -p` as `cli_agent.py` runs it, unchanged) and `pi`
  (headless `pi -p`, a session directory, the role's rules appended, provider and model from the role; returns usage,
  tool errors, the reported sha); `fake` replays a scenario and is never started by a person; each worker has a role, a
  model from the profile, a brief and a cost/turn cap; result `{sha|verdict|text, usage}`. Test:
  `fichero-server/tests/unit/workflows/test_worker_node.py::test_worker_kinds`.
- `dev-workflows.tool.check` [PROPOSED] — the `check` tool runs the ladder: `scripts/lane_ready_check.sh`, the named pytest,
  `scripts/check_*.py` with the skip list and time budgets carried over from `pipeline/projects/fichero.toml`, diff bound,
  failing run pasted; argv lists, a cwd and a timeout per command; typed results; the same set the land step re-runs on
  the rebased head. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`.
- `dev-workflows.tool.git` [GAP] (#6116) — a closed list of operations as typed inputs (worktree add/remove, status, diff
  stat, rebase onto, merge --no-ff, range-diff, log of a range; push only by the land step); argv values match
  `^[A-Za-z0-9._/-]+$`, no leading `-`, no `..`, names from numeric ids; refuses any push to `main` or a `v*` tag. Test:
  `fichero-server/tests/unit/workflows/test_git_tool.py::test_operations_and_argv_jail`.
- `dev-workflows.builder.cluster` [PROPOSED] — the Builder's unit of work: one spec and its build-order issues (parser ported
  from `pipeline/plan.py`), in order, one commit per issue with its test; the brief is built by a script from the issue's
  body **and comments** (spec-link, residue, ruling; newest first), the spec lines and localisation ported from
  `pipeline/localise.py`; the cluster record (issue states, shas) lives on the plan. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_cluster_in_build_order_one_commit_each`.
- `dev-workflows.worker.steers` [PROPOSED] — the worker owns the task's judgement and calls the steps as tools (`brief`,
  `check`, `request-review`, `land`, `close`, `update-issue`, `file-bug`, `ask`, `hand-off`; for research `search`,
  `fetch`, `save-source`, `note`), each an audited action with its check; a model never moves an item. It **stops and
  asks** (parking only its item) when an acceptance line would change, a pinned check trips, the diff bound trips
  twice, the same test fails twice, a step is paid or irreversible, a source contradicts the premise, the spec
  contradicts the code, or the budget is hit; never for context. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_worker_steers_and_stop_and_ask_cases`.
- `dev-workflows.worker.handoff` [PROPOSED] — at 85 % of the context window or a task boundary, a harness hook (one per
  kind; the successor hook that runs today) writes the handoff from the engine's rows and git or the task's notes: the
  spec or question and its sections; ordered items with state and sha; one line per commit or saved source; commands
  run and results; the current failing command or open lead with its output tail; decisions and rejected
  alternatives; files or sources touched; the do-not list; budget used; under two thousand tokens plus one paragraph
  from the worker; then asks the engine to start the successor at once; a result already on the task (`git patch-id`,
  a source URL) is refused as re-done work. At 16-32k the same handoff fires per item. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_handoff_and_successor`.
- `dev-workflows.worker.two-capability-sets` [PROPOSED] — Builder: worktree, shell, git, the step tools, scratch base path,
  contributor tier only (the kind and the `check`/`git` tools are refused outside it); Researcher: read-only library
  actions, web search and fetch, source/note/task writes through the audited layer as the user's account, no shell,
  never a GitHub token; one session never holds both. Test:
  `fichero-server/tests/unit/workflows/test_capability_sets.py::test_sets_never_mix_and_builder_kind_gated`.

### B. Review, landing, gates and watches

- `dev-workflows.run.review-and-land` [PROPOSED] (maintainer 2026-10-31: land per cluster) — `request-review` starts a fresh
  reviewer worker on an issue's commit, its verdict bound to the sha with findings; NOT_READY returns them to the same
  session (two rounds, then the queue); `land` is a guard script that fast-forwards `integration` only when every
  issue is READY and the ladder is green on the rebased head (`patch-id` reuse of reviews), never `main`; each issue is
  then closed with its sha or left open with its residue (`close_fixed_issues.py`'s rule). A research task's review is
  the person's: sources and notes are proposals until accepted. Test:
  `fichero-server/tests/unit/workflows/test_review_and_land.py::test_review_per_issue_and_land_per_cluster`.
- `dev-workflows.run.land-gate` [PROPOSED] — landing is enforced outside the model: a worker's worktree has a disabled
  push URL and no token, so `git push` fails whatever it is told; only the land step pushes, with the harness's
  credential; a GitHub ruleset on `integration` requires the verdict status the land step writes; `main` stays PR-and-
  merge only (#6142). Test: `fichero-server/tests/unit/workflows/test_land_gate.py::test_worker_push_fails_and_only_the_land_step_pushes`.
- `dev-workflows.run.policy-hook` [PROPOSED] (enforce, don't ask) — each worker runs with a PreToolUse policy hook (Claude Code
  hook; Pi extension) and a `commit-msg` hook, plain scripts the engine installs, refusing with a reason: a write or `cd`
  outside the worktree and scratch path, `git stash`, push to `main` or `integration`, `xcodebuild`, `pkill`/`killall` by
  pattern, `rm -r` joined with a listing in one command, a second pytest (lock file), a commit with the wrong author or
  missing trailers, a paid call without a grant; each refusal a row. **Layers:** credential/OS holds the hard rules (no
  token, disabled push URL, no provider key, a sandbox allow-list on the worktree and scratch path, no ssh key to the
  test Macs); the hook is fast feedback, not a security boundary (shell text can be rewritten); guards at landing catch
  the rest (author and trailers over the range, diff bound, failing run, pinned checks, acceptance lines, weakened
  tests); rules only in prose ("ask before a design change") are listed as such and become hook or guard rules once
  seen twice. Test: `fichero-server/tests/unit/workflows/test_policy_hook.py::test_each_forbidden_command_is_refused_with_a_reason`.
- `dev-workflows.run.watch-tick` [PROPOSED] — the harness's own wake (`workflows/scheduler.py`, every twenty to thirty
  minutes) looks at every task and acts or asks: a worker gone with its task unfinished → a successor from the handoff,
  or a question with none; a handoff with no successor after twenty minutes → started; a cluster READY and unlanded
  after thirty minutes → `land` or its refusal as a question; a worker with no row for `stuck_minutes` → told once, then
  replaced; after an engine restart every gone worker is restarted from its handoff; a budget stop parks with a
  question; each action a row. Test: `fichero-server/tests/unit/workflows/test_watch_tick.py::test_gone_orphan_unlanded_stuck_and_restart`.
- `dev-workflows.run.machine-watch` [PROPOSED] — the tick reads load, free memory and free disk on every machine the harness
  uses (this Mac; the test Macs over ssh) and past the limits (load above twice the cores, disk under 20 GiB, memory
  pressure critical) refuses new starts, tells running workers to finish the step and park, writes an alert row and a
  question, and resumes after five minutes under; a run under way is paused, not only new work refused. Test:
  `fichero-server/tests/unit/workflows/test_machine_watch.py::test_overload_pauses_running_work_and_refuses_new`.
- `dev-workflows.run.records-are-truth` [PROPOSED] (maintainer 2026-10-31) — the checkpointer and jobs table are the truth for
  runs; the run log (one row per item attempt: model, provider, precision, context cap, prompt/cached/output tokens,
  tool calls and errors, diff lines or sources saved, wall time, cost, ladder, verdicts, rework rounds, false done) is
  written from them as rows and TSV; Activity shows the rows. Test:
  `fichero-server/tests/unit/workflows/test_records_are_truth.py::test_state_and_log_read_from_records`.
- `dev-workflows.run.supervision` [PROPOSED] — a supervisor (the Lead session, a Sonnet builder, the maintainer) can stop
  any run, worker or the harness (a hold blocks landing and closing), inspect checkpoints, rows, log, handoffs and
  worktree from the Activity row or the CLI chat, and repair (resume from the last checkpoint, re-brief from the
  handoff, rebuild rows from the log, set aside as needs-maintainer); every repair a row with who and why. Test:
  `fichero-server/tests/unit/workflows/test_supervision.py::test_stop_inspect_repair_and_hold_blocks_landing`.
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — the `ask` tool parks the task with a typed question (text, options,
  the artifact) and resumes durably across an engine restart from Activity, the Research workspace, the CLI chat or a
  page; a workflow's question and the Researcher's are one `HumanReviewRequest` in one queue. Test:
  `fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py::test_question_survives_restart`.
- `dev-workflows.rollout.dry-run` [PROPOSED] — the `fake` kind replays a scenario (scripted tool calls and reports plus the
  rows and log expected) through start/stop and the tools with no model and no money: every tool-call shape including
  a malformed one, three issues one commit each, handoff and successor, ask-park-answer-resume across a restart,
  NOT_READY and a rework round, the ladder tripping, a dead and an unbriefed worker, 429, 5xx, context overflow, a
  false done, the budget stop, land and close against a fake `gh`, three sources with quotes, a complete log row. Test:
  `fichero-server/tests/unit/workflows/test_dry_run.py::test_scenario_replays`.
- `dev-workflows.rollout.pipeline-frozen` [PROPOSED] (maintainer 2026-10-31) — `pipeline/` takes no new code; the engine calls
  the `scripts/` guards directly and ports localisation, the plan parser, the residue rule, the `gh` writer (dry run by
  default, every write logged) and the log columns; no step waits on parity with it; it is removed once the engine has
  landed real clusters for two weeks. Test: `fichero-server/tests/unit/workflows/test_pipeline_frozen.py::test_engine_calls_scripts_not_pipeline`.

### C. Records, sync, surfaces

- `dev-workflows.combined.entities` [GAP] (#6116) — one model of project work: Project = `ResearchProject`, Milestone =
  `ResearchPlan`, Issue = `ResearchTask` (+ GitHub URL, plan step, behaviour ids; a research task is the same record),
  Comment = `ResearchNote` on an issue, Run = a job row, Question/Approval = `HumanReviewRequest`; GitHub's names
  (Project, Milestone, Issue, Pull Request, Label, Comment, Release, Assignee) in the app, API and CLI, storage names
  behind aliases. Test: `fichero-server/tests/unit/research/test_combined_model_records.py::test_entities_and_names`.
- `dev-workflows.combined.github-sync` [GAP] (#6116) — for a project with a repo: pull with `gh` every five minutes and on
  open, by URL; Fichero's edits go out through one guarded step: a typed operation with a grant, then the **public
  boundary** (no personal names from the project's people list, no local paths, no private library text, no secret
  shapes; a hit refuses the write and parks a question), then the engine's journaled writer; every write, refused or
  made, is a row and a log line with operation, URL and who asked. Conflict rule: GitHub wins on work state when both
  changed since the last sync; Fichero wins on its own fields; a text conflict is a question showing both versions.
  Stage 2 pulls only, against this repo on a scratch base path. Test:
  `fichero-server/tests/unit/research/test_github_sync.py::test_pull_push_boundary_and_conflict_rule`.
- `dev-workflows.combined.spec-and-plan` [GAP] (#6116) — a spec is read from the repo file (status, behaviour ids with tags
  and issues, cited tests; the guards stay the binding); a plan is its build order as steps with dependencies and
  issues, proposed and filed by the ported `plan`/`plan-approve` (dry run by default); three approvals, each a question
  in the one queue: a spec's status flip, a plan, a check-file or acceptance-line change; nothing else waits for a
  person. Test: `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_spec_plan_and_approvals`.
- `dev-workflows.run.feeder` [PROPOSED] — scripts choose the next task: the person's pointed milestone, urgent, bugs, then
  the plan's build order; claimed, blocked and running skipped; a brief that fails lint (a spec id in an APPROVED spec
  or a bug label, acceptance, test path, in body or comments) goes to the queue as a write-up, never to a worker. Test:
  `fichero-server/tests/unit/workflows/test_feeder.py::test_feeder_order_and_lint`.
- `dev-workflows.workspace.source` [GAP] (#6116) — a repository is a workspace source: a folder tied in place, indexed lazily
  (outline, symbols, text search), never imported as pages; the Fichero repo is a separate dev library (ruling Q3); a
  cluster's worktree and branch derive from the spec and numeric issue ids and are recorded on the issues. Test:
  `fichero-server/tests/unit/sources/test_workspace_source.py::test_workspace_and_worktrees`.
- `dev-workflows.surface.one-action-layer` [PROPOSED] — `fichero chat` and the MCP tools list specs, milestones, issues and
  tasks, point a milestone, start a cluster or a research task, show runs, workers and questions, answer, approve; the
  Research workspace's Plan tab shows the same for any project; every verb is the audited action the app and the
  workers call. Test: `fichero-cli/tests/test_chat_dev_verbs.py::test_dev_verbs_are_audited_actions`.

### D. Models

- `dev-workflows.models.by-config` [PROPOSED] — a profile names a model per role (builder, reviewer, lead-model, helper,
  researcher, manager, decider): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`, `apple`, `claude-code`), model,
  precision, context cap, resident memory; the loader refuses a roster over the machine's cap; a role falls back along
  its list when a provider is absent; a role moves to a cheaper model only on the run log (twenty items, READY rate
  within fifteen points, no false done, no write outside the worktree; a reviewer also agrees with the binding one on
  ninety percent and is never READY where it said NOT_READY); on 128 GB the expected roster is several small models
  pinned at once. Test: `fichero-server/tests/unit/workflows/test_model_config.py::test_roles_cap_fallback_and_move_on_the_log`.
- `dev-workflows.models.decider` [PROPOSED] — small fixed-choice decisions (which model suits a step, environment or real
  failure, exact enough for a small model, what runs next) go to a rule where one exists, else to the `decider` role: a
  typed output over a fixed choice list (Apple Intelligence guided generation where present, else the helper) with an
  evidence line, refused without one, logged and scored against outcomes; a decider that trails the rule is turned
  off. Test: `fichero-server/tests/unit/workflows/test_decider.py::test_fixed_choices_with_evidence`.

### E. UX

- `dev-workflows.ux.activity-table` [PROPOSED] — one native sortable `Table` with disclosure rows over one data shape with a
  stored parent id: run › stage › step › batch › item (recipes), task › session › step (Researcher), cluster › issue ›
  session › step (Builder); columns in this order and these words: Name · Working on · Progress (a bar with a count, a
  spinner while unknown) · Time · Cost · State · Why (one short plain reason); more columns hidden by default; a few
  toolbar icons and a search field; a small summary strip; rows update one at a time in place, children load lazily,
  parents carry summaries (100k pages); every worker, handoff, review, question and landing is a row under its task.
  Overrides the approved Activity spec's measures-first columns and its stage bar; keeps its three groups, detail view
  and status island. Gaps to close for the rows: a workflow run's spaCy step, a recipe's status beside its row. Test:
  `fichero/Tests/Unit/general/Models/ActivityTableTests.swift`.
- `dev-workflows.ux.controls-work` [BROKEN] (#4402) — Pause, Resume and Stop are three distinct controls, each shows the state
  it put the row in and reaches the work: Stop cancels a running call rather than waiting for the item boundary
  (`pause_requested()` is read only there today, `builder.py:1176`); a control that has not acted in ten seconds says
  so on the row. Test: `fichero-server/tests/unit/workflows/test_controls_reach_the_call.py::test_stop_cancels_a_running_call`.

### F. Researcher and the web

- `dev-workflows.researcher.tasks` [PROPOSED] — three first tasks: **find sources** (search provider → fetch through the
  existing guards → `SearchSource` with title, URL, date, a one-line why and the quote it rests on; no quote, no save;
  duplicates by URL refused; accepted or discarded in the Sources tab); **search the libraries** (`local_search` and KG
  over the person's open libraries → sources linked to documents and segments with the matching words; an external
  catalogue is a later connector, none until asked); **read and note** (notes citing source and quote, follow-up tasks
  proposed; one source per 16-32k session with handoff; a synthesis that does not fit goes to an allowed cloud model or
  is refused with the reason). The search provider is configured: SearXNG JSON first, a paid API, the DuckDuckGo
  scrape last; every URL logged on the task. Test:
  `fichero-server/tests/unit/research/test_researcher_tasks.py::test_find_sources_search_libraries_read_and_note`.
- `dev-workflows.security.untrusted-text` [GAP] (#6116) — issue bodies, comments, spec text and fetched pages reach a model
  only as fenced, labelled data; the turn that reads them has no write tool; anything proposed is acted on by a later
  script step with a fixed argv and a grant; no token, key or credential reaches state, rows, log or captured output
  (`BoundedLog` redacts known shapes). Test:
  `fichero-server/tests/unit/security/test_untrusted_text.py::test_injected_text_makes_no_write_and_no_secret_persists`.
- `dev-workflows.builder.bug-narrowing` [PROPOSED] — before a bug's brief reaches a model, a script reproduces and narrows it
  (failing command, localisation, the base's history, the failing tail pasted); a bug it cannot reproduce goes to the
  thinker role marked so. Test: `fichero-server/tests/unit/workflows/test_bug_narrowing.py::test_reproduced_or_marked`.

## Rulings

- 2026-10-26 (kept): pinned separate dev engine first (Q1); the repo is a separate dev library (Q3); model steps do
  bookkeeping only (Q4); GitHub names (Q6); `plan-approve` first (Q8); contributor tier off by default (Q5); chains
  retire into recipes (Q9); invites for contributors (Q10). Replaced: Q2 (journal as truth) and Q7 (pull-only sync).
- 2026-10-27 (Activity, kept): one window and one job model; lanes sized from the machine; cloud by default per recipe
  step with cost shown; the embedder's own lane.
- 2026-10-31 (paraphrased): one harness, two uses; built in Fichero; a long-running builder on Claude Code first, judged
  by use; land per cluster; models by configuration and results; Pi a kind, not the assumption; the Researcher's
  machine is a 24 GB laptop; the deployment profiles; Activity Monitor as the model; issues managed in Fichero and
  synced with a guarded write; engine records are the truth under supervision; `pipeline/` frozen; thin engine; two
  worker kinds; fixed steps as scripts; enforce by hook, credential and guard rather than ask; standing by the end of
  November.
- Deferred as text: invited contributors; shared projects; the release as a dev workflow (the one fixed sequence that
  earns one: long, resumable at the failed step, a yes before anything public, step by step in Activity).

## Build order

Thin slices through November 2026, each one a Claude Code builder can take from its heading; dogfooding from 1.1.
Stage 3 is held to one step until Stage 1 has run a real cluster. `Depends on` defaults to the step before.

### Stage 1 — a Claude Code builder runs one cluster, the engine recording and guarding it (weeks 1-2)

#### Step 1.1 — the engine starts and stops a worker; the check tool; the worker's address
- Behaviours: `dev-workflows.run.worker-start-stop`, `dev-workflows.tool.check`, `dev-workflows.run.worker-address`
- Tests: fichero-server/tests/unit/workflows/test_worker_start_stop.py, fichero-server/tests/unit/workflows/test_check_tool.py, fichero-server/tests/unit/workflows/test_worker_address.py
- Size: M

#### Step 1.2 — worker kinds: claude today, fake for the dry run; pipeline frozen
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.rollout.dry-run`, `dev-workflows.rollout.pipeline-frozen`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py, fichero-server/tests/unit/workflows/test_dry_run.py, fichero-server/tests/unit/workflows/test_pipeline_frozen.py
- Size: M

#### Step 1.3 — the cluster, the worker steers, the git tool
- Behaviours: `dev-workflows.builder.cluster`, `dev-workflows.worker.steers`, `dev-workflows.tool.git`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_git_tool.py
- Size: M

#### Step 1.4 — review and land, the land gate, the durable question
- Behaviours: `dev-workflows.run.review-and-land`, `dev-workflows.run.land-gate`, `dev-workflows.node.human-question`
- Tests: fichero-server/tests/unit/workflows/test_review_and_land.py, fichero-server/tests/unit/workflows/test_land_gate.py, fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py
- Size: M

#### Step 1.5 — the handoff hook, records as truth, supervision
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.records-are-truth`, `dev-workflows.run.supervision`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_records_are_truth.py, fichero-server/tests/unit/workflows/test_supervision.py
- Size: M

#### Step 1.6 — the policy hook, the watch tick, the machine watch, the two capability sets
- Behaviours: `dev-workflows.run.policy-hook`, `dev-workflows.run.watch-tick`, `dev-workflows.run.machine-watch`, `dev-workflows.worker.two-capability-sets`
- Tests: fichero-server/tests/unit/workflows/test_policy_hook.py, fichero-server/tests/unit/workflows/test_watch_tick.py, fichero-server/tests/unit/workflows/test_machine_watch.py, fichero-server/tests/unit/workflows/test_capability_sets.py
- Size: M

### Stage 2 — seen in the app: the Activity table, the records, the sync, the Researcher's first tasks (weeks 2-3)

#### Step 2.1 — the Activity table with a hierarchy, and controls that work
- Behaviours: `dev-workflows.ux.activity-table`, `dev-workflows.ux.controls-work`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero-server/tests/unit/workflows/test_controls_reach_the_call.py
- Depends on: 1.1
- Size: M

#### Step 2.2 — the records and the guarded GitHub sync
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-sync`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py, fichero-server/tests/unit/research/test_github_sync.py
- Depends on: 1.6
- Size: M

#### Step 2.3 — spec and plan, approvals, the feeder
- Behaviours: `dev-workflows.combined.spec-and-plan`, `dev-workflows.run.feeder`
- Tests: fichero-server/tests/unit/research/test_spec_and_plan_layers.py, fichero-server/tests/unit/workflows/test_feeder.py
- Size: M

#### Step 2.4 — the CLI chat and app over one action layer; the repo as a workspace source
- Behaviours: `dev-workflows.surface.one-action-layer`, `dev-workflows.workspace.source`
- Tests: fichero-cli/tests/test_chat_dev_verbs.py, fichero-server/tests/unit/sources/test_workspace_source.py
- Size: M

#### Step 2.5 — the Researcher's first tasks and untrusted text
- Behaviours: `dev-workflows.researcher.tasks`, `dev-workflows.security.untrusted-text`
- Tests: fichero-server/tests/unit/research/test_researcher_tasks.py, fichero-server/tests/unit/security/test_untrusted_text.py
- Depends on: 1.6
- Size: M

### Stage 3 — models by configuration (week 4; detailed after Stage 1 has run a real cluster)

#### Step 3.1 — models in configuration, the decider, bug narrowing
- Behaviours: `dev-workflows.models.by-config`, `dev-workflows.models.decider`, `dev-workflows.builder.bug-narrowing`
- Tests: fichero-server/tests/unit/workflows/test_model_config.py, fichero-server/tests/unit/workflows/test_decider.py, fichero-server/tests/unit/workflows/test_bug_narrowing.py
- Depends on: 2.5
- Size: M

## Behaviour tests

Every behaviour names its test above, written in its step; each `security.*` and gate test includes its failing case.

| Behaviour | Step |
|-----------|------|
| `dev-workflows.run.worker-start-stop` | 1.1 |
| `dev-workflows.tool.check` | 1.1 |
| `dev-workflows.run.worker-address` | 1.1 |
| `dev-workflows.node.worker` | 1.2 |
| `dev-workflows.rollout.dry-run` | 1.2 |
| `dev-workflows.rollout.pipeline-frozen` | 1.2 |
| `dev-workflows.builder.cluster` | 1.3 |
| `dev-workflows.worker.steers` | 1.3 |
| `dev-workflows.tool.git` | 1.3 |
| `dev-workflows.run.review-and-land` | 1.4 |
| `dev-workflows.run.land-gate` | 1.4 |
| `dev-workflows.node.human-question` | 1.4 |
| `dev-workflows.worker.handoff` | 1.5 |
| `dev-workflows.run.records-are-truth` | 1.5 |
| `dev-workflows.run.supervision` | 1.5 |
| `dev-workflows.run.policy-hook` | 1.6 |
| `dev-workflows.run.watch-tick` | 1.6 |
| `dev-workflows.run.machine-watch` | 1.6 |
| `dev-workflows.worker.two-capability-sets` | 1.6 |
| `dev-workflows.ux.activity-table` | 2.1 |
| `dev-workflows.ux.controls-work` | 2.1 |
| `dev-workflows.combined.entities` | 2.2 |
| `dev-workflows.combined.github-sync` | 2.2 |
| `dev-workflows.combined.spec-and-plan` | 2.3 |
| `dev-workflows.run.feeder` | 2.3 |
| `dev-workflows.surface.one-action-layer` | 2.4 |
| `dev-workflows.workspace.source` | 2.4 |
| `dev-workflows.researcher.tasks` | 2.5 |
| `dev-workflows.security.untrusted-text` | 2.5 |
| `dev-workflows.models.by-config` | 3.1 |
| `dev-workflows.models.decider` | 3.1 |
| `dev-workflows.builder.bug-narrowing` | 3.1 |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | workers, tools, gates, watches, records, sync, researcher tasks, models | `fichero-server/tests/unit/workflows/`, `tests/unit/research/`, `tests/unit/security/`, `tests/unit/sources/` |
| CLI (pytest) | y | chat verbs are audited actions | `fichero-cli/tests/test_chat_dev_verbs.py` |
| Swift unit | y | the table's rows, columns, in-place update, lazy children | `fichero/Tests/Unit/general/Models/ActivityTableTests.swift` |

## Documentation matrix

| Doc | Says |
|-----|------|
| `docs/contributor_manual/how-fichero-is-built.md` | Fichero builds itself through its harness; how to run a cluster on a scratch path; the Researcher as the same harness |
| `ui/research.md`, `ui/activity-and-automatic-work.md` | the surfaces; point here for orchestration, the window's columns and worker rows |
| `harness/deterministic-conductor.md` | the frozen runner's record |

## Open questions for the maintainer

None open. The external catalogue connector is proposed as none until a person asks (own libraries plus web search first).
