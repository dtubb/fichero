# Agent profiles, harness adapters and generic workflows — a worker is MODEL × HARNESS × PROFILE on a declared workflow — Design Spec

> Milestone: Builder: agent profiles and generic workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — one section ("Who builds, on what, through which steps")
> saying that a worker is a model on a harness with a role profile, that a project declares its profile and its
> workflow, where the prompts live, and that a role moves to a cheaper model or harness only on a measured bake-off and
> a person's ruling.

> **Status: DRAFT — awaiting the owner's approval (written 2026-11-16 from the owner's direction and answers of that
> day, paraphrased).** Tags: [OK] built and tested by name · [PARTIAL] exists, not wired · [GAP] not built · [BROKEN]
> built, does not run. Issues: one per build-order step under the milestone above.
> Scope with other specs: `harness/dev-workflows.md` keeps the loop (start path, jail, watcher, check, review, land,
> handoff, `[models]` by config, `run.local-parity`, `node.worker`, the ledger's sources `ledger.*`); this spec owns
> **what a worker is told, how each harness is driven, the MCP servers, the project profile and the declared workflow,
> the small-worker rule, the run record and the console's comparison pages, the Swift test rungs, the commit trailer,
> the cleanup step, the bake-off and worker isolation**. Where a bullet here changes a dev-workflows bullet, the change is named under
> "Changes to dev-workflows". The prompt review of 2026-11-16 (kept untracked with the manager's briefs as `REVIEW.md`
> and `prompts/*.md`) is the inventory this spec starts from: worker instructions live in nine places, no system prompt
> is passed, the generated MCP config is empty, and the trailer rule was stated four ways.

## Purpose

The builder today starts one kind of worker (Claude Code in a pane, Pi by RPC behind it) with no system prompt, no MCP
servers, Fichero's branch, paths and rungs wired into code and prose, and project rules spread over `AGENTS.md`,
`harness.toml [brief].rules`, two pre-builder prompt folders and a review script's f-string. The owner's goals
(2026-11-16): run the builder much more cheaply on open coder models (Qwen3-Coder-Next first) and compare harnesses and
models per role, since they may be good at different things; and make the builder **generic**: any project set up the
same way (a Swift front end, a Python back end), and beyond code, systematic work on a book or a research project inside
Fichero. So a worker becomes three independent choices, **model** (from `[models]`), **harness** (Claude Code, Codex
CLI, Gemini CLI or Antigravity, opencode, goose, Qwen Code, Pi; Ollama and OpenAI-compatible endpoints through one of
those) and **profile** (common prompt, role, a thin project layer), and a project becomes two declarations, its
**profile** (languages, tools, checks, paths) and its **workflow** (the ordered steps a worktree moves through).
Fichero's code workflow is one instance. Every run is recorded the same way, so the console compares roles, models and
harnesses over time and a bake-off is just runs that share a brief.

## Terms

- **Worker** — one running session: a model, on a harness, with a profile, on one workflow step, in one worktree.
- **Harness** — the agent program holding the tool loop. A bare endpoint (Ollama, an OpenAI-compatible server) is a
  **provider** reached through a harness that speaks it (Pi, opencode, Qwen Code, goose).
- **Adapter** — one module per harness under `fichero-builder/agents/adapters/<harness>/` with the fixed interface of
  § C and a `capabilities.md` saying what the harness supports and what it does not.
- **Profile** — `common/common.md` + `roles/<role>.md` + `stacks/<stack>.md` + `projects/<project>/project.md` (the thin
  project layer): a worker's prompt and tools compose as common + ROLE + STACK (+ project), owner 2026-11-16.
- **Role** — what the worker does, stack-neutral: feature, testing, bug-fixing, code-review, perf, measure-speed,
  measure-ram, measure-disk, landing, builder-harness, manager; for text projects: writing, editing, sourcing,
  reviewing. Today's `[models]` roles map onto these (builder → feature on the step's stack; reviewer → code-review).
- **Stack** — the language and toolchain a step is in, declared per project in `[project].stacks` (Fichero: `swift`,
  `python`; others later), each a `stacks/<stack>.md` carrying the stack's commands, test runner, lint, MCP tools and
  rules. A worker is a role on a stack: testing × swift is a Swift test worker, perf × python a Python performance
  worker; `builder-harness`, `manager` and the text roles take no stack.
- **Project profile** — the `[project]` table of a project's `harness.toml`: name, kind (code or text), languages,
  tools, the checks it owns, the paths each rung applies to, the integration branch.
- **Workflow** (a recipe) — the ordered steps a worktree moves through, declared in `[workflow]`: brief, work, the
  rungs, review, land, cleanup. A **step** is one worker's whole job.
- **Run** — one worker from start to its end row; a **bake-off** is runs sharing one brief id.
- **Trailer** — `Written-By: <MODEL> using <HARNESS> using Fichero Builder`, MODEL as its display name (owner 2026-11-16).

## Behaviours

### A. The trailer (first, because every worker commits)

- `agent-profiles.trailer.one-line` [PARTIAL] (#6622) (owner 2026-11-05: one `Written-By:`; 2026-11-16: its shape) — every
  commit a worker makes carries exactly one trailer, the last line: `Written-By: <MODEL> using <HARNESS> using Fichero
  Builder`, MODEL the display name from `[models]` (`Claude Sonnet 4.6`, `Qwen3-Coder-Next`), e.g. `Written-By:
  Qwen3-Coder-Next using opencode using Fichero Builder`. No `Co-Authored-By`, no `Directed-By`, no second trailer. The
  commit-msg hook (`fichero-builder/fichero_builder/policy_hook.py`, installed by `start_tool.prepare`) refuses any other shape on new
  commits, including a bare `Written-By: <model>` and the old `Directed-By: the maintainer`; it is the one enforcement
  for every harness, since every harness runs `git commit`; the push-range guard keeps a date floor for commits made
  before 2026-11-05. The MODEL and HARNESS words come from the adapter, so the prompt tells the worker the exact line
  and the hook compares it. Acceptance: the exact line passes; one with `Co-Authored-By` as well, `Directed-By` only,
  `Written-By: sonnet` only, and two `Written-By` lines are each refused naming the rule;
  `check_agent_commits_authored_as_claude.py` treats a `Written-By:` commit as an agent commit and still requires the
  author `Claude <noreply@anthropic.com>`. Files that must change (Step 1.1): `harness.toml` (`required_trailers`,
  `trailer_one_of`, the trailer sentence in `[brief].rules`), `fichero-builder/fichero_builder/policy_hook.py`,
  `docs/contributor_manual/review-checklist.md` item 10, `AGENTS.md` "Commit Format",
  `scripts/check_agent_commits_authored_as_claude.py` (`AGENT_TRAILER`), `scripts/harness_review.py`'s prompt. Test (to write): fichero-builder/tests/test_trailer (new).

### B. Profiles: one folder, one common prompt, roles, a thin project layer

- `agent-profiles.folder.one-place` [PARTIAL] (#6623) — every prompt the builder gives a worker lives under
  `fichero-builder/agents/`: `common/common.md`, `roles/<role>.md`, `stacks/<stack>.md`, `projects/<project>/project.md`,
  `adapters/<harness>/` (its module, `capabilities.md`, the harness-shaped files it needs; Pi's `models.json`,
  `settings.json` and `policy.ts` move here from `pipeline/pi-agent/` and `fichero-builder/pi/`). `agents/prompts/` and
  `agents/skills/` at the repo root (pre-builder) are deleted in the same step with a line in `AGENTS.md` saying where
  they went. No prompt names a task id, sha, date, worker name, person, home path or archive; a guard greps the folder
  for the `[land].boundary` patterns and the people list and fails on a hit. Acceptance: the folder holds exactly
  common, roles, stacks, projects, adapters; the root `agents/` is gone; the guard refuses a prompt with a home path. Test: fichero-builder/tests/test_profiles.py, case test_the_folder_and_no_private_text.
  Built: the folder with `common/common.md`, the empty roles, stacks and projects, the claude-code adapter's `capabilities.md`, and a guard
  for the `[land].boundary` patterns, task ids, shas and dates. Not built: Pi's files move, the deletion of `agents/prompts/`,
  `agents/skills/` and the root `agents/` (diff bound of Step 1.2; `agents/ROADMAP.md` is cited by guard scripts), the people-list guard
  (no people list exists in the repo).
- `agent-profiles.prompt.common` [OK] (#6623) — one common
  prompt every worker gets, under 120 lines and project-free: who it is (a headless worker as a separate user in one
  worktree, no screen, no GitHub token, no person watching); one step and nothing outside it (§ E); where it may read
  and write and what the hook refuses (`[policy].rules` read into the prompt at start, never typed twice); find code
  with jcodemunch and docs with jdocmunch; test first; its own cheap rungs and the ladder's; the lazy senior developer
  rule; prose rules; the commit shape with the exact trailer; the DONE, WAITING and HANDOFF words. Acceptance: the
  assembled prompt for any role begins with the common text; the `[policy]` reasons appear verbatim; the trailer line
  equals what the hook requires; no Fichero path or branch name is in it. Test: fichero-builder/tests/test_profiles.py,
  case test_common_is_first_project_free_and_carries_policy_and_trailer.
- `agent-profiles.prompt.project-layer` [GAP] (#6627) — `projects/<project>/project.md`, under 60 lines, is the only
  prompt text that names the project: its interpreter and tool paths, its thread cap, the rungs a worker may run itself
  and the ones the ladder owns, its contract regeneration tools, its manual's headings to cite. It is generated in part
  from `[project]` and `[check]` so a path is written once. Acceptance: the assembled prompt is common + role + stack + project
  in that order; a second project's folder with its own `harness.toml` assembles a prompt naming none of Fichero's
  paths. Test (to write): test_profiles.py, case test_project_layer_is_the_only_project_text.
- `agent-profiles.prompt.roles` [GAP] (#6637) (owner 2026-11-16: roles × stacks, not frontend/backend) — one
  `roles/<role>.md` per role, under 80 lines, **stack-neutral**, holding only what the role does: **feature** (the
  step's behaviour with its test first, the smallest diff); **testing** (tests only, never product code; a test that
  cannot run fails); **bug-fixing** (reproduce red first, smallest fix, the readers' tests); **code-review** (the
  reviewer preamble now in `scripts/harness_review.py`, `review-checklist.md` as its data, the throwaway checkout,
  the READY line); **perf** (the hotspot table of `performance-sweep.md`, one spot, proved by the rung's figure, no
  timer of its own); **measure-speed**, **measure-ram**, **measure-disk** (the stack's named platform tool over the
  fixed workload, rows out, no product code); **landing** (`builder check`, `review`, `land` in order, pushes
  nothing); **builder-harness** (`fichero-builder/`, stdlib only, never a project string in code); **writing**,
  **editing**, **sourcing**, **reviewing** for text projects (§ D). Each carries its `diff_bound:` and `tools:` lines
  (§ D, § E). A role file names no command, runner, lint or file cap: those are the stack's. Acceptance: every role a
  brief names resolves to a file or is a Question; no role file contains a command or a stack's tool name (a guard
  greps for `pytest`, `xcodebuild`, `swiftlint`, `ruff`); testing and measuring roles say they change no product
  code. Test (to write): test_profiles.py, case test_every_role_resolves_and_is_stack_neutral.
- `agent-profiles.prompt.stacks` [GAP] (#6637) (owner 2026-11-16) — one `stacks/<stack>.md` per stack a project
  declares, under 80 lines, holding what the stack is: its own cheap rungs and their commands (swift: `swiftlint` and
  `swiftc -typecheck` on the touched files, the build and `xcodebuild test` are the ladder's, § F; python: `ruff` and
  one named `pytest` file at a time, red-on-base is the ladder's), its limits (swift: the file caps, no
  `swiftlint:disable`, no force unwrap, logic in the engine; python: the contract regenerators, a new engine file in
  the embed list), its MCP tools (swift: the xcode MCP when it runs inside Xcode, Apple documentation search; python:
  the Fichero dev MCP, jcodemunch's Python symbols), and the measuring tools its perf and measure roles use (swift:
  xctrace, xcresult, XCTest metrics; python: pyinstrument or py-spy, memray, `/usr/bin/time -l`). A stack's `tools:`
  list **overrides** the role's where they name the same kind (the role says "the profiler", the stack says which);
  the project layer may add a tool, never remove the two required servers. The step's stack comes from the step's
  paths against `[project].stacks` (each stack with its path globs); a step touching two stacks is split by `builder
  steps` or refused as a question. Acceptance: Fichero declares `swift` and `python`; testing × swift assembles the
  Swift runner and the Xcode tools and no `pytest`; perf × python assembles pyinstrument and no xctrace; a step under
  both stacks is a question; a role whose stack file is missing for the project is a Question. Test (to write):
  test_profiles.py, case test_role_times_stack_composes_commands_tools_and_rules.
- `agent-profiles.prompt.assembly` [PARTIAL] (#6623) — `start_tool.prepare` and the Pi start take `role`, `harness` and
  `project`, assemble common + role + stack + project plus the few run facts (worktree, scratch, the trailer words) and hand
  the text to the adapter; the brief stays the first user message. The worktree's own instruction files (`CLAUDE.md`,
  `AGENTS.md`, `opencode.json` and each harness's own hidden settings folder) are **never** a worker's rules (a worker can edit
  them): each adapter passes the setting that disables project and user instruction files where the harness has one
  and says in `capabilities.md` when it has none. Acceptance: the dry run shows the assembled text in the adapter's argv
  or file; a planted `CLAUDE.md` saying "push to main" changes nothing the worker is told. Test:
  fichero-builder/tests/test_profiles.py, case test_assembly_order_and_a_planted_file_is_not_obeyed. Built: the Claude Code start. Not built: the Pi start.

### C. Adapters

- `agent-profiles.adapter.interface` [OK] (#6623) — every adapter answers six questions, each a value or `Unsupported(reason)`, never a silent skip: (1)
  **system prompt**: append or replace, string or a file the worker user reads; (2) **MCP servers**: how jcodemunch and
  jdocmunch are written (file, flag or config dir) and whether a strict mode loads nothing else; (3) **model and
  provider**: the flag or file naming model, provider, base URL and key for Ollama / OpenAI-compatible endpoints; (4)
  **permission or sandbox mode**: the harness's non-interactive mode, and its own sandbox if any; (5) **hooks or
  policy**: the commit-msg hook always; a tool-use policy where the harness has a hook point (Claude Code PreToolUse,
  Pi's `tool_call` extension), `Unsupported` where it has none, in which case the OS jail and the land gate are the
  boundary and the capabilities file says so; (6) **session read**: where tokens, cost and the done state come from, in
  the shape `parse_session` returns. `builder run --harness <name>` picks the adapter; an unknown name refuses; a
  harness with (6) or (2) `Unsupported` cannot take a lane (no cost cap, or no index: § D). Acceptance: a fake
  adapter answering `Unsupported` for (6) or (2) refuses with the reason; one answering `Unsupported` for (5) starts
  and journals `policy: none (OS jail only)`. Test: fichero-builder/tests/test_adapters.py,
  case test_six_answers_and_unsupported_is_said.
- `agent-profiles.adapter.claude-code` [OK] (#6623) — adds `--append-system-prompt <text>`, `--setting-sources` naming only the generated settings, the two MCP
  entries under `--strict-mcp-config`, the session file read it has. Acceptance: argv carries the prompt, the strict
  MCP file names exactly the required servers, the settings path is the generated one. Test:
  fichero-builder/tests/test_adapters.py, case test_claude_code_argv.
  Built: `prepare` returns `sh -c` with the scratch `prompt.md` and the brief as arguments, then the claude words; the wrapper reads the prompt file, so argv carries the file, not the text.
- `agent-profiles.adapter.pi` [PARTIAL] (#6631) (`pi_rpc.py`, `policy.ts`, `pipeline/pi-agent/`; first open-model
  harness, owner 2026-11-16) — the agent dir moves under `adapters/pi/` (`PI_CODING_AGENT_DIR`); the system prompt
  through Pi's own mechanism (proven by the first test on 0.75.5); the MCP entries in its `mcp.json` with the index
  built before the first prompt; model and provider from `[models]` with a price in `models.json` (unpriced refuses);
  the `tool_call` extension as policy; RPC events as the session read; Ollama and OpenAI-compatible endpoints as Pi
  providers with a base URL. Acceptance: start argv and agent dir carry the prompt, the servers and the model; no
  price refuses; a Pi worker with the servers missing refuses (the confusion seen without them). Test:
  fichero-builder/tests/test_pi_rpc.py (extended).
- `agent-profiles.adapter.opencode` [GAP] (#6632), `agent-profiles.adapter.qwen-code` [GAP] (#6633),
  `agent-profiles.adapter.codex-cli` [GAP] (#6634), `agent-profiles.adapter.gemini-cli` [GAP] (#6635), `agent-profiles.adapter.goose` [GAP] (#6636) — in the owner's order, one step
  each: the six answers, the harness's own config files and flags, a `capabilities.md` written from a real run on one
  small issue, `Unsupported` wherever the harness has no hook, no strict MCP mode or no session file. A harness is
  admitted to `[models].providers` only when its adapter has run one real step to a READY verdict with both MCP
  servers loaded. Acceptance per adapter: a dry run with the fake, and the real-run row. Test (to write):
  test_adapters.py, one case per harness.

### D. Required MCP servers; project profile; declared workflows

- `agent-profiles.mcp.required` [GAP] (#6624) (owner 2026-11-16: Pi workers were confused without them) — jcodemunch
  and jdocmunch are **required** for every worker on every harness: the adapter writes both, the index is built or
  refreshed over the worktree as the worker user before the first prompt (under the workroot, never the owner's
  home), and a harness that cannot load them, or a start whose index build fails, **cannot take a lane**: it refuses
  with the reason and a journal row, never starts "without the index". Beyond those two, **tool sets are per role and
  per project** (owner 2026-11-16): `roles/<role>.md` carries a `tools:` list and a `diff_bound:` line (§ E) `stacks/<stack>.md` a `tools:`
  list that overrides the role's by kind, and `projects/<project>/project.md` a `tools:` list of the servers that
  project provides; a worker gets the two required servers plus the intersection of what its role × stack asks and
  its project provides, nothing else: a swift-stack worker gets the Xcode tools (the xcode MCP when it runs inside
  Xcode, Apple documentation search) and never the engine's; a python-stack worker gets the engine and Python tools
  (the Fichero dev MCP, the contract regenerators) and never Xcode's; testing, perf and measuring roles get their
  stack's measuring tools (xcresult, xctrace; pyinstrument, memray readers); the manager role gets the builder's own
  verbs; a server a role or stack names that the project does not provide is a journal row, not a silent drop. Each
  adapter delivers the set in its own config shape; a worker's prompt lists only the tools it has. Acceptance: every
  adapter's generated config names the two required servers with commands the worker user can run; a fake adapter
  whose MCP answer is `Unsupported` refuses; a failed index build refuses; a testing × swift worker's config has the
  Xcode set and no engine server, a testing × python worker's the reverse; a server the project lacks yields a
  row; the assembled prompt names exactly the delivered servers. Test (to write): fichero-builder/tests/test_mcp_servers (new).
- `agent-profiles.project.profile` [GAP] (#6627) — a project is its `harness.toml`: a `[project]` table (name, kind
  `code`, `data` or `text` (`data` is research on a Fichero library's records, the sibling's § E), languages, tools by name and path, the checks it owns, the paths each rung applies to, the
  integration branch) beside the existing `[check]`, `[policy]`, `[jail]`, `[land]`, `[models]` tables; the builder's
  code names no project (`dev-workflows.project.neutral` already guards strings). A second code project set up the
  same way (a Swift front end, a Python back end) runs a step from its file alone; a text project declares no build,
  no test rungs and its own guards. Acceptance: Fichero's profile loads; a fixture profile for a second code project
  and one for a text project load; a profile missing `kind` or naming a rung with no tool path refuses. Test (to write): fichero-builder/tests/test_project_profile (new).
- `agent-profiles.workflow.declared` [GAP] (#6627) — the steps a worktree moves through are a `[workflow]` list in
  the project's file, each with a name, the role that does it, what starts it and what ends it: `brief` (the brief
  tool), `work` (a worker), the rungs (each a `[check]` rung by name, in order), `review`, `land`, `cleanup`; the
  builder runs the list, never a hard-wired order, and refuses a file whose list lacks a rung it would otherwise
  assume. **What runs the list is one interface** (owner 2026-11-16): the harness's own plain loop today; LangGraph or
  LangChain, or Fichero's own workflows and recipes, as options behind it, chosen in `[workflow].engine`, none of them
  reaching a page, a verb or a prompt. Fichero's code workflow is one instance; a text project's list has `work`, its guards, `review`, `land`,
  `cleanup`. Acceptance: Fichero's list reproduces today's order; a list with `land` before `review` refuses; a text
  list with no build rung runs in the dry run. Test (to write): fichero-builder/tests/test_workflow (new).
- `agent-profiles.workflow.text-project` [GAP] (#6640) (owner 2026-11-16: a book, or a research project inside
  Fichero) — the proof that the builder is generic: a text project in a **scratch test repository** (owner
  2026-11-16; a real book repository later) with kind `text`, roles
  writing, editing, sourcing, reviewing, a step that is one chapter section or one source task, guards that are
  prose lints (length, citations present, no private names), review by a reviewer role, land as a fast-forward,
  cleanup; a research project uses the Researcher's tools through the same brief shape. Acceptance: a two-step text
  workflow lands on a scratch remote from its file alone, with both MCP servers (jdocmunch over the text) and the
  run rows of § G. Test (to write): fichero-builder/tests/test_text_project (new).

### E. Small, circumscribed workers

- `agent-profiles.worker.small` [GAP] (#6625) (owner 2026-11-16) — a worker gets **one step**, a brief under 120 lines
  that names its files and its tests by path, and a diff bound **per role** (owner 2026-11-16: no single global
  number): a `diff_bound:` line in `roles/<role>.md`, lines changed with generated files excluded, smaller for
  bug-fixing and code-review, larger for the feature role; the bound is the role's whatever the stack; a role file with no bound refuses to start; the brief tool refuses a cluster with more than one step or a brief over the line cap, the policy hook
  counts the bound and the worker is told once then parked with a question; a step whose named files exceed the
  bound is split by `builder steps` before any brief. Acceptance: a two-step brief refuses; a 121-line brief refuses;
  a diff past the role's bound yields one tell and then a park row; a role file with no `diff_bound:` refuses; a brief
  with no named test is refused for a code project. Test (to write): fichero-builder/tests/test_small_worker (new).

### F. Swift rungs and the UI smoke

- `agent-profiles.ladder.swift-tests` [GAP] (#6626) (the ladder builds the app and runs Python red-on-base only) — a
  diff under the project's Swift paths runs, on the build Mac (`[check].build_remote`) after the build rung, the Swift
  unit tests the diff names (its test files and the suites of the views or models it changes, the readers rule), **red
  on base and green on head**: `xcodebuild test-without-building` over the daily `build-for-testing` output with
  `-only-testing` on the base tree and on the head; a changed Swift test green on both is a question. Swift UI tests
  (XCUITest, the Mac UI plan) run the same way for a diff touching a view a UI test names, in a **dedicated GUI user**
  on the build Mac (owner 2026-11-16: set up by the owner, kept logged in, so the owner keeps using the Mac); the
  rung needs that user's name in `[machines]`, a live login session for it, and the test runner started inside that
  session; with none of the three it is `not-run` with the reason, never green and never skipped. Acceptance
  (fixtures, no Mac): the argv for a diff touching one view names that suite on base and head shas; green on both is a
  question; a missing GUI user or session yields a `not-run` row naming which. Test (to write): fichero-builder/tests/test_swift_rungs (new).
- `agent-profiles.ladder.ui-smoke` [GAP] (#6626) (`Fichero.sdef` and `FicheroDebug.sdef` carry `open project`,
  `screenshot`, `select nodes`, `show pane`, `undo step`, `describe window`; `scripts/ux_smoke.py` drives some) — a
  swift-stack worker asks in its DONE message for the UI smoke by name: the ladder launches the Dev Local build in the
  dedicated GUI user's session, runs a fixed script of the app's own verbs (open the scratch project, show the pane the
  step names, screenshot, undo step, screenshot, quit) and attaches the screenshots to the review; nothing drives the
  screen by coordinates. A worker cannot run it itself (`osascript` against the app is refused in the jail). Acceptance:
  the request word yields one smoke row with screenshot paths; no GUI session yields `not-run`. Test (to write):
  test_swift_rungs.py, case test_the_smoke_runs_the_sdef_verbs.

### G. Runs, comparison, the console, cleanup

- `agent-profiles.run.record` [GAP] (#6628) — every run writes one `run` record at its end, a Pydantic model in the harness store (owner 2026-11-16: Pydantic
  models over DuckDB, the sibling's `store.one-database`; `journal.jsonl` stays the event log and gets the same row): project, workflow step, role,
  model (display name), harness, provider, brief id, generation, input and output tokens, cache tokens, money (from
  `dev-workflows.ledger.*`'s cheap sources, never a model's own report), wall seconds, review rounds, refusals,
  landed (head on the integration branch, by `builder landed`) or not, and the end reason. A bake-off is runs sharing
  a brief id. The TSV of the ratchet is written from these rows. Acceptance (fake journal): a run through check,
  two review rounds and land yields one row with every column; two runs on one brief id are one bake-off group;
  a row with no price source is marked `cost: unknown`, never 0. Test (to write): fichero-builder/tests/test_run_record (new).
- `agent-profiles.console.runs` [GAP] (#6629) (`console.py` serves the status page at 127.0.0.1:8766) — the console
  shows the run rows and compares them: a **Runs** list (filters by project, role, model, harness, date), a **Compare**
  view per role (one row per model × harness: runs, landing rate, median rounds, median wall, cost per landed step,
  over a window and by week) and a **Bake-offs** view (the runs of one brief id side by side, the reference pair
  marked), all read from `/api/runs` (the rows of `run.record`, paged); no page changes `[models]`. The page design
  (layout, what sits beside Status, the website's other pages) is owned by the sibling spec
  `harness/builder-console.md`, being drafted from a separate review of the builder's website (it also carries the product's name, Fichero Harness, its one API for HTML and Swift front ends and its host-agnostic work store); this bullet owns only
  the three views' columns and their one data source, and is reconciled with that spec when it lands. Acceptance
  (fixture rows): Runs filters; Compare for feature × python ranks pairs by landing rate then cost; a Bake-offs view shows
  both runs of one brief id; each renders with zero rows. Test (to write): fichero-builder/tests/test_console_runs (new).
- `agent-profiles.cleanup.after-land` [PARTIAL] (#6630) —
  `cleanup` is the last step of every workflow: once a step's head is on the integration branch its land snapshot is
  removed, and once the lane is finished its worker tree and branch are removed; a tree whose head is not on origin
  is never removed; each removal is a journal row. This spec adds only the workflow position and the rows;
  the lane does the work. Acceptance: a landed step's snapshot goes; an unlanded tree stays with a row saying why.
  Test: the lane's test, named when it lands.

### H. The built-in manager role

- `agent-profiles.role.manager` [GAP] (#6638) (owner 2026-11-16: acts within rules) — a `manager` role the builder
  starts on the owner's side (never as the worker user; `gh` read, the journal, no push), supervised by the human
  manager. Within rules, on its own: retry a failed start, dismiss a report-only alert, write a fix brief for a
  NOT_READY verdict, queue the next step of the first unfinished milestone through `builder milestone`, start a
  successor for a parked or dead worker, re-run a `not-run` rung whose reason is known. Everything else is a
  question with its proposed answer. It never lands, pushes, edits `harness.toml`, closes an issue or spends past a
  cap; every action is a row naming the rule. Prompt `roles/manager.md`; model `[models].manager`. Acceptance (dry
  run, fake journal): a parked-at-cap row yields a successor; a NOT_READY row a brief file; a report-only alert a
  dismiss row; a question with no rule a question row and no action; a push attempt is refused. Test (to write): fichero-builder/tests/test_manager_role (new).

### I. The bake-off

- `agent-profiles.bakeoff.measured` [GAP] (#6639) (owner 2026-11-16: compare harnesses and models per role) —
  `builder bakeoff <role> --briefs DIR --pairs MODEL×HARNESS,…` replays the same briefs (three to five landed steps per
  role, from their base sha on a scratch remote) on each pair as ordinary workers under the same jail, hooks, ladder,
  MCP servers and reviewer, every run a `run.record` row sharing the brief id; Claude on Claude Code is the reference
  pair in every run. The result is the Compare and Bake-offs pages and one printed table per role; nothing in
  `[models]` changes from it: a role moves to a cheaper pair only when a person edits `[models]` after reading the
  table, the ruling cited in the file's comment. An earlier open-model trial (2026-10-18) did not match the Claude
  baseline; this replaces that judgement with rows. First run: feature × python, Claude on Claude Code against
  Qwen3-Coder-Next on Pi, then on opencode. Acceptance (dry run): two fake pairs over two briefs yield four rows with
  one brief id each pair; the table ranks by landing rate then cost; `[models]` is unchanged. Test (to write): fichero-builder/tests/test_bakeoff (new).

### J. Worker isolation (owner 2026-11-16: a long step of its own, after the adapters)

- `agent-profiles.isolation.baseline` [PARTIAL] (#6641) — today's wall stays the floor under every option below: a
  worker runs as the second macOS user (`fichero-builder/fichero_builder/jail.py`, `[jail]`, `sudo -u`), outside `staff`, the owner's
  home `700`, no GitHub credential, no ssh key, no Keychain item, the policy hook and the commit-msg hook, the
  once-per-set-up probe. Nothing in this section weakens it; an option is layered on top and a start still refuses when
  the user or its probe is missing. Acceptance: the probe's five refusals hold with any option on. Test (to write): fichero-builder/tests/test_jail (new), one case per option over the probe's refusals.
- `agent-profiles.isolation.research-and-choice` [GAP] (#6641) — a research step that ends in a **written choice**
  and a **measured trial**, not in code: for each option, one page under `docs/contributor_manual/architecture/` with
  what it gives, what it costs and what it cannot do, then one trial per option that runs the same small step (a Python
  test, a git commit, one guard) inside it as the worker user and records wall time, set-up time, what broke, and
  whether the four behaviours below hold. The options: **`sandbox-exec` profiles per worker** (deprecated but
  present; a maintained profile under `adapters/`'s `isolation/`; already probed to have no hostname rules); **macOS
  virtual machines** on the Virtualization framework (`tart`, `lume`): a VM per lane from a base image with Xcode
  installed, so Swift work builds inside it, at the cost of a large image, a copy of Xcode per image, the two-VM
  limit per host and no GPU for MLX; **Apple's `container`** for Linux-only Python work (engine tests with no MLX, no
  Xcode); **Docker** for engine-only lanes the same way; **network egress limits** (a per-worker allow-list of hosts,
  by the packet filter for a user, by the VM's network, or by the container's) and **per-worker credentials** (a
  scoped token per lane, if any, issued by the land side and expiring with the lane; never an owner key in the
  worker's reach). The page for each says plainly what it costs **for Xcode work**: `sandbox-exec` lets `xcodebuild`
  run but the profile must allow the derived-data and toolchain paths; a macOS VM builds but carries Xcode in its
  image and its own signing state; `container` and Docker cannot build or test Swift at all, so they serve engine
  lanes only. The choice names one option per lane kind (Swift, engine, text) and is a ruling by the owner on the
  trial's rows. Acceptance: one page and one trial row per option; a trial that did not run is `not-run` with its
  reason, never a judgement; the written choice names the option per lane kind, what it gives up, and the four
  behaviours' results in a table. Test (to write): fichero-builder/tests/test_isolation_trial (new) (the trial runner's
  rows from fixture outputs; the live trials skip only by name).
- `agent-profiles.isolation.implemented` [GAP] (#6642) — the chosen option behind the one wrapper
  `dev-workflows` Step 3.2 already names, so adapters, hooks and scripts do not change when the mechanism does; the
  start path refuses when the option's own check fails (a missing profile, image or token), never falling back to
  the bare user. Four behaviours, each with its failing probe run at every start: (1) a worker **cannot read the
  owner's home, keys or another lane's tree** (a read of each is refused); (2) it **cannot push** (`git push --dry-run`
  by URL fails, and no credential helper answers); (3) it **reaches only its declared hosts** (`[isolation].hosts` per
  project, the model endpoint and the package index at most; a connect to any other host fails); (4) **Swift and
  Xcode work still builds** for the Swift lane's option (the build rung runs inside it on the build Mac). Acceptance:
  each probe's failing case is a test; an option whose probe (3) cannot be enforced is admitted only for lanes with
  no secrets in reach and the journal row says `egress: open`; the Swift lane's option builds the app once in the
  trial. Test (to write): fichero-builder/tests/test_isolation (new).

## Rulings (owner 2026-11-16, paraphrased)

- The trailer names the model by display name. Pre-2026-11-05 `Directed-By` commits pass by date floor.
- Harness order: Pi, opencode, Qwen Code, Codex CLI, Gemini CLI (Antigravity shares its adapter), goose.
- Compare harnesses and models per role; a move is a person's edit on the evidence.
- The manager role acts within the rules listed in § H; anything else is a question.
- UI tests run in a dedicated GUI user on the build Mac that the owner sets up and keeps logged in.
- The bake-off replays landed steps.
- Both MCP servers are required on every harness; a harness that cannot load them takes no lane. Other tools
  are per role and per project: a role lists only its tools.
- Workers are small: one step, a short brief, named files and tests, a diff bound.
- The builder is generic: project profile and declared workflow per project; text projects too.
- A worker's prompt and tools compose as common + role + stack (+ project): roles are stack-neutral, stacks are
  declared per project and carry the commands, runners, lint, MCP tools and rules; a stack overrides a tool set.
- The diff bound is per role, in the role profile; the text proof runs on a scratch repository; costs and tokens are
  local only, never in an issue or the repository.
- The harness state is Pydantic models over DuckDB (the database Fichero already uses; shared by builder, researcher,
  writer and the generic harness), `journal.jsonl` kept as the event log; a workflow may run on LangGraph or LangChain
  or on Fichero's own workflows and recipes, as options behind one interface.
- The work stays inside the Fichero repository for now (its spec guards, specs and tests); the repository split is a
  step kept and HELD until the owner says; Fichero Researcher comes after the Harness is solid, not soon.
- Fichero's release comes first: the Harness is a side project with one of the three worker slots.
- Worker isolation: the second user stays the baseline; a stronger, still practical option is chosen by a written
  comparison and a measured trial, then implemented behind the one wrapper; late in the order, after the adapters.

## Open questions for the owner

All three answered 2026-11-16: the diff bound is per role in the role profile, no global number; Step 4.4 uses a scratch
test repository, a real book repository later; costs and tokens stay local on 127.0.0.1 and never reach an issue or the
repository. None open.

## Build order

Smallest first; each step is one lane batch unless marked; `Depends on` defaults to the step before.

### Stage 1 — the rule, the folder, the servers, the small worker, the Swift rungs

#### Step 1.1 — the trailer: one line, one rule, every file
- Behaviours: `agent-profiles.trailer.one-line`
- Tests: fichero-builder/tests/test_trailer (new)
- Size: S
- Order: (a) the test with the four refused shapes and the one accepted; (b) `policy_hook.py` compares one exact shape
  built from MODEL and HARNESS; (c) `harness.toml`; (d) `review-checklist.md` 10, `AGENTS.md`, `harness_review.py`,
  `check_agent_commits_authored_as_claude.py`; (e) a commit with the new line lands.

#### Step 1.2 — the folder, the common prompt, assembly, the adapter interface, the Claude Code adapter
- Behaviours: `agent-profiles.folder.one-place`, `agent-profiles.prompt.common`, `agent-profiles.prompt.assembly`, `agent-profiles.adapter.interface`, `agent-profiles.adapter.claude-code`
- Tests: fichero-builder/tests/test_profiles (new), fichero-builder/tests/test_adapters (new)
- Size: M

#### Step 1.3 — jcodemunch and jdocmunch required for every worker; tool sets per role and per project
- Behaviours: `agent-profiles.mcp.required`
- Tests: fichero-builder/tests/test_mcp_servers (new)
- Size: S

#### Step 1.4 — the small-worker rule: one step, a short brief, named files and tests, a diff bound
- Behaviours: `agent-profiles.worker.small`
- Tests: fichero-builder/tests/test_small_worker (new)
- Depends on: 1.2
- Size: S

#### Step 1.5 — Swift unit and UI test rungs in the dedicated GUI user; the UI smoke on request
- Behaviours: `agent-profiles.ladder.swift-tests`, `agent-profiles.ladder.ui-smoke`
- Tests: fichero-builder/tests/test_swift_rungs (new)
- Depends on: 1.2
- Size: M

### Stage 2 — generic: project profile, workflow, run record, console, cleanup

#### Step 2.1 — the project profile, the declared workflow, the thin project prompt layer
- Behaviours: `agent-profiles.project.profile`, `agent-profiles.workflow.declared`, `agent-profiles.prompt.project-layer`
- Tests: fichero-builder/tests/test_project_profile (new), fichero-builder/tests/test_workflow (new), fichero-builder/tests/test_profiles (new)
- Depends on: 1.4
- Size: M

#### Step 2.2 — the run record
- Behaviours: `agent-profiles.run.record`
- Tests: fichero-builder/tests/test_run_record (new)
- Depends on: 2.1
- Size: S

#### Step 2.3 — the console's Runs, Compare and Bake-offs views (reconciled with `builder-console.md`)
- Behaviours: `agent-profiles.console.runs`
- Tests: fichero-builder/tests/test_console_runs (new)
- Depends on: 2.2
- Size: M

#### Step 2.4 — cleanup as the workflow's last step (#6589 item 16)
- Behaviours: `agent-profiles.cleanup.after-land`
- Tests: fichero-builder/tests/test_workflow (new)
- Depends on: 2.1
- Size: S

### Stage 3 — adapters, one per step, in the owner's order

#### Step 3.1 — the Pi adapter in the folder; Ollama and OpenAI-compatible providers through it
- Behaviours: `agent-profiles.adapter.pi`
- Tests: fichero-builder/tests/test_pi_rpc.py
- Depends on: 1.3
- Size: S

#### Step 3.2 — the opencode adapter
- Behaviours: `agent-profiles.adapter.opencode`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: M

#### Step 3.3 — the Qwen Code adapter
- Behaviours: `agent-profiles.adapter.qwen-code`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

#### Step 3.4 — the Codex CLI adapter
- Behaviours: `agent-profiles.adapter.codex-cli`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

#### Step 3.5 — the Gemini CLI / Antigravity adapter
- Behaviours: `agent-profiles.adapter.gemini-cli`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

#### Step 3.6 — the goose adapter
- Behaviours: `agent-profiles.adapter.goose`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

### Stage 4 — roles, the manager, the bake-off, the text project

#### Step 4.1 — the role profiles and the stack profiles: a worker is role × stack
- Behaviours: `agent-profiles.prompt.roles`, `agent-profiles.prompt.stacks`
- Tests: fichero-builder/tests/test_profiles (new)
- Depends on: 2.1
- Size: M
- Order: the `swift` and `python` stacks with the feature role first (one real step each), then code-review (the
  reviewer script reads its file), testing and bug-fixing on both stacks, perf and the measuring roles against
  `performance-sweep.md`'s rungs on both stacks, landing, then the text roles.

#### Step 4.2 — the built-in manager role
- Behaviours: `agent-profiles.role.manager`
- Tests: fichero-builder/tests/test_manager_role (new)
- Depends on: 4.1
- Size: M

#### Step 4.3 — the bake-off
- Behaviours: `agent-profiles.bakeoff.measured`
- Tests: fichero-builder/tests/test_bakeoff (new)
- Depends on: 2.3, 3.2, 4.1
- Size: M

#### Step 4.4 — a text project runs the generic workflow
- Behaviours: `agent-profiles.workflow.text-project`
- Tests: fichero-builder/tests/test_text_project (new)
- Depends on: 4.1
- Size: M

### Stage 5 — worker isolation (the longest steps: several trials each; after the adapters)

#### Step 5.1 — isolation research: one page and one measured trial per option, a written choice per lane kind
- Behaviours: `agent-profiles.isolation.baseline`, `agent-profiles.isolation.research-and-choice`
- Tests: fichero-builder/tests/test_isolation_trial (new), fichero-builder/tests/test_jail (new)
- Depends on: 3.6
- Size: M
- Order: (a) the trial runner and its row shape with fixtures; (b) `sandbox-exec`; (c) a macOS VM (`tart`, then `lume`
  if `tart` fails the Xcode build); (d) `container` and Docker for an engine lane; (e) egress and per-worker
  credentials on each; (f) the pages and the choice table go to the owner as a question.

#### Step 5.2 — the chosen isolation behind the wrapper, with the four probes at every start
- Behaviours: `agent-profiles.isolation.implemented`
- Tests: fichero-builder/tests/test_isolation (new)
- Depends on: 5.1
- Size: M

## Behaviour tests

| Behaviour | Step |
|---|---|
| `agent-profiles.trailer.one-line` | 1.1 |
| `agent-profiles.folder.one-place` · `prompt.common` · `prompt.assembly` · `adapter.interface` · `adapter.claude-code` | 1.2 |
| `agent-profiles.mcp.required` | 1.3 |
| `agent-profiles.worker.small` | 1.4 |
| `agent-profiles.ladder.swift-tests` · `ladder.ui-smoke` | 1.5 |
| `agent-profiles.project.profile` · `workflow.declared` · `prompt.project-layer` | 2.1 |
| `agent-profiles.run.record` | 2.2 |
| `agent-profiles.console.runs` | 2.3 |
| `agent-profiles.cleanup.after-land` | 2.4 |
| `agent-profiles.adapter.pi` · `opencode` · `qwen-code` · `codex-cli` · `gemini-cli` · `goose` | 3.1–3.6 |
| `agent-profiles.prompt.roles` · `prompt.stacks` | 4.1 |
| `agent-profiles.role.manager` | 4.2 |
| `agent-profiles.bakeoff.measured` | 4.3 |
| `agent-profiles.workflow.text-project` | 4.4 |
| `agent-profiles.isolation.baseline` · `isolation.research-and-choice` | 5.1 |
| `agent-profiles.isolation.implemented` | 5.2 |

## Changes to dev-workflows

Each bullet names a `dev-workflows.*` behaviour by its last two parts.

- In `node.worker`: "kinds `claude` and `pi`" becomes "one adapter per harness under `fichero-builder/agents/adapters/`";
  `--kind` becomes `--harness`.
- In `models.by-config`: a role row gains `harness`; the roles list is this spec's; `manager` is added; a move between
  pairs cites a bake-off.
- In `tool.check`: the Swift test rungs of § F join the build rung; `[check].red_paths` gains the project's Swift
  paths with their own runner; `[check].diff_bound` is read by the hook.
- In `run.local-parity`: "a third kind (Goose) is admitted only by one real cluster" becomes "any harness is admitted
  by its adapter's real-step row with both MCP servers, and moves a role only by the bake-off".
- In `run.worker-start-stop`: the system prompt and `--setting-sources` are passed, not only specified; the order of
  steps comes from `[workflow]`.
- In `ledger.comparison-view`: the console's Compare page is the same numbers per role × model × harness; the CLI
  view stays.
- In Step 3.2 (the sandbox chosen by test): its three candidates become the option list of § J, the choice is a
  written one per lane kind, and it moves to this spec's Stage 5 after the adapters.
- In `project.neutral`: the second project is declared by `[project]` and `[workflow]`, and a text project is the
  third.

## Documentation matrix

| Doc | Says |
|---|---|
| `docs/contributor_manual/how-fichero-is-built.md` | a worker is model × harness × profile on a declared workflow; where prompts live; role × stack; tool sets per role and stack; the diff bound per role; the bake-off rule; costs stay local |
| `harness/builder-console.md` (sibling, being drafted) | the website's pages; the Runs, Compare and Bake-offs views take their columns from here |
| `AGENTS.md` | the one trailer line; the root `agents/` folder is gone; prompts live in the builder |
| `docs/contributor_manual/review-checklist.md` | item 10 is the one trailer line |
