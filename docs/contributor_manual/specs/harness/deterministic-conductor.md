# Dev Pipeline — specs in, tested builds out, by scripts not by memory — Design Spec (#6116)

> Milestone: dev-orchestration-harness
> Manual: TBD — the contributor manual needs a "How Fichero is built" page: how a spec becomes issues, how lanes run,
> what runs on GitHub, on Xcode Cloud and on the test Macs, and what waits for the maintainer.
>
> Design-led. **Status: DRAFT 2026-10-25, for the maintainer's approval.** Supersedes the orchestration parts of
> `dev-orchestration-harness.md` (roles, dispatch) and the earlier drafts of this file. Rulings so far are under
> "Rulings". Tags: [OK] built · [PARTIAL] exists, not wired · [MISSING] not built · [BROKEN] fails today ·
> [PROPOSED] needs a ruling.

## Intent

The maintainer has an idea, decides it with Claude (Opus) as a spec, approves it, and from then on the work runs
itself: issues are filed from the spec, a coding agent (Qwen 3.8 in Pi, on OpenRouter now and a local model on a
128 GB Mac later) builds one milestone at a time in its own worktree, scripts check every result, a reviewer
reviews it, the gate runs, integration is pushed, issues close, a nightly build reaches the test devices, and a
weekly release waits only for the maintainer's yes. The maintainer follows it on one page and answers questions in
one queue, instead of chatting a lead session through each step. Today every one of those steps is an LLM lead's
judgement, so steps are forgotten: on 2026-10-25, 739 open issues were already cited by fix commits, 123 had no
milestone, a stale check-in prompt kept firing, and lanes stood idle unnoticed.

## Prior art (adopt, don't invent)

- **Our own runner** (`pipeline/`, this repo) is the engine: one state machine for an item (issue → coding →
  checks → review → candidate → gate → pushed → closed), with three faces over the same functions: a CLI, an MCP
  server (so Pi + a model, or Claude, can run it with tools that cannot skip a step), and a local web page the
  maintainer watches and works in. State lives in GitHub (issues, milestones, labels) and a local append-only
  journal; nothing a model says changes state except through a tool whose checks the code runs.
- **Bernstein** (sipyourdrink-ltd/bernstein 3.23.0) was trialled on 2026-10-25 and dropped (ruling below): of the
  31 behaviours here it supplied one (worktree per task); its gate ran outside the task's worktree, its self-upgrade
  spawned stray tasks, it priced nothing for Pi, its intent check passed an unreadable reply, and its dashboard
  rejected its own tokens. Borrowed, as ideas only: a cap and de-duplication on tasks the system spawns itself, and
  an allow-list of environment variables for the coder.
- **GitHub Actions** for everything that needs only GitHub and the repo. The repo is public, so standard
  GitHub-hosted runners (Linux and macOS) cost nothing.
- **Xcode Cloud** (included with the Apple Developer Program, 25 compute hours a month) for Apple builds, tests,
  notarized Developer ID exports and TestFlight delivery.
- Borrowed rules: OpenAI Symphony (poll the board, one isolated workspace per issue, restart a stalled agent);
  Issue-Orchestrator (re-check state independently; the agent's "done" is a claim); Aider / Ralph loops (test,
  feed the failure back, retry); fichero-skills' `fs_autoloop` (May–Sept 2026) as the counter-example: a markdown
  queue edited by the model, "done" taken from the model's report, a loop driven by prompts, no jail.
- Surveyed and not adopted: vibe-kanban (shut down 2026-04), Conductor, Superset, Claude Squad, Crystal (worktree
  GUIs, chat-driven, no machine check); OpenHands resolver, OpenCode's GitHub action (cloud runners, own agent).

## The pipeline

```
maintainer + Opus ──spec (APPROVED)──▶ spec→issues script ──▶ GitHub milestone, issues in build order
                                                                     │
   page + MCP ◀──── journal ◀──── runner (state machine) ◀── feeder (next milestone, next issues)
                                                │  one Pi + Qwen coder per milestone, several issues per context
                                                ▼
                         gates: ready check → named tests (Pro) → reviewer (Claude binding, Qwen shadow)
                                                ▼
                         candidate → full gate (Air by day, M4 by night) → push integration
                                                ▼
     GitHub Actions: close fixed issues · milestone hygiene · engine-free tests · PR checks
                                                ▼
     nightly: Xcode Cloud build + tests → dev TestFlight / dev DMG → iPhone, iPad, Mac
     weekly: release scripts → notarized DMG + Sparkle + TestFlight + site — stops for the maintainer's yes
```

## Behaviors

### Specs and issues
- `pipeline.spec-is-the-input` [PARTIAL] — work starts only from an APPROVED spec (or a bug issue); the spec
  guards (`check_spec_behaviors_are_tagged`, `check_spec_broken_has_issue`, `check_spec_milestones`) already hold
  the spec↔issue↔test binding.
- `pipeline.spec-to-issues` [MISSING] — a script files one issue per `[MISSING]`/`[GAP]`/`[BROKEN]` behaviour that
  has none, in the spec's milestone, with the behaviour id, its acceptance line and the test path to write.
- `pipeline.build-order-readable` [MISSING] — a spec's build order lists issue numbers (`(#N)` per line), held by a
  guard; the feeder follows it; without one, priority label then number.
- `pipeline.brief-lint` [MISSING] — an issue without a spec id, an acceptance line or a test path is not
  dispatched; it goes to the maintainer's queue to be written properly (by Opus with the maintainer).
- `pipeline.every-issue-has-a-milestone` [MISSING] — a ratchet: the count of open issues with no milestone only
  goes down (123 on 2026-10-25); a GitHub Action labels a new issue that has none.
- `pipeline.build-order-shape` [MISSING] (#6116) — a spec's build order has one fixed shape, so spec-to-issues is
  deterministic: `## Build order`, optional `### Stage N — title`, then `#### Step N.M — title (#NNNN)` with
  `- Behaviours:` (ids), `- Tests:` (paths), optional `- Depends on:` (earlier steps; default the one before) and
  `- Size: S | M | L`. One issue per STEP, never per behaviour: title `<spec short name> N.M: <title>`; body = the
  behaviour lines verbatim, the tests, the dependencies, a link to the section; the spec's milestone; label
  `stage:<spec>-<n>`. Filing writes `(#N)` into the heading as a commit on a branch for review, never straight to
  integration. Acceptance: `scripts/check_spec_build_order_shape.py` fails an APPROVED spec when a non-[OK]
  behaviour is in no step or in two, a step lacks Behaviours or Tests, a step is Size L, or Depends-on points
  forward; a DRAFT spec only warns. The cut into stages and steps is Opus's judgement with the maintainer, by the
  rules in `specs/_TEMPLATE.md` ("Build order"). Existing specs are not rewritten; the self-test parses
  `source/source-model.md`'s slices and reports the distance. Tests: `pipeline/tests/test_specs.py::test_build_order_parses`,
  `pipeline/tests/test_specs.py::test_build_order_guard_fails_on_orphan_behaviour`.
- `pipeline.bug-intake` [MISSING] (#6116) — a bug filed on the page, from MCP or on GitHub gets a milestone: the
  one the maintainer picked, else one the runner proposes and the maintainer confirms in the queue. A bug needs no
  spec id; it needs what was seen, the expected result and a test path, or it becomes a "write it up" queue item.
  A bug in the milestone being coded joins that list ahead of the feature issues; the `urgent` label puts it
  before the current milestone. The page shows a bug's state like any item. Tests:
  `pipeline/tests/test_feeder.py::test_bug_without_test_path_goes_to_queue`,
  `pipeline/tests/test_feeder.py::test_urgent_bug_is_ordered_first`.
- `pipeline.outside-bugs` [MISSING] (#6116) — an issue by anyone not on the config allow-list (the maintainer, the
  agent, GitHub's bots) is labelled `from-user` and goes to the queue as "triage". It is never given to a coder
  and its text never enters a model prompt until the maintainer or Opus has rewritten it into a triaged issue
  (seen, expected, test path, milestone) that links back; closing the triaged issue comments on the original.
  Reason: outside text in a prompt is a prompt-injection path. Test:
  `pipeline/tests/test_core.py::test_outside_issue_never_reaches_start`.
- `pipeline.spec-change` [MISSING] (#6116) — when a spec under `docs/contributor_manual/specs` changes on
  integration, spec-to-issues re-runs on that spec only: a new `[MISSING]`/`[GAP]`/`[BROKEN]` behaviour gets an
  issue; a changed behaviour gets a comment on its issue with the new acceptance line; a removed behaviour gets a
  comment and a "close?" queue item, never an automatic close. A coder picks the change up at its next issue (the
  runner re-reads the issue before each one, never mid-issue). The page shows "spec changed: N issues added or
  updated". Test: `pipeline/tests/test_specs.py::test_spec_change_plans_add_update_and_close_proposal` (dry run).
- `pipeline.uses-what-exists` [MISSING] (#6116) — the runner uses what the repo has and re-implements nothing.
  Specs: the 113 existing specs are adopted by reconciling, not re-filing — a dry run matches each behaviour to its
  issue by behaviour id in the issue, else `spec:<name>` label plus title, and reports matched / unmatched /
  orphans; nothing is filed in bulk; a spec's unmatched behaviours are filed only when its milestone is pointed
  at; the spec guards stay the authority and the runner calls them. Docs: a spec's `> Manual:` page is the one an
  item changing that spec's behaviour must touch (the reviewer's spec-diff rule); coder and reviewer read docs and
  specs through jdocmunch. Tests and guards are the existing scripts, wrapped, never forked (the ladder is under
  "Checks: the ladder"). Test: `pipeline/tests/test_specs.py::test_reconcile_three_real_specs_counts` (reads only).
- `pipeline.issues-and-milestones-kept-current` [MISSING] (#6116) — the runner works in the existing issues and
  milestones, never a second system. Before filing (spec-to-issues, bug intake, `verify_to_issues.sh`) it searches
  open and closed issues by behaviour id, then title, and reuses or reopens with a comment. Only existing
  milestones are used: a new one is a queue item, never created by the runner; one with every issue closed is
  proposed for closing in the queue; the no-milestone count only goes down. On GitHub: `claimed` is set while an
  item codes and removed on `failed` or `needs-maintainer`; a short comment on checked (check summary), reviewed
  (verdict) and pushed (sha); the issue closes only through close-on-push from `Fixes #N`; `Part of #N` leaves it
  open with what is left. Every write goes through one function, `--dry-run` by default in tests. Tests:
  `pipeline/tests/test_gh.py::test_every_write_goes_through_one_function_and_dry_run_writes_nothing`,
  `pipeline/tests/test_specs.py::test_filing_reuses_an_existing_issue`.

### Running the work (the runner + the feeder)
- `pipeline.feeder-picks-the-milestone` [PARTIAL] — `choose_next.py` (deterministic) picks the next milestone; it
  finds nothing today because the roadmap spine drifted; fall back to milestone due dates.
- `pipeline.one-state-machine` [MISSING] — an item moves only by the runner's transitions; each transition runs its
  own check (the ready check before review, a binding verdict before the candidate, a green gate before the push)
  and writes one journal line; a model's report never moves an item.
- `pipeline.three-faces` [MISSING] — the CLI, the MCP server and the web page call the same functions; anything the
  page can do, a Pi + model manager can do through MCP, and nothing either can do skips a check.
- `pipeline.one-coder-per-milestone` [MISSING] (#6116) — one Pi context takes several issues in a row: a stage's
  steps, or a batch of bugs grouped by the files or spec they touch. It commits once per issue (`Fixes #N`) and the
  per-item checks run per issue, so one bad issue does not sink its batch; the context carries on to the next issue
  with what it learned. A fresh context starts when the stage or batch ends or the session passes the token
  threshold in config (`context_tokens_max`, measured). The next context starts from a short handoff the runner
  writes from the journal (issues done, files touched, failures), never from the model's own summary. Test:
  `pipeline/tests/test_core.py::test_batch_of_three_issues_gives_three_commits_and_three_check_lines`.
- `pipeline.workers-in-tmux` [MISSING] (#6116) — every worker (each coder, the reviewer, the optional Pi + Qwen
  manager) is an INTERACTIVE Pi session in its own window of one tmux session `pipeline`, windows `coder-<milestone>`,
  `reviewer`, `manager`, so the maintainer can attach, watch or type. Pi is started with `--session <file>` so the
  runner reads cost, replies and idleness from that JSONL; pane text is never scraped for state. Test:
  `pipeline/tests/test_coder.py::test_worker_window_command_names_session_file`.
- `pipeline.messages` [MISSING] (#6116) — the runner sends a worker its next issue, a check's failure text, a
  verdict or the maintainer's answer by `tell` (lifted from `agent-work/status/briefs/tell.sh`: tmux send-keys,
  text, pause, Enter); long text goes in a brief file the message points at; one message, then wait for idle (read
  from the session log) before the next. Workers answer through the runner's MCP tools, so every message is in
  the journal and on the page: `report(task, text)`; `ask(task, question, options)` → a queue item whose answer is
  told back to that window; `done(task)` only REQUESTS the check transition — the runner runs the checks. Worker to
  worker goes only through the manager's `message_worker(window, text)`, logged; never directly. The maintainer and
  Opus have the same from the page and `python -m pipeline tell <window> "<text>"`. Spec-writing mode: the Pi +
  Qwen manager drafts a spec from `_TEMPLATE.md` (with the build-order shape) on a `spec/<name>` branch, runs the
  spec guards and queues "review spec draft"; approval is the maintainer's alone, on the page; until Qwen is
  measured on spec work, Opus reviews a draft first. Tests: `pipeline/tests/test_core.py::test_tell_journals_and_sends_keys`,
  `pipeline/tests/test_core.py::test_ask_queues_and_answer_is_told_to_the_right_window`,
  `pipeline/tests/test_core.py::test_done_never_moves_state_without_checks`,
  `pipeline/tests/test_core.py::test_worker_to_worker_only_through_message_worker`.
- `pipeline.tools-in-the-right-places` [MISSING] (#6116) — the coder and the reviewer find and read code through
  the jcodemunch MCP and docs and specs through the jdocmunch MCP (indexed on `docs/`). Pi loads MCP through the
  `pi-mcp-adapter` extension, so the runner gives Pi its own agent directory (`PI_CODING_AGENT_DIR=pipeline/pi-agent`)
  that loads only that adapter, those two servers, the `_shared` principles and a ponytail rules file: the coder
  gets ponytail FULL; the reviewer gets the ponytail review lens as one named check. The coder's prompt says to
  start with jcodemunch `plan_turn` and jdocmunch for the spec lines. Acceptance: the proof run's session log shows
  jcodemunch and jdocmunch tool calls. Test: `pipeline/tests/test_coder.py::test_pi_command_loads_only_the_pipeline_agent_dir`.
- `pipeline.model-per-role` [MISSING] (#6116) — the model is a config entry per role (coder, reviewer, manager):
  provider (`openrouter`, `anthropic`, or `omlx` at its local OpenAI-compatible endpoint, declared to Pi through its
  `models.json`) plus model id, so the end state — every role local through oMLX, one small model on a 16 GB Mac,
  several on the 128 GB Mac — is a config change. The machine budget counts each loaded oMLX model's RSS against
  free RAM and allows one request in flight per model unless config says more. oMLX is not run now: the config
  carries an example and the self-test loads nothing. Test: `pipeline/tests/test_coder.py::test_model_per_role_from_config`.
- `pipeline.machine-budget` [MISSING] (#6116) — the runner never overloads its machine (a 16 GB Pro now, a 128 GB
  Mac with local models later). Before any worker, check or test run it reads free memory, swap and load
  (`vm_stat`, `sysctl vm.swapusage`, `memory_pressure`) and starts the job only when the machine has room for the
  job kind's declared need (config: a cloud-model coder is small, a local model is its RSS, `gate part` is
  measured); otherwise the item waits and the page says why; N × a model's RSS stays under free RAM. Caps in
  config: coders 1; test runs 1 per machine (a FIFO lock, `pipeline.test-queue`); local model servers 1 request in
  flight per model; a cloud provider a requests-per-minute cap with backoff and jitter on 429 and 5xx, never a hot
  retry; everything the runner spawns is capped and de-duplicated. The maintainer's own Fichero comes first: while
  his engine is busy and pressure is up the runner holds new heavy work and never kills his. The page shows memory,
  swap, load and each waiting item's reason. Tests: `pipeline/tests/test_budget.py::test_item_waits_with_reason_when_memory_is_short`,
  `pipeline/tests/test_budget.py::test_429_backs_off_with_growing_delays`,
  `pipeline/tests/test_budget.py::test_second_test_run_waits_on_the_lock`,
  `pipeline/tests/test_budget.py::test_never_spawns_past_the_cap`.
- `pipeline.one-claim-label` [MISSING] — one claim convention (`claimed`) read by the feeder, the gates and the
  dashboard; `status:in-progress` and assignees are retired as locks.
- `pipeline.worktree-per-task` [MISSING] — the runner makes each task a worktree off origin/integration (`git
  worktree add`, removed with `git worktree remove`), and every check runs inside it.
- `pipeline.jailed-agent` [PARTIAL] — Pi runs with `--no-extensions` and an allow-listed environment; the worktree is the only writable path (sandbox backend or `run.sh`'s deny rules).
- `pipeline.key-per-lane` [MISSING] — the coder gets an OpenRouter key with its own credit limit, never the main
  key, passed only by environment.
- `pipeline.cost-cap` [MISSING] — the runner reads cost from Pi's session log per task and stops a task at its cap;
  the key's own OpenRouter limit is the backstop. When Qwen's budget runs out, the same task runs Claude (Sonnet)
  through Pi on the Anthropic key; a larger budget is asked for in the queue, never assumed.

### Checking the work
- `pipeline.ready-check` [OK] — `scripts/lane_ready_check.sh` (self-tested): current integration history, no
  private folders, agent author, every commit cites an issue, lint on the diff, a source change has a test change.
- `pipeline.test-red-on-base` [MISSING] — the new test fails on origin/integration and passes on the branch, run
  in a scratch worktree; a test that passes on the base proves nothing.
- `pipeline.gate-runs-in-the-worktree` [MISSING] — every check runs with the task's worktree as its directory
  (the trial's engine ran it in the project root and failed a correct fix).
- `pipeline.contract-current` [MISSING] — the gate fails when generated contract files (OpenAPI, CLI surface, Swift
  identity) are stale; the trial's correct fix did not regenerate them.
- `pipeline.test-queue` [MISSING] — one FIFO lock per test machine; small items test on the Pro; a red reruns once
  before it counts (a flaky suite does not burn a retry).
- `pipeline.retry-with-the-failure` [MISSING] — the runner retries; the retry carries the gate's failure text;
  two retries, then the next model, then the maintainer's queue.
- `pipeline.review` [PARTIAL] — the Claude reviewer's verdict binds; the Qwen shadow review runs beside it
  (`trial2/shadow/watch-reviews.sh`); once Qwen's adjudicated precision passes the bar over 30 items, small items
  pass on the machine checks plus Qwen, and Claude reviews the batch diff at the gate.
- `pipeline.ponytail-review` [PARTIAL] — the reviewer applies the ponytail lens (shortest working diff, no
  speculative code) as a named check in every review.

### Landing, closing, building, releasing
- `pipeline.quick-checks-per-item` [PARTIAL] — each item: the ready check, its own tests, red on base and green on
  the branch, and the test folders it touches (`gate part`), minutes on the Pro or Air.
- `pipeline.nightly-gate` [PARTIAL] — reviewed items merge into the night's candidate; the full engine gate runs on
  the M4 overnight; green → push integration → the nightly build; red → nothing is pushed and the page says which
  part and which item; nothing pushes main except the weekly release.
- `pipeline.rebase-after-push` [MISSING] — every live coder rebases on integration after a push; a conflict after
  the rebase stops that coder and goes to the queue.
- `pipeline.close-on-push` [PARTIAL] — a GitHub Action on push to integration runs `close_fixed_issues.py --apply`
  (the script exists and works); a `Part of #N` leaves the issue open with a comment.
- `pipeline.actions-engine-free-checks` [MISSING] — GitHub Actions runs ruff, the guard scripts that need no
  engine, the unit tests that need no models, and `lane_ready_check.sh` on every PR and push (`ci.yml` today runs on main and on pull requests, not on
  pushes to integration); Swift unit tests run there too, on the free macOS runners (no engine, no signing).
- `pipeline.xcode-cloud-builds` [PROPOSED, not now] (ruled 2026-10-25: not now; if tried later, with a prebuilt engine
  artifact from the M4, iOS TestFlight only, since a Briefcase engine rebuilt per cloud build eats the 25 hours) — Xcode Cloud builds and runs the Swift unit tests on every push to
  integration, archives Mac and iOS nightly, and delivers the dev build to TestFlight; the spike must show the
  embedded Python engine (Briefcase) can be built in `ci_post_clone.sh` within the time budget, else Xcode Cloud
  builds the app against a prebuilt engine artifact from the M4.
- `pipeline.resume-from-journal` [MISSING] — after a restart of the runner, the Pro or a test Mac, an unfinished task
  continues from its journal and worktree; finished issues and existing model results are not redone.
- `pipeline.nightly-build` [MISSING] — on the green nightly gate, built on the M4: dev DMG (notarized) and dev TestFlight; the Mac, iPhone and
  iPad get it; a red gate sends nothing and says why on the page.
- `pipeline.weekly-release` [PARTIAL] — `release-all.sh` on a schedule prepares the release (version, notes check,
  DMGs, TestFlight, GitHub release, Sparkle, site) and stops for the maintainer's yes before anything is public;
  the pre-release scan checks private docs as well as keys and paths.

### Following along
- `pipeline.dashboard` [MISSING] (#6116) — a local site (127.0.0.1 only; one HTML file with plain CSS and a little
  JS, system fonts, works in Safari) that is the main way to see AND direct the work. Live: it updates itself by
  SSE or polling every few seconds, no reload. Pages, plain links between them, each a readable filterable table:
  Specs (status, milestone, counts by tag; a spec opens to its behaviours with tags and linked issues, and its
  build order as stages and steps with each step's state); Milestones (open and closed, closed-of-total, the step
  being coded, which is pointed at); Issues (filters: open/closed, milestone, label, from-user, claimed, runner
  state; each row: title, state, links to GitHub and the spec line, journal history); Tests (tests added per item,
  red-on-base, latest checks, the nightly gate part by part with times, verify_all); Reviews (Claude's binding
  verdict beside Qwen's shadow, agreement, the running figure toward the 30-item bar); Builds and releases (last
  nightly, next weekly waiting for the yes); Workers (each tmux window, task, idle or busy, cost, last report);
  Queue (questions with option buttons, triage of outside bugs, "review spec draft", close-a-milestone proposals).
  Commands, the same functions as the CLI and MCP, none skipping a check: point at / pause / resume a milestone;
  start or stop a worker; tell a worker; file a bug (title, text, optional screenshot saved locally, milestone);
  answer a queue item; approve a spec draft; approve the weekly release. GitHub data is cached by the runner,
  refreshed every few minutes and on each transition, so the page never waits on `gh`. Stage 0 ships the minimal
  live page: items and states, workers, queue, a tell box, point-at-milestone. Tests:
  `pipeline/tests/test_web.py::test_api_endpoints_return_their_shape_from_a_fixture_journal`,
  `pipeline/tests/test_web.py::test_command_endpoints_call_the_same_functions_as_the_cli`,
  `pipeline/tests/test_web.py::test_page_loads_and_every_link_resolves`.
- `pipeline.retire-fs-skills` [MISSING] (#6116) — the old skills system leaves the repo once the runner runs work:
  `agents/` (manager-loop and worker-loop prompts, the session-start-* skills, `fs_session_start_manager`,
  `choose-next`, gardener-agent) is deleted after each skill's unique rules still in force are moved into AGENTS.md
  or this spec; AGENTS.md describes the runner (CLI, MCP, page, states, checks) and keeps the hard rules, with no
  reference to `agents/skills` or `agents/prompts`; `scripts/verify_python.sh`'s "autoloop" comment is fixed;
  `architecture/pi_agent_harness.md` is updated or marked superseded by this spec. Done outside the repo already:
  the fs_* Pi skills moved to `~/.pi/agent/skills.retired-2026-10-25/`, the Claude `fs_session` plugin disabled.
  Test: `fichero-server/tests/unit/scripts/test_no_agents_dir.py` (the folder and its references are gone).
- `pipeline.page-files-bugs` [MISSING] — the maintainer files a bug from the page (title, words, screenshot), picks
  or is offered its milestone, and it becomes a GitHub issue the feeder can take.
- `pipeline.point-at-a-milestone` [MISSING] — the maintainer sets which milestone runs next (and can pause one); the
  feeder follows that before its own order.
- `pipeline.maintainer-queue` [MISSING] — every question for the maintainer is one queue item with options; an
  answer is written back to the spec or issue and the work it unblocks resumes; no lane messages him for status.
- `pipeline.stuck-is-flagged` [MISSING] — a task past its time limit in one state is flagged on the page.
- `pipeline.runs-unattended` [MISSING] — launchd agents run the runner and the nightly and weekly schedules keep it running; no chat prompt
  has to remember a step.
- `pipeline.cost-recorded` [PARTIAL] — tokens and dollars per issue and per model (from Pi's session logs), so the open-model share is measured.

## Who does what

- **The maintainer + Claude Opus** (interactive): ideas, specs, rulings, exceptions. Later, the same role through a
  Pi + Qwen manager and the dashboard.
- **Pi + Qwen 3.8** (27B or Flash, in tight Pi with rules + checklist): coding, tests, docs, first reviews. In the
  2026-10-18 trials it wrote the right tests (6/6–7/7) and caught 3/3 planted bugs; Qwen3-coder-next missed one in
  every harness, so the model matters more than the harness.
- **The runner + scripts + GitHub Actions**: everything else.

## Rulings

- 2026-10-25 (morning): build on Bernstein. **Reversed the same day** after the round-2 trial and a review: Fichero
  writes its own runner, custom to its process (specs, milestones, issues, tests to the spec, reviews, nightly
  builds, the weekly release), visual, and drivable by Pi + a model over MCP. Tools are still adopted where they fit
  (GitHub Actions, `gh`, Pi, launchd); the runner is the small part that is ours.
- 2026-10-25: Fichero first, in this repo; a shared home (fichero-skills or a new name) only after it runs Fichero
  reliably, for the other projects in use (assistant, research_assistant).
- 2026-10-25: no OpenCode; Pi is the harness.
- 2026-10-25: never rerun a model pass whose result already exists for the same input and model; a resumed task
  continues from the runner's journal and the repo's state, it does not redo finished work.
- 2026-10-25 (pipeline questions): one coder at a time while the pipeline beds in; each item gets the quick checks
  (ready check, its own tests, the test folders it touches, on the Pro or Air, minutes); the full engine gate runs
  once a night on the M4, integration is pushed after that green gate, then the nightly dev build goes out (Mac,
  iPhone, iPad) — the nightly build is in effect a nightly release to the testers; the public release stays weekly.
  The first milestone for the Qwen coder is a guards/lint/docs one. The Claude reviewer stays binding until Qwen's
  reviews are measured over 30 items (bar: no missed HIGH, at least 90% agreement on verdicts). Xcode Cloud: not now.
  Onboarding work leaves the 230-issue `source-model` milestone; it goes with the Recipe Designer spec's milestone.

## Trial findings (Bernstein 3.23.0, 2026-10-25, #6100 and #6101)

- Worked: ticket import, a worktree per task, Pi on OpenRouter (model id `openrouter/qwen/qwen3.8-27b`), the
  signed journal; the agent's fix was correct (lint clean, 10 tests pass, red on base, green on the change) in
  226 s for US$0.09.
- Broke: the gate ran in the project root and failed the correct fix; a spawn-cooldown loop and 75 stray
  "Upgrade" tasks after the failure; no price for the model, so no budget; dashboard token auth rejected issued
  tokens (run with auth off, bound to 127.0.0.1). Round 2 works around these in configuration.
- Round 2 (#6101), with a gate wrapper: Qwen 3.8 needed three agent runs (29 min, about US$0.56) and never
  committed its own work; Claude Sonnet through Pi passed first time (5.5 min, about US$1.12); the two diffs match
  (an items envelope, contract files regenerated). Pi itself worked throughout: the coder is not the problem.
  Salvage (the patch, the gate scripts, the contract check) is in `agent-work/trial2/bernstein-salvage/`.

## Build order

Bootstrapped (ruled 2026-10-25): Stage 0 is built by hand, the smallest runner that can run one coder safely. From
Stage 1 on, the runner builds the rest of itself and Fichero through Pi coders, one step per issue, one stage per
coder context, one coder at a time. A step starts only when its dependencies are closed. The shape of this section is
`pipeline.build-order-shape`; the issue number is written into a step heading once the step is filed. Stage 0's
proof: one Stage 1 step taken through the checks by a Pi coder, review pending, nothing pushed.

### Stage 0 — the smallest safe runner (by hand)

#### Step 0.1 — the state machine and the journal
- Behaviours: `pipeline.one-state-machine`, `pipeline.resume-from-journal`, `pipeline.worktree-per-task`, `pipeline.gate-runs-in-the-worktree`
- Tests: pipeline/tests/test_core.py, pipeline/tests/test_journal.py
- Size: M

#### Step 0.2 — the per-item checks inside the worktree
- Behaviours: `pipeline.ready-check`, `pipeline.test-red-on-base`, `pipeline.quick-checks-per-item`, `pipeline.retry-with-the-failure`
- Tests: pipeline/tests/test_checks.py
- Depends on: 0.1
- Size: M

#### Step 0.3 — one coder: interactive Pi in tmux, with its tools and rules
- Behaviours: `pipeline.workers-in-tmux`, `pipeline.jailed-agent`, `pipeline.tools-in-the-right-places`, `pipeline.cost-cap`, `pipeline.cost-recorded`, `pipeline.one-coder-per-milestone`, `pipeline.machine-budget`, `pipeline.model-per-role`
- Tests: pipeline/tests/test_coder.py, pipeline/tests/test_budget.py
- Depends on: 0.1
- Size: M

#### Step 0.4 — messages, the review record, the CLI, the MCP server and the minimal live page
- Behaviours: `pipeline.messages`, `pipeline.review`, `pipeline.three-faces`, `pipeline.dashboard`, `pipeline.point-at-a-milestone`, `pipeline.maintainer-queue`, `pipeline.brief-lint`, `pipeline.feeder-picks-the-milestone`
- Tests: pipeline/tests/test_core.py, pipeline/tests/test_web.py, pipeline/tests/test_faces.py, pipeline/tests/test_feeder.py
- Depends on: 0.2, 0.3
- Size: M

### Stage 1 — GitHub and the spec become the input

#### Step 1.1 — GitHub Actions on pushes to integration
- Behaviours: `pipeline.actions-engine-free-checks`, `pipeline.close-on-push`, `pipeline.every-issue-has-a-milestone`
- Tests: .github/workflows/ci.yml, .github/workflows/close-fixed-issues.yml, .github/workflows/issue-milestone.yml (run on a test PR)
- Size: S
- TODO: Swift unit tests on a free macOS runner only once an unsigned `xcodebuild test` without the embedded engine is shown to work.

#### Step 1.2 — the build-order guard
- Behaviours: `pipeline.build-order-shape`, `pipeline.build-order-readable`
- Tests: pipeline/tests/test_specs.py, fichero-server/tests/unit/scripts/test_check_spec_build_order_shape.py
- Size: S

#### Step 1.3 — spec-to-issues and reconciliation with the existing issues
- Behaviours: `pipeline.spec-to-issues`, `pipeline.uses-what-exists`, `pipeline.issues-and-milestones-kept-current`, `pipeline.spec-is-the-input`
- Tests: pipeline/tests/test_specs.py, pipeline/tests/test_gh.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — spec changes flow to issues
- Behaviours: `pipeline.spec-change`
- Tests: pipeline/tests/test_specs.py
- Depends on: 1.3
- Size: S

#### Step 1.5 — bugs, from inside and outside
- Behaviours: `pipeline.bug-intake`, `pipeline.outside-bugs`, `pipeline.page-files-bugs`, `pipeline.one-claim-label`
- Tests: pipeline/tests/test_feeder.py, pipeline/tests/test_core.py
- Depends on: 1.3
- Size: M

### Stage 2 — the page, whole

#### Step 2.1 — specs, milestones and issues pages
- Behaviours: `pipeline.dashboard`
- Tests: pipeline/tests/test_web.py
- Depends on: 1.3
- Size: M

#### Step 2.2 — tests, reviews, workers and queue pages; stuck items
- Behaviours: `pipeline.dashboard`, `pipeline.stuck-is-flagged`, `pipeline.ponytail-review`
- Tests: pipeline/tests/test_web.py
- Depends on: 2.1
- Size: M

### Stage 3 — nights and weeks

#### Step 3.1 — the nightly gate on the M4, push, nightly build
- Behaviours: `pipeline.nightly-gate`, `pipeline.nightly-build`, `pipeline.contract-current`, `pipeline.test-queue`
- Tests: pipeline/tests/test_nightly.py
- Depends on: 0.4
- Size: M

#### Step 3.2 — rebase after push; a second coder; the lane key
- Behaviours: `pipeline.rebase-after-push`, `pipeline.key-per-lane`
- Tests: pipeline/tests/test_core.py
- Depends on: 3.1
- Size: S

#### Step 3.3 — unattended, and the weekly release
- Behaviours: `pipeline.runs-unattended`, `pipeline.weekly-release`
- Tests: pipeline/tests/test_nightly.py
- Depends on: 3.1
- Size: M

### Stage 4 — the old system leaves

#### Step 4.1 — retire agents/ and rewrite AGENTS.md
- Behaviours: `pipeline.retire-fs-skills`
- Tests: fichero-server/tests/unit/scripts/test_no_agents_dir.py
- Depends on: 0.4
- Size: S

Not in a step, by ruling: `pipeline.xcode-cloud-builds` (not now).

## Checks: the ladder

All existing scripts, wrapped, never forked; each rung records its measured time here once it has run through the
runner (ponytail: the times below are from one Pro run on 2026-10-25 with the venv; the runner re-measures).

| Rung | What | Where | Measured |
|------|------|-------|----------|
| per item | `scripts/lane_ready_check.sh` | the task's worktree | ~2 s |
| per item | the test files the spec's Test matrix and the issue name, red on base and green on the branch | worktree + a scratch base worktree | minutes |
| per item | `scripts/gate part <area>` for the folders the diff touches | worktree | minutes (not yet measured through the runner) |
| per item | the fast guards: every `scripts/check_*.py` under ~10 s with no Mac tool (all but the 13 the CI skip list names ran under 10 s; `check_docs_paths` 19 s) | worktree | ~1 min total |
| nightly | `scripts/gate` (full) and `scripts/verify_all.sh`; failures through `scripts/verify_to_issues.sh` into bug-intake | the M4 | hours |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Scripts (self-test) | y | each check can fail | `scripts/lane_ready_check.sh --self-test`, `python -m pipeline --self-test` |
| Runner (pytest) | y | no transition without its check; MCP and page call the same functions | `pipeline/tests/` |
| Backend (pytest) | y | close-on-push, spec-to-issues, brief lint | `fichero-server/tests/unit/scripts/` |
| Actions | y | workflows run on a PR | `.github/workflows/*.yml` (run on a test PR) |
| Swift / UI / MCP / CLI | n | — | — |

## Open questions

1. Who resolves a merge conflict a rebase leaves: proposed the Opus session with the maintainer, with the coder's
   diff and the conflicting commit in front of it.
