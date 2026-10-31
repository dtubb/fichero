# Fichero builds Fichero — Dev Workflows on the App Engine — Design Spec

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — a contributor section ("How Fichero is built") saying that
> the dev pipeline is a Fichero workflow you can open on the canvas or drive from the CLI chat, and how to run one on
> a scratch path.

> **Status: PROPOSED 2026-10-31, rewritten for the maintainer's approval.** It replaces the text approved on
> 2026-10-26 (c9c24dfbf, 739ad4ba4) with what the trials and the runner's journal taught since (evidence:
> `agent-work/status/briefs/studio-harness-report.md`). Tags: [OK] built · [PARTIAL] exists, not wired · [GAP] not
> built · [PROPOSED] decided here, not yet ruled. Issues: #6116 (the pipeline), #2067 (Research).
>
> What merges and retires: `harness/deterministic-conductor.md` stays the spec of the stdlib runner (`pipeline/`), which
> is the **bridge and oracle** here and retires with it (§ Rollout); its § Three tiers (2026-10-31) is restated here
> and no longer amended there. `ui/research.md` keeps the Research surface (chat, panes, workspace); its orchestration
> lines (`research.manager-with-workers-orchestration`, `research.future.agent-operates-projects`,
> `research.per-model-tool-grants`) are owned here. `ui/workflows.md` keeps the canvas and run log.

## Intent

Fichero is built within Fichero. The same system that runs a researcher's project (projects, milestones, issues,
specs, long-running workers, a human in the middle) runs Fichero's own development: a worker takes a cluster of issues
from one spec, builds them in order, checks, asks for review, lands the cluster, updates the issues, and the next
cluster starts. The maintainer sees specs, milestones and issues in the app or a CLI chat, delegates, approves and
answers questions there; a user of Fichero does the same with research tasks. Every bug the runner meets while building
Fichero is a bug in the product's own agent area, so the builder and the researcher get stronger together. Scripts
decide wherever a rule can decide; models do the judgement inside a cluster; the maintainer approves specs, plans and
anything public. Models are named in configuration, never in code, so the roster changes with the evidence: Claude
Code agents first, small models through OpenRouter next, several small models at once on a 128 GB machine as the end
state.

## Prior art (adopt, don't invent)

Microsoft Conductor (declared steps, script steps routed on exit codes, caps, validate before run); LangGraph
(`interrupt()` + checkpointer as pause/resume: already the engine); our runner (`pipeline/`, the behaviour to
reproduce and the oracle); GitHub (`gh`, REST) as the public record of work state; the operators who run coding agents
on 128 GB Macs for weeks (several small models at once, one model pinned per role, a session per task on a cached
prefix, a small pinned helper, a tool-call repair layer). Deliberately not adopted: a second orchestrator (Temporal,
Conductor itself), a second task store, a second question queue.

## What exists today (grounded; paths under `fichero-server/src/fichero_server/` unless stated)

- Engine: `workflows/builder.py` builds a `StateGraph` from a `WorkflowDef`, compiled with the DuckDB checkpointer
  (`workflows/checkpointer.py`); `workflows/human_review.py` `ask_human()` = `interrupt()`, resumed by
  `POST /threads/{thread_id}/resume`; `workflows/scheduler.py` (cron, interval), `workflows/file_watcher.py`;
  `workflows/validation.py` validates the archival graph; `workflows/safe_condition.py` routes on conditions.
- Dev-shaped nodes: `workflows/tools/cli_agent.py` runs `claude -p` / `codex exec` in its own process group with a
  timeout and returns stdout/stderr (#341); `tools/agent.py` ReAct node; `tools/mcp.py` external MCP tools as nodes
  (#5760); `tools/multi_agent.py`. No script, git or gh node.
- Recipes: `recipes/runner.py` runs a plan's cards in order as child jobs of one Activity row, parks on a step run
  (`ParkedOnStepRun`, `_park`, `_resume_step_run`), pauses and cancels, and a failed card stops only the cards that need
  its output: the shape of a cluster run.
- Research data: `models/research.py` `ResearchProject` (= Project), `ResearchPlan` (= Milestone), `ResearchTask`
  (= Issue), `ResearchStep` (a tool call), `ResearchNote`, `ResearchChecklist`; routes `api/routes/research/crud.py`
  (17 routes), `notes.py`, `tools.py` (DuckDuckGo-HTML search, browse, fetch, all behind SSRF and size guards);
  `workflows/tools/research.py` exposes the same as LangChain tools; the client `Models/ResearchModels.swift`,
  `Views/Chat/Research/*`. The chat tool loop runs over the audited action layer (`actions/chat_tools.py`,
  `actions/registry.py`: every mutation writes an `ActionAudit` row, role-gated).
- CLI and MCP: `fichero workflow …` (list, run), `fichero workflow-execution …` (threads, resume), the generated
  OpenAPI surface (`fichero-cli/src/fichero_cli/openapi_surface_generated.py`); `fichero-mcp` exposes the same
  routes as tools (`fichero_research_*`, `fichero_activity_get_workflow`, …). No chat verb that lists specs,
  milestones or issues; no GitHub code anywhere in the engine.
- The runner (`pipeline/`): journal and state machine (`core.py`), tmux Pi/API workers behind a key wrapper
  (`coder.py`), model-free brief localisation (`localise.py`), feeder and brief lint (`feeder.py`), the check ladder
  (`checks.py`, `projects/fichero.toml`: ready, red-on-base, fast guards, contract-current; the trial branch adds
  diff-bound and failing-run-pasted), reviewer verdicts bound to a sha, `land` (fast-forward to integration only),
  closer (residue keeps an issue open), `plan` / `plan-approve`, budgets in turns and dollars, a batch session with a
  handoff at `batch_end_pct` and park/wake, `gh.py` the one journaled GitHub writer. Live: 6 READY / 11 NOT_READY
  verdicts, 7 of the 11 spec-diff findings, a round-3 rewrite that re-broke round 2, 33 workers gone, 806 queue
  events for a person to read. Long-running builders with a `## Log` handoff did better on larger items (5 / 3).
- Trials (hosted, 1-2 runs per cell): Qwen3.8-27B in tight Pi: tests 6/6 mergeable, review 3/3, lead 7.5/8;
  Qwen3-Coder-Next on exact briefs: right, on diagnosis: wrong; self-judged tests 0/2; 27B CLOSE proposals 6/20
  right, NARROW 10/10. Measured servers: mlx_lm.server caches a prompt (8k: 23.6 s cold, 0.12 s repeat); oMLX adds
  multi-model pinning, an SSD prefix tier and batching (2.0×/2.6× at 4/8 concurrent).

## Decisions

- **GitHub stays the public record of work state** (open/closed, labels, milestone, assignee, PRs, releases): it is
  where contributors and users already look, its state survives any Fichero bug, and the runner's guards already
  write to it through one journaled path. **Fichero holds the mirror plus what GitHub has no field for** (spec,
  behaviour ids, plan step, run, question, approval), keyed by issue URL, pull-only, so it works offline and never
  wins a disagreement about state. Specs stay Markdown files in the repo (the guards bind them); Fichero reads them
  from the repo as a workspace source.
- **The worker steers, scripts guard.** A long-running worker owns one cluster and calls the deterministic steps as
  tools; scripts choose between clusters, wake, re-send, budget, bind verdicts to shas, land and close. A model never
  moves an item: every step tool is a transition with its check.
- **Land per cluster** (maintainer, 2026-10-31): a cluster's commits land together, in build order, after each issue's
  review is READY and the ladder is green on the rebased head.
- **One worker kind, two capability sets.** The same session shape (brief, cluster, handoff, budget, question queue,
  log) runs a dev cluster and a research task; what differs is granted per step: tools, data, egress.
- **Models by configuration.** Roles name a model (and its memory) in the profile; results pick; nothing in code names
  a model. First Claude Code agents, then small models through OpenRouter, then the local roster.

## Behaviours

### Project work: one model, GitHub as the record

- `dev-workflows.combined.entities` [GAP] (#6116) — one model of project work extends the existing records: Project =
  `ResearchProject`, Milestone = `ResearchPlan`, Issue = `ResearchTask` (+ GitHub URL, plan step, behaviour ids),
  Comment = `ResearchNote` on an issue, Run = a job row, Question/Approval = `HumanReviewRequest` attached to a spec,
  plan or issue; two layers above them: **Spec** (path, title, milestone, status, behaviours `{id, tag, issue}`) and
  **Plan** (the spec's build order; each step `{N.M, title, behaviours, tests, depends_on, size, issue}`). The app, API,
  docs and pipeline use GitHub's names (`dev-workflows.combined.github-names`). Test:
  `fichero-server/tests/unit/research/test_combined_model_records.py::test_entities`.
- `dev-workflows.combined.github-names` [GAP] (#6116) — Project, Milestone, Issue, Pull Request, Label, Comment,
  Release, Assignee are the words in the app, API and CLI; `ResearchPlan`/`ResearchTask` stay as storage names behind
  aliases. Test: `fichero-server/tests/unit/research/test_github_names_and_aliases.py::test_github_names`.
- `dev-workflows.combined.github-mirror` [GAP] (#6116) — for a project with a repo the mirror is **pull-only**: every
  five minutes and on open, issues, milestones, labels and PR state are read with `gh` and stored by URL; Fichero
  never wins a disagreement about state (`dev-workflows.run.state-stays-in-github`); the first stage is read-only
  against this repo on a scratch base path, no write. Test:
  `fichero-server/tests/unit/research/test_github_read_only_mirror.py::test_pull_only_mirror`.
- `dev-workflows.run.state-stays-in-github` [GAP] (#6116) — work state (open/closed, labels, milestone, assignee,
  merged) is GitHub's; the pipeline journal is the truth for runs (ruling Q2, 2026-10-26); workflow and Activity rows
  are views of both. Test: `fichero-server/tests/unit/research/test_github_read_only_mirror.py::test_state_stays_in_github`.
- `dev-workflows.combined.spec-layer` [GAP] (#6116) — a spec is read from the repo file: status line, behaviour ids with
  tags and issues, cited tests; the guards (`scripts/check_spec_*.py`) stay the binding; the app and CLI list specs
  with their tag counts. Test: `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_spec_layer`.
- `dev-workflows.combined.plan-layer` [GAP] (#6116) — a plan is the spec's build order as steps with dependencies and
  issue numbers; `plan`/`plan-approve` (the runner's, dry run by default) propose and file it; a plan is a typed proposal
  the maintainer accepts before any `gh` write (`dev-workflows.combined.approvals`). Test:
  `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_plan_layer`.
- `dev-workflows.combined.approvals` [GAP] (#6116) — three approvals, each a `HumanReviewRequest` in the one queue: the
  spec (status flip), the plan (issues filed), a check-file or acceptance-line change (`approve-checks`). Everything
  else runs without a person. Test: `fichero-server/tests/unit/research/test_approvals.py::test_three_approvals`.
- `dev-workflows.workspace.source-kind` [GAP] (#6116) — a code repository is a **workspace** source: added as a folder
  tied in place, indexed lazily (outline, symbols, text search on demand; jcodemunch is the precedent), never imported
  as pages; the Fichero repo is a separate dev library (ruling Q3). Test:
  `fichero-server/tests/unit/sources/test_workspace_source.py::test_workspace_source`.
- `dev-workflows.workspace.worktrees-map-to-issues` [GAP] (#6116) — a cluster's worktree and branch are derived from
  the spec and numeric issue ids (never titles) and recorded on the issues' records; `git worktree list` and the mirror
  agree. Test: `fichero-server/tests/unit/sources/test_workspace_worktrees_and_github.py::test_worktrees_map`.

### Workers: long-running, a cluster from one spec, handoff at 85 %

- `dev-workflows.worker.cluster` [PROPOSED] — the unit of work is a **cluster**: one spec and its build-order issues,
  worked in order, one commit per issue with its test in the same commit; the cluster record (issue states and shas,
  written by the runner from the journal and git) lives on the plan. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_cluster_in_build_order_one_commit_each`.
- `dev-workflows.worker.steers` [PROPOSED] — the worker session owns the cluster's judgement and calls the steps as
  tools (`brief`, `check`, `request-review`, `land`, `close`, `update-issue`, `file-bug`, `ask`), each a runner
  transition with its check; scripts act between clusters and as guards (wake, ack re-send within ten minutes,
  budgets, verdict bound to a sha, the ladder before any land); a model never moves an item. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_worker_steers_through_step_tools`.
- `dev-workflows.worker.handoff` [PROPOSED] — at 85 % of the context window (or at a cluster boundary) the runner writes
  the handoff from the journal and git — spec and sections; ordered issues with state and sha; one line per commit;
  test commands run and their results; the current failing command and its output tail; decisions taken and
  alternatives rejected; files touched; the do-not list; budget used; under two thousand tokens, one paragraph the
  worker may add — and starts the successor at once; a successor commit whose `git patch-id` is already on the cluster
  is refused as re-done work. Test: `fichero-server/tests/unit/workflows/test_cluster_run.py::test_handoff_and_successor`.
- `dev-workflows.worker.stop-and-ask` [PROPOSED] — a worker stops and asks (parking only its item) when an acceptance
  line would change, a pinned check trips, the diff bound trips twice, the same test fails twice, a step needs a paid
  or irreversible action, the spec contradicts the code, or the turn or dollar budget is hit; it never stops for
  context. Test: `fichero-server/tests/unit/workflows/test_cluster_run.py::test_stop_and_ask_cases`.
- `dev-workflows.worker.two-capability-sets` [PROPOSED] — a **dev** worker has a worktree, shell, git and the step
  tools, on a scratch base path, in the contributor tier only; a **research** worker has read-only library actions,
  web search and fetch, and note/claim/task writes through the audited action layer as the user's account, with no
  shell; one session never holds both sets. Test:
  `fichero-server/tests/unit/workflows/test_capability_sets.py::test_dev_and_research_sets_never_mix`.
- `dev-workflows.worker.bug-narrowing` [PROPOSED] — before a bug's brief reaches a model, a script reproduces and narrows
  it (runs the failing command, localises symbols and tests, searches the base's history for the names, pastes the
  failing tail); a bug it cannot reproduce goes to the thinker role marked so, not to the builder. Test:
  `fichero-server/tests/unit/workflows/test_bug_narrowing.py::test_reproduced_or_marked`.

### Nodes

- `dev-workflows.node.script` [GAP] (#6116) — argv list (no shell string), cwd, `timeout_s`; stdout, stderr and exit
  code as typed outputs; routes on the exit code with no model call; a node with no timeout is refused at validation.
  Test: `fichero-server/tests/unit/workflows/test_script_node.py::test_script_node`.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — one worker node with kinds: `claude` and `codex` (today's
  `cli_agent.py`, unchanged), `pi` (headless `pi -p`, a session directory, the role's rules appended, provider and
  model from the role; returns usage, tool errors, the reported commit sha), and `fake` (replays a scenario, § Dry
  runs); each with a role, a model alias from the profile, a brief and a cost/turn cap; result typed
  `{sha|verdict|text, usage}`. Test: `fichero-server/tests/unit/workflows/test_worker_node.py::test_worker_kinds`.
- `dev-workflows.node.git` [GAP] (#6116) — a closed list of operations (worktree add/remove, status, diff stat, rebase
  onto, merge --no-ff, range-diff, log of a range, push to the integration branch) as typed inputs; refuses any push
  to `main` or a `v*` tag; push is its own node. Test: `fichero-server/tests/unit/workflows/test_git_gh_nodes.py::test_git_node`.
- `dev-workflows.node.gh` [GAP] (#6116) — the read and write calls as typed operations through the runner's one
  journaled writer (`pipeline/gh.py`), with an allow-list per workflow. Test:
  `fichero-server/tests/unit/workflows/test_git_gh_nodes.py::test_gh_node`.
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — `ask_human()` + `POST /threads/{id}/resume` exist; the node
  parks the run with a typed question (text, options, the artifact) and resumes **durably** across an engine restart,
  from Activity, the Research workspace, the CLI chat or a page. Test:
  `fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py::test_human_question_survives_restart`.
- `dev-workflows.node.validate-before-run` [GAP] (#6116) — an unreachable step, an input no step writes, a loop without
  a cap, a script without a timeout, a gh write outside the allow-list refuse the run naming the node
  (`workflows/validation.py` extended, not duplicated). Test:
  `fichero-server/tests/unit/workflows/test_script_node.py::test_validate_before_run`.

### Runs: review, per-cluster landing, recovery

- `dev-workflows.run.cluster-workflow` [PROPOSED] — a cluster runs as the workflow `dev-cluster` (brief → worker →
  check → review question → next issue … → land → close), one Activity row with a child per step, headless on a
  scratch base path with a pinned dev engine (ruling Q1), never the user's engine or the real app DB. Test:
  `fichero-server/tests/unit/workflows/test_headless_scratch_run.py::test_cluster_headless_on_scratch`.
- `dev-workflows.run.review-per-issue` [PROPOSED] — each issue's commit gets a fresh review (a reviewer-role worker)
  bound to its sha, with findings; NOT_READY sends the findings back to the same cluster session (at most two
  rounds, then the question queue). Test: `fichero-server/tests/unit/workflows/test_review_and_land.py::test_review_per_issue`.
- `dev-workflows.run.land-per-cluster` [PROPOSED] (maintainer 2026-10-31) — a cluster lands as one fast-forward to the
  integration branch after every issue is READY and the ladder is green on the rebased head (`patch-id` reuse of
  reviews, as the runner does); never `main`; then each issue is closed with its sha or left open with its residue.
  Test: `fichero-server/tests/unit/workflows/test_review_and_land.py::test_land_per_cluster`.
- `dev-workflows.run.recovery` [PROPOSED] — on engine or runner restart every coding item whose worker has no delivered
  brief gets it again; a stuck worker (`stuck_minutes`) is told once, then replaced by a successor from the handoff;
  a budget stop parks the item with a question, never another attempt; the machine budget refuses to start a worker
  when memory, disk or load is short; every recovery is journaled. Test:
  `fichero-server/tests/unit/workflows/test_recovery.py::test_restart_stuck_budget_and_machine`.
- `dev-workflows.run.log` [PROPOSED] — one row per item attempt from the journal and the worker's session: model,
  provider, precision, context cap, prompt/cached/output tokens, tool calls and errors, diff lines, wall time, cost,
  ladder, verdicts, rework rounds, false done; shown in Activity and written as TSV. Test:
  `fichero-server/tests/unit/workflows/test_run_log.py::test_run_log_row`.
- `dev-workflows.run.feeder` [PROPOSED] — scripts choose the next cluster: the maintainer's pointed milestone, then
  urgent bugs, bugs, then the plan's build order; claimed, blocked and running issues skipped; a brief that fails lint
  (spec id in an APPROVED spec or a bug label, acceptance, test path) goes to the queue as a write-up, never to a
  worker. Test: `fichero-server/tests/unit/workflows/test_feeder.py::test_feeder_order_and_lint`.

### Models by configuration

- `dev-workflows.models.role-config` [PROPOSED] — the profile names a model per role (builder, reviewer, lead-model,
  helper, researcher, manager): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`), model id, precision, context
  cap, resident memory; the loader refuses a roster whose resident models exceed the machine's cap; no code names a
  model. Test: `fichero-server/tests/unit/workflows/test_model_config.py::test_roles_name_models_and_fit_the_cap`.
- `dev-workflows.models.results-pick` [PROPOSED] — a role moves to a cheaper model only on the run log: twenty items
  with READY rate within fifteen points of the current model's, no false done, no write outside the worktree; the
  reviewer additionally agrees with the binding reviewer on ninety percent and is never READY where it said
  NOT_READY. Test: `fichero-server/tests/unit/workflows/test_model_config.py::test_role_moves_only_on_the_log`.
- `dev-workflows.models.local-end-state` [PROPOSED] — on a 128 GB machine the expected roster is several small models
  pinned at once (a fast MoE builder, a reviewer, a helper, an embedder) under a memory cap with headroom for the gate
  and a build, served by an OpenAI-compatible local server with a prefix cache; the Studio is the end state, not the
  near-term work. Test: `fichero-server/tests/unit/workflows/test_model_config.py::test_local_roster_profile_validates`.

### Surfaces: one audited action layer, a CLI chat and the app

- `dev-workflows.surface.cli-chat` [PROPOSED] — `fichero chat` (and the MCP tools) can list specs, milestones and
  issues, point a milestone, start a cluster, show runs and questions, answer a question, approve a plan; every verb
  is an audited action, the same one the app and the workers call. Test:
  `fichero-cli/tests/test_chat_dev_verbs.py::test_dev_verbs_are_audited_actions`.
- `dev-workflows.surface.app` [GAP] (#2067) — the Research workspace's Plan tab shows the same milestones, issues and
  questions for a project with a repo; the workflow canvas and run log show a cluster run; the question queue is one
  list for research and dev (`dev-workflows.research.one-question-queue`). Test:
  `fichero-server/tests/unit/api/test_dev_project_view.py::test_app_surface_reads_the_same_records`.

### Research kind and the web

- `dev-workflows.research.one-task-model` [GAP] (#2067) — a research task and a dev issue are one record shape
  (`ResearchTask` extended), read and updated by workers through the audited action layer. Test:
  `fichero-server/tests/unit/research/test_combined_model_records.py::test_one_task_model`.
- `dev-workflows.research.one-question-queue` [GAP] (#2067) — a workflow's human question and the research agent's
  are one `HumanReviewRequest` in one queue; answering from any surface resumes the parked run. Test:
  `fichero-server/tests/unit/research/test_one_question_queue.py::test_one_queue`.
- `dev-workflows.research.web-search` [PROPOSED] — the research worker's search is a configured provider behind the
  existing SSRF and size guards (`api/routes/research/tools.py`): a self-hosted SearXNG JSON endpoint by default, a
  paid API as a fallback, the DuckDuckGo HTML scrape last; every URL fetched is logged on the task. Test:
  `fichero-server/tests/unit/research/test_web_search_provider.py::test_provider_order_and_url_log`.

### Security: untrusted text, grants, secrets

- `dev-workflows.security.untrusted-text` [GAP] (#6116) — issue bodies, comments, spec text and fetched pages reach a
  model only as fenced, labelled data; the turn that reads them has no write tool; anything proposed is acted on by a
  later script step with a fixed argv and a grant. Test:
  `fichero-server/tests/unit/security/test_untrusted_text.py::test_injected_text_makes_no_write`.
- `dev-workflows.security.argv-injection` [GAP] (#6116) — script, git and gh nodes take typed inputs; free text goes in
  a file or stdin, never argv; each argv value matches `^[A-Za-z0-9._/-]+$`, no leading `-`, no `..`; branch and
  worktree names come from numeric ids. Test: `fichero-server/tests/unit/workflows/test_git_gh_nodes.py::test_argv_injection_refused`.
- `dev-workflows.security.capability-grants` [GAP] (#6116) — a per-step grant (operation set + target) held by the
  engine; gh and git nodes refuse a write without one; model-reachable steps get bookkeeping grants only (comment,
  label, milestone move); gated script steps get commit, land and close. Test:
  `fichero-server/tests/unit/workflows/test_capability_grants.py::test_model_output_cannot_close`.
- `dev-workflows.security.dev-nodes-gated` [GAP] (#6116) — script, git, gh and worker nodes exist only in the
  contributor tier, off by default; a workflow using one is refused on import or share. Test:
  `fichero-server/tests/unit/workflows/test_script_node.py::test_dev_nodes_gated`.
- `dev-workflows.security.tokens-and-redaction` [GAP] (#6116) — a GitHub token lives in one `gh` subprocess's
  environment per call and nowhere else; no token, key or credential reaches workflow state, the checkpointer, the
  journal, the run log or captured output (`BoundedLog` redacts known shapes). Test:
  `fichero-server/tests/unit/security/test_no_secret_persists_after_a_run.py::test_tokens_and_redaction`.

### Dry runs and rollout

- `dev-workflows.rollout.dry-run` [PROPOSED] — the `fake` worker kind replays a **scenario** (scripted turns plus the
  journal events and Activity rows expected) through the engine with no model and no money, covering: every tool-call
  shape, including a malformed one; one commit per issue over a three-issue cluster; the handoff and the successor's
  first commit; ask, park, answer, resume, also across a restart; NOT_READY, send-back, a rework round; the diff-bound,
  failing-run and pinned-check rungs tripping; a worker that dies and one that never got its brief; a 429, a 5xx and
  a context-overflow reply; a false "done"; the budget stop; land and close against a fake `gh`; a complete log row.
  The same scenario is the oracle against `pipeline/`. A dry run proves the process, never a model. Test:
  `fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py::test_scenario_matches_the_runner`.
- `dev-workflows.rollout.stdlib-runner-stays` [GAP] (#6116) — `pipeline/` is the bridge and oracle: a step of it retires
  only when the engine runs the same scenario to the same events; the order is `coder.py` (worker node), `runner.land`
  (git/gh nodes), `runner.tick` and `steps.py` (the cluster workflow), `site.py`/`web.py` (Activity and the canvas),
  `feeder.py`/`plan.py` (the mirror and plan layer); `core.py` and the journal stay until the maintainer revisits
  ruling Q2. Test: `fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py::test_runner_stays_until_matched`.

## Rulings

- 2026-10-26 (kept): pinned separate dev engine first (Q1); the Fichero repo is a separate dev library (Q3); model nodes
  do bookkeeping only, gated script steps commit, land and close (Q4); GitHub names in the app (Q6); pull-only sync
  (Q7); the runner's `plan-approve` first (Q8); the JSONL journal stays the truth for runs (Q2); contributor tier, off
  by default (Q5); chains retire into recipes (Q9); a signed invite for contributors (Q10).
- 2026-10-31 (paraphrased): build it in Fichero, as part of the researcher/agent area, with a long-running builder, run
  with Claude Code agents first and judged by use, no two-shape comparison first; land per cluster; models are named
  in configuration and picked by results; the spec is rewritten, not amended; dogfood from the first slice.
- Deferred, not retired (text only, no behaviours until their stage is reached): invited contributors through the
  same model; shared projects (several Ficheros on one project, task leases); the release as a dev workflow with the
  maintainer's yes before anything public.

## Build order

Thin slices. Slice 1.1 is usable within days by a Claude Code builder and dogfoods from then on; every later slice is
built by a worker running inside the previous one. `Depends on` defaults to the step before within the stage.

### Stage 1 — one cluster runs in the engine, with Claude Code and with a fake model

#### Step 1.1 — the script node and the dev-cluster workflow on a scratch base path
- Behaviours: `dev-workflows.node.script`, `dev-workflows.run.cluster-workflow`, `dev-workflows.node.validate-before-run`
- Tests: fichero-server/tests/unit/workflows/test_script_node.py, fichero-server/tests/unit/workflows/test_headless_scratch_run.py
- Size: M

#### Step 1.2 — the worker node: claude today, fake for the dry run
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.rollout.dry-run`, `dev-workflows.rollout.stdlib-runner-stays`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py, fichero-server/tests/unit/workflows/test_dev_item_matches_runner.py
- Size: M

#### Step 1.3 — the cluster: order, one commit per issue, the worker steers
- Behaviours: `dev-workflows.worker.cluster`, `dev-workflows.worker.steers`, `dev-workflows.worker.stop-and-ask`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py
- Size: M

#### Step 1.4 — review per issue, land per cluster, the question survives a restart
- Behaviours: `dev-workflows.run.review-per-issue`, `dev-workflows.run.land-per-cluster`, `dev-workflows.node.human-question`
- Tests: fichero-server/tests/unit/workflows/test_review_and_land.py, fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py
- Size: M

#### Step 1.5 — handoff, successor and recovery
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.recovery`, `dev-workflows.run.log`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_recovery.py, fichero-server/tests/unit/workflows/test_run_log.py
- Size: M

#### Step 1.6 — secrets never persist
- Behaviours: `dev-workflows.security.tokens-and-redaction`
- Tests: fichero-server/tests/unit/security/test_no_secret_persists_after_a_run.py
- Depends on: 1.2
- Size: S

### Stage 2 — the records, the mirror and the surfaces

#### Step 2.1 — the records and GitHub names
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-names`, `dev-workflows.research.one-task-model`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py, fichero-server/tests/unit/research/test_github_names_and_aliases.py
- Depends on: 1.6
- Size: M

#### Step 2.2 — the pull-only mirror
- Behaviours: `dev-workflows.combined.github-mirror`, `dev-workflows.run.state-stays-in-github`
- Tests: fichero-server/tests/unit/research/test_github_read_only_mirror.py
- Size: M

#### Step 2.3 — spec and plan layers, approvals
- Behaviours: `dev-workflows.combined.spec-layer`, `dev-workflows.combined.plan-layer`, `dev-workflows.combined.approvals`
- Tests: fichero-server/tests/unit/research/test_spec_and_plan_layers.py, fichero-server/tests/unit/research/test_approvals.py
- Size: M

#### Step 2.4 — the CLI chat verbs and the feeder
- Behaviours: `dev-workflows.surface.cli-chat`, `dev-workflows.run.feeder`, `dev-workflows.research.one-question-queue`
- Tests: fichero-cli/tests/test_chat_dev_verbs.py, fichero-server/tests/unit/workflows/test_feeder.py, fichero-server/tests/unit/research/test_one_question_queue.py
- Size: M

#### Step 2.5 — the repo as a workspace source
- Behaviours: `dev-workflows.workspace.source-kind`, `dev-workflows.workspace.worktrees-map-to-issues`
- Tests: fichero-server/tests/unit/sources/test_workspace_source.py, fichero-server/tests/unit/sources/test_workspace_worktrees_and_github.py
- Depends on: 2.1
- Size: M

### Stage 3 — models by configuration, the research kind, the gates

#### Step 3.1 — git and gh nodes, argv jail, grants
- Behaviours: `dev-workflows.node.git`, `dev-workflows.node.gh`, `dev-workflows.security.argv-injection`, `dev-workflows.security.capability-grants`
- Tests: fichero-server/tests/unit/workflows/test_git_gh_nodes.py, fichero-server/tests/unit/workflows/test_capability_grants.py
- Depends on: 2.5
- Size: M

#### Step 3.2 — models in configuration, picked by results
- Behaviours: `dev-workflows.models.role-config`, `dev-workflows.models.results-pick`, `dev-workflows.models.local-end-state`
- Tests: fichero-server/tests/unit/workflows/test_model_config.py
- Depends on: 1.5
- Size: M

#### Step 3.3 — the research worker kind and the web
- Behaviours: `dev-workflows.worker.two-capability-sets`, `dev-workflows.research.web-search`, `dev-workflows.security.untrusted-text`
- Tests: fichero-server/tests/unit/workflows/test_capability_sets.py, fichero-server/tests/unit/research/test_web_search_provider.py, fichero-server/tests/unit/security/test_untrusted_text.py
- Depends on: 2.4
- Size: M

#### Step 3.4 — bug narrowing, dev nodes gated, the app surface
- Behaviours: `dev-workflows.worker.bug-narrowing`, `dev-workflows.security.dev-nodes-gated`, `dev-workflows.surface.app`
- Tests: fichero-server/tests/unit/workflows/test_bug_narrowing.py, fichero-server/tests/unit/workflows/test_script_node.py, fichero-server/tests/unit/api/test_dev_project_view.py
- Depends on: 3.1
- Size: M

## Behaviour tests

Every behaviour names its test above (one test per behaviour, written in its step); each `security.*` test includes
its failing case. The table is the pinning the guard reads.

| Behaviour | Step |
|-----------|------|
| `dev-workflows.node.script` | 1.1 |
| `dev-workflows.run.cluster-workflow` | 1.1 |
| `dev-workflows.node.validate-before-run` | 1.1 |
| `dev-workflows.node.worker` | 1.2 |
| `dev-workflows.rollout.dry-run` | 1.2 |
| `dev-workflows.rollout.stdlib-runner-stays` | 1.2 |
| `dev-workflows.worker.cluster` | 1.3 |
| `dev-workflows.worker.steers` | 1.3 |
| `dev-workflows.worker.stop-and-ask` | 1.3 |
| `dev-workflows.run.review-per-issue` | 1.4 |
| `dev-workflows.run.land-per-cluster` | 1.4 |
| `dev-workflows.node.human-question` | 1.4 |
| `dev-workflows.worker.handoff` | 1.5 |
| `dev-workflows.run.recovery` | 1.5 |
| `dev-workflows.run.log` | 1.5 |
| `dev-workflows.security.tokens-and-redaction` | 1.6 |
| `dev-workflows.combined.entities` | 2.1 |
| `dev-workflows.combined.github-names` | 2.1 |
| `dev-workflows.research.one-task-model` | 2.1 |
| `dev-workflows.combined.github-mirror` | 2.2 |
| `dev-workflows.run.state-stays-in-github` | 2.2 |
| `dev-workflows.combined.spec-layer` | 2.3 |
| `dev-workflows.combined.plan-layer` | 2.3 |
| `dev-workflows.combined.approvals` | 2.3 |
| `dev-workflows.surface.cli-chat` | 2.4 |
| `dev-workflows.run.feeder` | 2.4 |
| `dev-workflows.research.one-question-queue` | 2.4 |
| `dev-workflows.workspace.source-kind` | 2.5 |
| `dev-workflows.workspace.worktrees-map-to-issues` | 2.5 |
| `dev-workflows.node.git` | 3.1 |
| `dev-workflows.node.gh` | 3.1 |
| `dev-workflows.security.argv-injection` | 3.1 |
| `dev-workflows.security.capability-grants` | 3.1 |
| `dev-workflows.models.role-config` | 3.2 |
| `dev-workflows.models.results-pick` | 3.2 |
| `dev-workflows.models.local-end-state` | 3.2 |
| `dev-workflows.worker.two-capability-sets` | 3.3 |
| `dev-workflows.research.web-search` | 3.3 |
| `dev-workflows.security.untrusted-text` | 3.3 |
| `dev-workflows.worker.bug-narrowing` | 3.4 |
| `dev-workflows.security.dev-nodes-gated` | 3.4 |
| `dev-workflows.surface.app` | 3.4 |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | nodes, cluster run, review and land, recovery, mirror, layers, grants, secrets | `fichero-server/tests/unit/workflows/`, `tests/unit/research/`, `tests/unit/security/`, `tests/unit/sources/` |
| CLI (pytest) | y | chat verbs are audited actions | `fichero-cli/tests/test_chat_dev_verbs.py` |
| Runner (pytest) | y | the oracle: the same scenario, the same events | `pipeline/tests/` |
| Swift / UI | later | the Plan tab and canvas show the same records | `fichero/Tests/Unit/` (Stage 3.4) |

## Documentation matrix

| Doc | Says |
|-----|------|
| `docs/contributor_manual/how-fichero-is-built.md` | the dev pipeline is a Fichero workflow; how to run a cluster on a scratch path; what waits for the maintainer |
| `ui/research.md` | the surface; points here for orchestration |
| `harness/deterministic-conductor.md` | the bridge runner; retires per § Rollout |

## Open questions for the maintainer

1. When the mirror is in (Step 2.2), does the maintainer want to manage this repo's issues from the app or the CLI chat
   as the normal path, with `gh` kept for the rare case, or the reverse?
2. The journal as the truth for runs (ruling Q2) once Activity rows carry the same events: keep both, or let the
   checkpointer and jobs table become the truth and the journal a log?
