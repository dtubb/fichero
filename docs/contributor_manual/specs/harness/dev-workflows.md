# Fichero Builder and Fichero Researcher — one harness, two uses — Design Spec

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — a contributor section ("How Fichero is built") saying that
> Fichero builds itself through its own harness, how to run a cluster on a scratch path, and how the same harness runs
> a research project.

> **Status: APPROVED by the owner 2026-10-31 at bef07fa21 (rewrite 5: the second review verdict applied and the scope cut to what three weeks can
> hold; § 0 is Slice 0 on its own).** Replaces the text approved on 2026-10-26
> (c9c24dfbf, 739ad4ba4). Tags: [OK] built · [PARTIAL] exists, not wired · [GAP] not built · [BROKEN] fails today ·
> [PROPOSED] decided here, not yet ruled. Issues: #6116 (the pipeline), #2067 (Research), #5933 (Pause and Stop).
>
> Scope with other specs: `pipeline/` is **frozen** (no new code; ideas and the ladder ported; removed once the engine has
> landed real clusters for two weeks) and `harness/deterministic-conductor.md` is its record. `ui/research.md` keeps the
> Research surface; its orchestration lines (`research.manager-with-workers-orchestration`,
> `research.future.agent-operates-projects`, `research.per-model-tool-grants`) are owned here.
> `ui/activity-and-automatic-work.md` keeps the job model, lanes, throttling and durability; § E overrides its window
> columns and adds workers as rows. `ui/workflows.md` keeps the canvas; no graph drives a worker's loop.

## Intent

One harness, two uses, any project. The harness is **project-neutral**: its code names no project; what differs between
projects (integration branch, check commands, guard glob, forbidden commands, people list, review checklist, machine
limits, handoff line) lives in one rules file per project, and Fichero is the first project; Python-tested repositories
first. It carries the process that works here, each step with its decider: **rulings** (a person; paraphrased ruling files
cited in briefs) → **spec** (a model drafts after a script gathers rulings, symbols, tests and issues; a person approves;
the spec guards bind shape, tags, milestone, manual and tests) → **issues in build order** → **brief** (script) → **build**
(a long-running worker, one commit per issue, the spec's status line in the same commit) → **check** (script) → **review**
(a fresh reviewer, verdict at a sha, a checklist file) → **fix and re-review** (same worker, fresh reviewer, two rounds then
the queue) → **land** (script) → **close or leave open with residue** (script) → **gate** and **dev build** (long scripts, one
row each) → **release** (deferred workflow; a yes before anything public). A worker's words never move an item: only
`check`'s output and a verdict do.

**Fichero Builder** builds Fichero: a long-running worker takes a cluster of issues from one spec, builds them in order,
checks, asks for review, lands the cluster, updates the issues, hands off at 85 % of its context and a successor carries
on. **Fichero Researcher** does a person's research with the same harness: finds sources on the web, searches the person's
own libraries, reads and notes, files tasks under milestones, asks when unsure, hands off the same way. The two share one
**core** of engine code (records, jobs, Activity, questions, the tools, the sync) and differ in front end and profile; the
Researcher stays in Fichero (owner 2026-10-31). Target: Builder standing by 2026-11-21 on Claude Code, Pi through
OpenRouter by 2026-11-14 on one real cluster, local models by configuration after that.

## 0. Slice 0 — a real cluster in two to three days (read this section alone)

**What runs.** Today's long-running Sonnet builder in a tmux pane as the worker user, on the cluster **#6100, #6085,
#6107** (small engine and contract bugs, none from the frozen runner; checked against the code 2026-10-31: `/api/machines`
still returns `list[MachineOut]`; `segment_readings.py` still lists a stored reading beside its provisional twin;
`split_done` has a memo in `recipes/done.py`, so #6107 may be fixed already: the builder writes its failing test first, and
a test green on the base means no commit and the Lead closes the issue). No engine route: rows are JSON lines in a log both
users can write (`$FICHERO_HARNESS_LOG` under the workroot), imported later. No land credential: **the Lead pushes**.

**The wall (owner ruling 2026-10-31).** A second macOS user, here called the worker user, **not in `staff`** (its own
primary group) and with the owner's home made `700`, so it reads nothing of the owner's: no home, no real library, no
Keychain, no GitHub credential, no ssh key; its tmux server is its own socket. It owns one **workroot** (`/Users/Shared/<worker>`,
mode `1777`) holding: its clone of the **public repository over anonymous https** (no mirror, no refresh; a push fails with
no credential), its own `claude`, `uv`, `ruff` and the project's venv (the rules file names `[check] python` and the
`PATH`; nothing is reached in the owner's home), its git identity (`Claude <noreply@anthropic.com>`, `safe.directory` on
the workroot), the `commit-msg` hook installed in the clone by the start script, the engine-owned repository and the pinned
copy the ladder uses, and one **shared directory** that is the only channel across the boundary: the Lead writes briefs
and findings into it, the worker writes its requests (review, question, handoff) and its JSON rows, the Lead watches it and
reaches the pane only by `sudo -u <worker> tmux …`. In Slice 0 the Lead runs **brief**, **review** and **land**; the worker
runs **check**. Not promised: Seatbelt, a disabled push URL, a closed outbound network.

**Start path, fail-closed.** `scripts/harness_start.py` is the only way a worker starts, for generation 1 and for every
successor the handoff hook starts: it refuses unless it runs as the worker user, unless the **probe** has passed since the
last set-up change, and unless the rules file loads with every rung declared; then it writes the generated settings
(hooks, permission mode, empty strict MCP config) and opens the pane. The probe, run as the worker user, must **fail** on:
a `git push --dry-run` by URL, a `gh api` write, a read of the owner's home and of each real library path, a read of the
owner's Keychain; `deny_read` has a required floor and an empty list refuses. `check` run by the worker user runs
directly; run by the owner it uses `sudo -u <worker>`; with no `[jail]` in the rules file it refuses.

**Landing identity.** A verdict names each commit by `git patch-id --verbatim` (whitespace is behaviour in Python) **and**
its message hash; `land` refuses a range with a merge, a commit without exactly one id, a commit whose id or message is not
READY in the verdict store, any file **added** under a pinned path (`scripts/check_*` excepted), and a `conftest.py` or
`sitecustomize` anywhere in the diff that is not READY by name. The reviewer is `claude -p --tools Read,Grep,Glob` over
the prepared diff and the ladder's output, as the owner's user with no shell; a script computes the ids and writes the
verdict file into the store the worker cannot write.

**Build order (plain scripts and files; most exist on `feat/fichero-builds-fichero`):** 1 the owner's set-up by
`scripts/harness_setup.sh` (user and group, workroot, sudoers line) and the worker's (tools, venv, `claude` sign-in, clone,
git identity); the script applies `chmod 700 ~` only after listing what else reads the owner's home (`stat`, the open
files of other users, shared folders, any launchd job running as another user) and showing the list for a yes; it records
the previous mode and **undoes it** with `chmod <previous> ~` on `--undo`, which also removes the sudoers line; 2 the probe,
then the **smoke test** (below); 3 `harness.toml` fail-closed with `[jail]`, `[check] python`, `deny_read`; 4
`harness_start.py` and the hooks wired through it; 5 `harness_check.py` over the built `run_ladder`, `red_on_base` by path,
pinned set extended to `.github/`, `.gitattributes`, `.gitmodules`, `pyproject.toml`, `pytest.ini`, every `conftest.py`;
6 `harness_land.py` (fetch the sha into the engine-owned repository under the workroot, ladder there, verdict per
`--verbatim` id and message, boundary grep over diff and messages, print the fast-forward; on a non-fast-forward the Lead
rebases the worker's branch and the ladder runs again); 7 the review wrapper and `review-checklist.md`; 8 the brief script
(built); 9 the engine change: `worker.*` actions only on a dev-tier engine and owner-only (built), plus the
`FICHERO_DEV_WORKERS=1` refusal in `worker_process.start` (not yet in code).

**What a real run must show (the remaining doubts are settled here, not on paper):** as the worker user, `claude` completes
one turn after sign-in (`claude setup-token` if the Keychain is locked under `sudo`); the probe fails on all five tries;
the ladder runs green on a throwaway commit in the workroot with no "dubious ownership" refusal; a file written into the
shared directory by one user is read by the other; a successor started by the hook is the worker user with the hooks
loaded; a whitespace-only indentation change after READY is refused by `land`; a new `conftest.py` is refused; the three
fixes reach `integration` by the Lead's push with a verdict per commit, zero author or trailer findings, and a JSON row
per refusal, check, verdict and land. Findings are counted by hand and start the ratchet's TSV. Behaviour:
`dev-workflows.rollout.slice-zero`.

## What exists today (paths under `fichero-server/src/fichero_server/`; measured 2026-10-31)

- Engine: `workflows/builder.py` + `checkpointer.py` (DuckDB), `human_review.ask_human()` = `interrupt()` inside a running
  graph node (`HumanReviewRequest` is a payload, not a queue table), `scheduler.py` (by workflow id only), one `jobs` table
  per library (`execution/jobs.py`, 5,264 lines, about sixty lazy imports into `llm`, `recipes`, `workflows` and `api`),
  `pause_requested()` read at the item boundary and inside four tools (`llm/__init__.py`, `economy_htr.py`, `_together.py`,
  `remote_read/pipeline.py`); Pause and Stop on recipe runs are #5933.
- Agent pieces: `workflows/tools/cli_agent.py` runs `claude -p` per item (one-shot calls, not the Builder); the chat tool
  loop over the audited action layer (`actions/chat_tools.py`, `actions/registry.py`) returns within one chat turn at
  `MAX_CHAT_TOOL_ITERATIONS = 4`; `/api/actions/invoke` is on at every tier and runs any registered action.
- Research: `models/research.py` (296 lines); `api/routes/research/{crud,notes,tools}.py` (DuckDuckGo-HTML search, browse,
  fetch behind SSRF and size guards; `tools.py` declares the data diode: a browsing agent never holds library or KG
  read tools); no catalogue connector; no GitHub issue or milestone code.
- Activity (app paths under `fichero/fichero/`): `Views/Activity/` and `Models/ActivityStore*.swift`, 42 files, about 7,000
  lines, with roughly seventy-five app types referenced from outside the set; the approved spec's `Table` is not built.
- Imports: no engine module imports `mlx`, `kraken`, `spacy`, `torch` or `lancedb` at module top; `PIL` 7, `duckdb` 8,
  `numpy` 4, `langgraph` 2 do. Route tiers filter registration, not import: `api/main.py` imports every route module at
  top, so any route's closure is about 373 modules. `check_tool.py`, `brief_tool.py` and `policy_hook.py` import nothing
  from the engine (stdlib only): that is the part worth guarding.
- Built on `feat/fichero-builds-fichero` through 98ba83507: `worker_process.py` (the `claude` kind in a tmux window with
  `--strict-mcp-config` over an empty MCP config; gaps: no `-e` environment so `FICHERO_BASE_PATH` is not passed, SIGKILL
  only, the register is in memory, the pane log is re-read five times a second), `POST /api/workers` (+ `/tell`,
  `/{job}/stop`) dev-tier, `check_tool.py` (`run_ladder`, `pinned_violations`, `weakened_tests`, `acceptance_changed`,
  `_scratch_tree`; gaps: `python -m pytest` hard-coded, no lint rung, guards run through `runpy`, `red_on_base` red on any
  source change without a Python test), `brief_tool.py` (gap: asks `gh` for an issue field it lacks; title untrusted),
  `policy_hook.py` + `scripts/harness_policy_hook.py` (gap: matches the tool named `Bash` only; `git -C . push` passes).
- Measured so far (the briefs under `agent-work/` are not tracked, so the figures are here): the per-item runner reached 6
  READY of 13 verdicts; 7 of 11 NOT_READY findings were spec drift; long-running Claude Code builders reached about 6 of 8
  READY; about 1,090 commits and 125 merges landed in eight days with four by a person; the pane message helper re-sent
  Enter about 9,600 times in 24 days; the author-and-trailer finding appeared in 9 of 11 reviews; the project has no
  project-level hook and `integration` is unprotected. Small local models fit triage and routing and finished no exact
  edit; Pi's compaction error with a 35B is a harness fault to fix at the OpenRouter stage.

## Decisions

- **Issues are managed in Fichero and synced to GitHub** (maintainer 2026-10-31); GitHub stays the public record; every
  write goes through one guarded step. Specs stay Markdown in the repo, bound by the guards.
- **The engine's records are the truth for runs** (maintainer 2026-10-31); for a worker the truth is its rows, git and the
  handoff file; workers have no checkpointer.
- **Thin engine; the loop lives in the agent harness**: records, start and stop, Activity, questions, the log; a hook does
  handoff and successor; a few tools do brief, check, ask, hand off, land (git is the worker's own shell command; the user wall, not an argv jail, guards it). LangGraph only for recipes and the release.
- **Two worker kinds** (maintainer 2026-10-31): Claude Code and Pi; `fake` is the test double. **The Builder worker is an
  interactive session in a tmux pane** (probed: `claude -p` exits at the end of its turn and takes no pane message); Pi in
  a pane with its extension, the same shape.
- **Isolation by a second macOS user** (owner 2026-10-31): workers and the ladder run as it with no GitHub credential, and a
  start refuses if that user or its clean probe is missing; not Seatbelt, not a disabled push URL.
- **Land per cluster**, enforced outside the model; a READY verdict per commit's patch-id; the Lead pushes until a GitHub
  App exists (owner 2026-10-31).
- **Fixed steps are scripts**; only the release earns a workflow, deferred.
- **Enforce, don't ask; declare, don't narrate**: every standing rule names its layer (user boundary, hook, guard at landing,
  prose) and lives in one fail-closed rules file.
- **Project-neutral, Fichero first; Python-tested repositories first** (maintainer 2026-10-31): a second repository runs a
  cluster from its rules file alone.
- **Local models with the same enforced guardrails, and the losses said** (maintainer 2026-10-31): the user boundary and
  the scripts carry over whole; the binding review stays on a cloud model until the log shows agreement; counters replace
  model-obeyed stops. Order: Sonnet on Claude Code, then OpenRouter through Pi, then local.
- **Shared core, two front ends** (owner 2026-10-31): one core, the Researcher in Fichero; a Builder front end and an
  Activity package are deferred text until a second app is scheduled; a one-line guard keeps the three harness tools
  free of engine imports.
- **Messages are files** read by a hook on prompt submit and after each tool; an idle worker at its prompt is reached by
  the tick's keystroke tell, logged as such.

### Deployment profiles

| Profile | Machine | Models | Runs |
|---|---|---|---|
| Builder, now | M1 Pro 16 GB | Claude Code (Sonnet builds, Opus reviews; Fable or Opus writes specs); then OpenRouter through Pi | clusters, reviews, dry runs; engine on a scratch base path, workers as the second user |
| Builder, end state | M5 Studio 128 GB | small local models pinned under a memory cap, a local server with a prefix cache; cloud for the binding review until the log says otherwise | 2-3 builder sessions + research; headroom for the gate and a build |
| Researcher | M5 MacBook Pro 24 GB | one small local model at a time, Apple frameworks, MLX readers when chosen; cloud only where the person allows, cost shown first | one task at a time, 16-32k context, handoff per source |

## Behaviours

### A. Workers (the loop is the harness's)

- `dev-workflows.run.worker-start-stop` [PARTIAL] (#6116) — the engine starts a worker for a task (a Builder cluster, headless
  on a scratch base path with a pinned dev engine, ruling Q1; a Researcher task, in-app) with its brief, kind, model and
  allow-list. A Builder worker is an interactive tmux session **as the worker user**: Claude Code with an explicit
  permission mode, `--settings` and `--setting-sources` naming only the generated settings (no user or project hooks
  inherited), a generated MCP config under `--strict-mcp-config`, the role's model, and the environment passed with
  `tmux new-window -e` (`FICHERO_BASE_PATH` on the scratch path, `FICHERO_HARNESS_LOG`); Pi in a pane with its extension.
  The hooks post the rows; the pane log is not followed. The register (process group, pane, session directory,
  started-at) is a file, so a restart adopts or kills before any successor; stop is TERM then KILL after a grace. The
  route module and its actions load **only under the `dev` tier**, `owner_only`, and `start` refuses unless
  `FICHERO_DEV_WORKERS=1` from the scratch engine's launcher (built: dev-tier and owner-only actions; not yet: the
  variable); at release `worker.start` is unreachable through `/api/actions/invoke`. Every worker, generation 1 or a
  successor, starts through `scripts/harness_start.py` (§ 0), never bare. Tests: `fichero-server/tests/unit/workflows/test_worker_process.py`,
  `fichero-server/tests/unit/workflows/test_worker_route.py::test_a_release_engine_has_no_worker_actions_and_refuses_to_start`.
- `dev-workflows.run.worker-address` [PARTIAL] (#6116) — per task, the current generation's address (pane, process group,
  session directory, kind, started-at) is registered, rewritten at each handoff, cleared when gone; `tell` appends to
  that generation's inbox file, read by the worker's hook on prompt submit and after each tool; a worker idle at its
  prompt is reached by the tick's keystroke into the pane, logged as a fallback; under 800 characters; a tell to a stale
  generation is refused naming the current one. Test:
  `fichero-server/tests/unit/workflows/test_worker_address.py::test_tell_reaches_only_the_current_generation`.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — kinds `claude` and `pi`, both the pane shape above; each kind has one
  adapter (usage, tool errors, the reported sha, the tool names the hooks see) and a hook that meets an unknown tool name
  **refuses**, never passes; `fake` replays recorded hook events through the real hooks and is never started by a person.
  **Dated:** the `pi` kind runs one real cluster through OpenRouter by 2026-11-14 with its extension running the same hook
  scripts; the per-item `claude -p` of `cli_agent.py` stays for one-shot reviewers and clerks. Test:
  `fichero-server/tests/unit/workflows/test_worker_node.py::test_worker_kinds`.
- `dev-workflows.tool.check` [PARTIAL] (#6116) — the `check` tool runs the ladder from the rules file: every rung an **argv
  list** with cwd, explicit environment (scratch base path and HOME, `PYTHONPATH` relative to the tree under test, thread
  caps) and timeout; a guard runs by its own shebang; the test command is configured, not `python -m pytest`; typed
  results; refuses when blind (fewer guards than the floor). **Pinned checks** (built): the ladder runs from a pinned copy
  of `scripts/`, the hooks, the agent settings directory, the rules file, `.github/`, `.gitattributes`, `.gitmodules`,
  `pyproject.toml`, `pytest.ini` and every `conftest.py` (matched by name anywhere), laid over a scratch tree built by the
  land process from a fetched sha under the workroot, never the worker's clone or its git config; a diff touching a pinned
  path, **adding** a file under one (`scripts/check_*` excepted), rewriting the item's own acceptance lines, or weakening
  or deleting a test is a question, not a pass. **By path:** `red_on_base` applies to paths the rules
  file names (Python here); a Swift or contract change needs a Lead build row on the sha; docs and spec changes need
  neither. **Counters:** the same named test red twice, the diff bound tripped twice, a tool call repeated with the same
  arguments after an error, the turn or dollar cap: counted by `check` and a PostToolUse counter, and enforced (a refusal
  row and a question), not left to the model. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`.
- `dev-workflows.builder.cluster` [PARTIAL] (#6116) — one spec and its build-order issues (parser ported from
  `pipeline/plan.py`), in order, one commit per issue with its test; the brief is built by `scripts/harness_brief.py` from
  `gh api repos/{repo}/issues/N`: the body and the **title** only when the author association is owner, member or
  collaborator, the comments by the same rule newest first, the rest counted as "N outside texts, ask"; the spec lines and
  localisation from `pipeline/localise.py`; tested against a recorded real payload. The cluster record is the handoff
  file and the rows until the plan layer exists. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_cluster_in_build_order_one_commit_each`.
- `dev-workflows.worker.steers` [PROPOSED] — the worker owns the task's judgement and calls the steps as tools (`brief`,
  `check`, `request-review`, `verdicts`, `land`, `ask`, `hand-off`; `close`, `update-issue` and `file-bug` only once the
  guarded writer exists; for research `search`, `fetch`, `save-source`, `note`); it stops and asks when an acceptance line
  would change, a pinned check trips, a step is paid or irreversible, a source contradicts the premise or the spec
  contradicts the code; the countable stops are `check`'s (above); never for context. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_worker_steers_and_stop_and_ask_cases`.
- `dev-workflows.worker.handoff` [PARTIAL] (#6116) — at 85 % of the context window or a task boundary the handoff hook
  (tracked in the repository, no pane ids or session names in it) asks the worker to write the handoff: the spec or
  question and its sections; ordered items with state and sha; one line per commit or saved source; commands run and
  results; the failing command's tail; decisions and rejected alternatives; files touched; the do-not list; budget used;
  under two thousand tokens; then ends the session (TERM after a grace, since an interactive session does not exit on
  its own) and starts the successor **through the same start path**, in the jail; a result already on the task is refused
  as re-done work. A parked worker ends the same way and its successor resumes with the answer. At 16-32k the handoff
  fires per item. Test: `fichero-server/tests/unit/workflows/test_cluster_run.py::test_handoff_and_successor`.
- `dev-workflows.worker.two-capability-sets` [PROPOSED] — Builder: worktree, shell, git, the step tools, scratch base path,
  `dev` tier only. Researcher: capabilities **per task**, never mixed in one session: find-sources holds web search and
  fetch and no library read; search-libraries holds read-only library and KG actions and no web; read-and-note reads only
  saved sources with no egress; writes go through the audited layer as the user's account; no shell, never a GitHub
  token. Test: `fichero-server/tests/unit/workflows/test_capability_sets.py::test_sets_never_mix_and_builder_kind_gated`.
- `dev-workflows.security.grants` [PROPOSED] — a standing **allow-list** in the rules file per role (tools, paid providers,
  GitHub writes), checked at the tool; a paid or public step outside it is a question, answered once per task and
  logged; the full grant record (who, scope, expiry, per model) returns with #4721 when a second user needs it. Test:
  `fichero-server/tests/unit/workflows/test_grants.py::test_tool_refuses_outside_the_allow_list_and_asks`.

### B. Review, landing, gates and watches

- `dev-workflows.run.review-and-land` [PROPOSED] (maintainer 2026-10-31: land per cluster) — `request-review` starts a fresh
  reviewer (Opus; read-only; as the owner's user, never the worker's) on a range with the project's **review checklist
  file**, as `claude -p --tools Read,Grep,Glob` over the prepared diff and the ladder's output (no shell, so an injected
  diff cannot push or write a verdict); a script computes `git patch-id --verbatim` and the message hash per commit and
  writes the verdict file into the **verdict store** the worker user cannot write (rows later), and `land` reads only there; `request-review`
  returns at once and the worker reads verdicts with a `verdicts` tool; NOT_READY findings belong to the task's current
  generation (two rounds, then the queue). `land` is a script: fetch the sha into the engine-owned repository, ladder on
  the rebased head there, a READY verdict for **every commit** in the range by `--verbatim` patch-id and message hash (a
  merge, or a commit without exactly one id, refuses the range), the public-boundary grep over diff and messages, then the fast-forward of the integration branch (a merge mode for the release merge-back is added
  before any ruleset restricts updates); `main` never. Until the GitHub App exists the script prints the fast-forward and
  the Lead pushes. `Fixes #N` closes with the sha, `Part of #N` leaves open with the residue. A research task's review is
  the person's. Only `check`'s output and a verdict move an item. Test:
  `fichero-server/tests/unit/workflows/test_review_and_land.py::test_review_per_issue_and_land_per_cluster`.
- `dev-workflows.run.land-gate` [PROPOSED] — the wall is the **user boundary** (owner 2026-10-31): the worker user holds no GitHub
  credential, no ssh key, no Keychain item of the owner's, no read on the owner's home or the real libraries, and clones a
  the public repository over anonymous https (no mirror; `origin/integration` is a normal remote ref the worker fetches),
  with its own git identity and `safe.directory` on the workroot and nothing from the owner's git config; the worker user is
  not in `staff` and the owner's home is `700`; the ladder never runs in the worker's tree, and runs in trees the worker
  user owns under the workroot. The land process runs
  as the owner's user with no credential in its environment and prints the push for the Lead; later a **GitHub App**
  (Contents write and Metadata only, no Workflows) pushes from a separate process. Proof is a **once-per-set-up probe** run
  as the worker user: `git push --dry-run` by URL, a `gh api` write, a read of the owner's home, of each real library
  and of the owner's Keychain, all refused; `deny_read` has a required floor; `scripts/harness_start.py` refuses until the
  probe has passed. **Rulesets (owner 2026-10-31):** `integration` carries `protect-integration` (no deletion, no force-push, no
  required status) from 2026-10-31; `main` stays at zero approving reviews until a GitHub App exists; in Slice 0 the Lead
  pushes. **Not claimed:** a Seatbelt deny
  list (probed: no hostname rules, and a client inside a profile reaches the tmux server, `launchctl` and the engine);
  outbound network stays open, so a worker can send what it can read, which is now the public repository and its brief.
  Test: `fichero-server/tests/unit/workflows/test_land_gate.py::test_worker_user_cannot_push_and_the_ladder_never_runs_in_its_tree`.
- `dev-workflows.run.policy-hook` [PARTIAL] (#6116; built at 98ba83507) — each worker runs with a PreToolUse policy hook and a
  `commit-msg` hook, plain scripts reading `harness.toml [policy]`, refusing with a reason and a row: a write or `cd`
  outside the worktree and scratch path, `git stash`, any `git push` (parsed from argv, so `git -C . push` is caught),
  `xcodebuild`, `pkill`/`killall` by pattern, a listing and `rm -r` in one command, a second test run (lock file),
  wrong author or missing trailers, a paid call outside the allow-list; a kind's adapter maps its tool names, and an
  unknown tool name is refused. **Layers:** the user boundary holds the hard rules; the hook is fast feedback, not a
  security boundary; guards at landing catch the rest; prose-only rules are listed as such and become hook or guard
  rules once seen twice. Test: `fichero-server/tests/unit/workflows/test_policy_hook.py::test_each_forbidden_command_is_refused_with_a_reason`.
- `dev-workflows.run.watch-tick` [PROPOSED] — a `launchd` job (not a session cron, not the engine's scheduler) runs the tick
  every twenty to thirty minutes and keeps the dev engine alive: a worker gone with its task unfinished → a successor
  from the handoff, or a question with none; a handoff with no successor after twenty minutes → started; a cluster READY
  and unlanded after thirty minutes → `land` or its refusal as a question; a worker judged stuck by its process and its
  session transcript's age, never by a missing row → told once by keystroke, then replaced; after an engine restart the
  persisted register is adopted or killed before any successor; a budget stop parks with a question; the pinned dev
  engine moves to a newer sha only between clusters; each action a row. Test:
  `fichero-server/tests/unit/workflows/test_watch_tick.py::test_gone_orphan_unlanded_stuck_and_restart`.
- `dev-workflows.run.records-are-truth` [PROPOSED] (maintainer 2026-10-31) — the jobs table is the truth for runs, and for a
  worker its rows plus git plus the handoff; in Slice 0 the rows are JSON lines in `$FICHERO_HARNESS_LOG`, imported later
  by one script; the run log (one row per item attempt: model, provider, context cap, tokens, tool calls and errors,
  diff lines, wall time, cost, ladder, verdicts, rework rounds, false done) is written from them as rows and TSV. Test:
  `fichero-server/tests/unit/workflows/test_records_are_truth.py::test_state_and_log_read_from_records`.
- `dev-workflows.run.rules-file` [PARTIAL] (#6116) — one `harness.toml` at the repository root declares **what must hold**,
  never the worker's order of work: integration and protected branches, worktree root and branch pattern, commit author
  and trailers, scratch path, allowed tools and forbidden commands, each rung of the ladder **declared on or off** as an
  argv list with env, cwd and time budget, the pinned paths, the paths `red_on_base` applies to, turn and dollar caps,
  machine limits, landing conditions, the people list, the review checklist path, the role models, the handoff line.
  **Fail-closed:** an unknown or misspelt key refuses to load; an undeclared rung is an error, never "skipped". The hook,
  `check`, `land` and the tick read it. Test:
  `fichero-server/tests/unit/workflows/test_rules_file.py::test_unknown_key_refuses_and_every_rung_is_declared`.
- `dev-workflows.run.ratchet` [PROPOSED] (maintainer 2026-10-31: it only improves) — from the rows: READY to landed, first-pass
  READY rate, findings per issue by kind and severity, stall hours, false done, rework rounds, cost per landed issue, as a
  TSV per run and per week; a finding of the same kind on two issues becomes a rule in the rules file or a `check` rung
  (the spec-diff check is the first: a behaviour change touching no spec line is red in `check`, not in review); the
  backslide guard in the `check_*_ratchet.py` pattern is added once four weeks of rows exist. Test:
  `fichero-server/tests/unit/workflows/test_ratchet.py::test_repeat_finding_makes_a_rule`.
- `dev-workflows.run.supervision` [PROPOSED] — a supervisor (the Lead, the maintainer) can stop any worker or the harness (a
  hold blocks landing and closing), inspect rows, log, handoffs and the clone, and set a task aside as needs-maintainer;
  every action a row with who and why. Test:
  `fichero-server/tests/unit/workflows/test_supervision.py::test_stop_inspect_and_hold_blocks_landing`.
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — a small **question record** (task, generation, text, options, the
  artifact, asked-at, answer, answered-by) written by the `ask` tool, which parks the task; the parked worker is ended and
  its successor resumes with the answer; a question survives an engine restart because it is a row; it is answered from
  Activity, the Research workspace, the CLI or a page; a recipe's `HumanReviewRequest` is written to the same record so
  there is one queue. Test:
  `fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py::test_question_survives_restart`.
- `dev-workflows.rollout.dry-run` [PROPOSED] — the built `fake` kind plus **recorded hook events** replayed through the real
  hooks and tools, with no model and no money: a refused command, a weakened test, a pinned-path edit, an acceptance-line
  change, a handoff and successor, a question and its answer, a false done, a NOT_READY round, land and close against a
  fake `gh`, a complete log row. Test: `fichero-server/tests/unit/workflows/test_dry_run.py::test_scenario_replays`.
- `dev-workflows.rollout.pipeline-frozen` [PROPOSED] (maintainer 2026-10-31) — `pipeline/` takes no new code; the engine
  calls the `scripts/` guards directly and ports what it needs; it is removed once the engine has landed real clusters
  for two weeks. Test: `fichero-server/tests/unit/workflows/test_pipeline_frozen.py::test_engine_calls_scripts_not_pipeline`.
- `dev-workflows.rollout.slice-zero` [PROPOSED] (manager 2026-10-31) — § 0, as written: the cluster #6100, #6085, #6107
  within two to three days on today's tmux builder, as the second user, with the rules file, hooks, `check`, `land`
  (the Lead pushes), the brief fix, the checklist file and the B1 fix; done when the cluster is on the integration branch
  with a verdict per patch-id. The proof is the cluster itself; its rows seed the ratchet. Test:
  `fichero-server/tests/unit/workflows/test_slice_zero.py::test_land_requires_a_verdict_per_patch_id_and_the_boundary_grep`.

### C. Records, sync, surfaces

- `dev-workflows.combined.entities` [GAP] (#6116) — one model of project work: Project = `ResearchProject`, Milestone =
  `ResearchPlan`, Issue = `ResearchTask` (+ GitHub URL, plan step, behaviour ids), Comment = a `ResearchNote` **marked
  public** (a note is local until marked), Run = a job row, Question = the question record; GitHub's names in the app,
  API and CLI, storage names behind aliases. Test:
  `fichero-server/tests/unit/research/test_combined_model_records.py::test_entities_and_names`.
- `dev-workflows.combined.github-sync` [GAP] (#6116) — pull with `gh` every five minutes and on open, **incrementally by
  `updated_at`**; Fichero's edits go out through one guarded step: a typed operation within the allow-list, the **public
  boundary**, then the journaled writer; every write, refused or made, is a row. The boundary is the same grep `land`
  runs from Slice 0 (people list, home-path shapes, secret shapes); a hash list of private page text is **deferred**: it
  would make the land path read private libraries. Conflict rule: GitHub wins on work state, Fichero on its own fields,
  a text conflict is a question. Step 2.2 pulls only; the push through the same guarded step follows in Step 2.4. Test:
  `fichero-server/tests/unit/research/test_github_sync.py::test_pull_push_boundary_and_conflict_rule`.
- `dev-workflows.surface.one-action-layer` [PROPOSED] — `fichero workers …` and the MCP tools (the generated surface) list
  specs, milestones, issues and tasks, start a cluster or a research task, show workers and questions, answer, approve;
  every verb is an audited action; a chat verb is added only when these prove thin. Test:
  `fichero-cli/tests/test_chat_dev_verbs.py::test_dev_verbs_are_audited_actions`.

### D. Models

- `dev-workflows.models.by-config` [PROPOSED] — the rules file names **one model per role** (builder, reviewer, spec-writer,
  helper, researcher): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`, `claude-code`), model, precision, context cap;
  today builder Sonnet, reviewer Opus, spec-writer Fable for a rewrite and Opus for a small spec, approved by the owner; a
  missing provider is a **question**, never a silent fallback; a role changes model only by a person editing the file
  after reading the run log (READY rate, false done, writes outside the worktree, reviewer agreement per model). Test:
  `fichero-server/tests/unit/workflows/test_model_config.py::test_one_model_per_role_and_a_missing_provider_asks`.

### E. UX

- `dev-workflows.ux.activity-table` [PROPOSED] — one native sortable `Table` with disclosure rows over one data shape with a
  stored parent id: run › stage › step › batch › item (recipes), task › session › step (Researcher), cluster › issue ›
  session › step (Builder); columns Name · Working on · Progress · Time · Cost · State · Why; rows update in place,
  children load lazily, parents carry summaries; stored rows go down to step and batch, items by the paged read, tool
  calls as a count on the session row, rows past the retention folded into their parent; sorting and paging in the
  engine. The maintainer sees Builder rows by opening the dev library in a Dev build (Stage 2); the CLI until then.
  Overrides the approved Activity spec's measures-first columns and stage bar; keeps its groups, detail view and status
  island. Test: `fichero/Tests/Unit/general/Models/ActivityTableTests.swift`.
- `dev-workflows.ux.controls-work` [BROKEN] (#5933) — Pause, Resume and Stop are three distinct controls, each shows the state
  it put the row in and reaches the work: Pause inside a step, Stop cancelling a running call in every tool; a control
  that has not acted in ten seconds says so on the row. Test:
  `fichero-server/tests/unit/workflows/test_controls_reach_the_call.py::test_stop_cancels_a_running_call`.

### F. Researcher and the web

- `dev-workflows.researcher.tasks` [PROPOSED] — three first tasks: **find sources** (search → fetch through the existing guards
  → `SearchSource` with title, URL, date, a one-line why and the quote it rests on; no quote, no save; duplicates by URL
  refused); **search the libraries** (`local_search` and KG over the person's open libraries); **read and note** (notes
  citing source and quote; one source per 16-32k session with handoff; a synthesis that does not fit goes to an allowed
  cloud model or is refused with the reason). Each task runs with its own capability set (`two-capability-sets`), keeping
  the data diode `research/tools.py` declares. The in-app loop is the chat tool loop **extracted to a task runner**: a
  detached run with an iteration budget, a context count, the handoff, a Stop and a row. One search provider (the
  existing one); another is added when it fails. Test:
  `fichero-server/tests/unit/research/test_researcher_tasks.py::test_find_sources_search_libraries_read_and_note`.
- `dev-workflows.security.untrusted-text` [GAP] (#6116) — issue bodies, titles, comments, spec text and fetched pages reach a
  model only as fenced, labelled data. Researcher: the turn that reads them has no write tool; anything proposed is acted
  on by a later script step with a fixed argv. Builder: the defence is the trusted-author filter plus the user boundary,
  said plainly. No token, key or credential reaches state, rows, log or captured output: the bounded log gains a
  redaction of known shapes (today it only bounds). Test:
  `fichero-server/tests/unit/security/test_untrusted_text.py::test_injected_text_makes_no_write_and_no_secret_persists`.

### G. Any project, any model

- `dev-workflows.project.neutral` [PROPOSED] (maintainer 2026-10-31) — harness code (hooks, tools, `check`, `land`, the tick, the
  templates) carries no project **string**: no branch name, path, command or guard name; all of it comes from the rules
  file and the checklist; a guard greps the harness code for the first project's branch, path and command strings and
  fails on a hit (module imports are not strings). The second project is a small Python-tested CLI repository with one
  shell guard: it runs a two-issue cluster through brief, build, check, review, land and close on a scratch remote from
  its rules file alone, and the cluster lands green. Test:
  `fichero-server/tests/unit/workflows/test_second_project.py::test_unrelated_repo_runs_a_cluster_from_its_rules_file_alone`.
- `dev-workflows.run.local-parity` [PROPOSED] (maintainer 2026-10-31) — the harness runs on a local model server with the same
  **enforced** guardrails, and the ones that are not carried are said. Carried whole: the user boundary, the rules file,
  the hook scripts (through each kind's adapter; unknown tool names refused), `check`, `land`, the verdict store, the
  question record, the inbox file, the handoff file and fresh session (instead of compaction), launchd and the tick
  (instead of a session cron), skills as markdown files under sixty lines (instead of plugin skills), roles as
  `roles/<role>.md` plus the role table, usage through the kind's adapter (instead of the transcript), the turn and
  dollar cap as a PostToolUse counter. **Not carried, said:** the binding review is a guardrail made of model strength and
  stays on a cloud model until the log shows agreement with it; a bare chat-completions loop has no hook point and no
  tool-call repair, so a local kind is Pi or the harness's own loop; Claude Code's edit rules (read before edit, unique
  match) and its injection resistance are not reproduced and small models are weaker at both; the fake kind proves
  wiring, not guardrails. A third kind (Goose) is admitted only by one real cluster against Pi on the same model. Test:
  `fichero-server/tests/unit/workflows/test_local_parity.py::test_same_hooks_rules_and_rows_on_every_kind`.
- `dev-workflows.core.shared` [PROPOSED] (owner 2026-10-31: shared core, two front ends) — the Researcher area and a future
  Builder front end share one core: the records, jobs, Activity route and rows, the question record, the allow-list,
  the tools and the sync. What is kept free of the engine **now** is the three harness tools (`check_tool.py`,
  `brief_tool.py`, `policy_hook.py`: stdlib only), by a one-line guard that imports each alone and fails on any
  `fichero_server` module in `sys.modules`. A `builder` tier, a Builder bundle and the Activity table as a Swift package
  are deferred text until a second app is scheduled: tiers filter registration, not import (a route's closure is about
  373 modules), a bundle without the model stack still carries `lancedb`, `langgraph`, spaCy and OpenCV, and the Activity
  views reach about seventy-five app types from 42 files, so each is size L for no consumer today. Test:
  `fichero-server/tests/unit/workflows/test_core_shared.py::test_the_three_harness_tools_import_nothing_from_the_engine`.

## Rulings

- 2026-10-26 (kept): pinned separate dev engine first (Q1); the repo is a separate dev library (Q3); model steps do
  bookkeeping only (Q4); GitHub names (Q6); `plan-approve` first (Q8); contributor tier off by default (Q5); chains
  retire into recipes (Q9); invites for contributors (Q10). Replaced: Q2 (journal as truth) and Q7 (pull-only sync).
- 2026-10-27 (Activity, kept): one window and one job model; lanes sized from the machine; cloud by default per recipe
  step with cost shown; the embedder's own lane.
- 2026-10-31 (paraphrased): one harness, two uses; built in Fichero; a long-running builder on Claude Code first, judged
  by use; land per cluster; models by configuration; Pi a kind, not the assumption; the Researcher's machine is a 24 GB
  laptop; Activity Monitor as the model; issues managed in Fichero and synced with a guarded write; engine records are
  the truth under supervision; `pipeline/` frozen; thin engine; two worker kinds; fixed steps as scripts; enforce by
  user boundary, hook and guard rather than ask; project-neutral with Fichero first; local models with the enforced
  guardrails and the losses said; Sonnet on Claude Code first, then OpenRouter, then local; shared core, two front
  ends, the Researcher in Fichero; no app work before Slice 0.
- 2026-10-31, owner (isolation and landing): second macOS user for workers and the ladder, refuse if missing;
  `protect-integration` on the integration branch; `main` at zero approvals until an App exists; the Lead pushes in
  Slice 0; the Activity package is a line of deferred text under the shared-core ruling.
- 2026-10-31, manager (after the reviews): the Builder worker is an interactive pane session; Slice 0 first with the Lead
  pushing; the decider, the workspace source, the feeder, bug narrowing, the Activity package, the `builder` tier and the
  promotion thresholds are cut to deferred text; pinned checks and the allow-list are kept.
- Deferred as text: a typed git tool with an argv jail (the user wall guards git; the policy hook refuses push); a
  machine watch (the one-test-run lock is the control on load; a watch returns if the lock proves insufficient); a spec
  and plan layer with approvals in the engine (the Lead's `gh` and the spec guards do this for now; the pull sync stays);
  invited contributors; shared projects; a `decider` role; a repository as a workspace source; a feeder
  (a person points the milestone); bug narrowing before a brief; a Builder front end, `builder` tier and bundle; the
  Activity table as a Swift package; the private-text hash list; the ratchet's backslide guard; the release as a dev
  workflow (long, resumable at the failed step, a yes before anything public, step by step in Activity).

## Rulings of 2026-10-31 on isolation and landing (decided, no longer open)

- Workers and the ladder run as a second macOS user with no GitHub credential; a start refuses if the user or its clean
  probe is missing (set-up in § 0: the user outside `staff`, the owner's home `700`, a workroot, one sudoers line, the
  worker's own tools and `claude` sign-in, an anonymous clone of the public repository).
- `integration` has the ruleset `protect-integration`: no deletion, no force-push, no required status check. A later
  "restrict updates" rule waits for a GitHub App and three clusters landed by `land`.
- `main` stays at zero approving reviews until a GitHub App exists; the Lead pushes in Slice 0; the App (Contents write
  and Metadata, no Workflows) pushes later from a separate process.
- #4402 is not an owner question; `ux.controls-work` cites #5933.

## Build order

Steps a Claude Code builder can take from the heading. `Depends on` defaults to the step before. Dates are the owner's
targets: Slice 0 by 2026-11-03, Pi by 2026-11-14, the second project and local parity by 2026-11-21.

### Stage 0 — Slice 0 (days 1-3): § 0

#### Step 0.1 — the rules file, the hooks, check and land as scripts, the verdict store, the second user, the B1 fix
- Behaviours: `dev-workflows.rollout.slice-zero`, `dev-workflows.run.rules-file`, `dev-workflows.run.policy-hook`, `dev-workflows.run.land-gate`, `dev-workflows.run.review-and-land`
- Tests: fichero-server/tests/unit/workflows/test_slice_zero.py, fichero-server/tests/unit/workflows/test_rules_file.py, fichero-server/tests/unit/workflows/test_policy_hook.py, fichero-server/tests/unit/workflows/test_land_gate.py, fichero-server/tests/unit/workflows/test_review_and_land.py
- Size: M

### Stage 1 — the engine records and guards the cluster (weeks 1-2)

#### Step 1.1 — the engine starts and stops a worker; the check tool; the worker's address
- Behaviours: `dev-workflows.run.worker-start-stop`, `dev-workflows.tool.check`, `dev-workflows.run.worker-address`
- Tests: fichero-server/tests/unit/workflows/test_worker_process.py, fichero-server/tests/unit/workflows/test_worker_route.py, fichero-server/tests/unit/workflows/test_check_tool.py, fichero-server/tests/unit/workflows/test_worker_address.py
- Size: M

#### Step 1.2 — worker kinds: claude, pi through OpenRouter by 2026-11-14, fake for the dry run; pipeline frozen
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.rollout.dry-run`, `dev-workflows.rollout.pipeline-frozen`
- Tests: fichero-server/tests/unit/workflows/test_worker_node.py, fichero-server/tests/unit/workflows/test_dry_run.py, fichero-server/tests/unit/workflows/test_pipeline_frozen.py
- Size: M

#### Step 1.3 — the cluster, the worker steers
- Behaviours: `dev-workflows.builder.cluster`, `dev-workflows.worker.steers`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py
- Size: M

#### Step 1.4 — the question record, records as truth
- Behaviours: `dev-workflows.node.human-question`, `dev-workflows.run.records-are-truth`
- Tests: fichero-server/tests/unit/workflows/test_pause_resume_survives_restart.py, fichero-server/tests/unit/workflows/test_records_are_truth.py
- Size: M

#### Step 1.5 — the handoff hook in the repository, supervision, the ratchet's TSV
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.supervision`, `dev-workflows.run.ratchet`
- Tests: fichero-server/tests/unit/workflows/test_cluster_run.py, fichero-server/tests/unit/workflows/test_supervision.py, fichero-server/tests/unit/workflows/test_ratchet.py
- Size: M

#### Step 1.6 — the watch tick under launchd, the two capability sets, the allow-list
- Behaviours: `dev-workflows.run.watch-tick`, `dev-workflows.worker.two-capability-sets`, `dev-workflows.security.grants`
- Tests: fichero-server/tests/unit/workflows/test_watch_tick.py, fichero-server/tests/unit/workflows/test_capability_sets.py, fichero-server/tests/unit/workflows/test_grants.py
- Size: M

### Stage 2 — seen in the app; records and sync; the Researcher; the second project (weeks 2-3)

#### Step 2.1 — the Activity table with a hierarchy, and controls that work
- Behaviours: `dev-workflows.ux.activity-table`, `dev-workflows.ux.controls-work`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero-server/tests/unit/workflows/test_controls_reach_the_call.py
- Depends on: 1.1
- Size: M

#### Step 2.2 — the records and the guarded GitHub sync (pull)
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-sync`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py, fichero-server/tests/unit/research/test_github_sync.py
- Depends on: 1.6
- Size: M

#### Step 2.4 — the CLI verbs and app over one action layer; the push through the guarded sync step
- Behaviours: `dev-workflows.surface.one-action-layer`
- Tests: fichero-cli/tests/test_chat_dev_verbs.py
- Size: M

#### Step 2.5 — the Researcher's first tasks and untrusted text
- Behaviours: `dev-workflows.researcher.tasks`, `dev-workflows.security.untrusted-text`
- Tests: fichero-server/tests/unit/research/test_researcher_tasks.py, fichero-server/tests/unit/security/test_untrusted_text.py
- Depends on: 1.6
- Size: M

#### Step 2.6 — a second, unrelated Python-tested repository runs a cluster from its rules file; the three tools stay engine-free
- Behaviours: `dev-workflows.project.neutral`, `dev-workflows.core.shared`
- Tests: fichero-server/tests/unit/workflows/test_second_project.py, fichero-server/tests/unit/workflows/test_core_shared.py
- Depends on: 1.6
- Size: M

### Stage 3 — models by configuration and local parity (week 3-4)

#### Step 3.1 — one model per role in the rules file; a missing provider asks
- Behaviours: `dev-workflows.models.by-config`
- Tests: fichero-server/tests/unit/workflows/test_model_config.py
- Depends on: 2.5
- Size: M

#### Step 3.2 — local parity: the same hooks, rules and rows on the Pi kind and a local server
- Behaviours: `dev-workflows.run.local-parity`
- Tests: fichero-server/tests/unit/workflows/test_local_parity.py
- Depends on: 3.1
- Size: M

## Behaviour tests

Every behaviour names its test above, written in its step; each `security.*` and gate test includes its failing case.

| Behaviour | Step |
|-----------|------|
| `dev-workflows.rollout.slice-zero` | 0.1 |
| `dev-workflows.run.rules-file` | 0.1 |
| `dev-workflows.run.policy-hook` | 0.1 |
| `dev-workflows.run.land-gate` | 0.1 |
| `dev-workflows.run.review-and-land` | 0.1 |
| `dev-workflows.run.worker-start-stop` | 1.1 |
| `dev-workflows.tool.check` | 1.1 |
| `dev-workflows.run.worker-address` | 1.1 |
| `dev-workflows.node.worker` | 1.2 |
| `dev-workflows.rollout.dry-run` | 1.2 |
| `dev-workflows.rollout.pipeline-frozen` | 1.2 |
| `dev-workflows.builder.cluster` | 1.3 |
| `dev-workflows.worker.steers` | 1.3 |
| `dev-workflows.node.human-question` | 1.4 |
| `dev-workflows.run.records-are-truth` | 1.4 |
| `dev-workflows.worker.handoff` | 1.5 |
| `dev-workflows.run.supervision` | 1.5 |
| `dev-workflows.run.ratchet` | 1.5 |
| `dev-workflows.run.watch-tick` | 1.6 |
| `dev-workflows.worker.two-capability-sets` | 1.6 |
| `dev-workflows.security.grants` | 1.6 |
| `dev-workflows.ux.activity-table` | 2.1 |
| `dev-workflows.ux.controls-work` | 2.1 |
| `dev-workflows.combined.entities` | 2.2 |
| `dev-workflows.combined.github-sync` | 2.2 |
| `dev-workflows.surface.one-action-layer` | 2.4 |
| `dev-workflows.researcher.tasks` | 2.5 |
| `dev-workflows.security.untrusted-text` | 2.5 |
| `dev-workflows.project.neutral` | 2.6 |
| `dev-workflows.core.shared` | 2.6 |
| `dev-workflows.models.by-config` | 3.1 |
| `dev-workflows.run.local-parity` | 3.2 |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | workers, tools, gates, watches, records, sync, researcher tasks, models | `fichero-server/tests/unit/workflows/`, `tests/unit/research/`, `tests/unit/security/` |
| CLI (pytest) | y | dev verbs are audited actions | `fichero-cli/tests/test_chat_dev_verbs.py` |
| Swift unit | y | the table's rows, columns, in-place update, lazy children | `fichero/Tests/Unit/general/Models/ActivityTableTests.swift` |

## Documentation matrix

| Doc | Says |
|-----|------|
| `docs/contributor_manual/how-fichero-is-built.md` | Fichero builds itself through its harness; how to run a cluster on a scratch path as the worker user; the Researcher as the same harness |
| `docs/contributor_manual/review-checklist.md` | the reviewer's checklist (spec diff, range-diff after a rebase, tests of changed readers, the shell file cap) |
| `ui/research.md`, `ui/activity-and-automatic-work.md` | the surfaces; point here for orchestration, the window's columns and worker rows |
| `harness/deterministic-conductor.md` | the frozen runner's record |
