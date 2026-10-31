# Fichero Builder and Fichero Researcher — one harness, two uses — Design Spec

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — a contributor section ("How Fichero is built") saying that
> Fichero builds itself through its own harness, how to run a cluster on a scratch path, and how the same harness runs
> a research project.

> **Status: PROPOSED 2026-10-31 (rewrite 4: the review verdict of 2026-10-31 applied; § G project neutrality, the carried
> process and local-model parity; § H the shared core with two front ends), for the maintainer's approval.** Replaces the text
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

One harness, two uses, any project. The harness is **project-neutral**: its code names no project; everything that differs
between projects (the integration branch, the check commands, the guard glob, the forbidden commands, the people list, the
review checklist, the machine limits, the handoff line) lives in one rules file per project, and Fichero is the first
project. It carries the process that works here (§ G): rulings → spec bound to tests → issues in build order → a
long-running builder → a fresh review bound to a sha → fix and re-review → a scripted land → gate → dev build → release.
**Fichero Builder** builds Fichero: a long-running worker takes a cluster of issues from one spec,
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

- Engine: `workflows/builder.py` + `checkpointer.py` (DuckDB), `human_review.ask_human()` = `interrupt()` inside a running
  graph node with `POST /threads/{id}/resume` (`HumanReviewRequest` is a payload, not a queue table), `scheduler.py`
  (schedules by workflow id only), `execution/throttle.py` (battery, memory and heat readings; no load reading), one `jobs`
  table per library with `parent_id` (`execution/jobs.py`), `pause_requested()` read only at the item boundary
  (`builder.py:1176`; #4402 is closed, the Pause residue needs its own issue).
- Agent pieces: `workflows/tools/cli_agent.py` runs a local agent CLI (`claude -p`) in its own process group with a
  timeout (the per-item form; not the Builder's shape, see `run.worker-start-stop`); `tools/agent.py`; `tools/mcp.py`; the
  chat tool loop over the audited action layer (`actions/chat_tools.py`, `actions/registry.py`: every mutation an
  `ActionAudit` row, role-gated; per-model grants #4721 GAP). The loop sits in the chat route and returns within one turn
  at `MAX_CHAT_TOOL_ITERATIONS = 4`: no detached run, Stop, row or handoff yet.
- Research: `models/research.py` `ResearchProject`/`ResearchPlan`/`ResearchTask`/`ResearchStep`/`ResearchNote`/`SearchSource`;
  `api/routes/research/{crud,notes,tools}.py` (DuckDuckGo-HTML search, browse, fetch behind SSRF and size guards;
  `tools.py` declares the data diode: a browsing agent never holds library or KG read tools); `workflows/tools/research.py`.
  No catalogue connector; no GitHub issue or milestone code (recipes reach GitHub only for model catalogues).
- Apple Intelligence: Foundation Models through the bundled `fm-bridge` (`llm/__init__.py:2229`, provider `apple`); text
  only today, no typed output or tool.
- Activity (app paths under `fichero/fichero/`): `Views/Activity/` (about 9,000 lines in 30 files: `Window/*`, `Monitor/*`,
  `RunControls.swift`), `Models/ActivityStore*.swift` (about 1,200 lines), the route `api/routes/system/activity.py` per
  library; the approved spec's `Table` with disclosure rows (its Stage 3) is not built.
- CLI/MCP: `fichero workflow …`, `fichero workflow-execution …`, the generated surface; `fichero-mcp` exposes the routes.
  There is no `fichero chat` command today ([GAP], `surface.one-action-layer`); nothing lists specs, milestones or issues.
- Runs without the document and model stack already in part: no engine module imports `mlx`, `kraken`, `spacy`, `torch` or
  `lancedb` at module top (lazy imports, guarded by `tests/unit/api/test_lazy_engine_imports.py`, `MODULE_BUDGET = 823`);
  routes are registered per feature tier (`register_tiered_routes`); Kraken and MLX enter the bundle by two separate
  install steps (`[tool.fichero.kraken_bundle]`, `[tool.fichero.mlx_bundle]`). What couples the core to the rest:
  `execution/jobs.py` (3,800 lines) lazily imports `llm`, `recipes`, `workflows` and `api` for recipe job kinds; the
  Activity route imports `recipes.run_view`; jobs live in the library database. Evidence and the cost estimate: § H.
- `pipeline/` (frozen): journal, Pi/API workers, `localise.py`, feeder and lint, the ladder (`checks.py`, `fichero.toml`),
  verdicts bound to a sha, `land`, closer, `plan`/`plan-approve`, budgets, handoff, `gh.py`. What to port is named below.
- Measured so far (the briefs under `agent-work/` are not tracked, so the figures that decide this spec are repeated here):
  the per-item runner on the API reached 6 READY of 13 binding verdicts (46 %), 7 of its 11 NOT_READY findings were spec
  drift, one item took four attempts, 33 workers were lost mid-item; long-running Claude Code builders on larger items
  reached about 6 of 8 READY (75 %) with one to two rework rounds; the integration branch took about 1,090 commits and 125
  merges in the eight days to 2026-10-31 with four commits by a person; the pane message helper re-sent Enter about 9,600
  times in 24 days; the author-and-trailer finding appeared in 9 of 11 reviews; the project has no project-level hook
  and `integration` is not protected. Small local models fit triage and routing and finished no exact edit; Pi's
  compaction error with a 35B is a harness fault to fix at the OpenRouter stage.

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
  loop is the engine's chat tool loop, extracted to a task runner (`researcher.tasks`), so a 24 GB laptop needs no terminal.
- **The Builder worker is an interactive session in a tmux pane** (manager 2026-10-31, after the review): the only shape
  that has worked here. For Claude Code: `claude` with an explicit permission mode, a generated settings file, a generated
  MCP config under `--strict-mcp-config`, the model, and hooks that post rows; `claude -p` exits when the turn ends,
  prints only its final answer unless given `--output-format stream-json`, and takes no pane message, so it is not the
  Builder (probed: `claude --help`, 2026-10-31; a long-running `-p --input-format stream-json` form exists and is
  untested here). Pi fits the same shape: `pi` in a pane with the extension that runs the same hook scripts.
- **Shared core, two front ends** (owner 2026-10-31): the Researcher area of Fichero and Fichero Builder share one core of
  engine code (records, jobs, Activity, questions, grants, the tools, the sync) and one Activity package; they differ in
  front end and profile. The Researcher stays in Fichero; Builder is a second front end over the same core (§ H). No
  app work before Slice 0.
- **Slice 0 first** (manager 2026-10-31): a real cluster within two to three days on today's tmux builder, with the scripts
  and the enforced layer, before any engine route.
- **Land per cluster** (maintainer 2026-10-31), enforced outside the model.
- **Fixed steps are scripts** (`lane_ready_check.sh`, `check_*.py`, `scripts/gate`, `verify_all.sh`, `build-and-validate.sh`,
  `close_fixed_issues.py`, the `land` guard), each one Activity row with a count and a Stop where it runs long; only the
  release earns a workflow, deferred.
- **Enforce, don't ask; declare, don't narrate**: every standing rule names its layer (credential or OS, hook, guard at
  landing, prose only) and lives in one declarative rules file that states what must hold, not the order of work.
- **A ratchet**: slowdowns, failures and review findings are logged with causes, a few numbers are compared with a
  baseline on each run, and a repeated finding becomes a rule or a check (baseline table in the report).
- **Two capability sets over one worker shape**; **models by configuration, with fallback; a person reads the log before a
  role moves**; **small-context handoff is a core requirement** (the Researcher's machine is a 24 GB laptop).
- **Project-neutral, Fichero first** (maintainer 2026-10-31): a second, unrelated repository runs a real cluster by changing
  only its rules file and review checklist; a project name in harness code is a defect.
- **Local models with the same guardrails** (maintainer 2026-10-31): the harness must run reliably on local models, and every
  guardrail Claude Code gives today has a carrier that is a plain file, a script, an OS or git rule, or a harness feature
  (§ G); rules are enforced outside the model, and skills are markdown on disk any model reads. Order of work: Sonnet on
  Claude Code, then OpenRouter through Pi, then local on the Studio.
- **Messages are files, not keystrokes** (evidence in `how-we-work.md`: about 9,600 re-sent Enter keys in 24 days): a
  worker's inbox is a file its hook reads before each turn; typing into a pane is the fallback only.

### Deployment profiles (configuration over one harness)

| Profile | Machine | Models | Runs |
|---|---|---|---|
| Builder, now | M1 Pro 16 GB | Claude Code agents; then OpenRouter models | clusters, reviews, dry runs; engine on a scratch base path |
| Builder, end state | M5 Studio 128 GB | several small local models pinned under a memory cap (a fast MoE builder, a reviewer, a helper, an embedder), a local server with a prefix cache; cloud by exception | 2-3 builder sessions + reviewer + research; headroom for the gate and a build |
| Researcher | M5 MacBook Pro 24 GB | one small local model at a time (4B-9B 4-bit, 2.7-6 GB), Apple Intelligence for typed small jobs, Apple Vision/Speech/Translation, MLX readers when chosen; cloud only where the person allows, cost shown first | one research task at a time, 16-32k context, handoff per source; the engine's heavy steps (import, embed, Kraken: 10-40 GB) and the model alternate under the machine budget; what needs more goes to an allowed cloud model or is refused plainly |

Apple Intelligence (reported, 2026-10-31): a ~3 B on-device model, ~1.2 GB, 4k window on macOS 26 and 8k reported for 27
(read `contextSize` at run time), guided generation with typed enum outputs that developers find reliable, a `Tool`
protocol, non-disableable guardrails with false positives. It fits clerk jobs (typed small choices) in the Researcher
profile, never coding, review or synthesis. A separate decider role is deferred (below).

## Behaviours

### A. Workers (the loop is the harness's)

- `dev-workflows.run.worker-start-stop` [PROPOSED] — the engine starts a worker for a task (a Builder cluster, headless on
  a scratch base path with a pinned dev engine, ruling Q1; a Researcher task, in-app) with its brief, kind, model and
  grants. A Builder worker is an **interactive session in a tmux pane**: Claude Code with an explicit permission mode, a
  generated settings file (hooks, no inherited user settings), a generated MCP config under `--strict-mcp-config` (never
  the owner's `fichero` server), the role's model and `FICHERO_BASE_PATH` on the scratch path; Pi in a pane with its
  extension. The hooks post the rows (one Activity row per worker, a child row per report and check; tool calls stay in
  the session log with a count). The engine persists the worker's process group, pane, session directory and started-at
  to a file so a restart adopts or kills it before any successor; stop is TERM, then KILL after a grace, on the process
  group (never a message); a successor starts when the hook hands off. The route and the Builder kind are registered in
  the `dev` feature tier only, from the first step, and are absent from release builds. Built so far (branch
  `feat/fichero-builds-fichero`): `workflows/worker_process.py` opens the `claude` kind in a tmux window with
  `--strict-mcp-config` over an empty MCP config, follows the pane's piped log for the row's words and its process group
  for the end, and still passes `--dangerously-skip-permissions` until the sandbox of `run.land-gate` lands; `POST
  /api/workers`, `/tell` and `/{job}/stop` are dev-tier audited actions. `workflows/tools/cli_agent.py` is a different
  thing: the per-item `claude -p` for one-shot calls. Tests:
  `fichero-server/tests/unit/workflows/test_worker_process.py::test_claude_kind_is_an_interactive_session_with_no_inherited_mcp`,
  `fichero-server/tests/unit/workflows/test_worker_route.py`.
- `dev-workflows.run.worker-address` [PROPOSED] — per task, the current generation's address (pane or process group,
  session directory, kind, started-at) is registered, rewritten at each handoff, cleared when gone; a supervisor's
  `tell` appends to that generation's **inbox file**, which the worker's hook reads before each turn and marks delivered (a
  pane keystroke is the fallback and is logged as such; the built `tell` still types into the pane, the inbox file is
  Step 0.1's); under 800 characters; a tell to a stale
  generation is refused naming the current one, so a handoff never leaves two workers in one worktree. Test:
  `fichero-server/tests/unit/workflows/test_worker_address.py::test_tell_reaches_only_the_current_generation`.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — kinds `claude` and `pi`, both the pane shape of `run.worker-start-stop`
  (a session directory, the role's rules file appended, provider and model from the role; usage, tool errors and the
  reported sha read from the kind's own report by one adapter per kind); `fake` drives the same pane protocol from a
  scripted model server and is never started by a person; each worker has a role, a model from the profile, a brief and
  a cost/turn cap; result `{sha|verdict|text, usage}`. The per-item `claude -p` of `cli_agent.py` stays for one-shot
  reviewers and clerks only. Test:
  `fichero-server/tests/unit/workflows/test_worker_node.py::test_worker_kinds`.
- `dev-workflows.tool.check` [PROPOSED] — the `check` tool runs the ladder: `scripts/lane_ready_check.sh`, the named pytest,
  `scripts/check_*.py` with the skip list and time budgets carried over from `pipeline/projects/fichero.toml`, diff bound,
  failing run pasted; argv lists, a cwd, an explicit environment (scratch base path, `PYTHONPATH` relative to the tree
  under test, thread caps) and a timeout per command; typed results; refuses when blind (fewer guards than the floor).
  **Pinned checks** (restored from the frozen runner; built in `check_tool.py` as `pinned_violations`, `weakened_tests`,
  `acceptance_changed`, `_scratch_tree` and `run_ladder`, with `check_paths`, `spec_dir` and `test_globs` read from the
  repository's `harness.toml`): at review request and at land the ladder runs from a pinned copy of the base's
  `scripts/` and rules file (the hooks and the agent settings directory join the pinned set in Step 0.1) laid over a
  scratch tree with a scratch HOME and base path on every rung, never the worker's copies; a diff that touches a pinned
  path, rewrites the item's own acceptance lines, or weakens or deletes an existing test is a question for a person, not
  a pass. **Build rung:** a cluster touching Swift or the contract is not READY to land without a Lead
  build row (Mac and iOS as the project's rules file says) on that sha; the nightly gate is one script with one row. Test:
  `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`.
- `dev-workflows.tool.git` [GAP] (#6116) — a closed list of operations as typed inputs (worktree add/remove, status, diff
  stat, rebase onto, range-diff, log of a range; no merge: `land` fast-forwards the integration branch to the rebased
  cluster head; push only by the land step); argv values match
  `^[A-Za-z0-9._/-]+$`, no leading `-`, no `..`, names from numeric ids; refuses any push to `main` or a `v*` tag. Test:
  `fichero-server/tests/unit/workflows/test_git_tool.py::test_operations_and_argv_jail`.
- `dev-workflows.builder.cluster` [PROPOSED] — the Builder's unit of work: one spec and its build-order issues (parser ported
  from `pipeline/plan.py`), in order, one commit per issue with its test; the brief is built by a script
  (`scripts/harness_brief.py`, built) from the issue's
  body and its **trusted comments only** (author association owner, member or collaborator; spec-link, residue, ruling;
  newest first); comments from anyone else are counted as "N outside comments, ask" and never reach a worker with a
  shell, because the repository is public; the spec lines and localisation are ported from `pipeline/localise.py`; the
  cluster record (issue states, shas) lives on the plan. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_cluster_in_build_order_one_commit_each`.
- `dev-workflows.worker.steers` [PROPOSED] — the worker owns the task's judgement and calls the steps as tools (`brief`,
  `check`, `request-review`, `land`, `close`, `update-issue`, `file-bug`, `ask`, `hand-off`; for research `search`,
  `fetch`, `save-source`, `note`), each an audited action with its check; a model never moves an item. It **stops and
  asks** (parking only its item) when an acceptance line would change, a pinned check trips, the diff bound trips
  twice, the same test fails twice, a step is paid or irreversible, a source contradicts the premise, the spec
  contradicts the code, or the budget is hit; never for context. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_worker_steers_and_stop_and_ask_cases`.
- `dev-workflows.worker.handoff` [PROPOSED] — at 85 % of the context window or a task boundary, a harness hook (one per
  kind; today's successor hook, which reads usage from the transcript and asks the worker to write the file; the engine's
  rows feed it once they exist) writes the handoff from git and the task's rows or notes: the
  spec or question and its sections; ordered items with state and sha; one line per commit or saved source; commands
  run and results; the current failing command or open lead with its output tail; decisions and rejected
  alternatives; files or sources touched; the do-not list; budget used; under two thousand tokens plus one paragraph
  from the worker; then asks the engine to start the successor at once; a result already on the task (`git patch-id`,
  a source URL) is refused as re-done work. A parked worker (a question, a budget stop) exits; its successor resumes
  from the handoff and the answer. At 16-32k the same handoff fires per item. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_handoff_and_successor`.
- `dev-workflows.worker.two-capability-sets` [PROPOSED] — Builder: worktree, shell, git, the step tools, scratch base path,
  `dev` tier only (the kind and the `check`/`git` tools are refused outside it); Researcher: capabilities **per task**,
  never mixed in one session (`researcher.tasks`): find-sources holds web search and fetch and no library read;
  search-libraries holds read-only library and KG actions and no web; read-and-note reads only saved sources with no
  egress; writes go through the audited layer as the user's account; no shell, never a GitHub token. Test:
  `fichero-server/tests/unit/workflows/test_capability_sets.py::test_sets_never_mix_and_builder_kind_gated`.
- `dev-workflows.security.grants` [PROPOSED] (restored) — a grant is a record: who granted, to which task and worker
  generation, which capability (a tool, a paid provider, a GitHub write, a library read), scope and expiry; every tool
  checks the grant at the call and refuses with a row when none holds; the person grants from the question queue or the
  rules file (standing grants per project); the Researcher's grants are the user's, the Builder's the maintainer's;
  #4721's per-model grants are the same record keyed by model. Test:
  `fichero-server/tests/unit/workflows/test_grants.py::test_tool_refuses_without_a_grant_and_logs_it`.

### B. Review, landing, gates and watches

- `dev-workflows.run.review-and-land` [PROPOSED] (maintainer 2026-10-31: land per cluster) — `request-review` starts a fresh
  reviewer worker on an issue's commit with the project's **review checklist file** (named in the rules file; for Fichero:
  spec diff, range-diff after a rebase, tests of changed readers, the shell file cap; author, trailers, lint and guards are
  `check`'s, not the reviewer's), its verdict bound to the sha with findings; `request-review` returns at once and the
  worker reads verdicts with a `verdicts` tool at each commit; NOT_READY findings belong to the task's current
  generation (two rounds, then the queue); `land` is a guard script that fast-forwards the integration branch only when
  every issue is READY and the ladder is green on the rebased head (`patch-id` reuse of reviews), never `main`; a
  rebase conflict goes back to the worker, not to a person; the public boundary (`combined.github-sync`) runs over the
  land diff and the commit messages before the push; `Fixes #N` closes the issue with its sha, `Part of #N` leaves it
  open with its residue (`close_fixed_issues.py`'s rule; the built commits say which). A research task's review is the
  person's: sources and notes are proposals until accepted. Test:
  `fichero-server/tests/unit/workflows/test_review_and_land.py::test_review_per_issue_and_land_per_cluster`.
- `dev-workflows.run.land-gate` [PROPOSED] — landing is enforced outside the model, at the credential and OS layer, because a
  disabled push URL alone stops nothing on a Mac whose git and `gh` hand every process the owner's token: each worker
  works in its **own clone** (`git clone --shared` of the repository, no remote, no credential helper, `GH_TOKEN` and
  `~/.config/gh` unreachable) and the land step fetches from it; an OS sandbox denies the worker `~/.config/gh`, `~/.ssh`,
  the owner's git config and network access to the code host, with unsandboxed commands off; the land step runs the
  ladder with no credential in its environment and pushes from a separate later process holding a **land credential
  that is not the owner's** (a GitHub App or a fine-grained token kept outside every worker's reach); `main` stays
  PR-and-merge only (#6142). The test tries a push by URL and a `gh api` write from inside a worker and expects both to
  fail. **Owner decisions, open:** which land credential; whether a ruleset on the integration branch requires the land
  status (it would also block the Lead's hand merges and the release merge-back) and whether `main` requires one
  approval. Test: `fichero-server/tests/unit/workflows/test_land_gate.py::test_worker_push_fails_and_only_the_land_step_pushes`.
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
- `dev-workflows.run.watch-tick` [PROPOSED] — a wake that **outlives the engine**: a `launchd` job (not a session cron, not
  the engine's scheduler, which schedules by workflow id and dies with the engine) runs the tick every twenty to thirty
  minutes and keeps the dev engine alive; the tick looks at every task and acts or asks: a worker gone with its task
  unfinished → a successor from the handoff, or a question with none; a handoff with no successor after twenty minutes
  → started; a cluster READY and unlanded after thirty minutes → `land` or its refusal as a question; a worker is judged
  stuck by its **process and its session transcript's age**, never by a missing row (a held writer or a long test run is
  not stuck) → told once, then replaced; after an engine restart every worker in the persisted register is adopted or
  killed before any successor; a budget stop parks with a question; the pinned dev engine moves to a newer sha only
  between clusters; each action a row. Test: `fichero-server/tests/unit/workflows/test_watch_tick.py::test_gone_orphan_unlanded_stuck_and_restart`.
- `dev-workflows.run.machine-watch` [PROPOSED] — its own sixty-second check (not the tick) reads load, free memory and free
  disk on this Mac (other machines only when a later step adds them) and past the limits in the rules file (load above
  twice the cores, disk under 20 GiB, memory pressure critical) refuses new starts, stops running workers' process
  groups with SIGSTOP, writes an alert row and a question, and continues them (SIGCONT) after five minutes under; a run
  under way is paused, not only new work refused. Test:
  `fichero-server/tests/unit/workflows/test_machine_watch.py::test_overload_pauses_running_work_and_refuses_new`.
- `dev-workflows.run.records-are-truth` [PROPOSED] (maintainer 2026-10-31) — the jobs table is the truth for runs, and for a
  worker the truth is its job rows plus git plus the handoff file (workers have no checkpointer; the checkpointer is
  the recipes' and the release workflow's); the run log (one row per item attempt: model, provider, precision, context cap, prompt/cached/output tokens,
  tool calls and errors, diff lines or sources saved, wall time, cost, ladder, verdicts, rework rounds, false done) is
  written from them as rows and TSV; Activity shows the rows. Test:
  `fichero-server/tests/unit/workflows/test_records_are_truth.py::test_state_and_log_read_from_records`.
- `dev-workflows.run.rules-file` [PROPOSED] (maintainer 2026-10-31: declarative guardrails) — one rules file per project or
  use (`harness.toml` at the repository root; built with its `[check]` table: python paths, base-path variable, ready
  command, guard glob, floor, skip list, contract paths and guards, pinned check paths, spec dir, test globs, test
  environment) declares **what must hold**, never the worker's order of work: the integration
  and protected branches, the worktree root and branch pattern, the commit author and trailers, the worktree and
  scratch path, allowed tools and forbidden commands, required checks as argv lists with env, cwd and time budgets (lint,
  named tests, the guard glob with a found-floor and skip list, contract regeneration and when it applies), turn and
  dollar budgets, machine limits (one test run per agent, disk floor, load), landing conditions, the people list for the
  public boundary, the review checklist path, the role models, the handoff line. The policy hook, the `check`
  and `land` tools, the land gate, the watch tick and the machine watch read it; no rule lives only in prose or code,
  and a rule that is not in the file is not enforced. The boundary is deliberate: driving a worker's steps from data was
  the shape that lost here (the frozen runner's `[[steps]]`), so the file constrains, the worker decides. Test:
  `fichero-server/tests/unit/workflows/test_rules_file.py::test_hook_gate_and_tick_read_the_same_rules`.
- `dev-workflows.run.ratchet` [PROPOSED] (maintainer 2026-10-31: it only improves) — from the records and log, a small set of
  numbers per run and per week: time from READY to landed, first-pass READY rate, review findings per issue by kind and
  severity, stall hours (a worker gone or waiting with no row), false done, rework rounds, cost per landed issue; a
  baseline file in the repo and a guard in the `scripts/check_*_ratchet.py` pattern that goes red when a number
  backslides past its band, raised only with a reason; a review finding of the same kind on two issues must produce a
  new rule in the rules file or a new check before review (the 7 spec-diff findings of 11 are the first: a spec-diff
  check runs in `check`, not in review). Slow steps record what they waited on; failures record a kind. Test:
  `fichero-server/tests/unit/workflows/test_ratchet.py::test_baseline_compare_and_repeat_finding_makes_a_rule`.
- `dev-workflows.run.supervision` [PROPOSED] — a supervisor (the Lead session, a Sonnet builder, the maintainer) can stop
  any run, worker or the harness (a hold blocks landing and closing), inspect checkpoints, rows, log, handoffs and
  worktree from the Activity row or the CLI chat, and repair (resume from the last checkpoint, re-brief from the
  handoff, rebuild rows from the log, set aside as needs-maintainer); every repair a row with who and why. Test:
  `fichero-server/tests/unit/workflows/test_supervision.py::test_stop_inspect_repair_and_hold_blocks_landing`.
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — a small **question record** (task, generation, text, options, the
  artifact, asked-at, answer, answered-by) in the dev library, written by the `ask` tool, which parks the task; the
  parked worker exits and its successor resumes from the handoff and the answer; a question survives an engine restart
  because it is a row, not an `interrupt()`; it is answered from Activity, the Research workspace, the CLI chat or a
  page; a recipe's `HumanReviewRequest` is written to the same record so there is one queue. Test:
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
  Comment = a `ResearchNote` on an issue **marked public** (a note is local until marked), Run = a job row,
  Question/Approval = the question record of `node.human-question`; GitHub's names
  (Project, Milestone, Issue, Pull Request, Label, Comment, Release, Assignee) in the app, API and CLI, storage names
  behind aliases. Test: `fichero-server/tests/unit/research/test_combined_model_records.py::test_entities_and_names`.
- `dev-workflows.combined.github-sync` [GAP] (#6116) — for a project with a repo: pull with `gh` every five minutes and on
  open, **incrementally by `updated_at`** since the last sync (this repo has over six thousand issues); Fichero's edits go
  out through one guarded step: a typed operation with a grant, then the **public boundary**, then the engine's
  journaled writer; every write, refused or made, is a row and a log line with operation, URL and who asked. The
  boundary runs over issue writes, commit messages and the **land diff** alike, with these detectors: the project's
  people list (names and handles), path shapes of a home directory, secret shapes (tokens, keys, pairing codes), and a
  hash list of the private libraries' page text and file names kept outside the repo; a hit refuses the write or the
  land and parks a question. Conflict rule: GitHub wins on work state when both changed since the last sync; Fichero
  wins on its own fields; a text conflict is a question showing both versions. Step 2.2 pulls only, against this repo on
  a scratch base path; Step 2.3 adds the push through the same step. Test:
  `fichero-server/tests/unit/research/test_github_sync.py::test_pull_push_boundary_and_conflict_rule`.
- `dev-workflows.combined.spec-and-plan` [GAP] (#6116) — a spec is read from the repo file (status, behaviour ids with tags
  and issues, cited tests; the guards stay the binding); a plan is its build order as steps with dependencies and
  issues, proposed and filed by the ported `plan`/`plan-approve` (dry run by default); three approvals, each a question
  in the one queue: a spec's status flip, a plan, a check-file or acceptance-line change; apart from these and the
  worker's own stop-and-ask cases (`worker.steers`), nothing waits for a person. Test: `fichero-server/tests/unit/research/test_spec_and_plan_layers.py::test_spec_plan_and_approvals`.
- `dev-workflows.run.feeder` [PROPOSED] — scripts choose the next task: the person's pointed milestone, urgent, bugs, then
  the plan's build order; claimed, blocked and running skipped; a brief that fails lint (a spec id in an APPROVED spec
  or a bug label, acceptance, test path, in body or comments) goes to the queue as a write-up, never to a worker. Test:
  `fichero-server/tests/unit/workflows/test_feeder.py::test_feeder_order_and_lint`.
- `dev-workflows.surface.one-action-layer` [PROPOSED] — a new `fichero chat` command and the MCP tools list specs, milestones, issues and
  tasks, point a milestone, start a cluster or a research task, show runs, workers and questions, answer, approve; the
  Research workspace's Plan tab shows the same for any project; every verb is the audited action the app and the
  workers call. Test: `fichero-cli/tests/test_chat_dev_verbs.py::test_dev_verbs_are_audited_actions`.

### D. Models

- `dev-workflows.models.by-config` [PROPOSED] — the rules file names a model per role (builder, reviewer, lead-model, helper,
  researcher, manager, spec-writer): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`, `apple`, `claude-code`), model,
  precision, context cap, resident memory; the loader refuses a roster over the machine's cap; a role falls back along
  its list when a provider is absent; a role changes model only by a person editing the file after reading the run log
  (the log carries READY rate, false done, writes outside the worktree and reviewer agreement per model, so the
  reading is short); on 128 GB the expected roster is several small models pinned at once. Test:
  `fichero-server/tests/unit/workflows/test_model_config.py::test_roles_cap_fallback_and_move_on_the_log`.
- Deferred as text: a `decider` role for fixed-choice decisions (no failure today asks for it; rules and the helper
  suffice; it needs the fm-bridge typed output first); a repository as a workspace source (worktrees and the symbol
  index do this today).

### E. UX

- `dev-workflows.ux.activity-table` [PROPOSED] — one native sortable `Table` with disclosure rows over one data shape with a
  stored parent id: run › stage › step › batch › item (recipes), task › session › step (Researcher), cluster › issue ›
  session › step (Builder); columns in this order and these words: Name · Working on · Progress (a bar with a count, a
  spinner while unknown) · Time · Cost · State · Why (one short plain reason); more columns hidden by default; a few
  toolbar icons and a search field; a small summary strip; rows update one at a time in place, children load lazily,
  parents carry summaries. Stored rows go down to step and batch; items (pages) are read by the existing paged read
  (`GET /jobs/{id}/pages`), never materialised as rows; a worker's tool calls stay in its session log with a count on the
  session row; rows older than the rules file's retention are folded into their parent's summary; sorting and paging
  happen in the engine, not in the view. Every worker, handoff, review, question and landing is a row under its task.
  The maintainer sees Builder rows by opening the dev library in a Dev build (Stage 2); the CLI shows them until then.
  Overrides the approved Activity spec's measures-first columns and its stage bar; keeps its three groups, detail view
  and status island. Gaps to close for the rows: a workflow run's spaCy step, a recipe's status beside its row. Test:
  `fichero/Tests/Unit/general/Models/ActivityTableTests.swift`.
- `dev-workflows.ux.controls-work` [BROKEN] (#4402, closed: Stop now reaches some tools; the Pause residue needs its own issue
  or that one reopened) — Pause, Resume and Stop are three distinct controls, each shows the state it put the row in and
  reaches the work: Pause takes effect inside a step rather than at the item boundary (`pause_requested()` is read only
  there today, `builder.py:1176`), Stop cancels a running call in every tool, not only those that read cancellation; a
  control that has not acted in ten seconds says so on the row. Test: `fichero-server/tests/unit/workflows/test_controls_reach_the_call.py::test_stop_cancels_a_running_call`.

### F. Researcher and the web

- `dev-workflows.researcher.tasks` [PROPOSED] — three first tasks: **find sources** (search provider → fetch through the
  existing guards → `SearchSource` with title, URL, date, a one-line why and the quote it rests on; no quote, no save;
  duplicates by URL refused; accepted or discarded in the Sources tab); **search the libraries** (`local_search` and KG
  over the person's open libraries → sources linked to documents and segments with the matching words; an external
  catalogue is a later connector, none until asked); **read and note** (notes citing source and quote, follow-up tasks
  proposed; one source per 16-32k session with handoff; a synthesis that does not fit goes to an allowed cloud model or
  is refused with the reason). Each task runs with its own capability set and never another's (`two-capability-sets`),
  keeping the data diode `research/tools.py` declares: web with no library read, library with no web, notes with no
  egress; the same rule holds for a cloud model given library text. The in-app loop is the chat tool loop **extracted to
  a task runner**: a detached run with an iteration budget, a context count, the handoff per source, a Stop and a row,
  not the chat route's four-iteration turn. The search provider is configured: SearXNG JSON first, a paid API, the
  DuckDuckGo scrape last; every URL logged on the task. Test:
  `fichero-server/tests/unit/research/test_researcher_tasks.py::test_find_sources_search_libraries_read_and_note`.
- `dev-workflows.security.untrusted-text` [GAP] (#6116) — issue bodies, comments, spec text and fetched pages reach a model
  only as fenced, labelled data. For the Researcher, the turn that reads them has no write tool and anything proposed is
  acted on by a later script step with a fixed argv and a grant. For the Builder, which has one loop and a shell, the
  defence is the trusted-comment filter (`builder.cluster`) plus the sandbox and credential layer (`run.land-gate`), said
  plainly. No token, key or credential reaches state, rows, log or captured output: the bounded log gains a redaction of
  known shapes (today it only bounds). Test:
  `fichero-server/tests/unit/security/test_untrusted_text.py::test_injected_text_makes_no_write_and_no_secret_persists`.
- `dev-workflows.builder.bug-narrowing` [PROPOSED] — before a bug's brief reaches a model, a script reproduces and narrows it
  (failing command, localisation, the base's history, the failing tail pasted); a bug it cannot reproduce goes to the
  reviewer role marked so. Test: `fichero-server/tests/unit/workflows/test_bug_narrowing.py::test_reproduced_or_marked`.

### G. Any project, any model: the process the harness carries

- `dev-workflows.run.process` [PROPOSED] (maintainer 2026-10-31) — the harness carries the outer loop as it is practised, each
  step marked by who decides: **rulings** (a person; recorded as paraphrased ruling files cited in briefs), **spec**
  (a model drafts after a script gathers rulings, symbols, tests and open issues; a person approves; the spec guards bind
  shape, tags, milestone, manual and tests), **issues in build order** (script), **brief** (script: body, trusted comments,
  spec lines, localisation, the applicable rulings), **build** (the long-running worker, one commit per issue, the spec's
  status line in the same commit), **check** (script), **review** (a fresh reviewer, verdict at a sha, the checklist
  file), **fix and re-review** (same worker, fresh reviewer, two rounds then the queue), **land** (script, own
  credential), **close or leave open with residue** (script), **gate** and **dev build** (long scripts as one row each),
  **release** (the deferred workflow, a yes before anything public). A worker's claim of done is never a state change:
  only `check`'s output and a verdict move an item. Test:
  `fichero-server/tests/unit/workflows/test_process_steps.py::test_each_step_has_its_decider_and_only_check_moves_an_item`.
- `dev-workflows.project.neutral` [PROPOSED] (maintainer 2026-10-31) — harness code (hooks, tools, `check`, `land`, the tick,
  the templates) contains no project name, path, branch, command or guard; all of it is read from the project's rules
  file and review checklist; a guard greps the harness code for the first project's name and fails on a hit. A second
  project is any repository with a rules file: the test points the harness at a small unrelated repository (a CLI with a
  pytest suite and one shell guard), runs a two-issue cluster through brief, build, check, review, land and close on a
  scratch remote, and compares the rows with a Fichero cluster's: same step names, same row shape, only the config
  differs. Test: `fichero-server/tests/unit/workflows/test_second_project.py::test_unrelated_repo_runs_a_cluster_from_its_rules_file_alone`.
- `dev-workflows.run.local-parity` [PROPOSED] (maintainer 2026-10-31) — the harness runs on a local model server with the same
  guardrails as on Claude Code. Each Claude Code feature the process depends on has a named carrier, and the carrier is
  what the harness uses on every kind, so switching kind changes nothing but the rules file's roles: skills → markdown
  files under the harness's `skills/` loaded as rules by every kind; agent definitions → `roles/<role>.md` plus the
  rules file's role table; teammates and messages → the inbox file (`run.worker-address`); PreToolUse, PostToolUse and
  Stop hooks → the same scripts run by the Claude Code hook, the Pi extension, or the harness's own loop around each
  tool call; permissions → the OS sandbox, no token in the worktree, the forbidden-command list (`run.policy-hook`);
  compaction → the handoff file and a fresh session (`worker.handoff`); auto-memory → the rules file for rules, ruling
  files cited in the brief for judgement, the handoff for state; MCP tools → Pi's MCP client or a `symbols` script;
  `AskUserQuestion` → the question queue (`node.human-question`); session cron → launchd and the tick; usage from the
  transcript → usage from the kind's own report, one adapter per kind; model picker → the role table. Known gaps,
  stated: a bare chat-completions loop has no hook point and no tool-call repair, so a local kind is Pi or the
  harness's own loop, never raw completions; tool-call shape differs per model family and gets a repair layer; a local
  model reads short files, so each skill stays under sixty lines and the brief cites rulings rather than memory. A
  third kind (Goose) is admitted only by one real cluster against Pi on the same model, judged on tool errors, false
  done and rework; its recipe schema (tool allowlist, shell checks, max turns) is the idea to copy either way. A person
  reads the run log before a role moves local. Test:
  `fichero-server/tests/unit/workflows/test_local_parity.py::test_same_hooks_rules_and_rows_on_every_kind`.
- `dev-workflows.rollout.slice-zero` [PROPOSED] (manager 2026-10-31) — within two to three days and before any engine route,
  one real cluster of engine-bug issues runs on today's tmux builder with the enforced layer in place: the rules file,
  the `commit-msg` and PreToolUse hooks reading it, `check` and `land` as plain scripts (the `land` script with its own
  credential and the pinned overlay), the worker's own clone and sandbox, the trusted-comment filter, the review
  checklist file, the inbox file, and hook-posted rows into the dev library; the test replays the cluster's recorded
  events and asserts zero author findings, zero keystroke re-sends, a verdict and a land row per issue. Test:
  `fichero-server/tests/unit/workflows/test_slice_zero.py::test_real_cluster_on_scripts_and_hooks_before_any_route`.

### H. Shared core, two front ends (owner 2026-10-31)

- `dev-workflows.core.shared` [PROPOSED] — the Researcher area of Fichero and Fichero Builder share one **core**: the records
  (`models/research.py`, about 300 lines, imports only `core`), the jobs table and its runner (`execution/jobs.py`), the
  Activity route and rows (`api/routes/system/activity.py`), the question record, grants, the `check`/`land`/`brief`
  tools, the worker start/stop, the tick, the sync, and the chat tool loop over the audited action layer
  (`actions/chat_tools.py`, imports only `actions`). They differ in front end and profile only. **How the core runs
  without the document and model stack:** the same engine package, under a `builder` feature tier that registers only
  the core routes (`register_tiered_routes` exists; no second package), a scratch base path and a dev library; no core
  module may import `mlx`, `kraken`, `spacy`, `torch` or `lancedb` at module top (true today for the whole engine, held
  by the lazy-import test and its module budget); a guard imports the core under the `builder` tier and fails on any
  heavy module in `sys.modules`. A Builder bundle skips the two heavy install steps (the Kraken and MLX bundle tables in
  `pyproject.toml`) by a build flag; the release-size ratchet gains a `builder.app_bundle` row. What couples the core to
  the rest today and the cost of cutting it: `execution/jobs.py` (3,800 lines) lazily imports `llm`, `recipes`,
  `workflows` and `api` in about thirty places for recipe job kinds; a Builder run creates only `worker` kind rows, so
  those branches are never taken and the file is **not split now**; the Activity route imports `recipes.run_view` for
  recipe rows (a Builder's rows render without it); jobs live in the library database, so Builder's dev library is the
  one ruled in Q3. Estimated cost of the split: one tier, one build flag, one guard, a size-ratchet row: size M, after
  Slice 0; a package split of `jobs.py` is not needed and is refused until a Builder-only import fails. Test:
  `fichero-server/tests/unit/workflows/test_core_shared.py::test_core_imports_under_builder_tier_load_no_heavy_module`.
- `dev-workflows.core.activity-package` [PROPOSED] — the Activity table is a Swift package (`FicheroActivity`) both front
  ends depend on, beside `FicheroAPIClient` (the one local package today): it holds `Views/Activity/` (about 9,000 lines,
  30 files) and `Models/ActivityStore*.swift` (about 1,200 lines) and depends on the generated client; the app-side
  services it calls today (`ActivityService`, `ActivityStreamService`, `RemoteRunService`, `WorkflowExecutionStore`,
  `AppState`: about twenty references) are reached through one small protocol the host app implements, so the package
  imports nothing from the app target. Cost: size M to L (one Sonnet builder for about a week and one Lead build cycle on
  Mac and iOS); it starts only after `ux.activity-table` is built, and after Slice 0. Test:
  `fichero/Tests/Unit/general/Models/ActivityTableTests.swift`.

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
  November; project-neutral with Fichero first; local models with guardrails as strong as Claude Code's, Sonnet on Claude
  Code first, then OpenRouter, then local on the Studio.
- 2026-10-31, owner (paraphrased): the Researcher area and Builder share one core of code with two front ends; the
  Researcher stays in Fichero; no app work before Slice 0.
- 2026-10-31, manager (after the review): the Builder worker is an interactive pane session; Slice 0 first; the decider,
  the workspace source and the promotion thresholds are cut; pinned checks and grants are restored; the land credential
  and any ruleset on the integration branch are the owner's to rule on.
- Deferred as text: invited contributors; shared projects; a `decider` role; a repository as a workspace source; the
  release as a dev workflow (the one fixed sequence that earns one: long, resumable at the failed step, a yes before
  anything public, step by step in Activity).

## Build order

Thin slices through November 2026, each one a Claude Code builder can take from its heading; dogfooding from 0.1.
Stage 3 is held to two steps until Stage 1 has run a real cluster. `Depends on` defaults to the step before.

### Stage 0 — Slice 0: a real cluster on scripts and hooks, no engine route (days 1-3)

#### Step 0.1 — the rules file, the hooks, the check and land scripts, the worker's clone and sandbox, the review checklist
- Behaviours: `dev-workflows.rollout.slice-zero`, `dev-workflows.run.land-gate`, `dev-workflows.run.policy-hook`
- Tests: fichero-server/tests/unit/workflows/test_slice_zero.py, fichero-server/tests/unit/workflows/test_land_gate.py, fichero-server/tests/unit/workflows/test_policy_hook.py
- Size: M

### Stage 1 — a Claude Code builder runs one cluster, the engine recording and guarding it (weeks 1-2)

#### Step 1.1 — the engine starts and stops a worker; the check tool; the worker's address
- Behaviours: `dev-workflows.run.worker-start-stop`, `dev-workflows.tool.check`, `dev-workflows.run.worker-address`
- Tests: fichero-server/tests/unit/workflows/test_worker_process.py, fichero-server/tests/unit/workflows/test_worker_route.py, fichero-server/tests/unit/workflows/test_check_tool.py, fichero-server/tests/unit/workflows/test_worker_address.py
- Size: M

#### Step 1.2 — worker kinds: claude today, fake for the dry run; pipeline frozen
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.rollout.dry-run`, `dev-workflows.rollout.pipeline-frozen`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py, fichero-server/tests/unit/workflows/test_dry_run.py, fichero-server/tests/unit/workflows/test_pipeline_frozen.py
- Size: M

#### Step 1.3 — the cluster, the worker steers, the git tool
- Behaviours: `dev-workflows.builder.cluster`, `dev-workflows.worker.steers`, `dev-workflows.tool.git`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_git_tool.py
- Size: M

#### Step 1.4 — review and land, the durable question
- Behaviours: `dev-workflows.run.review-and-land`, `dev-workflows.node.human-question`
- Tests: fichero-server/tests/unit/workflows/test_review_and_land.py, fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py
- Size: M

#### Step 1.5 — the handoff hook, records as truth, supervision, the rules file, the ratchet
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.records-are-truth`, `dev-workflows.run.supervision`, `dev-workflows.run.rules-file`, `dev-workflows.run.ratchet`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_records_are_truth.py, fichero-server/tests/unit/workflows/test_supervision.py, fichero-server/tests/unit/workflows/test_rules_file.py, fichero-server/tests/unit/workflows/test_ratchet.py
- Size: M

#### Step 1.6 — the watch tick, the machine watch, the two capability sets, grants
- Behaviours: `dev-workflows.run.watch-tick`, `dev-workflows.run.machine-watch`, `dev-workflows.worker.two-capability-sets`, `dev-workflows.security.grants`
- Tests: fichero-server/tests/unit/workflows/test_watch_tick.py, fichero-server/tests/unit/workflows/test_machine_watch.py, fichero-server/tests/unit/workflows/test_capability_sets.py, fichero-server/tests/unit/workflows/test_grants.py
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

#### Step 2.4 — the CLI chat and app over one action layer
- Behaviours: `dev-workflows.surface.one-action-layer`
- Tests: fichero-cli/tests/test_chat_dev_verbs.py
- Size: M

#### Step 2.5 — the Researcher's first tasks and untrusted text
- Behaviours: `dev-workflows.researcher.tasks`, `dev-workflows.security.untrusted-text`
- Tests: fichero-server/tests/unit/research/test_researcher_tasks.py, fichero-server/tests/unit/security/test_untrusted_text.py
- Depends on: 1.6
- Size: M

#### Step 2.6 — the process as steps with deciders; a second, unrelated project runs a cluster; the Pi kind on the same cluster
- Behaviours: `dev-workflows.run.process`, `dev-workflows.project.neutral`
- Tests: fichero-server/tests/unit/workflows/test_process_steps.py, fichero-server/tests/unit/workflows/test_second_project.py
- Depends on: 1.6
- Size: M

#### Step 2.7 — the shared core runs under a builder tier without the document and model stack
- Behaviours: `dev-workflows.core.shared`
- Tests: fichero-server/tests/unit/workflows/test_core_shared.py
- Depends on: 1.6
- Size: M

#### Step 2.8 — the Activity table as a Swift package both front ends use
- Behaviours: `dev-workflows.core.activity-package`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift
- Depends on: 2.1
- Size: L

### Stage 3 — models by configuration and local parity (week 4; detailed after Stage 1 has run a real cluster)

#### Step 3.1 — models in configuration, bug narrowing
- Behaviours: `dev-workflows.models.by-config`, `dev-workflows.builder.bug-narrowing`
- Tests: fichero-server/tests/unit/workflows/test_model_config.py, fichero-server/tests/unit/workflows/test_bug_narrowing.py
- Depends on: 2.5
- Size: M

#### Step 3.2 — local parity: the same hooks, rules and rows on a Pi kind and a local server
- Behaviours: `dev-workflows.run.local-parity`
- Tests: fichero-server/tests/unit/workflows/test_local_parity.py
- Depends on: 3.1
- Size: M

## Behaviour tests

Every behaviour names its test above, written in its step; each `security.*` and gate test includes its failing case.

| Behaviour | Step |
|-----------|------|
| `dev-workflows.rollout.slice-zero` | 0.1 |
| `dev-workflows.run.land-gate` | 0.1 |
| `dev-workflows.run.policy-hook` | 0.1 |
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
| `dev-workflows.node.human-question` | 1.4 |
| `dev-workflows.worker.handoff` | 1.5 |
| `dev-workflows.run.records-are-truth` | 1.5 |
| `dev-workflows.run.supervision` | 1.5 |
| `dev-workflows.run.rules-file` | 1.5 |
| `dev-workflows.run.ratchet` | 1.5 |
| `dev-workflows.run.watch-tick` | 1.6 |
| `dev-workflows.run.machine-watch` | 1.6 |
| `dev-workflows.worker.two-capability-sets` | 1.6 |
| `dev-workflows.security.grants` | 1.6 |
| `dev-workflows.ux.activity-table` | 2.1 |
| `dev-workflows.ux.controls-work` | 2.1 |
| `dev-workflows.combined.entities` | 2.2 |
| `dev-workflows.combined.github-sync` | 2.2 |
| `dev-workflows.combined.spec-and-plan` | 2.3 |
| `dev-workflows.run.feeder` | 2.3 |
| `dev-workflows.surface.one-action-layer` | 2.4 |
| `dev-workflows.researcher.tasks` | 2.5 |
| `dev-workflows.security.untrusted-text` | 2.5 |
| `dev-workflows.run.process` | 2.6 |
| `dev-workflows.project.neutral` | 2.6 |
| `dev-workflows.core.shared` | 2.7 |
| `dev-workflows.core.activity-package` | 2.8 |
| `dev-workflows.models.by-config` | 3.1 |
| `dev-workflows.builder.bug-narrowing` | 3.1 |
| `dev-workflows.run.local-parity` | 3.2 |

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

1. The land credential: a GitHub App or a fine-grained token, kept outside every worker's reach (`run.land-gate`).
2. A ruleset on the integration branch requiring the land status: it also blocks the Lead's hand merges and the release
   merge-back; and whether `main` requires one approving review.
3. The Pause residue of #4402 (closed): reopen it or file a new issue for `ux.controls-work`.
The external catalogue connector stays none until a person asks (own libraries plus web search first).
