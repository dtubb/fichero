# Fichero Builder and Fichero Researcher — one harness, two uses — Design Spec

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — a contributor section ("How Fichero is built") saying that
> Fichero builds itself through its own harness, how to run a cluster on a scratch path, and how the same harness runs
> a research project.

> **Status: APPROVED by the owner 2026-11-01 at a597b5320 (rewrite 6 with the Decisions bullet on deterministic verbs and Step 2.3; earlier: rewrite 5: the second review verdict applied and the scope cut to what three weeks can
> hold; § 0 is Slice 0 on its own). Rewrite 6, 2026-11-01: the Decisions and the Build order below follow the owner's direction of 2026-11-01 and the harness audit of the same day (kept untracked with the manager's briefs as `audit-2026-11-01-harness.md`); they await the owner's approval, and the two rulings they name are marked.** Replaces the text approved on 2026-10-26
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
(hooks, permission mode, empty strict MCP config) and opens the pane. The pane's command line carries a short prompt
naming the brief file, never the brief's text, which the worker reads itself (a 22 KB brief made tmux refuse "command too
long", 2026-11-02; test `fichero-server/tests/unit/workflows/test_start_tool.py::test_a_brief_over_100_kb_reaches_the_worker_as_a_short_prompt_naming_its_file`). The probe, run as the worker user, must **fail** on:
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
6 `harness_land.py` (fetch the sha into the engine-owned repository (first thought under the workroot; it lives outside every home dir, see tool.check), ladder there, verdict per
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

- **The whole chain is deterministic verbs** (owner 2026-11-01): write a spec, break an approved spec into build-order
  steps as issues under its milestone, take a milestone's connected issues as one cluster brief, build, check, review,
  land. No step picks issue numbers by hand; a person approves specs and answers questions. The verbs come right after
  check and land are in use (Step 2.3).
- **Issues are managed in Fichero and synced to GitHub** (maintainer 2026-10-31); GitHub stays the public record; every
  write goes through one guarded step. Specs stay Markdown in the repo, bound by the guards.
- **The Builder is separate from the engine** (owner 2026-11-01, products: Fichero client, Fichero iOS, Fichero Server,
  Fichero Builder). The Builder is a top-level `fichero-builder/` package of plain Python on the standard library, with no
  import of `fichero_server` (`check_harness_neutral.py` points at it); the engine never starts, stops or records a worker,
  and `worker_process.py`, `routes/workers.py` and their routes go. For a worker the truth is its journal rows, git and the
  handoff file; workers have no checkpointer. An app (Fichero Agents, later) reads the same journal; no app need shapes the CLI.
- **CLI first, in real use before any app** (owner 2026-11-01): `builder run`, `builder check`, `builder review`,
  `builder land`, `builder ask`, `builder clean`, in that enforced order for one cluster. Fixed steps are plain code; a model
  step gets a fixed input, a context budget and a schema-checked output; plain code owns worktrees and assembles briefs
  (jcodemunch, the issue text, the spec lines, the rules file). Graphs (LangGraph) only where a model step needs branching;
  the review graph first, and only if the TSV shows it saves tokens.
- **The watcher is the harness** (audit 2026-11-01): one process starts a worker and reads its session file for context,
  cost, idle, stuck and red, for Claude and Pi alike; an unknown price refuses to start; per-session and daily caps; a silent
  worker raises an alert; on restart it reconciles with the journal. The Stop hook, the pane regex and keystroke tells go.
- **Two worker kinds** (maintainer 2026-10-31): Claude Code and Pi; `fake` is the test double. **Pi is driven by RPC**
  (`prompt`, `steer`, `abort` on a pipe), not by typing into a pane; a Pi `tool_call` extension carries `[policy]` and
  fails closed (its crash blocks; tested first). Claude Code stays an interactive session in a pane until the Pi kind is
  proven, then the pane shape is retired. Providers and Pi, not Max (owner 2026-11-01): a metered key with a low credit limit.
- **Isolation**: the second macOS user is the bootstrap (owner 2026-11-01: a Builder user cannot be expected to make one)
  and holds today: workers and the ladder run as it with no GitHub credential, and a start refuses if that user or its clean
  probe is missing. The shipped sandbox is chosen by test, not by reading: a signed launcher with App Sandbox entitlements and
  inherited sandbox, raw Seatbelt with a maintained profile, and Apple `container` are each tried with Pi, git and one pytest
  inside; Linux containers cannot run MLX or Xcode, so they serve untrusted or Linux work only. One wrapper, so graphs and
  scripts do not change when the mechanism does. Build, merge and push stay outside the sandbox as plain steps; the model is
  reached over a local port.
- **Review has a shell** (audit 2026-11-01: reading alone missed the HIGHs): a fresh reviewer gets a throwaway checkout as
  the worker user, runs the named tests one at a time, the guards and ruff, reverts each fix to see its test go red, and
  writes a verdict keyed on the exact range; the size rule ignores generated files; a second round is range-diff plus probes.
- **Land per cluster**, enforced outside the model; a READY verdict per commit; the Lead pushes until a GitHub App exists
  (owner 2026-10-31). **Owner ruling pending (c):** whether the tool ever pushes or a person always does.
- **Spend**: caps in the watcher per session and per day, prices from the rules file, unknown price refuses. **Owner ruling
  pending (d):** how much a provider key may spend per day.
- **The Macs are the only gate** (owner 2026-11-01): no GitHub CI; GitHub keeps only the issue and milestone workflows.
- **Dev builds per milestone** (owner 2026-11-01): a build is triggered when a milestone's issues are closed and its specs
  are [OK], not by the clock; the owner tests that build and findings go to triage.
- **Enforce, don't ask; declare, don't narrate**: every standing rule names its layer (user boundary, sandbox, hook, guard
  at landing, prose) and lives in one fail-closed rules file per project, which `harness_start` reads only after checking its
  owner and mode.
- **Project-neutral, Fichero first; Python-tested repositories first** (maintainer 2026-10-31): a second repository runs a
  cluster from its rules file alone.
- **Local models with the same enforced guardrails, and the losses said** (maintainer 2026-10-31): the user boundary, the
  sandbox and the scripts carry over whole; the binding review stays on a cloud model until the TSV shows agreement; counters
  replace model-obeyed stops. Order: Claude Code under Max on real issues for about a week; then Pi on a metered provider
  (Sonnet first, so only the agent changes); then local on the Studio, coder only, one issue per session.
- **The ratchet is the yardstick**: rounds, findings by class and cost per cluster in one TSV, from cluster-c on; every
  later step is compared with it.
- **Shared core, two front ends** (owner 2026-10-31): the Researcher stays in Fichero and keeps the engine's records; the
  Builder shares only the rules-file shape and the sandbox wrapper. Activity rows for workers are deferred to the app.
- **Messages are files**: a question or an answer is a row in the journal and a file the worker reads at its next turn;
  `builder ask` writes it; no pane typing.

### Deployment profiles

| Profile | Machine | Models | Runs |
|---|---|---|---|
| Builder, now | M1 Pro 16 GB | Claude Code (Sonnet builds, Opus reviews; Fable or Opus writes specs); then OpenRouter through Pi | clusters, reviews, dry runs; engine on a scratch base path, workers as the second user |
| Builder, end state | M5 Studio 128 GB | small local models pinned under a memory cap, a local server with a prefix cache; cloud for the binding review until the log says otherwise | 2-3 builder sessions + research; headroom for the gate and a build |
| Researcher | M5 MacBook Pro 24 GB | one small local model at a time, Apple frameworks, MLX readers when chosen; cloud only where the person allows, cost shown first | one task at a time, 16-32k context, handoff per source |

### tool.triage — what `builder triage` reads and writes

`builder triage` is the one writer of GitHub metadata besides `builder steps` and `builder landed`; a person edits by
hand only to overrule. It reads three things: the spec files under `docs/contributor_manual/specs/<area>/` (which issues
each cites, its `> Milestone:` line), `harness.toml [triage.labels]` (old label → kept label or `spec:<stem>` hint; edit
there, not in code) and `docs/contributor_manual/specs/build-order.md` (the owner's order of milestones; read, proposed
to, never written). Each flag is one rule of `harness/issues-and-labels.md` and runs alone or with the others, in the
order labels → specs → milestones → assignees → order; a rerun changes nothing (idempotent), and `--dry` shows the counts
the write path would produce.

## Behaviours

### A. Workers (the loop is the harness's)

- `dev-workflows.run.worker-start-stop` [PARTIAL] (#6116) — `builder run <issues>` starts a worker for a cluster: one plain
  process, no engine. It builds the brief (`brief`), writes the rules check (`check_tool.load` on `harness.toml`, read only
  after its owner and mode are checked), and launches the worker **as the worker user** through the one start path
  (`scripts/harness_start.py` today, `builder start` after the move), never bare: Claude Code with an explicit permission
  mode, `--settings` and `--setting-sources` naming only the generated settings (no user or project hooks inherited), a
  generated MCP config under `--strict-mcp-config`, the role's model, and the environment (`FICHERO_BASE_PATH` on the scratch
  path, `FICHERO_HARNESS_LOG`); Pi over RPC with its extension. The register (process group, pane or pipe, session
  directory, started-at) is a file, so a restart adopts or kills before any successor; stop is TERM then KILL after a grace.
  The engine has no worker route or action (owner 2026-11-01: the Builder is apart from the engine); `worker_process.py`,
  `routes/workers.py` and their actions are deleted in Step 1.1. Built: the start path, the jail probe, the rules check.
  Built 2026-11-01: `python -m fichero_builder run --worktree W --brief F` (`fichero_builder/run.py`), run as the worker
  user, starts through the start path and watches the newest session file under that user's `~/.claude/projects/<slug>`
  every tick; a cap or a provider refusal parks it (the pane is killed), a worker idle with the brief's DONE word in its last
  text is ended, and the end is a `cost` row; the Stop hook accepts that `DONE <sha>` line too, so it stays the worker's last
  text instead of being pushed out by a continue nudge (live run 2026-11-01). First live run 2026-11-01: a one-word brief, started as the worker user, read,
  priced and parked at a 5-cent trial cap in 30 s. Not yet: the register file. Tests:
  `fichero-builder/tests/test_dry_run.py`, `fichero-server/tests/unit/workflows/test_start_tool.py`.
- `dev-workflows.run.worker-address` [PARTIAL] (#6116) — per task, the current generation's address (pane or RPC pipe,
  process group, session directory, kind, started-at) is registered in the journal, rewritten at each handoff, cleared when
  gone; `builder ask` and a steer write a file in that generation's inbox, read by the worker at its next turn (the hook on
  Claude, the extension on Pi); no keystroke into a pane (audit 2026-11-01: `unstick.sh` pressed Enter 11,081 times, 356
  into a draft); a message to a stale generation is refused naming the current one; under 800 characters. Built: the
  inbox file and the hook read. Not yet: the register in the journal; the refusal. Test (unwritten, Step 2.2): a message reaches only the current
  generation; today `fichero-server/tests/unit/workflows/test_worker_address.py`.
- `dev-workflows.node.worker` [PARTIAL] (#6116) — kinds `claude` and `pi`; each kind has one adapter (usage from the
  session file, tool errors, the reported sha, the tool names the policy sees) and a policy that meets an unknown tool name
  **refuses**, never passes; `fake` replays recorded events through the real policy and is never started by a person.
  `claude` is an interactive session in a pane (probed: `claude -p` exits at the end of its turn). `pi` is driven over its
  RPC mode (`prompt`, `steer`, `abort` on a pipe; Pi 0.75.5, its own `rpc.md`) and carries `[policy]` in a `tool_call`
  extension that can block (Pi's `extensions.md`); the extension's crash must block, not allow, and that is tested before
  the kind is used (audit 2026-11-01: the old claim that Pi has no policy hook was false). The context read must know both
  usage shapes (Claude `input_tokens`; Pi `input` and `cacheRead`), else it reads 0 and stays silent. Order: Claude under
  Max on real issues first, then Pi on a metered provider with Sonnet so only the agent changes, then local. The per-item
  `claude -p` of `cli_agent.py` stays for one-shot clerks. Built 2026-11-01 (Step 3.1): `fichero_builder/pi_rpc.py` starts
  `pi --mode rpc --no-extensions -e fichero-builder/pi/policy.ts` in the worktree on a bytes pipe (LF is the only record
  end), correlates responses by id, queues events, and feeds the brief as the first `prompt`; the extension sends every
  `tool_call` to `python -m fichero_builder.pi_rpc policy` and runs the tool only on an exact `ALLOW` (no argv, a non-zero
  exit, other output, a timeout or its own throw all block; Pi turns a throw into the tool's error). Pi's `bash`, `write`,
  `edit`, `read`, `grep`, `find`, `ls` map onto the policy's names; any other tool name is refused. Proven live against a
  fake OpenAI-completions provider (no key): an allowed command ran and its output reached the model, a refused one was
  blocked with the reason, a crashing extension blocked the tool. `builder run --kind pi` reads the Pi session file
  under the scratch path with the same parser, delivers the 85 % word itself by `steer`, and refuses a model with no
  `cost` in Pi's models.json. Not yet: a Pi worker on a real issue. Tests: `fichero-builder/tests/test_pi_rpc.py`,
  `fichero-builder/tests/test_pi_policy_extension.py` (the live ones skip without `pi`).
- `dev-workflows.tool.check` [PARTIAL] (#6116) — the `check` tool runs the ladder from the rules file: every rung an **argv
  list** with cwd, explicit environment (scratch base path and HOME, `PYTHONPATH` relative to the tree under test, thread
  caps) and timeout; a guard runs by its own shebang; the test command is configured, not `python -m pytest`; typed
  results; refuses when blind (fewer guards than the floor). **Pinned checks** (built): the ladder runs from a pinned copy
  of `scripts/`, the hooks, the agent settings directory, the rules file, `.github/`, `.gitattributes`, `.gitmodules`,
  `pyproject.toml`, `pytest.ini` and every `conftest.py` (matched by name anywhere), laid over a scratch tree built by the
  land process from a fetched sha, never the worker's clone or its git config (the engine-owned repository is `[check].engine_repo`, owner-owned and world-readable OUTSIDE every home directory, since a tree under the owner's home is unreadable to the jailed user: first real check 2026-11-01; the scratch trees are made from it under the workroot); a diff touching a pinned
  path, **adding** a file under one (`scripts/check_*` excepted), rewriting the item's own acceptance lines, or weakening
  or deleting a test is a question, not a pass. **By path:** `red_on_base` applies to paths the rules
  file names (Python here); a Swift or contract change needs a Lead build row on the sha; docs and spec changes need
  neither. **Counters:** the same named test red twice, the diff bound tripped twice, a tool call repeated with the same
  arguments after an error, the turn or dollar cap: counted by `check` and a PostToolUse counter, and enforced (a refusal
  row and a question), not left to the model. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`. **Build** (owner 2026-11-01, built): a diff under `[check].build_paths` runs `[check].build` (a build-only compile, never a test run) in the scratch tree, one build at a time under `[check].build_lock` (a file in the owner's own state dir, taken by the owner's check process; the build itself runs as the worker user with signing off), after the contract rung; red refuses. Proven 2026-11-01: the rung's exact command (Dev Local scheme, signing off, derived data under the shared area) run as the worker user compiled the app; the Dev Embedded scheme fails at its embed-the-engine script phase, so the rung names Dev Local. The check tree is owner-made and read-only to the worker user and `Package.resolved` is tracked, so `[check].build` carries `-disableAutomaticPackageResolution`: resolution reads the file and writes nothing (a first real Swift check failed with exit 74 writing it, 2026-11-01; proven the same day: the rung's argv as the worker user over a read-only copy ended BUILD SUCCEEDED). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_rung_runs_only_for_build_paths_and_reports_red`, `::test_the_build_rung_never_resolves_packages_so_a_read_only_check_tree_builds`. **Check row** (built 2026-11-01): `builder check` appends a `check` row (repo, since, the head's full sha, ok, failed, maintainer) to the owner's journal, and `builder land` refuses a head with no green row there (Step 2.1: check before review and land; the row lives in the owner's journal, never the worker's, so a worker cannot forge one). `builder run` journals under `[jail].workroot/state` by default so the owner reads the worker's rows without sudo. A red rung's tail keeps pytest's failure section whatever follows it (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_red_pytest_tail_keeps_the_failure_when_warnings_follow_it`). A test file owes no red only when every commit touching it is test-only and carries `Already built: #N <path>::<test>` naming a file in that commit; the worker writes the message, so a line on a commit that changes source earns nothing; such a test must pass on base, which is what "already built" claims; a range that changes source (under `[check].red_paths`) with every changed test excused is refused, so another test must go red for that change, though the check cannot tell that this test is the one that proves it; and the excused test still runs in the green run (tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_already_built_exempts_only_a_test_only_commit_that_names_its_test`, `::test_already_built_must_pass_on_base_so_a_source_commit_before_it_cannot_skip_the_red`, `::test_a_source_change_whose_every_test_is_excused_is_refused`, `::test_a_source_change_with_another_test_that_goes_red_may_also_carry_an_excused_one`, `::test_an_already_built_test_that_goes_red_on_head_is_refused_by_the_green_run`). A pytest rung runs with a throwaway pycache prefix, because `python -I` ignores `PYTHONDONTWRITEBYTECODE` and pytest's rewrite cache keys on mtime seconds and size, so a same-size edit in the same second would run the previous rung's bytecode (test `::test_a_commit_that_says_already_built_owes_no_red_on_base_but_its_test_still_runs_green`). The rules checks accept `[queue]`, `[triage]`, `[jail].code_map` and `[land].pinned_dir` before the code that reads them, because a check in pieces overlays the batch tip's `harness.toml` on each piece; a misspelt name still refuses (test `fichero-builder/tests/test_main.py::test_the_rules_checks_accept_the_settings_later_commits_add_and_still_refuse_a_misspelt_one`). The reviewer reads every commit of the range whole, never truncated. Its cap is 40% of the reviewer model's window (`[models].reviewer` `context` in `harness.toml`, 200000 tokens when absent) at 3.5 bytes a token (`land_tool.review_cap`); a range over it is reviewed in consecutive commit groups that each fit, and the READY verdict for the whole range is written only when every group's last line is READY; a single commit over the cap is refused (`land_tool.review_groups`, `scripts/harness_review.py`; tests `fichero-server/tests/unit/workflows/test_land_tool.py::test_the_review_cap_refuses_one_byte_past_it_and_the_default_takes_a_step_a_big_worker_writes`, `::test_a_range_over_the_cap_splits_into_consecutive_groups_that_each_fit_and_lose_nothing`, `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_range_over_the_cap_is_reviewed_group_by_group_and_ready_only_if_every_group_is`, `::test_one_group_not_ready_writes_no_verdict`, `::test_a_diff_over_the_cap_is_refused_not_truncated`). Every group runs even after one is not READY, so all findings go back at once; each group's prompt says the batch lands whole at its head, names every file the whole batch changes, and makes a finding the head fixes (a red mid-range, a spec line a later commit adds) a note, not a blocker (2026-11-02; test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_group_not_ready_still_lets_every_later_group_run_and_each_prompt_frames_the_whole_batch`). **Delta review** (manager 2026-11-02): each group's range and verdict (a blocking reply's text with it) go into `<verdicts>.groups` under the base; when the last run's head is an ancestor of this head, its READY groups are kept and only last-head..head is reviewed, its prompt naming the kept groups and quoting what blocked before for the reviewer to check at the head; a READY delta writes the one verdict for the whole range, a blocked one carries the earlier findings forward. A rewritten head (the last one no longer its ancestor), no record or `--full` reviews the whole range (test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_rerun_after_a_fix_reviews_only_the_new_commits_and_keeps_the_ready_groups`). The ready rung runs `scripts/lane_ready_check.sh --no-guards HEAD`: the guards rung runs every guard from the pinned copy, so the ready check's own copy of them (60 s each) only doubled the time and refused a green batch on a timeout under load (2026-11-02; a bare run still runs them; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_ready_check_skips_its_guard_copy_with_no_guards_because_the_guards_rung_runs_them`). `[check].since_guards` maps a guard to a path prefix: a diff under the prefix runs it in the scratch tree with `--since <base>`, its question about this range only; Fichero runs the SwiftLint ratchet so for `fichero/` (#6318; swiftlint is a copy in the worker's bin; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_since_guard_runs_with_the_range_base_only_when_the_diff_touches_its_prefix`; not yet: a real Swift item through it). Its lint of the changed files is a ratchet (manager 2026-11-02: a 997-line store cut to 919 was refused for file_length it already broke): per touched file, `fichero-builder/fichero_builder/lint.py` counts ruff's and swiftlint's findings by rule on base (the base copy on stdin, the repo's config) and on head, and refuses only a rule whose count grows, or any finding in a new file (test `fichero-builder/tests/test_lint.py`); a linter that crashes, or prints nothing where it owes JSON, is a refusal (`lint.LintError`), never zero findings, and `fichero-builder/fichero_builder/lint.py` is a pinned path run under `python -I`, so a batch never edits the copy that judges it (test `::test_a_linter_that_fails_or_prints_nothing_is_a_refusal_never_zero_findings`). An empty range (since equals head) is refused, never judged green: a landing branch that never received its commit passed once (2026-11-02). Test: `fichero-builder/tests/test_main.py`. **Whole tests** (built 2026-11-02): `[check.whole_tests]` maps a path prefix to a tests directory; a diff under the prefix (a deletion too) runs that directory whole, not only the changed test files (a Builder source change broke an old Builder test its own new test never imported). Each listed directory runs as its own pytest from its package (the directory's parent): `-c <package>/pyproject.toml` when it exists (every pytest config name, `pyproject.toml`, `pytest.ini`, `.pytest.ini`, `pytest.toml`, `.pytest.toml`, `tox.ini`, `setup.cfg`, is a pinned name anywhere in the tree, so a worker cannot add one that changes what either run collects), the package first on the path, so its `from tests import x` finds its own `tests` and not the engine's; the engine-shaped run keeps only the changed test files; both must be green, and the row records both commands and tails (`runs`). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_change_under_a_whole_tests_prefix_runs_that_tests_dir_whole_in_the_green_run`. **Maintainer batch** (built 2026-11-02): `builder check --maintainer` records a changed pinned file in the pinned-checks row instead of refusing, so a harness change is judged by the same ladder (pointed at its own rules with `--pinned`); only a changed or deleted pinned check file is recorded; a symlink, a `sitecustomize`/`.pth` file, the agent settings directory, a new file under a pinned path, a weakened test and a rewritten acceptance still refuse. A maintainer batch is not held to the diff bound (`[check].max_files`/`max_lines`): its diff-bound row shows the size and stays green; a jailed worker's range keeps the bound. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_maintainer_batch_records_the_pinned_change_and_runs_the_rest`, `::test_a_maintainer_batch_skips_the_diff_bound_and_a_worker_range_keeps_it`.
  row and a question), not left to the model. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`. **Build** (owner 2026-11-01, built): a diff under `[check].build_paths` runs `[check].build` (a build-only compile, never a test run) in the scratch tree, one build at a time under `[check].build_lock` (a file in the owner's own state dir, taken by the owner's check process; the build itself runs as the worker user with signing off), after the contract rung; red refuses. Proven 2026-11-01: the rung's exact command (Dev Local scheme, signing off, derived data under the shared area) run as the worker user compiled the app; the Dev Embedded scheme fails at its embed-the-engine script phase, so the rung names Dev Local. The check tree is owner-made and read-only to the worker user and `Package.resolved` is tracked, so `[check].build` carries `-disableAutomaticPackageResolution`: resolution reads the file and writes nothing (a first real Swift check failed with exit 74 writing it, 2026-11-01; proven the same day: the rung's argv as the worker user over a read-only copy ended BUILD SUCCEEDED). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_rung_runs_only_for_build_paths_and_reports_red`, `::test_the_build_rung_never_resolves_packages_so_a_read_only_check_tree_builds`. **Check row** (built 2026-11-01): `builder check` appends a `check` row (repo, since, the head's full sha, ok, failed, maintainer) to the owner's journal, and `builder land` refuses a head with no green row there (Step 2.1: check before review and land; the row lives in the owner's journal, never the worker's, so a worker cannot forge one). `builder run` journals under `[jail].workroot/state` by default so the owner reads the worker's rows without sudo. A red rung's tail keeps pytest's failure section whatever follows it (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_red_pytest_tail_keeps_the_failure_when_warnings_follow_it`). A test file owes no red only when every commit touching it is test-only and carries `Already built: #N <path>::<test>` naming a file in that commit; the worker writes the message, so a line on a commit that changes source earns nothing; such a test must pass on base, which is what "already built" claims; a range that changes source (under `[check].red_paths`) with every changed test excused is refused, so another test must go red for that change, though the check cannot tell that this test is the one that proves it; and the excused test still runs in the green run (tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_already_built_exempts_only_a_test_only_commit_that_names_its_test`, `::test_already_built_must_pass_on_base_so_a_source_commit_before_it_cannot_skip_the_red`, `::test_a_source_change_whose_every_test_is_excused_is_refused`, `::test_a_source_change_with_another_test_that_goes_red_may_also_carry_an_excused_one`, `::test_an_already_built_test_that_goes_red_on_head_is_refused_by_the_green_run`). A pytest rung runs with a throwaway pycache prefix, because `python -I` ignores `PYTHONDONTWRITEBYTECODE` and pytest's rewrite cache keys on mtime seconds and size, so a same-size edit in the same second would run the previous rung's bytecode (test `::test_a_commit_that_says_already_built_owes_no_red_on_base_but_its_test_still_runs_green`). The rules checks accept `[queue]`, `[triage]`, `[jail].code_map` and `[land].pinned_dir` before the code that reads them, because a check in pieces overlays the batch tip's `harness.toml` on each piece; a misspelt name still refuses (test `fichero-builder/tests/test_main.py::test_the_rules_checks_accept_the_settings_later_commits_add_and_still_refuse_a_misspelt_one`). The reviewer reads every commit of the range whole, never truncated. Its cap is 40% of the reviewer model's window (`[models].reviewer` `context` in `harness.toml`, 200000 tokens when absent) at 3.5 bytes a token (`land_tool.review_cap`); a range over it is reviewed in consecutive commit groups that each fit, and the READY verdict for the whole range is written only when every group's last line is READY; a single commit over the cap is refused (`land_tool.review_groups`, `scripts/harness_review.py`; tests `fichero-server/tests/unit/workflows/test_land_tool.py::test_the_review_cap_refuses_one_byte_past_it_and_the_default_takes_a_step_a_big_worker_writes`, `::test_a_range_over_the_cap_splits_into_consecutive_groups_that_each_fit_and_lose_nothing`, `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_range_over_the_cap_is_reviewed_group_by_group_and_ready_only_if_every_group_is`, `::test_one_group_not_ready_writes_no_verdict`, `::test_a_diff_over_the_cap_is_refused_not_truncated`). Every group runs even after one is not READY, so all findings go back at once; each group's prompt says the batch lands whole at its head, names every file the whole batch changes, and makes a finding the head fixes (a red mid-range, a spec line a later commit adds) a note, not a blocker (2026-11-02; test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_group_not_ready_still_lets_every_later_group_run_and_each_prompt_frames_the_whole_batch`). **Delta review** (manager 2026-11-02): each group's range and verdict (a blocking reply's text with it) go into `<verdicts>.groups` under the base; when the last run's head is an ancestor of this head, its READY groups are kept and only last-head..head is reviewed, its prompt naming the kept groups and quoting what blocked before for the reviewer to check at the head; a READY delta writes the one verdict for the whole range, a blocked one carries the earlier findings forward. A rewritten head (the last one no longer its ancestor), no record or `--full` reviews the whole range (test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_rerun_after_a_fix_reviews_only_the_new_commits_and_keeps_the_ready_groups`). **Remote runner** (manager 2026-11-02, optional): `[check].remote = "host:dir"` sends the engine pytest runs (the changed files, the whole-tests dirs, red-on-base's base runs) over ssh: the check tree's files (`git ls-files -co`, never `.git`) are shipped once per tree into a fresh `dir/run-*`, the same command runs there with `[check].remote_python` (default `dir/venv/bin/python`) and the rung's env, and the copies are removed when the ladder ends. Guards, ready and build stay here. An unreachable runner (ssh's own exit 255, or the copy failing) is one `alert` row per ladder (step `remote`), and the tests run here: progress never waits on that machine. The remote runs tests unjailed as the ssh user, so it holds nothing but its gate dir (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_remote_runner_runs_the_engine_pytest_there_and_an_unreachable_one_alerts_and_runs_it_here`; not yet: a real run on the iMac). The ready rung runs `scripts/lane_ready_check.sh --no-guards HEAD`: the guards rung runs every guard from the pinned copy, so the ready check's own copy of them (60 s each) only doubled the time and refused a green batch on a timeout under load (2026-11-02; a bare run still runs them; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_ready_check_skips_its_guard_copy_with_no_guards_because_the_guards_rung_runs_them`). `[check].since_guards` maps a guard to a path prefix: a diff under the prefix runs it in the scratch tree with `--since <base>`, its question about this range only; Fichero runs the SwiftLint ratchet so for `fichero/` (#6318; swiftlint is a copy in the worker's bin; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_since_guard_runs_with_the_range_base_only_when_the_diff_touches_its_prefix`; not yet: a real Swift item through it). An empty range (since equals head) is refused, never judged green: a landing branch that never received its commit passed once (2026-11-02). Test: `fichero-builder/tests/test_main.py`. **Whole tests** (built 2026-11-02): `[check.whole_tests]` maps a path prefix to a tests directory; a diff under the prefix (a deletion too) runs that directory whole, not only the changed test files (a Builder source change broke an old Builder test its own new test never imported). Each listed directory runs as its own pytest from its package (the directory's parent): `-c <package>/pyproject.toml` when it exists (every pytest config name, `pyproject.toml`, `pytest.ini`, `.pytest.ini`, `pytest.toml`, `.pytest.toml`, `tox.ini`, `setup.cfg`, is a pinned name anywhere in the tree, so a worker cannot add one that changes what either run collects), the package first on the path, so its `from tests import x` finds its own `tests` and not the engine's; the engine-shaped run keeps only the changed test files; both must be green, and the row records both commands and tails (`runs`). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_change_under_a_whole_tests_prefix_runs_that_tests_dir_whole_in_the_green_run`. **Maintainer batch** (built 2026-11-02): `builder check --maintainer` records a changed pinned file in the pinned-checks row instead of refusing, so a harness change is judged by the same ladder (pointed at its own rules with `--pinned`); only a changed or deleted pinned check file is recorded; a symlink, a `sitecustomize`/`.pth` file, the agent settings directory, a new file under a pinned path, a weakened test and a rewritten acceptance still refuse. A maintainer batch is not held to the diff bound (`[check].max_files`/`max_lines`): its diff-bound row shows the size and stays green; a jailed worker's range keeps the bound. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_maintainer_batch_records_the_pinned_change_and_runs_the_rest`, `::test_a_maintainer_batch_skips_the_diff_bound_and_a_worker_range_keeps_it`.
  row and a question), not left to the model. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`. **Build** (owner 2026-11-01, built): a diff under `[check].build_paths` runs `[check].build` (a build-only compile, never a test run) in the scratch tree, one build at a time under `[check].build_lock` (a file in the owner's own state dir, taken by the owner's check process; the build itself runs as the worker user with signing off), after the contract rung; red refuses. Proven 2026-11-01: the rung's exact command (Dev Local scheme, signing off, derived data under the shared area) run as the worker user compiled the app; the Dev Embedded scheme fails at its embed-the-engine script phase, so the rung names Dev Local. The check tree is owner-made and read-only to the worker user and `Package.resolved` is tracked, so `[check].build` carries `-disableAutomaticPackageResolution`: resolution reads the file and writes nothing (a first real Swift check failed with exit 74 writing it, 2026-11-01; proven the same day: the rung's argv as the worker user over a read-only copy ended BUILD SUCCEEDED). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_rung_runs_only_for_build_paths_and_reports_red`, `::test_the_build_rung_never_resolves_packages_so_a_read_only_check_tree_builds`. **Check row** (built 2026-11-01): `builder check` appends a `check` row (repo, since, the head's full sha, ok, failed, maintainer) to the owner's journal, and `builder land` refuses a head with no green row there (Step 2.1: check before review and land; the row lives in the owner's journal, never the worker's, so a worker cannot forge one). `builder run` journals under `[jail].workroot/state` by default so the owner reads the worker's rows without sudo. A red rung's tail keeps pytest's failure section whatever follows it (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_red_pytest_tail_keeps_the_failure_when_warnings_follow_it`). A test file owes no red only when every commit touching it is test-only and carries `Already built: #N <path>::<test>` naming a file in that commit; the worker writes the message, so a line on a commit that changes source earns nothing; such a test must pass on base, which is what "already built" claims; a range that changes source (under `[check].red_paths`) with every changed test excused is refused, so another test must go red for that change, though the check cannot tell that this test is the one that proves it; and the excused test still runs in the green run (tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_already_built_exempts_only_a_test_only_commit_that_names_its_test`, `::test_already_built_must_pass_on_base_so_a_source_commit_before_it_cannot_skip_the_red`, `::test_a_source_change_whose_every_test_is_excused_is_refused`, `::test_a_source_change_with_another_test_that_goes_red_may_also_carry_an_excused_one`, `::test_an_already_built_test_that_goes_red_on_head_is_refused_by_the_green_run`). A pytest rung runs with a throwaway pycache prefix, because `python -I` ignores `PYTHONDONTWRITEBYTECODE` and pytest's rewrite cache keys on mtime seconds and size, so a same-size edit in the same second would run the previous rung's bytecode (test `::test_a_commit_that_says_already_built_owes_no_red_on_base_but_its_test_still_runs_green`). The rules checks accept `[queue]`, `[triage]`, `[jail].code_map` and `[land].pinned_dir` before the code that reads them, because a check in pieces overlays the batch tip's `harness.toml` on each piece; a misspelt name still refuses (test `fichero-builder/tests/test_main.py::test_the_rules_checks_accept_the_settings_later_commits_add_and_still_refuse_a_misspelt_one`). The reviewer reads every commit of the range whole, never truncated. Its cap is 40% of the reviewer model's window (`[models].reviewer` `context` in `harness.toml`, 200000 tokens when absent) at 3.5 bytes a token (`land_tool.review_cap`); a range over it is reviewed in consecutive commit groups that each fit, and the READY verdict for the whole range is written only when every group's last line is READY; a single commit over the cap is refused (`land_tool.review_groups`, `scripts/harness_review.py`; tests `fichero-server/tests/unit/workflows/test_land_tool.py::test_the_review_cap_refuses_one_byte_past_it_and_the_default_takes_a_step_a_big_worker_writes`, `::test_a_range_over_the_cap_splits_into_consecutive_groups_that_each_fit_and_lose_nothing`, `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_range_over_the_cap_is_reviewed_group_by_group_and_ready_only_if_every_group_is`, `::test_one_group_not_ready_writes_no_verdict`, `::test_a_diff_over_the_cap_is_refused_not_truncated`). Every group runs even after one is not READY, so all findings go back at once; each group's prompt says the batch lands whole at its head, names every file the whole batch changes, and makes a finding the head fixes (a red mid-range, a spec line a later commit adds) a note, not a blocker (2026-11-02; test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_group_not_ready_still_lets_every_later_group_run_and_each_prompt_frames_the_whole_batch`). **Delta review** (manager 2026-11-02): each group's range and verdict (a blocking reply's text with it) go into `<verdicts>.groups` under the base; when the last run's head is an ancestor of this head, its READY groups are kept and only last-head..head is reviewed, its prompt naming the kept groups and quoting what blocked before for the reviewer to check at the head; a READY delta writes the one verdict for the whole range, a blocked one carries the earlier findings forward. A rewritten head (the last one no longer its ancestor), no record or `--full` reviews the whole range (test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_rerun_after_a_fix_reviews_only_the_new_commits_and_keeps_the_ready_groups`). **Remote runner** (manager 2026-11-02, optional): `[check].remote = "host:dir"` sends the engine pytest runs (the changed files, the whole-tests dirs, red-on-base's base runs) over ssh: the check tree's files (`git ls-files -co`, never `.git`) are shipped once per tree into a fresh `dir/run-*`, the same command runs there with `[check].remote_python` (default `dir/venv/bin/python`) and the rung's env, and the copies are removed when the ladder ends. Guards, ready and build stay here. An unreachable runner (ssh's own exit 255, or the copy failing) is one `alert` row per ladder (step `remote`), and the tests run here: progress never waits on that machine. The remote runs tests unjailed as the ssh user, so it holds nothing but its gate dir (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_remote_runner_runs_the_engine_pytest_there_and_an_unreachable_one_alerts_and_runs_it_here`; not yet: a real run on the iMac). The ready rung runs `scripts/lane_ready_check.sh --no-guards HEAD`: the guards rung runs every guard from the pinned copy, so the ready check's own copy of them (60 s each) only doubled the time and refused a green batch on a timeout under load (2026-11-02; a bare run still runs them; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_ready_check_skips_its_guard_copy_with_no_guards_because_the_guards_rung_runs_them`). Its lint of the changed files is a ratchet (manager 2026-11-02: a 997-line store cut to 919 was refused for file_length it already broke): per touched file, `fichero-builder/fichero_builder/lint.py` counts ruff's and swiftlint's findings by rule on base (the base copy on stdin, the repo's config) and on head, and refuses only a rule whose count grows, or any finding in a new file (test `fichero-builder/tests/test_lint.py`). `[check].since_guards` maps a guard to a path prefix: a diff under the prefix runs it in the scratch tree with `--since <base>`, its question about this range only; Fichero runs the SwiftLint ratchet so for `fichero/` (#6318; swiftlint is a copy in the worker's bin; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_since_guard_runs_with_the_range_base_only_when_the_diff_touches_its_prefix`; not yet: a real Swift item through it). An empty range (since equals head) is refused, never judged green: a landing branch that never received its commit passed once (2026-11-02). Test: `fichero-builder/tests/test_main.py`. **Whole tests** (built 2026-11-02): `[check.whole_tests]` maps a path prefix to a tests directory; a diff under the prefix (a deletion too) runs that directory whole, not only the changed test files (a Builder source change broke an old Builder test its own new test never imported). Each listed directory runs as its own pytest from its package (the directory's parent): `-c <package>/pyproject.toml` when it exists (every pytest config name, `pyproject.toml`, `pytest.ini`, `.pytest.ini`, `pytest.toml`, `.pytest.toml`, `tox.ini`, `setup.cfg`, is a pinned name anywhere in the tree, so a worker cannot add one that changes what either run collects), the package first on the path, so its `from tests import x` finds its own `tests` and not the engine's; the engine-shaped run keeps only the changed test files; both must be green, and the row records both commands and tails (`runs`). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_change_under_a_whole_tests_prefix_runs_that_tests_dir_whole_in_the_green_run`. **Maintainer batch** (built 2026-11-02): `builder check --maintainer` records a changed pinned file in the pinned-checks row instead of refusing, so a harness change is judged by the same ladder (pointed at its own rules with `--pinned`); only a changed or deleted pinned check file is recorded; a symlink, a `sitecustomize`/`.pth` file, the agent settings directory, a new file under a pinned path, a weakened test and a rewritten acceptance still refuse. A maintainer batch is not held to the diff bound (`[check].max_files`/`max_lines`): its diff-bound row shows the size and stays green; a jailed worker's range keeps the bound. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_maintainer_batch_records_the_pinned_change_and_runs_the_rest`, `::test_a_maintainer_batch_skips_the_diff_bound_and_a_worker_range_keeps_it`.
- `dev-workflows.tool.milestone` [PARTIAL] (#6116; owner 2026-11-01) — `builder milestone <name>` reads the milestone's open
  issues (`gh`), places each under the build-order step of the spec that names it (the issue body's step line, or the
  milestone's spec by its `> Milestone:` line), orders steps by `Depends on`, and prints one cluster brief per step
  through the brief tool; an issue under no step, or a step whose dependency is still open, is a **question**, never a
  guess; nothing is picked by hand. Built 2026-11-01: `fichero_builder/milestone.py` and `builder milestone <name>
  --spec FILE --out DIR`: `gh issue list --milestone`, the step from the issue title (`Step 1.3`) or a `Step: 1.3`
  body line, the build order from the spec guard's own parser, one brief per step through the brief tool, questions on
  stderr and exit 2 when any. Not yet: `builder steps` files issues in that title shape. Test:
  `fichero-builder/tests/test_milestone_verb.py` (a fake `gh`: three issues over two dependent steps give two briefs
  and two questions). **Rules in the brief** (built 2026-11-01): the project's standing worker rules (one pytest at a time
  with its own `--basetemp` under the workroot, `PYTHONPATH=src`, never xcodebuild, author Claude, the trailers) are
  `[brief].rules` in `harness.toml`, the third line of every cluster brief, with any `#N` filled from the cluster's issues
  (the project's own rules have none), so no brief needs a hand edit. The brief names the issues the step owes and tells the worker to put `Fixes #N` on the
  commit that finishes each and `Part of #N` on any before it (test `fichero-server/tests/unit/workflows/test_brief_tool.py::test_the_brief_names_what_the_step_owes_and_the_line_that_closes_each`). Tests: `fichero-server/tests/unit/workflows/test_brief_tool.py::test_the_rules_are_the_briefs_third_line_with_part_of_filled_from_the_clusters_issues`,
  `::test_the_projects_standing_worker_rules_are_in_harness_toml_so_no_brief_needs_a_hand_edit`.
  **Waits and the step's map** (built 2026-11-01): a step whose dependency still has open issues is a brief and, with
  `--enqueue`, a queued step of the lane, and every wait is said in ONE question line; every step brief opens with a map:
  the spec's path, the directories its design section names that exist in the repo, and only the files that the step's
  section, its behaviour lines and its issues' Where/Test lines name, plus the Python files that import them, each with its
  outline, from the code map when the repo is indexed (a file the tree lacks is dropped), else read by regex; a named file
  the step will write is shown as its existing directory; never `agent-work/` or `LICENSE` (real use 2026-11-02: a search by
  the step's words listed both, and openapi.json). `--repo-dir` without a `harness.toml` refuses with a `milestone` row.
  Tests: `::test_the_where_list_names_only_what_the_step_its_behaviours_and_its_issues_name_plus_importers`,
  `::test_a_repo_dir_that_is_not_a_checkout_refuses_with_a_row_not_a_traceback`, `fichero-builder/tests/test_milestone_verb.py::test_plan_orders_clusters_and_asks_instead_of_guessing`,
  `::test_the_where_list_is_the_spec_the_designs_directory_and_the_files_found_by_the_steps_words_with_their_outlines`,
  `::test_the_where_list_uses_the_code_map_when_the_repo_is_indexed_and_drops_what_the_tree_lacks`,
  `::test_a_server_that_fails_or_finds_nothing_falls_back_to_grep`.
  **Step from the heading** (built 2026-11-01): a build-order heading that names an issue (`#### Step 1.3 — title (#N)`) places it too, for a spec written before `builder steps` (test `fichero-builder/tests/test_milestone_verb.py::test_a_step_heading_that_names_an_issue_places_it`).
  **Step from the label** (built 2026-11-01): the verb lists issues with their labels and reads the step from `step:N.M`
  first; the title shape and the `Step: N.M` body line are the fallback for an issue with no step label. Test:
  `fichero-builder/tests/test_milestone_verb.py::test_the_step_label_is_read_first_and_the_title_shape_only_for_an_issue_with_no_step_label`.
- `dev-workflows.tool.work` [PARTIAL] (#6116) — `builder work --brief FILE --worktree W --name N --issues N...` is the build,
  check, review and land chain as one process: `builder run`, then on end `done` the worktree's commits as patches
  (`git format-patch` over `origin/<[land].branch>` into `<state>/patches-<name>/`), the branch fetched into
  `[check].engine_repo` as `work-<name>` from a bundle the owner names (never by the worker's branch name; the worker side, `builder run`, `format-patch` and the bundle, runs through `sudo -n -H -u <jail user>`), the check over base..head from the pinned copy (`--pinned` required), the
  review script with the check's JSON as `--ladder` and `[models].reviewer`, then the land gate, whose push line it prints;
  it never pushes. A parked or gone worker, a red check, a NOT READY review or a refused land stops it with
  `QUESTION: <why>` and exit 2; every step is a journal row (event `work`: step, ok, detail). **Built** (2026-11-01), **no real run has completed yet**: a real test covers
  the patch count on a scratch git repo, the bundle fetch with a branch named like an option attack (nothing runs), the
  `sudo -n -H -u <user> sh -c "cd <workroot> && ..."` argv, and the end read from the shared journal; the order, the
  stops and the journal rows are tested with the steps replaced by fakes, and the sudo boundary with a fake runner.
  Nothing has yet run the real sudo, a real worker, the real check, review and land through this verb; the first real
  run is Step 2.2's. Test:
  `fichero-builder/tests/test_work_verb.py::test_the_chain_runs_in_order_with_the_roles_models_prints_the_push_and_never_pushes`.
  **Pinned copy** (built 2026-11-01): with no `--pinned`, the verb makes `[land].pinned_dir/pinned-<base7>` (an absolute
  path; the base is `--base` or the `(base <sha>)` of the brief's first line) as a worktree of `[check].engine_repo` on a
  `pinned-<base7>` branch when it is missing, finds it otherwise, and reads the rules from that copy; a brief with no base
  line is a `QUESTION:`. Test: `fichero-builder/tests/test_work_verb.py::test_work_without_pinned_makes_the_pinned_worktree_for_the_briefs_base_and_reads_the_rules_from_it`.
  **A missing worktree** (built 2026-11-01): `builder work` and the queue's start make the worktree when its path is missing, as the jail user, from `<workroot>/root` on a new branch (the name for `work`, `lane-<id>` for a lane), at `--base` when given, else origin's head of the land branch; a failure is a `QUESTION:`, and an existing tree costs no sudo (tests `fichero-builder/tests/test_work_verb.py::test_run_makes_a_missing_worktree_as_the_jail_user_from_its_clone_and_leaves_an_existing_one`, `::test_do_run_refuses_with_the_reason_when_the_worktree_cannot_be_made`).
  **Two lanes in turn** (built 2026-11-01): after `run` and before `patches`, a `rebase` step as the worker fetches origin
  and rebases the worktree onto `origin/<[land].branch>`, so a lane that lands after another is checked on the range that
  will land; a conflict aborts the rebase and stops with a `QUESTION:` row, never resolved here. A landing makes its new pinned copy
  under the `ladder` lock and the chain finds its copy again inside that lock, so a landing never removes the copy another lane's check is reading (tests
  `fichero-builder/tests/test_landed_verb.py::test_making_the_new_pinned_copy_waits_for_a_running_ladder`, `fichero-builder/tests/test_work_verb.py::test_the_chain_finds_its_pinned_copy_again_inside_the_ladder_lock`). The `land` step and
  `builder land` check `--log` first (a path it cannot append to refuses before anything runs, here and in the hand-run
  ladder; test `fichero-builder/tests/test_main.py::test_land_refuses_a_log_it_cannot_write_before_anything_with_a_row`), and run the verdict and the boundary only once a green check row over exactly `<[land].branch>..<head>` exists (`land_tool.gate`; test `fichero-builder/tests/test_main.py::test_land_refuses_a_green_row_that_does_not_cover_the_range`);
  the ladder is not run a second time (it doubled the pytest load against the one-pytest rule); `scripts/harness_land.py`
  keeps the ladder for a hand run. Tests: `fichero-builder/tests/test_work_verb.py::test_rebase_puts_the_worktree_on_top_of_the_branch_another_lane_moved`,
  `::test_a_rebase_conflict_is_aborted_and_said_never_resolved`,
  `fichero-builder/tests/test_main.py::test_land_with_a_green_check_row_runs_the_verdict_and_boundary_only_never_the_ladder_again`.
- `dev-workflows.tool.spec` [PARTIAL] (#6116) (owner 2026-11-01) — `builder spec <issue>` starts the **spec-writer** role from
  `[models]` as a worker whose brief is the spec template, the issue and the spec guards' rules; the result is one spec
  file under `spec_dir` on a branch with `> **Status: PROPOSED**`; the guards run on it; the owner approves by editing
  the status line, and nothing in the spec is built before that. **Built** (2026-11-01): `builder spec --issue N --out FILE [--gh gh]` writes the brief (the spec template, the issue through the brief tool, the guards' rules in words, the instruction to write ONE spec with `> **Status: PROPOSED**`) and prints the `[models].spec-writer` model; it does not start the worker, `builder run` does (the spec's first wording said the verb starts it; the verb stays a brief writer so one start path exists). A missing role model is a `QUESTION:` (exit 2). The steps verb refuses a PROPOSED spec. Test: `fichero-builder/tests/test_spec_verb.py::test_the_brief_names_the_template_the_issue_the_guards_and_the_proposed_status`.
- `dev-workflows.tool.steps` [PARTIAL] (#6116) (owner 2026-11-01) — `builder steps <spec>` reads an APPROVED spec's build order
  and files one issue per step under the spec's milestone (`gh`): the step's title, behaviours, tests, size and
  `Depends on` as issue links in the body; a second run updates the step's issue rather than filing another (the body
  carries the step id); every write is a journal row. **Built** (2026-11-01): `builder steps --spec FILE [--gh gh] [--dry-run]` titles each issue `<milestone> Step N.M: <title>`, finds it again by that exact title
  (it lists the milestone's issues with `gh issue list --milestone` and compares exact titles; no search), edits it on a second run, writes `Depends on: #N` once those issues exist, and refuses a PROPOSED spec; `--dry-run` writes nothing.
  Test: `fichero-builder/tests/test_steps_verb.py::test_a_second_run_updates_by_title_and_files_nothing_new`. **The step key is
  (milestone, `step:N.M`)** (built 2026-11-01; owner: the milestone is the spec, no spec label): every step issue carries
  `step:N.M` and `type:feature` in the spec's milestone; the verb lists the repo's labels once, creates only the absent
  step labels (`gh label create`, before any issue write) and applies them on create and on update; existing issues' other
  labels are left alone. Test: `fichero-builder/tests/test_steps_verb.py::test_every_step_issue_carries_the_step_label_and_type_feature_never_a_spec_label`.
- `dev-workflows.tool.landed` [PARTIAL] (#6116) — `builder landed <sha> [--push] [--no-issues] [--keep-worktree]` (`--verdicts` defaults to the `verdicts*.json` under `--state` that holds a READY for the range; test `fichero-builder/tests/test_landed_verb.py::test_without_verdicts_the_store_under_state_that_holds_the_ready_is_used`): after a verdict the maintainer
  runs one command instead of fifteen. It refuses a journal that is not this user's alone to write (it allows the push and
  names what `scratch` removes) and a rules file the land gate would refuse, then refuses unless the verdict store has READY
  for the sha, the journal has a green check row over exactly `<[land].branch>..<sha>` (a `--maintainer` row counts, because a
  person typed the flag, and the row says the landing was one), the sha is a fast-forward of `origin/<[land].branch>` in
  `[check].engine_repo` and no added line or message crosses `[land].boundary`. A rerun after a red step past the refresh
  does the steps left, from the first run's base (test `fichero-builder/tests/test_landed_verb.py::test_a_red_step_after_the_refresh_can_be_run_again_and_finishes_the_rest`);
  with `--push`
  (the maintainer typed it; nothing else sets it) it pushes `<sha>:refs/heads/<branch>`; then it refuses unless the sha is on `origin/<branch>` (a hand push counts), so
  an unpushed sha pins, removes and closes nothing and a `--push` rerun pushes (test `fichero-builder/tests/test_landed_verb.py::test_without_push_an_unpushed_sha_is_refused_before_anything_moves_and_a_push_rerun_finishes`); then it refreshes the engine
  repo's local branch, makes the `pinned-<sha7>` branch and worktree under `[land].pinned_dir` (absolute, else refused
  before anything moves) and removes the previous pinned pair, fast-forwards the jail root as the jail user (from `/`: the owner's cwd is unreadable to it; a local file equal to what lands is
  dropped first, any other local edit refuses the merge and stays; test `fichero-builder/tests/test_landed_verb.py::test_the_jail_root_drops_a_local_edit_the_target_already_has_and_refuses_a_real_one`), sweeps the jail
  root's worktrees (#6204: one is removed only when its HEAD is on `origin/<branch>`, it has been idle `[land].worktree_grace_hours`, default 36,
  by the newer of its index's mtime and its HEAD's commit time, and no queue lane with steps left holds it; its uncommitted and untracked
  files go to a patch under `<workroot>/.removed/` first, kept even if the removal fails; `git worktree remove`, never rm; the branch stays;
  tests `fichero-builder/tests/test_landed_verb.py::test_scratch_worktrees_of_the_work_rows_for_that_sha_are_removed_as_the_worker`,
  `::test_the_sweep_keeps_unlanded_live_and_recently_used_worktrees_and_a_longer_grace_keeps_them_all`; `--keep-worktree`, which the queue passes, still names the lane's worktree as kept;
  test `fichero-builder/tests/test_landed_verb.py::test_keep_worktree_leaves_a_lanes_worktree_for_its_open_session`), and, only once the sha is on `origin/<branch>` (the on-origin step has held it to that), updates the cited issues through `gh`:
  one comment per issue per landing naming every citing commit (sha7, subject, the test files it touches); `Fixes`/`Closes
  #N` closes with it, `Part of #N` stays open, `Already built: #N <test>` comments the proving test and labels
  needs-your-test; a behaviour id on a `Behaviour: <id>` trailer line of a commit (an id the message only mentions does not count) gets its spec line's open tag set to [OK] with the commit's
  test files named when the line names none (a `spec-ok` row each; the owner commits the spec edit with the next batch; a spec
  file it would edit that has uncommitted changes refuses before the push);
  `--no-issues` skips both. A `Fixes` or `Closes` line may name several issues. The `done` row's `left_open` names every cited issue with no
  such line, and the verb prints it: a row, not a close. Every step is a journal row (event `landed`); a red step stops the rest with exit 1.
  **Built** 2026-11-01: `fichero_builder/landed.py`. Tests:
  `fichero-builder/tests/test_landed_verb.py::test_the_happy_path_without_push_pins_and_refreshes_but_leaves_origin_alone`,
  `::test_refuses_a_sha_that_is_not_a_fast_forward_of_origin`, `::test_the_cited_issues_are_closed_or_commented_through_gh`,
  `::test_a_range_over_the_boundary_is_not_pushed`, `::test_a_journal_landed_does_not_own_or_others_can_write_refuses_before_anything`,
  `::test_a_green_row_counts_only_for_the_range_being_landed`, `::test_issues_are_untouched_until_the_sha_is_on_origin`, `::test_the_spec_behaviour_line_a_landed_commit_names_gets_ok_with_the_test`, `::test_a_dirty_spec_file_it_would_edit_refuses_before_the_push_and_nothing_else_does`, `::test_a_fixes_line_naming_several_issues_closes_each_and_the_done_row_names_what_stayed_open`. Not yet: a run with the real jail user and the real `gh`; both are faked in every test.
- `dev-workflows.tool.watch` [OK] (#6116; owner 2026-11-01) — `builder watch [--port 8765] [--state DIR] [--root DIR]` is a live progress
  page: a stdlib `http.server` bound to 127.0.0.1 serving one HTML page (no JavaScript; a 5 s meta refresh) read from the
  owner's journal and the worker's under `[jail].workroot/state` (from that file, which the worker can write, only its run rows, and a line that does not parse is skipped; test `fichero-builder/tests/test_watch.py::test_a_worker_cannot_put_a_check_or_a_landing_on_the_owners_page_and_a_bad_line_is_skipped`), newest first: one table per kind and nothing else: each run (name, worktree, model, started, turns, cost USD,
  status done/parked/handoff or running), each check (range, green/red, the failed rung), each landing (tip, last step,
  branch, pushed). A naive page by design: the SwiftUI Builder app replaces it later and reads the same journal.
  Tests: `fichero-builder/tests/test_watch.py::test_the_page_shows_every_run_check_and_land_newest_first_with_status_and_cost`,
  `::test_watch_serves_the_journal_page_on_the_loopback_only`, `::test_the_page_reads_the_owners_journal_and_the_workers_shared_one`,
  `::test_a_run_that_handed_off_shows_running_once_its_next_generation_starts`.
- `dev-workflows.tool.triage` [OK] (#6336; owner 2026-11-01) — `builder triage [--labels] [--specs] [--milestones]
  [--assignees] [--order] [--dry]` cleans the repo's GitHub metadata deterministically and changes it directly (owner
  ruling: no proposals file, no manual approval) by the rules of `harness/issues-and-labels.md`; every change is one journal
  row (event `triage`) and one `gh` call that can be read back; `--dry` reads, prints and journals rows marked dry, writes
  nothing. **The milestone is the spec**: `--milestones` moves an open issue to the milestone of the spec that cites `#N`
  (created on the repo first when missing), else of the spec a `spec:<stem>` label hints at, and removes the `spec:*` label
  once the issue sits there (triage deletes no label, and creates none but a missing kept one); a spec with no
  `> Milestone:` line gets one, the milestone most of its cited issues carry (a `spec-milestone-line` row); an issue no
  spec cites with no milestone goes to `Next release` only if it is `type:bug`; a milestone with no open issue that no spec names is closed (a spec's stays, and a closed one a spec needs is reopened, never made twice);
  a milestone with open issues that no spec names and that is not an ops bucket (`Bugs - *`, `Lint - *`, `Performance - *`)
  or a grab-bag (`Next release`, `cand 16`) or parked in the build-order file gets one `spec: write <milestone> spec` issue labelled `needs-spec`, filed
  once. **The label set is closed** (`--labels`): the table in `harness/issues-and-labels.md` (`step:N.M`,
  `type:bug|feature|task`, `priority:P0-P3`, `phase:R0-R6` until the recipe phases are in a build order, `needs-spec`,
  `needs-your-decision`, `needs-your-test`, `status:blocked`); every other label is reported (one `label-unknown` row each) and never deleted, and
  its issues get what `harness.toml [triage.labels]` maps it to (absent = nothing; a `spec:<stem>` value is a hint
  for `--milestones`), and the mapping applied is printed; a missing kept label is created first, and a missing `spec:` hint is skipped, never made. **needs-spec** (`--specs`) goes on an open issue inside a spec's
  milestone that no spec cites and comes off one a spec cites; ops buckets, grab-bags and issues with no milestone are left
  alone. **Assignees** (`--assignees`): the `gh api user` login on `needs-your-decision` / `needs-your-test` only; every
  other assignee is removed. **The build order** (`--order`): `docs/contributor_manual/specs/build-order.md` is the
  owner's; triage reads it and prints a proposed line (one `order-missing` row) for each open milestone with open issues it does not name, never writes it; `builder milestone` with no name takes the first milestone under `## In order`
  that still has open issues and the spec its line names. **Built** 2026-11-01: `fichero_builder/triage.py`. Tests:
  `fichero-builder/tests/test_triage_verb.py::test_labels_are_the_closed_set_priority_and_phase_kept_spec_labels_never_created`,
  `::test_dry_changes_nothing_and_prints_the_counts`, `::test_needs_spec_only_inside_a_spec_milestone_and_only_when_no_spec_cites_the_issue`,
  `::test_milestones_follow_the_citing_spec_and_the_spec_label_goes_once_the_issue_sits_there`,
  `::test_a_specs_empty_milestone_stays_open_and_a_closed_one_is_reopened_not_made_twice`, `::test_labels_creates_a_missing_kept_target_and_skips_a_missing_spec_hint`, `::test_order_does_not_propose_what_the_file_already_lists_under_then`, `::test_assignees_are_the_owner_on_needs_your_only`, `::test_order_reads_the_build_order_file_and_proposes_a_diff_never_writes`,
  `fichero-builder/tests/test_milestone_verb.py::test_no_name_takes_the_first_ordered_milestone_with_open_issues_and_its_spec`.
- `dev-workflows.tool.queue` [PARTIAL] (#6166; owner 2026-11-01) — `builder queue [add|run|pause|resume] [--push] [--once]`: one
  long-running worker per lane (a milestone), fed step by step, so it keeps what it has read and never re-reads the tree.
  `<state>/queue.json` holds the lanes: worktree (stored absolute, test `fichero-builder/tests/test_queue_verb.py::test_a_relative_worktree_is_stored_absolute`), cursor, message number, the steps in build order (`builder milestone
  --enqueue` puts them there; a waiting step is a brief and a queued step, and the plan says all the waits in one line; such a brief names the lane's branch and head, not a fixed base).
  A step goes queued, sent, done, checking, reviewing, landed, or blocked. The worker side is `builder run --feed DIR`, as
  the jail user: a good `DONE <sha>` ends the step, not the session: one `step` row for the owner, then idle until
  `msg-<seq+1>.txt` appears in the folder (the owner's, made exclusively under a name no worker can plant a link at, so a worker cannot write its own next brief; test `fichero-builder/tests/test_queue_verb.py::test_a_planted_inbox_cannot_turn_the_owners_chmod_or_writes_on_another_folder`) and is typed into the
  same pane, or `stop` appears. The owner side is one loop: it sees the `step` row, runs `work.after_run` (rebase, patches,
  fetch, the ladder under the `ladder` lock, review, reused when this exact range already has READY, the land gate; the sha comes from the fetch, never from the worker's
  row), then `builder landed --keep-worktree` (push only with `--push`; the session is still working there), moves the cursor, rebases the worktree and sends the next brief. A
  red check (each red guard named, test `fichero-builder/tests/test_work_verb.py::test_a_red_guard_is_named_in_what_goes_back_to_the_worker`), a NOT READY review or a refused land goes back into the same session as a fix brief with the findings, two
  rounds, then blocked with `<state>/question-<lane>-<step>.txt`; a DONE with no commit, a refused landing or a chain error
  blocks at once. A new session only at the worker's own 85 % handoff or when it is gone (three times on a step blocks); a
  parked worker blocks. After a landing the queue reads each of the step's issues from GitHub; one still open is an `issue-open` row and
  stays on the step's line, and the lane goes on: only `builder landed` closes; `gh` failing or timing out here counts as unread, never a traceback (test `fichero-builder/tests/test_queue_verb.py::test_a_gh_that_times_out_or_is_missing_counts_as_unread_and_the_lane_goes_on`). Without `--push` a step stops there: `builder landed` refuses a sha origin lacks, so the step blocks until a person pushes. Pause = idle with nothing sent; resume = send the next brief, and clears a block. At most
  `[queue].workers` lanes at a time; every transition is a journal row (event `queue`); `builder watch` shows the steps.
  **Built** 2026-11-01 against fake processes: `fichero_builder/queue.py`. Not yet: a run on the real jail user. Tests:
  `fichero-builder/tests/test_queue_verb.py::test_a_two_step_lane_lands_the_first_then_sends_the_second_into_the_same_session_and_stops_at_the_end`,
  `::test_a_red_check_goes_back_as_a_fix_brief_into_the_same_session_before_the_cursor_moves`,
  `::test_two_fix_rounds_then_blocked_with_the_row_file_and_the_cursor_stays`,
  `::test_a_gone_worker_gets_a_new_session_on_the_same_step_and_a_parked_one_blocks`,
  `::test_pause_leaves_the_worker_idle_with_nothing_sent_and_resume_sends_the_next_brief`,
  `::test_an_issue_of_a_landed_step_that_stayed_open_is_a_row_and_on_the_step_never_a_close`,
  `fichero-builder/tests/test_dry_run.py::test_feed_mode_keeps_the_session_and_types_the_next_brief_into_the_same_pane`,
  `fichero-builder/tests/test_milestone_verb.py::test_enqueue_puts_each_step_brief_in_the_milestones_lane_in_build_order`.
  **Roll-on and lanes** (owner 2026-11-02, built against fakes): `builder queue run [--lanes N] [--push]` feeds itself from the
  build-order file: while fewer than N lanes have steps left, it takes the first `## In order` milestone that no lane holds,
  has open issues and a spec, with one brief per step (`queue.next_in_order`, the `milestone --enqueue` plan; a milestone
  whose issues place no step is a `question` row and is skipped). One command so runs a spec to the end and then the next,
  until the order is done or a lane blocks on a QUESTION or a cap, which keeps its lane. N defaults to 1; with more, each
  lane's check and review run in their own thread, so a lane waits only for the ladder lock, one ladder at a time on the
  machine. A blocked step labels each of its issues `needs-your-decision` and comments the QUESTION (#6343; a `gh` that fails
  is an `ask-failed` row); `resume` takes the label off (test `fichero-builder/tests/test_queue_verb.py::test_a_blocked_step_labels_its_issues_needs_your_decision_and_comments_the_question`).
  Tests: `fichero-builder/tests/test_queue_verb.py::test_the_queue_rolls_on_to_the_next_build_order_milestone_when_a_lanes_steps_have_landed`,
  `::test_a_question_stops_the_roll_on_and_the_next_milestone_is_not_taken`,
  `::test_n_lanes_hold_n_milestones_and_their_chains_overlap_but_the_ladder_is_one_at_a_time`,
  `fichero-builder/tests/test_milestone_verb.py::test_the_queue_takes_the_first_ordered_milestone_no_lane_holds_with_its_step_briefs`.
- `dev-workflows.run.code-map` [OK] (#6340; owner 2026-11-01) — jail workers find code with jcodemunch instead of reading the
  tree. `[jail].code_map` names the owner's install; the worker cannot read the owner's home, so before a start the owner
  copies the install's whole venv under the workroot and writes `<workroot>/bin/jcodemunch-mcp`, which runs the script with
  the copy's python and lifts the 2000-file default (again only after an upgrade). The start path writes that one server
  into the worker's `--strict-mcp-config` file, and the worker's command indexes the worktree first. No setting, no install, a planted folder (each folder is made first and then checked, so no link can be planted between a check and a mkdir; tests `::test_a_planted_install_folder_refuses_the_copy_and_touches_nothing_behind_it`, `::test_a_folder_planted_between_the_check_and_the_mkdir_is_refused`)
  or a failed copy or index means a worker that greps, never a refusal. `[brief].rules` tells the worker to use the tools.
  Built and run 2026-11-01 as the real worker user: a full index of the repo took about two minutes and the server answered over
  MCP. Limit: the server names every worktree of a repo the same, so two lanes at once would share one index.
  **Reading metric**: a run's first tick with the worktree's HEAD moved writes a `reading` row (turns and tokens before the
  first commit, per generation), the cost row repeats them (none when nothing was committed) and `builder watch` shows them per run.
  Tests: `fichero-builder/tests/test_codemap.py::test_provide_copies_the_install_and_the_wrapper_runs_it_past_the_owner_only_shebang`,
  `::test_prepare_registers_only_the_copied_server_and_keeps_the_strict_config`,
  `::test_the_worker_side_command_indexes_the_worktree_first_and_a_failed_index_does_not_stop_it`,
  `fichero-builder/tests/test_dry_run.py::test_a_run_records_what_it_read_before_its_first_commit`,
  `fichero-builder/tests/test_watch.py::test_each_run_shows_turns_and_tokens_before_its_first_commit_live_and_after_it_ends`.
- `dev-workflows.tool.build` [PARTIAL] (#6344; owner 2026-11-02) — `builder build --dev` is the owner's dev DMG as one command, so nobody
  re-derives the procedure. It runs the project's own `scripts/build-release-dmg.sh` from `--root` and rewrites none of it: the dev
  tier, the current `MARKETING_VERSION` so the script's auto-stamp leaves the tree alone, the running venv first on `PATH` for the
  engine preflight, no notarizing. One journal row (event `build`: tier, sha, dirty, ok, rc, dmg, log, seconds), the log in the
  state directory, and `PASSED <dmg>` or `FAILED` with the log's tail. A green script with no new DMG is a failure. Without `--dev`
  it refuses: a full release needs the owner's yes. The jail user is refused. **Built** 2026-11-02 against a fake script: `fichero_builder/build.py`.
  Not yet: a run of the real script. Tests: `fichero-builder/tests/test_build_verb.py::test_dev_runs_the_projects_script_for_the_dev_tier_without_a_stamp_or_notarizing_and_prints_the_dmg`,
  `::test_a_red_script_fails_with_the_log_and_the_row_says_so`, `::test_a_green_script_that_leaves_no_new_dmg_is_a_failure`,
  `::test_without_dev_it_refuses_a_full_release_needs_the_owner`.
- `dev-workflows.builder.cluster` [PARTIAL] (#6116) — one spec and its build-order issues (parser ported from
  `pipeline/plan.py`), in order, one commit per issue with its test; the brief is built by `scripts/harness_brief.py` from
  `gh api repos/{repo}/issues/N`: the body and the **title** only when the author association is owner, member or
  collaborator, the comments by the same rule newest first, the rest counted as "(N comment(s) from untrusted authors left out.)"; the spec lines and
  localisation from `pipeline/localise.py`; tested against a recorded real payload. The cluster record is the handoff
  file and the rows until the plan layer exists. Several issues with `--branch` and `--base` make one cluster brief: a
  preamble ending in the DONE line, the text of `harness.toml` `[brief].rules`, then every issue, so a worker needs no issue
  tool. A cluster brief with no `harness.toml` in the repo dir refuses with one line on stderr naming the file, exit 1, no brief
  (`test_the_brief_script_refuses_a_missing_harness_toml_in_one_line_and_prints_no_brief`). Tests: `fichero-server/tests/unit/workflows/test_brief_tool.py::test_a_cluster_brief_has_the_preamble_then_every_issue_and_never_tells_the_worker_to_use_gh`,
  `fichero-server/tests/unit/workflows/test_brief_tool.py::test_the_brief_script_puts_the_rules_files_text_in_a_cluster_brief`,
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_cluster_in_build_order_one_commit_each`.
- `dev-workflows.worker.steers` [PROPOSED] — the worker owns the task's judgement and calls the steps as tools (`brief`,
  `check`, `request-review`, `verdicts`, `land`, `ask`, `hand-off`; `close`, `update-issue` and `file-bug` only once the
  guarded writer exists; for research `search`, `fetch`, `save-source`, `note`); it stops and asks when an acceptance line
  would change, a pinned check trips, a step is paid or irreversible, a source contradicts the premise or the spec
  contradicts the code; the countable stops are `check`'s (above); never for context. Test:
  `fichero-server/tests/unit/workflows/test_cluster_run.py::test_worker_steers_and_stop_and_ask_cases`.
- `dev-workflows.worker.handoff` [PARTIAL] (#6116) — at 85 % of the context window or a task boundary the **watcher**, reading
  the session file (not a Stop hook: audit 2026-11-01 H5, the hook is inert for workers), asks the worker to write the
  handoff: the spec or question and its sections; ordered items with state and sha; one line per commit or saved source;
  commands run and results; the failing command's tail; decisions and rejected alternatives; files touched; the do-not
  list; budget used; under two thousand tokens; then ends the session (TERM after a grace, since an interactive session does
  not exit on its own) and starts the successor **through the same start path**, in the jail, from the handoff file; a
  result already on the task is refused as re-done work. A parked worker ends the same way and its successor resumes with
  the answer. At 16-32k the handoff fires per item. The handoff file is tracked in the repository with no pane ids or
  session names in it. Built: the hook form (`scripts/harness_handoff_hook.py`, reuses `sys.executable`) tells the worker at 85 %; the
  watcher form (2026-11-01): `builder run` sees the worker idle with HANDOFF READY, ends it (TERM to the pane's process group,
  a grace, then the pane is killed), writes a `cost` row ending `handoff`, and starts generation plus one through the same
  start path with a brief naming the handoff file (`<worktree>/HANDOFF.md` unless `--handoff`); a generation cap parks.
  Not yet: the hook's tell replaced by a file the worker reads. Tests: `fichero-builder/tests/test_dry_run.py` (handoff and successor, the generation cap),
  `fichero-server/tests/unit/workflows/test_handoff_hook.py`.
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
  returns at once and the worker reads verdicts with a `verdicts` tool (built 2026-11-01 in `scripts/harness_review.py`: the reviewer's cwd is an empty owner-only dir and it reads a detached checkout of the head by absolute path, so it verifies cited tests and spec lines while a planted CLAUDE.md is never obeyed; the ladder reaches it as one line per rung, never a truncated tail; first real run said NOT READY on a rewritten acceptance line); NOT_READY findings belong to the task's current
  generation (two rounds, then the queue). `land` is a script: fetch the sha into the engine-owned repository, ladder on
  the rebased head there, a READY verdict for **every commit** in the range by `--verbatim` patch-id and message hash (a
  merge, or a commit without exactly one id, refuses the range), the public-boundary grep over diff and messages (a hit names the commit, the file or message and the pattern's index, never the matching text, since it goes to logs), then the fast-forward of the integration branch (a merge mode for the release merge-back is added
  before any ruleset restricts updates); `main` never. The push is never automatic (owner 2026-11-01): the script prints
  the fast-forward and a person (the owner or the manager) runs it, or invokes a `land --push` step by hand; nothing
  pushes on its own. `Fixes #N` closes with the sha, `Part of #N` leaves open with the residue. A research task's review is
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
- `dev-workflows.run.watch-tick` [PROPOSED] — the watcher is the `builder run` process itself, reading the worker's session
  file (context, cost, idle, stuck, red), for Claude and Pi alike (`parse_session` reads both); not a session cron, not the
  engine's scheduler, not a pane regex. A worker gone with its task unfinished → a successor from the handoff, or a question
  with none; a handoff with no successor after twenty minutes → started; a cluster READY and unlanded after thirty minutes →
  `land` or its refusal as a question; a worker judged stuck by its process and its session file's age, never by a missing
  row → told once by file, then replaced; a silent worker raises an alert; an unknown price refuses to start; a per-session
  or daily spend cap parks with a question (owner ruling pending: the daily amount); on restart the journal is reconciled
  before any successor; the pinned dev engine moves to a newer sha only between clusters; each action a journal row. A
  `launchd` job only keeps the watcher itself alive. Built 2026-11-01: the judgement (`fichero_builder/watcher.py`: caps from
  `[spend]`, a missing cap or an unknown price refuses, decisions park, handoff, alert from a session state). Not yet: the
  process that starts, reads and acts. Test: `fichero-builder/tests/test_watcher.py`.
  The caps in `harness.toml [spend]` are owner settings (8 USD a session, 60 USD a day as of 2026-11-01 evening). `[spend].window` is 200000 and
  `[models].builder` is plain `sonnet` (owner 2026-11-02: every turn under 200k, handoffs often, cheap and reliable), because a lane takes its model from the role (test `fichero-builder/tests/test_model_config.py::test_a_window_past_the_standard_one_has_a_builder_model_that_gets_it`).
- `dev-workflows.run.loop` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) (owner 2026-11-02: the harness keeps going with nobody watching; a stage that waits on a
  person is a defect) — `builder loop` runs indefinitely: `builder queue run --lanes N --push` ticking forever, one `loop` heartbeat
  row a tick. It runs as the owner (a LaunchAgent with KeepAlive), because check rows, verdicts, the push and `gh` are the owner's
  and a worker never holds them; workers stay the jail user. Killed and restarted, it resumes every lane from `queue.json` and the
  journal, never repeating a landed step. Every stage transition is deterministic code; a model is called only to code (the
  builder), to review (the reviewer) or to fix findings (the builder). Test (to write): `fichero-builder/tests/test_loop.py`
  (fakes: a restart mid-chain resumes; a landed step is never re-run).
  **Built** 2026-11-02 against fakes: `builder loop` (lanes and rounds from `[loop]`, push on, forever, a `loop` tick row each tick; a rules file that cannot run it is a row). Tests: `fichero-builder/tests/test_loop.py::test_a_restart_mid_chain_resumes_the_step_and_never_lands_it_twice`, `::test_rounds_come_from_the_loop_table`. `builder launchd` writes the owner's two LaunchAgents (`builder loop` with KeepAlive; `builder heartbeat` every three ticks) and prints the `launchctl bootstrap` lines, never loading them; the loop runs a lane's chain beside the ticks, so a long ladder never starves the heartbeat. Tests `::test_the_launch_agents_keep_the_loop_alive_and_run_the_watchdog_every_three_ticks`, `::test_a_one_lane_chain_runs_beside_the_ticks_so_the_heartbeat_keeps_beating`. Not yet: the agents loaded on the owner's Mac.
- `dev-workflows.run.loop-chain` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — per lane, with no person: the worker's DONE row → `builder check` with the
  integration tip as base → the review wrapper (in commit groups when over the cap) → on READY the land gate and `builder landed
  --push`, which closes the Fixes issues → the lane rebased on the new tip → its next step's brief into the same session. A
  worker's DONE is a claim the ladder verifies, never taken on its word. Test (to write): `fichero-builder/tests/test_loop.py`
  (two steps of one lane land through fakes, each transition a row).
  **Built** against fakes (`queue.tick_lane` over `work.after_run`): test `fichero-builder/tests/test_queue_verb.py::test_a_two_step_lane_lands_the_first_then_sends_the_second_into_the_same_session_and_stops_at_the_end`. A land gate refused because the landing branch moved after the rebase (another lane landed) rebases and runs the check, review and gate again, up to three times, never a hand rebase (manager 2026-11-02; test `fichero-builder/tests/test_work_verb.py::test_a_ready_range_whose_base_moved_before_the_land_gate_is_rebased_and_checked_again`). Not yet: a real lane; a push refused by a move after the gate.
- `dev-workflows.run.loop-fix-rounds` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — a red check or a NOT READY review sends its findings back to the same worker
  as a fix brief and the chain runs again, up to `[loop].rounds` rounds (default 2); after that, and on a spend cap, a dead or
  stalled worker or a refused guard, the lane parks with an alert. A parked lane never blocks the other lanes. Test (to write):
  `fichero-builder/tests/test_loop.py` (NOT READY → fix → READY lands; three reds → one alert, the lane parked, the other lane
  goes on).
  **Built** against fakes: `[loop].rounds`; a red with its session gone starts a new session on the step's brief plus the findings (`fix-<lane>-<step>-<round>.txt`), never into the dead feed. Test `fichero-builder/tests/test_loop.py::test_a_red_with_no_live_session_starts_a_new_one_on_a_fix_brief_with_the_findings`. Not yet: the alert at the last round (Step 2.10).
- `dev-workflows.run.loop-rolls-on` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — when a lane's milestone has no open step left, the loop runs `builder build
  --dev` (one row, pass or fail; a failure is an alert, the roll-on goes on) and the lane takes the first `## In order`
  milestone of `build-order.md` that no lane holds; up to N lanes at once, one ladder at a time on the machine. The order done
  is a row, and the loop keeps ticking for new issues. Test: `fichero-builder/tests/test_queue_verb.py::test_the_queue_rolls_on_to_the_next_build_order_milestone_when_a_lanes_steps_have_landed`,
  `::test_n_lanes_hold_n_milestones_and_their_chains_overlap_but_the_ladder_is_one_at_a_time`; (to write) the build after a
  milestone.
  **Built** 2026-11-02 against fakes: a lane whose last step landed with push runs `builder build --dev` once (a `built` or `build-failed` queue row; a failure is an `alert` row with no action, and the next milestone is taken regardless). Test `fichero-builder/tests/test_queue_verb.py::test_a_finished_milestone_gets_one_dev_build_and_a_failed_build_is_an_alert_while_the_roll_on_goes_on`. Not yet: the build runs inside the tick, so a long build reads as a stale heartbeat; a real build.
- `dev-workflows.run.loop-alerts` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — every stop is an `alert` row: id, lane, step, what failed in one line, the path
  of its evidence (ladder JSON, review text, session file, log) and the allowed actions, a subset of `retry`, `park`,
  `ask-owner`. `builder alert <id> retry|park|ask-owner` is the manager's whole job, so a small model can do it: retry re-queues
  the step with its findings, park leaves it, ask-owner labels its issues `needs-your-decision` with the alert as the comment.
  The loop never ends silently: a heartbeat older than three ticks is itself an alert, raised by a second LaunchAgent that reads
  only the journal. Test (to write): `fichero-builder/tests/test_loop.py` (each stop kind gives one alert with its evidence and
  actions; each action does what it says; a stale heartbeat alerts).
  **Built** 2026-11-02 against fakes: every block in the queue is an `alert` row (id `<lane>-<step>-<n>`, what, evidence: the ladder JSON, the review text or the question file, actions); `builder alert <id> <action>` answers it (an action not offered is a refused `alert-answer` row). A block no longer labels the issues by itself: `ask-owner` does (#6343's label and comment, test `fichero-builder/tests/test_queue_verb.py::test_a_blocked_step_labels_its_issues_needs_your_decision_and_comments_the_question`). Tests `fichero-builder/tests/test_loop.py::test_every_stop_is_an_alert_with_evidence_and_actions_and_retry_lands_it`, `::test_send_back_and_ask_owner`. The watchdog `builder heartbeat` reads only the journal: no `loop` tick row for more than three ticks is one `alert` row (step `heartbeat`, evidence the journal, no actions: KeepAlive restarts a dead loop, a wedged one is the owner's), once per silence; exit 1 while stale. Test `::test_a_stale_heartbeat_is_one_alert_per_silence_and_a_fresh_one_is_none`.
- `dev-workflows.run.loop-roles` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — the model and the worker kind are per role in `harness.toml [models]` (builder,
  reviewer, manager; today sonnet, opus, haiku), the kind from the provider: an interactive Claude Code session in tmux today,
  a Pi RPC session on OpenRouter or a local server next. The loop reads only journal rows and the DONE / QUESTION protocol, so
  nothing in it assumes Claude Code; no model name is written in code. Test (to write): `fichero-builder/tests/test_loop.py`
  (a fake provider kind runs a step end to end; a role with no provider is a question).
  **Built** 2026-11-02: the `manager` role (haiku) in `[models]`; the loop takes builder and reviewer from the roles; `builder run` with no `--model` takes `[models].builder` and a rules file without one refuses as a question. Test `fichero-builder/tests/test_model_config.py::test_the_loop_has_a_manager_role_and_no_verb_names_a_model_of_its_own`. Not yet: `scripts/harness_review.py` run by hand still falls back to `--model opus`; the Pi kind through the loop.
- `dev-workflows.run.loop-machine-checked` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) (the open-model trial of 2026-10-18 failed on these) — after each step the
  loop checks that the jail root and every other lane's worktree are unmoved and clean (HEAD and `git status`), and alerts
  otherwise; the policy hook refuses `git reset --hard`, `git checkout --`, `git clean -f` and `git stash` outside the worker's
  own worktree, and any write outside it. Test (to write): `fichero-builder/tests/test_loop.py` (a step that moves another
  lane's tree alerts), `fichero-builder/tests/test_pi_policy_extension.py` and the policy hook's tests (each refused command).
  **Built** 2026-11-02 against fakes: a step snaps the jail root and every quiet lane's worktree (no live session of its own, step queued, blocked or landed) as `HEAD status-hash` before its worker starts; at the worker's DONE a changed one is one `alert` row naming each tree (no actions; the step goes on: the stray write was not in its tree). A landing meanwhile (`landed` row `jail-root`) excuses the jail root. The policy hook (both kinds: Pi's extension calls the same `check`) refuses `git -C`/`--work-tree`/`--git-dir` at another tree with `reset --hard`, `checkout --`, `clean -f` or `stash`, and a shell redirect or `tee` to an absolute path outside the worktree and scratch path. Tests `fichero-builder/tests/test_loop.py::test_a_step_that_moves_another_lanes_tree_or_the_jail_root_alerts`, `::test_a_landing_meanwhile_excuses_the_jail_root_and_a_busy_lane_is_not_checked`, `fichero-server/tests/unit/workflows/test_policy_hook.py::test_each_forbidden_command_is_refused_with_a_reason` (six new cases), `::test_ordinary_commands_pass`. Not yet: a lane with a live session is skipped, so a write there is seen only when it is quiet.
- `dev-workflows.run.loop-status` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — `builder status`: a read-only page on 127.0.0.1 (stdlib HTTP, journal only):
  lanes, each lane's step and state, the last check and landing, issues closed today, spend today, open alerts; the same as
  JSON at `/status.json` for the app. Test (to write): `fichero-builder/tests/test_status_page.py` (a journal of fixed rows gives
  that page and that JSON).
  **Built** 2026-11-02: `builder status` is `builder watch` (one page, one server): a Status, Today and Open alerts table on top of the runs, checks, lands and queue; `/status.json` serves the same dict (lanes with step and state, last check, last landing, issues closed today = `done` rows' issues less `left_open`, spend today = today's `cost` rows, open alerts = alerts with no answer that took). Tests `fichero-builder/tests/test_status_page.py::test_a_journal_of_fixed_rows_gives_that_status_and_that_page`, `::test_status_json_is_served_on_the_loopback`, `::test_the_status_verb_is_the_watch_page`.
  **Console** (owner order 2026-11-02, APPROVED by the manager): `builder status` is an interactive console, the owner's main view;
  `builder watch` keeps the read-only page. A stdlib server on 127.0.0.1 (a Tailscale bind behind a token later):
  `GET /api/status` is the JSON above plus the last review and the heartbeat (the last `loop` tick); `GET /api/events` is a
  server-sent-events tail of the journal. Actions are `POST /api/action` calls onto the existing verbs and nothing else (a lane's
  pause and resume, loop start and stop through `launchctl` on the `local.builder.loop` agent, `alert <id> <action>`,
  `build --dev`, `queue add`, `done`); a verb not on that list is refused, and every action, refused or not, writes one `console`
  row naming who did it, the verb and its exit. A POST must carry the token the page was served with and a loopback Host, so
  another site in the owner's browser cannot drive it. The page is one static `console.html` with Preact and htm from a pinned
  CDN ESM URL, no npm and no build step: a lanes table with each lane's steps under a disclosure, alert cards with their action
  buttons, a Build button. Test (to write): `fichero-builder/tests/test_status_page.py` (the API and each action against a fake
  journal and a fake verb runner; a missing token, a foreign Host and an unlisted verb refused with a row).
  Owner additions (2026-11-02): the page updates itself from `/api/events` with no reload; each lane shows its current step
  (id and the brief's title), what it is doing now (its last row and the worktree's last commit), elapsed time, turns, tokens
  and spend. A Milestones view lists the build order (In order, Then, Parked) with open and closed counts, and an In order
  milestone's steps from the `builder milestone` plan (done, running, next, waiting, question), its questions and its open
  issues with labels and the step that names them; GitHub is read through `gh` only on Refresh (`POST /api/refresh`), cached
  with the time shown, never on a request. Start lane (one milestone) and Start N lanes (ticked ones, up to `[loop].lanes`)
  call `builder milestone <name> --enqueue`. Built: tests `fichero-builder/tests/test_status_page.py` (API, actions, refusals,
  events, milestones). Not yet: Start as one lane from ticked issues, Run check, Run tests, Install on a `[machines]` machine
  (`builder install`), the worker's last tool from its session file.
  Status per issue and step (owner 2026-11-02), from git and gh, no new labels: open (nothing built); in progress (a
  `Part of #N` commit on an unlanded branch, naming the lane); built, waiting to land (a `Fixes #N` or `Closes #N` commit on an
  unlanded branch, naming it); landed (closed, its `Fixes` commit on the land branch); released (that commit on main). The
  unlanded branches are the queue's lanes' worktrees, external ones included (commits past the land branch). A step's status is
  the lowest of its issues'; a milestone shows a count per status, and its Start button reads Lane running when a lane holds
  it, Built, waiting to land when no step is still open, and is offered only when a step has nothing built and no lane holds
  the milestone. An external lane reads working when its HEAD moved in the last 15 minutes, else idle; a loop with no tick
  for three ticks reads "Loop is off: lanes are not fed or landed automatically", Start loop beside it.
  Look (owner 2026-11-02): a Mac window: the system font (SF Mono for shas), the system colours light and dark, a toolbar with a
  segmented control for the views and bordered buttons (Build prominent), summary cards with a coloured dot, an Activity
  Monitor table (compact zebra rows, state pills: working a pulsing green dot, queued grey, paused orange, a question red),
  relative times with the full time on hover, inline icons; a lane's step column is its id and title, its brief behind the
  disclosure. Worktrees view (E): every worktree of the owner's checkout and of the jail root with branch, last commit, dirty,
  landed (HEAD on origin/<land branch>) and the sweep's grace deadline; Clean up only on a landed, clean, linked tree no lane
  holds, through `builder sweep --worktree P` = the landing's sweep for that one tree with no grace (a patch first,
  `git worktree remove`, never rm; a jail tree as the worker), one `sweep` row (test
  `fichero-builder/tests/test_status_page.py::test_worktrees_lists_each_tree_and_clean_up_sweeps_only_a_landed_clean_one_with_a_patch`).
  Views A-D (owner 2026-11-02), read-only from the journal, git and gh: (A) Activity: every check, review, build and landing
  that is running, from `activity` rows each writes at its start and end (a check also one per rung, a review one per group,
  `group i of n`), including those started by hand, with elapsed time; (B) Landing queue: every branch with commits not on the
  land branch (the lanes' and landing worktrees'), its head, commits, files, stage (waiting, checking, reviewing, READY, landing,
  landed; `batch i of n` for a lane's steps) and the `Fixes` issues it closes; (C) Issues: today's closes, comments and labels
  the harness made, linked to GitHub; (D) Integration to main: the commits on the land branch not on main, the last release tag
  and whether a release PR is open (gh, cached on Refresh); Make release PR is shown only as the owner's to do, never done.
  Progress reads `step i/N` everywhere: a lane row `Step 1.4 · 4/25 in <milestone>` (N from the spec's build order; an external
  lane's step from its last commit's `Step N.M` or `Behaviour:` line), a milestone row a bar of done over total steps.
  New code (manager 2026-11-02; a hand restart is a defect): between ticks, with no chain in flight and no live worker session,
  the loop compares its `fichero_builder` sources' names, sizes and mtimes with those it started with and, when they changed,
  writes a `loop` row `restarted` ("loop restarted for new code", pid, args) and execs itself with the same arguments (test
  `fichero-builder/tests/test_loop.py::test_the_loop_re_execs_itself_between_ticks_when_its_code_changes_and_nothing_is_in_flight`).
  Locks (manager 2026-11-02: a landing sat 16 minutes in flock behind a check, with no row): the holder of a lock writes its pid
  and what it is doing into the lock file; a wait longer than 30 s is one `lock` row (`waiting for <lock> held by <pid> <what>`)
  and an `acquired` row when it ends, and the console shows a waiting one as a banner. The landing's `pinned` step never waits
  for a running check: with the ladder held it pins its copy and keeps the older ones for the next landing to remove. A lane row
  shows its check or review's running rung and since when (from the `activity` rows); views A-D are built (tests
  `fichero-builder/tests/test_status_page.py::test_a_lock_wait_over_its_limit_is_a_row_naming_the_holder_and_the_console_shows_it`).
  **Stop** (manager 2026-11-02, built): pause = no new step is fed; `builder queue stop --lane L [--grace S]` = the session
  ends: the lane is paused, a live worker is told to commit what is green and end, and the loop closes the session when the
  grace is over (default 300 s) or the worker ends first; the tree is kept, a step in flight goes back to queued with a brief
  that says to continue from the tree, and `queue resume` starts a fresh session on it. Rows `stop`, `stopped`, `stop-refused`.
  Test `fichero-builder/tests/test_loop.py::test_stop_tells_the_worker_closes_its_session_after_the_grace_and_resume_starts_a_fresh_one_from_the_tree`.
- `dev-workflows.run.loop-soak` [GAP] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — acceptance for the loop as a whole: it runs a real build-order milestone for six
  hours with no hand step; every step either lands or ends as an alert row with evidence, never as silence; the heartbeat has no
  gap longer than three ticks. Manual: the maintainer reads only `builder status` and the alerts for the six hours, and the
  journal is attached to the issue.
- `dev-workflows.run.loop-session-cap-hands-off` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated; ie-lane2 was
  parked mid-step with uncommitted work at the session cap) — reaching `[spend].session_usd` does what the context handoff does:
  the session ends and a fresh one starts on the same step with "continue from the tree: the step, its brief and the commits so
  far"; uncommitted work stays in the worktree. Only `[spend].day_usd` parks. Test (to write): `fichero-builder/tests/test_loop.py`
  (a session over its cap gets a successor on the same step; over the day cap the lane parks with an alert).
  **Built** 2026-11-02: `watcher.assess` gives `handoff: session spend` at the session cap and parks only at the day cap; `builder run` tells the worker why and to hand off, and the successor starts as at the context mark. Tests `fichero-builder/tests/test_watcher.py::test_the_session_cap_then_the_day_cap_park`, `fichero-builder/tests/test_dry_run.py::test_the_session_cap_parks_and_stops_the_worker` (names kept from before). Not yet: a real lane at its cap.
- `dev-workflows.run.loop-handoff-tokens` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated; ie-lane2 used 17M tokens for
  three steps on a 1M window) — the handoff threshold is an absolute token count, `[spend].handoff_tokens` (175000, owner 2026-11-02), not a share
  of the window; a session whose context passes it hands off. Test (to write): `fichero-builder/tests/test_watcher.py` (a session
  at 150001 tokens on a 1M window hands off).
  **Built** 2026-11-02: `[spend].handoff_tokens = 175000` (owner, was 150000); `watcher.threshold` and the in-session hook (through the registry's `handoff_tokens`) both use it. Tests `fichero-builder/tests/test_watcher.py::test_the_handoff_threshold_is_an_absolute_token_count_when_set`, `scripts/harness_handoff_hook.py`'s self-test through `fichero-server/tests/unit/workflows/test_handoff_hook.py`.
- `dev-workflows.run.loop-fetches-the-lane` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated; a check refused "not a
  commit in the engine repo" until a person fetched by hand) — on DONE the loop fetches the lane's head from its worktree into
  `[check].engine_repo` and makes it readable to the jail user, before the check. Test (to write): `fichero-builder/tests/test_loop.py`
  (a head that exists only in the lane's worktree is checked with no hand step).
  **Built** in the chain: `work.do_fetch` bundles the worktree's commits as the jail user and the owner fetches them into the engine repo before the check (test `fichero-builder/tests/test_work_verb.py::test_fetch_never_passes_the_workers_branch_name_to_git`); the hand case was a bare `builder check`.
- `dev-workflows.run.loop-tell` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated; a finding was typed into a jail pane by
  hand) — a check or review finding goes into the lane's live session (`builder tell <lane> <text>`, through the lane's feed, one
  journal row) while it runs; with no live session it becomes the fix brief of a new one. The brief rules say: whenever you add a
  tool or a route, run the generators (the capability reference, the OpenAPI and MCP files) in the same commit. Test (to write):
  `fichero-builder/tests/test_loop.py` (a finding reaches the live session as its next message; with none, a new session gets it).
  **Built**: `builder queue tell --lane L --text T|--file F` writes the next message into the live feed and bumps the lane's seq (a `told` row); with no live session a `tell-refused` row; the generators rule is in `[brief].rules`. Test `fichero-builder/tests/test_loop.py::test_tell_puts_a_finding_into_the_live_session_and_refuses_with_a_row_when_there_is_none`.
- `dev-workflows.run.loop-needs-maintainer` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — a pinned-checks refusal
  that says needs-maintainer becomes an alert carrying the diff of each pinned file, with actions `approve` (the check runs again
  with `--maintainer`) and `send-back` (a fix brief). Separately, `scripts/verify_workflows.py` reads its image-input tool list
  from the tool registry, so adding a node never edits a pinned check. Test (to write): `fichero-builder/tests/test_loop.py`
  (the alert carries the diff; approve re-runs with --maintainer); `fichero-server/tests/unit/scripts/test_verify_workflows.py`
  (a new image tool in the registry is in the list with no edit to the script).
  **Built** against fakes: `work.after_run` turns a pinned-checks needs-maintainer refusal into kind `needs-maintainer` with the diff of `[check].check_paths` in `pinned-<lane>.diff`; the queue alerts with approve|send-back (never a fix round); approve re-runs the chain with the check as `--maintainer`. Test `fichero-builder/tests/test_loop.py::test_needs_maintainer_is_an_alert_with_the_pinned_diff_and_approve_reruns_as_maintainer`. `scripts/verify_workflows.py` reads the image-input tools from the live registry (a vision or transform tool with a `files` input port; 13 vision presets that were given the `.txt` fixture now get the text-page image); test `fichero-server/tests/unit/scripts/test_verify_workflows.py::test_a_new_image_tool_in_the_registry_is_in_the_list_with_no_edit_to_the_script`. Not yet: the diff writer through a real check; the e2e lane run with the new selection.
  **Weakened tests** (manager 2026-11-02): a range that renames, drops or weakens an existing test on purpose (an owner ruling,
  #6088) is the same alert as needs-maintainer: evidence the diff of every test file in the range, actions approve | send-back;
  approve re-runs the step's check with `--approve-weakened` (not `--maintainer`), which records `approved weakened tests: …` in
  the pinned-checks row and in the check row; a maintainer batch alone still refuses a weakened test. Tests
  `fichero-server/tests/unit/workflows/test_check_tool.py::test_weakened_tests_refuse_until_the_manager_approves_and_the_approval_is_recorded`,
  `fichero-builder/tests/test_loop.py::test_weakened_tests_are_an_alert_with_the_test_diff_and_approve_reruns_recording_the_approval`.
  **Red-on-base** (manager 2026-11-02, sharing a0d60afec2): a changed test file whose test functions are all unchanged (only
  module-level data such as a registration set changed) owes no red and runs in the green run; any other red-on-base refusal
  (a test that passes on base, an Already built test that fails there, a source change with no test) says `needs-approval` and is
  the same approve | send-back alert; approve re-runs with `--approve-red`, which records the refusal in the row and still
  needs the green run. Tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_test_file_whose_tests_are_unchanged_owes_no_red_and_any_other_refusal_can_be_approved`,
  `fichero-builder/tests/test_loop.py::test_a_red_on_base_refusal_is_an_alert_and_approve_reruns_with_approve_red`.
  **New pinned file** (manager 2026-11-02: a dead end on a `--maintainer` batch): a new file under a pinned path that is not a
  guard is the same approve | send-back alert (evidence the added files' diff); approve re-runs with `--approve-pinned-new`,
  recorded as `approved new pinned files: …` in the pinned-checks row. Tests
  `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_new_file_under_a_pinned_path_refuses_until_approved_and_the_approval_is_recorded`,
  `fichero-builder/tests/test_loop.py::test_a_new_file_under_a_pinned_path_is_an_alert_and_approve_reruns_with_approve_pinned_new`.
- `dev-workflows.run.loop-external-lane` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated: the baseline comparison) — a
  lane of kind `external` is a branch in a worktree that the loop does not start a worker for; `builder done <lane> <sha>` is its
  DONE, and from there the same chain runs (fetch, check, review, landed --push, alert on a stop, findings by `builder tell` when
  the lane names a pane, else as an alert). Plain Claude Code lanes land through the loop this way. Test (to write):
  `fichero-builder/tests/test_loop.py` (`builder done` on an external lane lands it through fakes; no worker is started).
  **Built** 2026-11-02 against fakes: `builder queue add --kind external` makes the lane; the loop starts no worker for it and its step waits; `builder done <lane> <sha>` sets the step done (a `done` row; a worker lane or no waiting step is a `done-refused` row) and the chain runs; a red, NOT READY or refused is an alert with its evidence, never a fix round. Test `fichero-builder/tests/test_loop.py::test_builder_done_on_an_external_lane_lands_it_and_no_worker_is_started`. Not yet: findings by `builder tell` into a named pane; the real chain's rebase, export and fetch run as the jail user, so an owner-made external worktree must be readable by it.
- `dev-workflows.run.loop-external-intake` [PARTIAL] (#6116; manager 2026-11-02, owner-delegated) — a lane that commits on its own
  branch is landed with no manager step. Trigger: `builder done <lane> [--sha S]` (S = the lane's HEAD when it runs; later commits
  go in the next batch), or the loop by itself when an external lane has `[loop].intake_commits` commits (default 8) or
  `[loop].intake_hours` (default 3) since its last landed batch and its HEAD subject is a finished step (`(Step ` or a
  `Behaviour:` trailer); a lane added with `--hold` (a milestone a person holds) is never taken. One batch per lane in the ladder
  at a time. Take: the lane's own worktree and branch are never touched (an agent works there): the loop makes or refreshes
  `land-<lane>` beside it at S and the chain rebases that onto origin/<land branch> as the owner; a conflict is a send-back.
  Check and review as for any lane, never `--maintainer` for a product lane; a rerun after a send-back is a delta review. Any red
  rung, refusal or NOT READY writes `findings-<lane>-<n>.txt` under the state dir, tells the lane's registered pane (`queue add
  --pane %N`, through `[loop].tell`) and is an alert; the lane fixes on its branch and runs `done` again, which re-takes from its new
  HEAD. Land: `landed --push` with full shas and the engine repo; then the lane is told `LANDED <sha>, rebase onto
  origin/<branch> at your next step boundary` and `land-<lane>` is swept (patch first). Console: an external lane row shows its
  stage and the commits waiting since its last landing. Test (to write): `fichero-builder/tests/test_loop.py` (done snapshots the
  HEAD into land-<lane>, the lane's tree untouched; a red tells the pane and writes the findings; a re-done re-takes; the
  thresholds take a finished step and never a held lane).
  **Built** 2026-11-02 against fakes and real git: `builder done <lane> [sha|--sha S]` (land_tree, done), `queue add --hold
  --pane`, `[loop].intake_commits/intake_hours/tell`, findings + tell on any stop, LANDED + sweep after landing, commits
  waiting in the console. Tests `fichero-builder/tests/test_loop.py::test_done_snapshots_the_lanes_head_into_a_land_tree_and_a_red_tells_its_pane_and_a_re_done_re_takes`,
  `::test_the_intake_takes_a_finished_step_past_its_thresholds_and_never_a_held_lane`. Not yet: Sonnet/Opus review by path
  (speed item 6a); the first real run (lane-sharing, lane-onboard).
- `dev-workflows.run.measure` [PARTIAL] (#6116; manager 2026-11-02: a measurement run on a test machine was a hand step) —
  `builder measure --lane <lane> --machine <name> [--sha S] -- <script> [args]`: the lane's commit (default its HEAD) ships its engine
  source and the script (`git archive`, never the worktree) to `<dir>/wt/<sha12>` on the `[machines].<name>` host over ssh, runs
  it there with `<dir>/venv/bin/python`, `PYTHONPATH` the shipped source and `TMPDIR=<dir>/tmp`, which is emptied after; a host
  with less than `min_free_gb` (default 5) free refuses before shipping. One `measure` row (lane, machine, sha, args, exit, the
  last JSON line of its output) and the line told to the lane's pane. The console offers it per lane. Test
  `fichero-builder/tests/test_measure.py` (a fake ssh). Not yet: a lane's `MEASURE <machine> <cmd>` request read by the loop, a
  step marked measure.
  `builder install <machine> [dmg]` (owner 2026-11-02): the newest dev DMG of the journal (or the one named) streamed over ssh to
  the `[machines]` host, its app copied into ~/Applications there (no sudo) and opened; the `install` row says whether the app
  and its engine are running (a machine with no GUI session says so). The console's Release view has Install on <machine>. Test
  `fichero-builder/tests/test_measure.py::test_install_copies_the_newest_dev_dmg_installs_and_reports_the_app_and_engine`.
  Start as one lane (owner 2026-11-02): ticked open issues in the Milestones view become one lane, `builder lane <name> --issues
  N...`: one cluster brief from them (the brief tool, as `builder milestone` writes them), queued as a worker lane in the jail; a
  lane already working is refused. Test `fichero-builder/tests/test_queue_verb.py::test_ticked_issues_become_one_lane_with_one_cluster_brief`.
  Run tests (owner 2026-11-02): `builder test <paths...> [--head S]` runs the pinned pytest over those paths in a scratch tree of
  origin/<land branch> (or S), as the jail user, on `[check].remote` when one is set, one pytest per package; one `test` row; the
  console's Release view runs it. Test `fichero-server/tests/unit/workflows/test_check_tool.py::test_run_tests_runs_the_named_paths_in_a_scratch_tree_of_the_head`.
  Not yet: Run check on a lane's head (an external lane's `builder done` checks, reviews and lands it).
- `dev-workflows.run.records-are-truth` [PROPOSED] (maintainer 2026-10-31; owner 2026-11-01: no engine) — for a worker the
  truth is its **journal** (JSON lines, one file per cluster under the Builder's state directory; `$FICHERO_HARNESS_LOG` in
  Slice 0), plus git plus the handoff file; the run log (one row per item attempt: model, provider, context cap, tokens,
  tool calls and errors, diff lines, wall time, cost, ladder, verdicts, rework rounds, false done) is written from the
  journal as rows and TSV; the engine's jobs table is the truth only for recipe runs and the Researcher, and an app reads
  the journal later. Test (unwritten, Step 1.2): state and log read from the journal, under the Builder's tests folder.
- `dev-workflows.run.rules-file` [PARTIAL] (#6116) — one `harness.toml` at the repository root declares **what must hold**,
  never the worker's order of work: integration and protected branches, worktree root and branch pattern, commit author
  and trailers, scratch path, allowed tools and forbidden commands, each rung of the ladder **declared on or off** as an
  argv list with env, cwd and time budget, the pinned paths, the paths `red_on_base` applies to, turn and dollar caps,
  machine limits, landing conditions, the people list, the review checklist path, the role models, the handoff line, the
  project rules put in every cluster brief (`[brief].rules`, text), the watcher's caps (`[spend]`: window, handoff share,
  session and day USD, silent seconds, a price per model for a kind whose session file carries none).
  **Fail-closed:** an unknown or misspelt key refuses to load; an undeclared rung is an error, never "skipped". The hook,
  `check`, `land` and the tick read it. Test:
  `fichero-server/tests/unit/workflows/test_rules_file.py::test_unknown_key_refuses_and_every_rung_is_declared`,
  `fichero-server/tests/unit/workflows/test_rules_problems.py::test_each_gap_is_a_named_problem`,
  `fichero-server/tests/unit/workflows/test_brief_tool.py::test_the_brief_script_refuses_a_misspelt_brief_key_and_prints_no_brief`,
  `fichero-builder/tests/test_watcher.py::test_the_table_is_read_and_an_unknown_key_or_bad_price_refuses`.
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
- `dev-workflows.rollout.dry-run` [PARTIAL] (#6116) — the loop runs with no model and no money: `builder run` takes its
  process control (start, alive, stop, read the session file) as a small object, and the dry run swaps in fakes with a
  scripted sequence of session states. Built 2026-11-01: a missing price refuses before anything starts; a healthy worker
  that ends leaves one `worker` row and one `cost` row; an idle worker is ended on its DONE line and left alone without it
  while its branch has not moved; idle with the branch moved and no good DONE line (none, or one naming another sha) for two ticks it is nudged once with the
  exact line to end on, through the pane, and still idle two more ticks later, even after a reply without the line, it is ended `done-unsaid` (a `watch` row, the cost row's end, exit
  0, and `builder work` goes on to the check, because the branch holds the work; tests `fichero-builder/tests/test_dry_run.py::test_a_done_line_naming_the_wrong_sha_on_a_moved_branch_is_nudged_and_ended_too`, `::test_a_worker_that_answers_the_nudge_without_the_line_still_ends`, `fichero-builder/tests/test_work_verb.py::test_a_worker_that_committed_and_never_said_done_goes_on_to_the_check`); a hand brief that carries no DONE instruction is started on a copy in the worktree that does (built 2026-11-01,
  `fichero-builder/tests/test_dry_run.py::test_an_idle_worker_whose_branch_moved_but_said_no_done_is_nudged_once_then_ended_done_unsaid`,
  `::test_a_hand_brief_without_the_done_instruction_gets_it_added_in_the_copy_the_worker_is_started_on`);
  the session cap and the day cap park and stop the pane; a silent
  worker alerts once and is not stopped; a handoff decision is recorded. Not yet: recorded hook events replayed through the
  real policy (a refused command, a weakened test, a pinned-path edit, an acceptance-line change), a question and its
  answer, a false done, a NOT_READY round, land and close against a fake `gh`. Test: `fichero-builder/tests/test_dry_run.py`.
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

- `dev-workflows.models.by-config` [PARTIAL] (#6116) — the rules file names **one model per role** (builder, reviewer, spec-writer,
  helper, researcher): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`, `claude-code`), model, precision, context cap;
  today builder Sonnet, reviewer Opus, spec-writer Fable for a rewrite and Opus for a small spec, approved by the owner; a
  missing provider is a **question**, never a silent fallback; a role changes model only by a person editing the file
  after reading the run log (READY rate, false done, writes outside the worktree, reviewer agreement per model). Test:
  Built 2026-11-01: `harness.toml` [models] (`providers` and one `{provider, model, context?}` row per role) read by
  `fichero_builder/models.py`; a missing role or a provider not in `providers` raises a Question. Not yet: `builder run`
  and the reviewer start read their model from it (they still take `--model`). Test:
  `fichero-builder/tests/test_model_config.py::test_one_model_per_role_and_a_missing_provider_asks`.

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
- `dev-workflows.core.shared` [PARTIAL] (#6116; owner 2026-10-31: shared core, two front ends; owner 2026-11-01: the
  Builder apart from the engine) — the Builder is the top-level `fichero-builder/` package, plain Python on the standard
  library: `check_tool`, `jail`, `land_tool`, `start_tool`, `brief_tool` and `policy_hook` live there (moved 2026-11-01),
  the `scripts/harness_*.py` entry points import them from there, and the old `fichero_server.workflows.<name>` paths are
  shims returning the same module object for the engine's dev-tier route and the older tests until Step 1.1 deletes that
  route. `journal` (the state directory is `FICHERO_BUILDER_STATE`, else the XDG state home), `budget` and `session`
  (`parse_session`, both kinds' usage shapes) are ported from `pipeline/` (2026-11-01); not yet: the watcher. The Researcher
  stays on the engine's core (records, jobs, Activity, the question record, the sync). A `builder` tier, a Builder bundle
  and the Activity table as a Swift package are deferred text until a second app is scheduled: tiers filter registration,
  not import (a route's closure is about 373 modules), a bundle without the model stack still carries `lancedb`,
  `langgraph`, spaCy and OpenCV, and the Activity views reach about seventy-five app types from 42 files. Test:
  `fichero-builder/tests/test_no_engine_import.py` (every module's imports are standard library; each imports alone with
  no `fichero_server` in `sys.modules`), `fichero-builder/tests/test_journal.py`, `fichero-builder/tests/test_budget.py`,
  `fichero-builder/tests/test_session.py`; `fichero-server/tests/unit/workflows/test_harness_neutral.py`.

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
  invited contributors; shared projects; a `decider` role; a repository as a workspace source; bug
  narrowing before a brief; a Builder front end, `builder` tier and bundle; the
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

Steps a long-running builder can take from the heading. `Depends on` defaults to the step before. No dates (owner
2026-11-01: no deadline, do it right); each step ends on a real issue where it can, and the TSV of step 1.1 measures it.

### Stage 0 — Slice 0: done by hand (§ 0)

#### Step 0.1 — the rules file, the hooks, check and land as scripts, the verdict store, the second user, the B1 fix
- Behaviours: `dev-workflows.rollout.slice-zero`, `dev-workflows.run.rules-file`, `dev-workflows.run.policy-hook`, `dev-workflows.run.land-gate`, `dev-workflows.run.review-and-land`
- Tests: fichero-server/tests/unit/workflows/test_rules_problems.py, fichero-server/tests/unit/workflows/test_policy_hook.py, fichero-server/tests/unit/workflows/test_land_tool.py, fichero-server/tests/unit/workflows/test_check_tool.py, fichero-server/tests/unit/workflows/test_start_tool.py
- Size: M

#### Step 0.2 — the cluster brief; pipeline frozen
- Behaviours: `dev-workflows.builder.cluster`, `dev-workflows.rollout.pipeline-frozen`
- Tests: fichero-server/tests/unit/workflows/test_brief_tool.py, fichero-server/tests/unit/workflows/test_pipeline_frozen.py
- Size: S

### Stage 1 — the Builder package and the watcher

#### Step 1.1 — `fichero-builder/` on the standard library: check, land, jail, policy, start, brief, journal, budget; the ratchet's TSV
- Behaviours: `dev-workflows.core.shared`, `dev-workflows.project.neutral`, `dev-workflows.run.ratchet`
- Tests: fichero-builder/tests/test_no_engine_import.py, fichero-builder/tests/test_second_project.py, fichero-builder/tests/test_ratchet.py
- Size: M

#### Step 1.2 — `builder run`: one process starts a worker and watches its session file; caps; the fake kind
- Behaviours: `dev-workflows.run.worker-start-stop`, `dev-workflows.run.watch-tick`, `dev-workflows.rollout.dry-run`, `dev-workflows.run.records-are-truth`
- Tests: fichero-builder/tests/test_watcher.py, fichero-builder/tests/test_journal.py, fichero-builder/tests/test_session.py, fichero-builder/tests/test_dry_run.py
- Size: M

#### Step 1.3 — handoff and successor from the session file; supervision; the worker steers within its brief
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.supervision`, `dev-workflows.worker.steers`
- Tests: fichero-builder/tests/test_handoff.py, fichero-builder/tests/test_supervision.py, fichero-builder/tests/test_cluster_run.py
- Size: M

#### Step 1.4 — `builder ask`: the question record as a file and a journal row
- Behaviours: `dev-workflows.node.human-question`
- Tests: fichero-builder/tests/test_ask.py
- Size: S

### Stage 2 — check, review, land, in that order

#### Step 2.1 — `builder check` then `builder review` with a shell and a throwaway checkout, then `builder land`; the size rule ignores generated files
- Behaviours: `dev-workflows.tool.check`, `dev-workflows.security.grants`, `dev-workflows.worker.two-capability-sets`
- Tests: fichero-builder/tests/test_check.py, fichero-builder/tests/test_review_with_a_shell.py, fichero-builder/tests/test_land_order.py
- Size: M

#### Step 2.2 — a week on real issues under Claude Code; the TSV compared with Slice 0
- Behaviours: `dev-workflows.run.worker-address`
- Tests: fichero-builder/tests/test_real_cluster_record.py
- Size: S

#### Step 2.3 — the chain as verbs: `builder milestone`, `builder spec`, `builder steps` (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.milestone`, `dev-workflows.tool.work`, `dev-workflows.tool.spec`, `dev-workflows.tool.steps`
- Tests: fichero-builder/tests/test_milestone_verb.py, fichero-builder/tests/test_work_verb.py, fichero-builder/tests/test_spec_verb.py, fichero-builder/tests/test_steps_verb.py
- Depends on: 2.1
- Size: M

#### Step 2.4 — one command after a verdict, no hand edits, two lanes in turn (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.landed`, `dev-workflows.tool.watch` (the pinned copy, the rebase step, the no-second-ladder land and the rules in the brief are Built sentences under `tool.work`, `tool.milestone` and `tool.check`, whose steps they stay in)
- Tests: fichero-builder/tests/test_landed_verb.py, fichero-builder/tests/test_watch.py, fichero-builder/tests/test_work_verb.py, fichero-builder/tests/test_main.py, fichero-server/tests/unit/workflows/test_brief_tool.py
- Depends on: 2.3
- Size: M

#### Step 2.5 — `builder triage`: the closed label set, the milestone is the spec, needs-spec, assignees, the build-order file read (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.triage`
- Tests: fichero-builder/tests/test_triage_verb.py, fichero-builder/tests/test_milestone_verb.py
- Depends on: 2.4
- Size: M

#### Step 2.6 — `builder queue`: one long-running worker per lane, fed step by step, checked and landed in between (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.queue`
- Tests: fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_dry_run.py, fichero-builder/tests/test_milestone_verb.py
- Depends on: 2.5
- Size: M

#### Step 2.7 — the code map for jail workers, briefs that carry it, the reading metric (owner 2026-11-01)
- Behaviours: `dev-workflows.run.code-map`
- Tests: fichero-builder/tests/test_codemap.py, fichero-builder/tests/test_milestone_verb.py, fichero-builder/tests/test_dry_run.py, fichero-builder/tests/test_watch.py
- Depends on: 2.6
- Size: M

#### Step 2.8 — `builder build --dev`: the dev DMG as a verb (owner 2026-11-02)
- Behaviours: `dev-workflows.tool.build`
- Tests: fichero-builder/tests/test_build_verb.py
- Depends on: 2.1
- Size: S

#### Step 2.9 — the continuous loop: a lane's DONE lands with no person (chain, fetch, fix rounds, tell) (owner 2026-11-02)
- Behaviours: `dev-workflows.run.loop`, `dev-workflows.run.loop-chain`, `dev-workflows.run.loop-fetches-the-lane`, `dev-workflows.run.loop-fix-rounds`, `dev-workflows.run.loop-tell`
- Tests: fichero-builder/tests/test_loop.py
- Depends on: 2.6
- Size: M

#### Step 2.10 — the loop's stops: alerts with evidence and actions, needs-maintainer, the session cap hands off, the token handoff, roles (owner 2026-11-02)
- Behaviours: `dev-workflows.run.loop-alerts`, `dev-workflows.run.loop-needs-maintainer`, `dev-workflows.run.loop-session-cap-hands-off`, `dev-workflows.run.loop-handoff-tokens`, `dev-workflows.run.loop-roles`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_watcher.py
- Depends on: 2.9
- Size: M

#### Step 2.11 — the loop at large: rolls on, external lanes, machine-checked trees, `builder status`, the six-hour soak (owner 2026-11-02)
- Behaviours: `dev-workflows.run.loop-rolls-on`, `dev-workflows.run.loop-external-lane`, `dev-workflows.run.loop-machine-checked`, `dev-workflows.run.loop-status`, `dev-workflows.run.loop-soak`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_status_page.py
- Depends on: 2.10
- Size: M

### Stage 3 — the Pi kind by RPC, the sandbox, local parity

#### Step 3.1 — `--kind pi` over RPC with a fail-closed `tool_call` extension; a metered provider; one model per role in the rules file
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.models.by-config`
- Tests: fichero-builder/tests/test_pi_rpc.py, fichero-builder/tests/test_pi_policy_extension.py, fichero-builder/tests/test_model_config.py
- Size: M

#### Step 3.2 — the sandbox chosen by test (launcher with entitlements, Seatbelt profile, Apple container) behind one wrapper
- Behaviours: `dev-workflows.security.untrusted-text`
- Tests: fichero-builder/tests/test_sandbox_wrapper.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — local on the Studio: coder only, one issue per session, review on a cloud model until the TSV agrees
- Behaviours: `dev-workflows.run.local-parity`
- Tests: fichero-builder/tests/test_local_parity.py
- Depends on: 3.1
- Size: M

### Stage 4 — cleanup, the records, the Researcher, the app

#### Step 4.1 — an issue lint matched to how issues are written; `builder clean`; `pipeline/` deleted; AGENTS.md rewritten
- Behaviours: `dev-workflows.surface.one-action-layer`
- Tests: fichero-builder/tests/test_issue_lint.py, fichero-builder/tests/test_clean.py
- Depends on: 2.2
- Size: M

#### Step 4.2 — the records and the guarded GitHub sync (pull)
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-sync`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py, fichero-server/tests/unit/research/test_github_sync.py
- Depends on: 2.2
- Size: M

#### Step 4.3 — the Researcher's first tasks
- Behaviours: `dev-workflows.researcher.tasks`
- Tests: fichero-server/tests/unit/research/test_researcher_tasks.py
- Depends on: 4.2
- Size: M

#### Step 4.4 — the app reads the journal: the Activity table with a hierarchy, and controls that work
- Behaviours: `dev-workflows.ux.activity-table`, `dev-workflows.ux.controls-work`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero-server/tests/unit/workflows/test_controls_reach_the_call.py
- Depends on: 4.1
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
| `dev-workflows.tool.milestone` | 2.3 |
| `dev-workflows.tool.work` | 2.3 |
| `dev-workflows.tool.spec` | 2.3 |
| `dev-workflows.tool.steps` | 2.3 |
| `dev-workflows.tool.landed` | 2.4 |
| `dev-workflows.tool.watch` | 2.4 |
| `dev-workflows.tool.triage` | 2.5 |
| `dev-workflows.tool.queue` | 2.6 |
| `dev-workflows.run.code-map` | 2.7 |
| `dev-workflows.tool.build` | 2.8 |
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
