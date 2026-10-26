# Dev Pipeline — specs in, tested builds out, by scripts not by memory — Design Spec (#6116)

> Milestone: dev-orchestration-harness
> Manual: docs/contributor_manual/how-fichero-is-built.md — "How Fichero is built" (written by Stage 1: how a spec
> becomes issues, how coders run, what runs on GitHub and on the test Macs, and what waits for the maintainer).
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
one queue, instead of chatting a lead session through each step. The runner takes over everything the lead sessions
do by hand today, on schedules and triggers instead of memory: the nightly candidate, gate and push; the dev builds
to the devices; the steps toward a release up to the maintainer's yes; the watchers (a hung gate part, a stalled
worker, a CI failure, disk and memory pressure); and the cron-like jobs (close_fixed_issues after a push, backlog
sweeps, the Qwen shadow reviews, milestone hygiene). Everything specific to Fichero is one project file, so the same
runner later serves another repo or a writing project. Today every one of those steps is an LLM lead's
judgement, so steps are forgotten: on 2026-10-25, 739 open issues were already cited by fix commits, 123 had no
milestone, a stale check-in prompt kept firing, and lanes stood idle unnoticed.

## Prior art (adopt, don't invent)

- **Our own runner** (`pipeline/`, this repo) is the engine: one state machine for an item (issue → coding →
  checks → review → candidate → gate → pushed → closed), with three faces over the same functions: a CLI, an MCP
  server (so Pi + a model, or Claude, can run it with tools that cannot skip a step), and a local web page the
  maintainer watches and works in. State lives in GitHub (issues, milestones, labels) and a local append-only
  journal; nothing a model says changes state except through a tool whose checks the code runs.
- **Agentless** (deterministic localisation, then one focused repair): the runner finds the files and symbols and
  builds the brief itself, so the model makes one focused edit, which is why an issue costs a few turns, not twenty.
  **Aider's repo map** (a compact symbol map instead of whole files) and **SWE-agent's narrow tool interface** (few
  tools, each shaped for the job) are the models for the brief and for the one tool list every role shares.
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

Every behaviour names its acceptance and its test. Stage 0 behaviours are built by hand; the rest the runner builds
through coders. One behaviour sits in exactly one build-order step. Behaviours that were one function have been
merged (2026-10-25): the merged ids are listed under "Merged ids" at the end of this section.

### Specs and issues
- `pipeline.spec-to-issues` [MISSING] (#6116) — one issue per build-order STEP (never per behaviour): title
  `<spec short name> N.M: <title>`; body = the step's behaviour lines verbatim with their acceptance, the test paths,
  the dependencies and a link to the section; the spec's milestone; label `stage:<spec>-<n>`. Filing writes `(#N)`
  into the step heading as a commit on a branch for review, never straight to integration. Before filing it searches
  open and closed issues by behaviour id, then by title, and reuses or reopens with a comment. Test:
  `pipeline/tests/test_specs.py::test_spec_to_issues_files_one_issue_per_step_and_reuses_existing` (dry run).
- `pipeline.build-order-shape` [MISSING] (#6116) — a spec's build order has one fixed shape so spec-to-issues is
  deterministic: `## Build order`, optional `### Stage N — title`, then `#### Step N.M — title (#NNNN)` (the number
  once filed; the feeder follows the steps in order) with `- Behaviours:` (ids), `- Tests:` (paths), optional
  `- Depends on:` (earlier steps; the default is the step before, stopping at the stage boundary) and
  `- Size: S | M | L`. Acceptance: `scripts/check_spec_build_order_shape.py` fails an APPROVED spec when a non-[OK]
  behaviour is in no step or in two, a step has no Behaviours or no Tests, a step is Size L or has more than five
  behaviours, or Depends-on points forward; a DRAFT spec only warns. The cut into stages and steps is Opus's
  judgement with the maintainer, by the rules in `specs/_TEMPLATE.md` ("Build order"). Existing specs are not
  rewritten; the self-test parses `source/source-model.md`'s slices and reports the distance. Tests:
  `pipeline/tests/test_specs.py::test_build_order_parses`,
  `pipeline/tests/test_specs.py::test_build_order_guard_fails_on_orphan_behaviour`,
  `fichero-server/tests/unit/scripts/test_check_spec_build_order_shape.py`.
- `pipeline.brief-lint` [MISSING] (#6116) — work starts only from an APPROVED spec's step or a bug issue; an issue
  without a spec id (or the bug label), an acceptance line or a test path is not dispatched; it goes to the queue
  as "write it up" (Opus with the maintainer, later the Qwen manager). Tests:
  `pipeline/tests/test_feeder.py::test_brief_lint_names_each_missing_field`,
  `pipeline/tests/test_feeder.py::test_only_approved_spec_or_bug_is_dispatched`.
- `pipeline.bug-intake` [MISSING] (#6116) — a bug filed on the page (title, words, optional screenshot saved
  locally), from MCP or on GitHub gets a milestone: the one the maintainer picked, else one the runner proposes and
  the maintainer confirms in the queue. A bug needs no spec id; it needs what was seen, the expected result and a
  test path, or it becomes a "write it up" queue item. A bug in the milestone being coded joins that list ahead of
  the feature issues; the `urgent` label puts it before the current milestone. A bug filed by a failed build target
  or by `verify_to_issues.sh` is de-duplicated by title before filing. Tests:
  `pipeline/tests/test_feeder.py::test_bug_without_test_path_goes_to_queue`,
  `pipeline/tests/test_feeder.py::test_urgent_bug_is_ordered_first`,
  `pipeline/tests/test_web.py::test_file_bug_from_the_page_goes_through_bug_intake` (dry run).
- `pipeline.outside-bugs` [MISSING] (#6116) — an issue, or a comment, by anyone not on the profile's allow-list
  (the maintainer, the agent, GitHub's bots) is labelled `from-user` and goes to the queue as "triage". It is never
  given to a coder, and its text never enters a model prompt: the prompt builder takes only the body and the
  comments of allow-listed authors. The maintainer or Opus rewrites it into a triaged issue (seen, expected, test
  path, milestone) that links back; closing the triaged issue comments on the original. Reason: outside text in a
  prompt is a prompt-injection path. Tests: `pipeline/tests/test_core.py::test_outside_issue_never_reaches_start`,
  `pipeline/tests/test_coder.py::test_prompt_builder_rejects_from_user_text`.
- `pipeline.spec-change` [MISSING] (#6116) — when a spec under `docs/contributor_manual/specs` changes on
  integration, spec-to-issues re-runs on that spec only: a new step gets an issue; a changed step gets a comment on
  its issue with the new behaviour lines; a removed step gets a comment and a "close?" queue item, never an automatic
  close. A coder picks the change up at its next issue (the runner re-reads the issue before each one, never
  mid-issue). The page shows "spec changed: N issues added or updated". Test:
  `pipeline/tests/test_specs.py::test_spec_change_plans_add_update_and_close_proposal` (dry run).
- `pipeline.uses-what-exists` [MISSING] (#6116) — the runner uses what the repo has and re-implements nothing.
  Specs: the 113 existing specs are adopted by reconciling, not re-filing — a dry run matches each behaviour to its
  issue by behaviour id in the issue, else `spec:<name>` label plus title, and reports matched / unmatched /
  orphans; nothing is filed in bulk; a spec's unmatched steps are filed only when its milestone is pointed at; the
  spec guards stay the authority and the runner calls them. Docs: a spec's `> Manual:` page is the one an item
  changing that spec's behaviour must touch (the reviewer's spec-diff rule); coder and reviewer read docs and specs
  through jdocmunch. Tests and guards are the existing scripts, wrapped, never forked ("Checks: the ladder").
  Test: `pipeline/tests/test_specs.py::test_reconcile_three_real_specs_counts` (reads only).
- `pipeline.issues-and-milestones-kept-current` [MISSING] (#6116) — the runner works in the existing issues and
  milestones, never a second system. Only existing milestones are used: a new one is a queue item, never created by
  the runner; one with every issue closed is proposed for closing in the queue; progress (closed of total) is on the
  Milestones page; the no-milestone count only goes down. One claim convention: `claimed` is set while an item codes
  and removed on `failed` or `needs-maintainer`; `status:in-progress` and assignees are retired as locks. A short
  comment with a `<!-- pipeline:<event>:<task> -->` marker goes on checked (check summary), reviewed (verdict) and
  pushed (sha), so resume can see which comments exist; the issue closes only through close-on-push from `Fixes #N`;
  `Part of #N` leaves it open with what is left. Every write goes through one function, `--dry-run` by default in
  tests. Tests: `pipeline/tests/test_gh.py::test_every_write_goes_through_one_function_and_dry_run_writes_nothing`,
  `pipeline/tests/test_core.py::test_claimed_label_follows_the_state`,
  `pipeline/tests/test_feeder.py::test_claimed_issues_are_skipped`.
- `pipeline.github-actions` [PARTIAL] (#6116) — GitHub keeps a small, natural role, one workflow each: `ci.yml` runs ruff,
  the guard scripts that need no Mac tool, the unit tests that need no models, on pushes to integration as well as
  main and on PRs, plus `lane_ready_check.sh` on PRs (Swift unit tests stay on the Macs until an unsigned
  `xcodebuild test` without the embedded engine is shown to work on a free runner); `close-fixed-issues.yml` runs
  `close_fixed_issues.py --apply` after a push to integration (a `Part of #N` never closes); `issue-milestone.yml`
  labels a new issue with no milestone `no-milestone` and one by an outside author `from-user`. Anything more on
  GitHub needs a reason. Tests: a `test_workflows` pytest under `fichero-server/tests/unit/scripts/`, written with
  Step 1.1 (the YAML is parsed and each
  workflow's trigger, condition and command are asserted); run on a test PR.

### Running the work (the runner + the feeder)
- `pipeline.one-state-machine` [OK] — an item moves only by the runner's transitions, each in the
  states table below with its check; the transition writes one journal line; a model's report never moves an item;
  `start`, `check`, `verdict`, `candidate`, `gate`, `push`, `close` are the only paths. Test:
  `pipeline/tests/test_core.py::test_states_table_is_the_only_transition_path`.
- `pipeline.project-profile` [OK] — everything specific to Fichero lives in ONE file,
  `pipeline/projects/fichero.toml` (stdlib `tomllib`): the repo path and branches; the spec folder; the check ladder
  naming the scripts per rung; the build targets and the schedule; the milestone and label names; the worker roles
  and their models; the machine names. The runner's code names no Fichero path, script or label; the self-test greps
  `pipeline/*.py` for the project name outside comments and fails on a hit. Another project is another file
  (`pipeline/projects/example-writing.toml`: a writing project whose ladder is a word count, a citation check and
  proofreading; it loads and validates, nothing more is built for it). Tests:
  `pipeline/tests/test_config.py::test_runner_code_names_no_project_specifics`,
  `pipeline/tests/test_config.py::test_example_writing_profile_loads_and_validates`.
- `pipeline.resume-from-journal` [PARTIAL] (#6116) — the journal is append-only JSONL under `~/.local/state/pipeline/<checkout>/`; state
  is the journal replayed; an intent line precedes each side effect (commit, gh write, tell, worktree) and a done
  line follows it; on restart an item with an open intent is reconciled against the world (the `Fixes #N` commit on
  the branch, the marker in the GitHub comment, the worktree) before anything is redone, so nothing is lost or
  doubled; finished issues and existing model results are never redone. One `flock` on the journal is taken by
  whoever dispatches (launchd's runner or the CLI), so two runners never dispatch the same work. Tests:
  `pipeline/tests/test_journal.py::test_replay_gives_the_same_state`,
  `pipeline/tests/test_core.py::test_resume_after_kill_between_intent_and_done`,
  `pipeline/tests/test_journal.py::test_second_dispatcher_waits_on_the_journal_lock`.
- `pipeline.pause-all` [OK] — a kill switch: `python -m pipeline pause` (and `resume`) writes a journal
  line after which no transition starts a coder, a check or a job; running work finishes its current step. The page
  shows PAUSED. Test: `pipeline/tests/test_core.py::test_paused_runner_starts_nothing`.
- `pipeline.pinned-checks` [OK] — the checks (`scripts/lane_ready_check.sh`, `scripts/check_*`,
  `scripts/gate`, `pipeline/`) run in a SCRATCH TREE made of the task's committed HEAD with the pinned checkout's
  check files laid over it (`git worktree add --detach`, then `git checkout <pinned sha> -- <check paths>`), so a
  guard that scans `ROOT = Path(__file__).parent.parent` sees the coder's diff and never the pinned tree, uncommitted
  edits or the worktree's own copies; a coder cannot edit the check it is judged by (the runner builds itself, so
  this matters most; the trial's engine ran the gate in the project root and failed a correct fix). A diff that changes or removes a file under those paths goes to `needs-maintainer`; adding a new guard is
  allowed, since the pinned runner does not run it until the maintainer pulls it in. The runner moves to a new sha only on the
  maintainer's command, after the push. Tests: `pipeline/tests/test_checks.py::test_a_coder_change_that_breaks_a_guard_turns_the_check_red`,
  `pipeline/tests/test_checks.py::test_checks_run_from_the_pinned_checkout`,
  `pipeline/tests/test_checks.py::test_diff_touching_check_paths_needs_maintainer`,
  `pipeline/tests/test_checks.py::test_a_new_guard_may_be_added_but_no_check_changed`,
  `pipeline/tests/test_checks.py::test_checks_cwd_is_the_worktree`,
  `pipeline/tests/test_checks.py::test_a_coder_sitecustomize_cannot_green_the_guards`,
  `pipeline/tests/test_core.py::test_rewriting_own_acceptance_in_the_spec_needs_maintainer`.
- `pipeline.three-faces` [OK] — the CLI, the MCP server and the page call the same functions
  (`core.API`) and nothing skips a check. MCP tools are per role: the coder gets `report`, `ask`, `done`; the
  reviewer gets `verdict`; the manager gets `status`, `next`, `start`, `check`, `tell`, `file_bug`, `point`. Approve
  (a spec draft, the weekly release) and `answer` exist on the page and the CLI only, never over MCP: a model cannot
  answer its own question. Tests: `pipeline/tests/test_faces.py::test_cli_mcp_and_page_call_the_same_function`,
  `pipeline/tests/test_faces.py::test_mcp_has_no_approve_or_answer_tool`.
- `pipeline.feeder-picks-the-milestone` [PARTIAL] (#6116) — the milestone the maintainer pointed at, else the first
  milestone with an open step whose dependencies are closed (`choose_next.py` is retired with `agents/ROADMAP.md`);
  within it urgent bugs, bugs, then steps in build order, then priority label, then number. Test:
  `pipeline/tests/test_feeder.py::test_pointed_milestone_wins_then_build_order`.
- `pipeline.one-coder-per-milestone` [PARTIAL] (#6116) — one Pi context takes several issues in a row (a stage's
  steps, or bugs grouped by the files or spec they touch). Each issue gets its own commit range on the branch and its
  own per-item checks; a failed item blocks the later ones on that branch until it is fixed or dropped, and the
  candidate lands the green ranges without the red one (cherry-picked, in order). The context carries on to the next
  issue with what it learned; a fresh context starts when the stage or batch ends or the session passes
  `context_tokens_max` (measured). The next context starts from a short handoff the runner writes from the journal
  (issues done, files touched, failures), never from the model's own summary. Test:
  `pipeline/tests/test_core.py::test_batch_of_three_issues_gives_three_commits_and_three_check_lines`.
- `pipeline.worktree-per-task` [OK] — each task is a worktree off origin/integration at
  `.worktrees/pipeline/<task>` (`git worktree add`, removed only with `git worktree remove`). Test:
  `pipeline/tests/test_core.py::test_worktree_is_made_off_base_and_removed_with_git`.
- `pipeline.jailed-agent` [PARTIAL] (#6116) — Pi runs with `--no-extensions` plus only the adapter path, in an
  allow-listed environment (PATH, HOME, TERM, LANG, the agent dir, `PIPELINE_WORKER`); no runner path is in that
  environment: the worker's MCP server is a wrapper generated under the state dir (outside every worktree) and put
  on PATH; the CLI refuses the runner's controls (`verdict`, `answer`, `start`, `check`, `tell`, `pause`, `point`,
  `reset`) from a shell that carries `PIPELINE_WORKER`; the generated wrapper names no state path (the MCP server
  resolves it alone). Plainly: until the write jail exists this is a CONVENTION, not a boundary — the worker runs as
  the same user, so a shell inside it can unset the mark, read the wrapper or derive the default state dir from
  HOME and reach the journal. Nothing may consume `reviewed` (Stage 3) before the jail is real. The key is a lane key with its own credit limit
  (`~/.config/<provider>/key-lane`, else the main key), read from its file by the worker wrapper into the one
  variable Pi expects; the runner never holds, prints, logs or writes it. Tests:
  `pipeline/tests/test_coder.py::test_env_allow_list_drops_everything_else`,
  `pipeline/tests/test_coder.py::test_runner_never_reads_the_key_and_prefers_the_lane_key`,
  `pipeline/tests/test_coder.py::test_worker_env_carries_no_runner_path_only_a_generated_wrapper_on_path`,
  `pipeline/tests/test_faces.py::test_a_worker_shell_cannot_run_the_runners_controls`.
- `pipeline.workers-in-tmux` [PARTIAL] (#6116) — every worker (each coder, the reviewer, later the Pi + Qwen
  manager) is an INTERACTIVE Pi session in its own window of one tmux session `pipeline` (windows `coder-<task>`,
  `reviewer`, `manager`, `jobs`), so the maintainer can attach, watch or type. Pi gets `--session-dir` per task so
  the runner reads cost, replies and idleness from its JSONL; pane text is never scraped for state; a lock per
  window serialises `tell` with anyone typing. A worker is idle only after it has ANSWERED the latest message: a new
  assistant turn (more turns than before the tell) that ended with no tool call pending. The cost cap stops the
  worker (Escape, then the window is killed) and a window that died no longer counts toward the coder cap. An API
  error on the latest turn is read from Pi's structured error, never from prose: a passing one (5xx, overloaded, a
  timeout) backs off with jitter and is looked at again, up to four times; a 4xx other than 402/429 stops the item
  at once as `failed`; 402/429 is `rate-limited` and the fallback list moves on. Test: `pipeline/tests/test_coder.py::test_worker_window_command_names_session_dir`.
- `pipeline.messages` [OK] — the runner sends a worker its next issue, a check's failure text, a
  verdict or the maintainer's answer with `tell` (lifted from `agent-work/status/briefs/tell.sh`: tmux send-keys,
  text, pause, C-m); the send is not trusted: delivery is confirmed by a new user turn in the session log within
  30 s, else C-m goes again (three times) and the page flags the worker "message not delivered" (three lanes sat
  idle for hours on 2026-10-25 with text left in the input box); long text goes in a brief file the message points
  at; one message, then wait for idle. Idle =
  the last assistant turn in the session JSONL ended (`stop`/`end_turn`) with no tool call pending. Workers answer
  through the runner's MCP tools, so every message is in the journal and on the page: `report(task, text)`;
  `ask(task, question, options)` → a queue item whose answer is told back to that window; `done(task)` only REQUESTS
  the check transition — the runner runs the checks. Workers never message each other (v1 runs one coder). The
  maintainer and Opus have `tell` from the page and `python -m pipeline tell <window> "<text>"`. Tests:
  `pipeline/tests/test_core.py::test_tell_journals_and_sends_keys`,
  `pipeline/tests/test_core.py::test_ask_queues_and_answer_is_told_to_the_right_window`,
  `pipeline/tests/test_core.py::test_done_never_moves_state_without_checks`,
  `pipeline/tests/test_coder.py::test_idle_is_read_from_the_session_jsonl`.
- `pipeline.spec-writing-mode` [MISSING] (#6116) — the maintainer asks the Pi + Qwen manager for a spec draft: it
  reads the existing specs and docs with jdocmunch, writes to `_TEMPLATE.md` (with the build-order shape) on a
  `spec/<name>` branch, runs the spec guards and queues "review spec draft". Approval is the maintainer's alone, on
  the page; an approved spec flows into spec-to-issues; until Qwen is measured on spec work, Opus reviews a draft
  first. Test: `pipeline/tests/test_core.py::test_spec_draft_queues_review_and_only_the_page_approves`.
- `pipeline.tools-in-the-right-places` [PARTIAL] (#6116) — the coder and the reviewer find and read code through
  the jcodemunch MCP and docs and specs through the jdocmunch MCP (indexed on `docs/`). Pi loads MCP through the
  `pi-mcp-adapter` extension, so the runner gives Pi its own agent directory (`PI_CODING_AGENT_DIR=pipeline/pi-agent`)
  that loads only that adapter, those two servers plus the runner's own, the `_shared` principles and a ponytail
  rules file: the coder gets ponytail FULL; the reviewer gets the ponytail review lens as one named check. The
  coder's prompt makes the first step a REQUIRED `jdocmunch_search_sections` for the item's spec id (plus
  `plan_turn` for the code) followed by a `pipeline_report` of what it found; when the session log shows no such
  call by the first `done`, the item gets a note "tools unused" — information, never a failure (Qwen 3.8 made 0
  such calls in the first two proof runs). The brief also forbids the coder to change its own acceptance (the text of its
  behaviour lines and of its step's Behaviours/Tests lines, compared with the status tag and `(#N)` stripped, so
  flipping [MISSING] to [OK] is allowed): such a diff is a pinned-checks red; `ask` instead.
  Tests:
  `pipeline/tests/test_coder.py::test_pi_command_loads_only_the_pipeline_agent_dir`,
  `pipeline/tests/test_coder.py::test_session_fixture_shows_jcodemunch_and_jdocmunch_calls`,
  `pipeline/tests/test_coder.py::test_reviewer_prompt_carries_the_ponytail_lens`.
- `pipeline.worker-roles` [PARTIAL] (#6116) — the worker is a config entry per role (coder, coder-small, reviewer,
  manager), one ORDERED list each: kind `pi` with provider (`openrouter`, `anthropic`, or `omlx` at its local
  OpenAI-compatible endpoint, declared to Pi in `pipeline/pi-agent/models.json`) plus model id. Ruled 2026-10-25
  (evening): every role runs on the Anthropic API through Pi — coder claude-sonnet-5-5, coder-small claude-haiku-5-5,
  reviewer claude-sonnet-5-5 (owner 2026-10-25: every worker is Sonnet or Haiku), the key from `~/.config/anthropic/key` passed only through env by the worker wrapper;
  Qwen stays configured but off; a `claude-code` kind (Claude Max) was built and parked on the claude-code-worker branch.
  Known limit, accepted for now: the Pi worker's jail is a convention — it can write the shared git common dir and
  `config.worktree`; the runner's own git runs with `core.hooksPath=/dev/null` and `core.fsmonitor=false` so a
  planted hook or monitor never runs in the runner, and the checks' scratch trees live under the state dir. One list serves
  every fallback: a cost-cap stop, a credit or quota error (402, 429, "insufficient"), two failed retries and a
  Claude Code usage limit all move the role to the next entry; after the last entry the item goes to the queue,
  which asks for budget, never assumes it. A `claude-code` worker is an interactive `claude` in its own tmux window
  with cwd the task worktree; its worktree-local Claude Code settings file sets the model, the MCP servers (jcodemunch,
  jdocmunch, the runner's own), the ponytail plugin and the lanes' permission mode; replies and idleness come from
  its JSONL under `~/.claude/projects/<encoded cwd>/`; its tokens are recorded without a price. Both kinds get the
  same prompt, tools, checks and journal. The end state — every role local through oMLX, one small model on a 16 GB
  Mac, several on the 128 GB Mac — is a config change; oMLX is not run now, the config carries an example and the
  self-test loads nothing. Tests: `pipeline/tests/test_coder.py::test_one_fallback_list_serves_cost_quota_and_retries`,
  `pipeline/tests/test_coder.py::test_worker_kind_selection_and_fallback_on_rate_limit`,
  `pipeline/tests/test_coder.py::test_idle_state_from_fixture_jsonl_of_each_kind`,
  `pipeline/tests/test_coder.py::test_model_per_role_from_config`.
- `pipeline.cost-cap` [OK] — the runner sums `message.usage.cost.total` from Pi's session JSONL per
  task while the coder runs and stops the SESSION at `cost_cap_usd` (US$5 per coder or reviewer window; the page
  shows dollars per issue, the session's cost over the issues it finished — step 1.2 cost US$6.40 over four rounds,
  far too much for one small guard); a DAILY cap across every item and role (`daily_cap_usd`, US$25, summed from
  the journal's cost lines) refuses `start`
  and `review`, stops a running item as `rate-limited` ("daily cap"), and lifts only with the next day or the
  maintainer's `resume --raise-cap <usd>` (journaled); the page shows today's spend against the cap. Items drain
  one at a time, sequentially: `start 6140 6139` runs them in order, each checked before the next. Tokens and dollars are recorded per issue and per model, so the open-model share is measured. Tests:
  `pipeline/tests/test_coder.py::test_cost_parser_on_redacted_real_sample`,
  `pipeline/tests/test_coder.py::test_cost_cap_stops_the_task`,
  `pipeline/tests/test_coder.py::test_cost_is_recorded_per_issue_and_model`.
- `pipeline.retry-with-the-failure` [OK] — a failed check is told to the coder with the failure text;
  `retries` (2) retries, then the fallback list, then the queue. Test:
  `pipeline/tests/test_core.py::test_failed_check_retries_twice_then_needs_maintainer`.
- `pipeline.machine-budget` [PARTIAL] (#6116) — Stage 0 hard-codes: coders 1, one test run at a time (a FIFO
  `flock`), and a free-memory check (`vm_stat` pages free + speculative + purgeable, `memory_pressure` not critical)
  before a coder, a check or a test run; below the job kind's need the item waits with its reason in the journal.
  Later: `sysctl vm.swapusage` and load; per-kind needs in the profile (a cloud coder small, a local model its RSS,
  `gate part` measured; N × a model's RSS under free RAM, one request in flight per oMLX model); the maintainer's
  engine first — the signal is the profile's `owner_process` above 0 % CPU in `ps` while pressure is not normal, and
  then the runner holds new heavy work and never kills his; a cloud provider gets a requests-per-minute cap and
  backoff with full jitter on 429 and 5xx; everything spawned is capped and de-duplicated. Tests:
  `pipeline/tests/test_budget.py::test_item_waits_with_reason_when_memory_is_short`,
  `pipeline/tests/test_budget.py::test_429_backs_off_with_growing_delays`,
  `pipeline/tests/test_budget.py::test_second_test_run_waits_on_the_lock`,
  `pipeline/tests/test_budget.py::test_never_spawns_past_the_cap`,
  `pipeline/tests/test_budget.py::test_owner_engine_busy_signal`.
- `pipeline.batch-session` [MISSING] (#6116) — the runner does what the lead and two Sonnet workers did by hand, as a
  FIXED ROSTER of long-lived tmux workers: the lead is scripts (no model), plus two coders, one reviewer and one
  bug-intake worker. Each coder is pinned to one milestone; the feeder keeps its queue topped up with that
  milestone's open issues in build order, two or three briefs ahead, and hands the next brief the moment the worker
  says done or goes idle; issues touching the same files go into one brief. The runner PRE-COMPUTES every brief so the
  worker edits and does not explore: the issue text, the spec lines it cites, the files and symbols to touch (from
  jcodemunch, or a stdlib grep fallback when it is absent) and the failing or new test to write first. Checks run by
  scripts; only a failure goes back to the worker, as capped retry text. `pipeline_done(task, issue, residue)` per
  issue journals the sha and the usage so far and triggers THAT issue's checks while the worker moves on; the
  per-issue turns, tokens and dollars are the difference between two done lines. A profile budget per issue (turns
  and tokens, e.g. 10 turns / 150k tokens) is flagged on the page when exceeded, never silently raised. Context
  carries across issues in one worker; near full (`batch_end_pct`) the runner writes a short handoff note from the
  journal (issues done, files touched, failures; never a transcript replay) and a fresh worker takes the milestone
  on. A worker that has nothing ready PARKS: the window stays with no model calls, and a new issue of the same kind
  wakes it with only the new brief while its context has room and it has idled less than `park_ttl` (profile, 30 min);
  never more parked than the machine budget; the page shows parked workers. One Sonnet reviewer reviews per
  milestone batch. Cost target: per issue, cheaper than today's lead plus two Sonnet workers, never a bigger fleet.
  Tests: `pipeline/tests/test_core.py::test_batch_done_per_issue_checks_while_the_worker_moves_on`,
  `pipeline/tests/test_core.py::test_batch_ends_at_the_context_budget_with_a_handoff_note`,
  `pipeline/tests/test_core.py::test_parked_worker_is_woken_for_the_same_kind_within_park_ttl`,
  `pipeline/tests/test_core.py::test_brief_carries_spec_lines_files_and_the_test_to_write`.
- `pipeline.prompt-cache` [MISSING] (#6116) — every prompt is laid out as a stable prefix then a variable tail, so
  Anthropic prompt caching (cache_control through Pi — Pi 0.75.5's Anthropic provider sets it, and its OpenAI-style
  provider passes it for Anthropic models on OpenRouter) and an oMLX/llama prefix KV cache both hit: the order is
  tools, system prompt, the profile's rules, the milestone brief, then the per-issue and retry tail. The tool list is the
  same, in the same order, for every role (role differences come from permissions or the profile, never a different
  MCP tool set); the system prompt holds no timestamps, task ids or worker names — those go in the tail; when several
  workers start together, one starts, its first reply is awaited (the cache written), then the rest (staggered starts). Provider-neutral:
  cached-token counts are read from each provider's usage (Anthropic cache_read/cache_creation, Pi's cacheRead/cacheWrite,
  OpenRouter's cached_tokens, oMLX whatever it reports, else 0) into one journal field per session, as cache_read, cache_write and fresh, and the page shows
  the hit rate; for OpenRouter the profile pins the provider order per model so one Qwen provider keeps the cache
  warm; oMLX runs one long-lived server per model (a profile entry, not built). Models are named by tier: each provider has a big and a small model (Anthropic sonnet and haiku; OpenRouter a big and a cheaper small Qwen, enabled = false; oMLX the same later), roles name big or small, so switching provider is one profile line. Non-interactive model work (batch
  reviews, sweeps, triage) may go through Anthropic's Message Batches API at half price behind a profile flag, off by
  default. Tests: `pipeline/tests/test_coder.py::test_cache_tokens_are_read_from_each_providers_usage`,
  `pipeline/tests/test_core.py::test_brief_is_a_stable_prefix_then_the_issue_tail`.
- `pipeline.schedule` [MISSING] (#6116) — the runner takes over everything the lead sessions did by hand, on
  schedules and triggers: a `schedule` table in the profile, each entry a name, a when (cron, or `on:push`,
  `on:gate-green`, `on:idle`), the job (an existing script, run through the runner so it gets the budget, the
  journal and the page) and a machine (pro, air, m4 over ssh). A launchd agent starts the runner at login and keeps
  it running; the runner fires the schedule; a missed run fires once on wake, never N times; output goes to the
  `jobs` tmux window; the page lists the schedule with each job's last result. Watchers are schedule entries too: a
  hung gate part, a stalled worker, a CI failure on Actions, disk and memory pressure. Tests:
  `pipeline/tests/test_schedule.py::test_missed_run_fires_once_on_wake`,
  `pipeline/tests/test_schedule.py::test_event_entries_fire_on_their_event`,
  `pipeline/tests/test_schedule.py::test_launchd_plist_runs_the_runner`.

### Checking the work
- `pipeline.ready-check` [OK] — `scripts/lane_ready_check.sh` (self-tested): current integration history, no
  private folders, agent author, every commit cites an issue, lint on the diff, a source change has a test change.
  Test: `scripts/lane_ready_check.sh --self-test`.
- `pipeline.test-red-on-base` [OK] — the branch's changed or new test files are copied into a scratch
  worktree at origin/integration and must fail there, and must pass on the branch; a test that passes on the base
  proves nothing. Tests: `pipeline/tests/test_checks.py::test_red_on_base_fails_a_test_that_passes_on_base`,
  `pipeline/tests/test_checks.py::test_red_on_base_passes_a_real_fix`.
- `pipeline.quick-checks-per-item` [PARTIAL] (#6116) — each item, in order, stopping at the first red: the ready check,
  the test files the spec's Test matrix and the issue name (red on base, green on the branch), `scripts/gate part`
  for the areas the diff touches, the fast guards, and on an engine diff the contract guards
  (`check_openapi_route_set_current`, `check_contract_identity_current`, `check_mcp_generated_current`, so stale
  generated files fail); minutes on the Pro or Air. One FIFO lock per test machine; a red reruns once before it
  counts (a flaky suite does not burn a retry). Tests: `pipeline/tests/test_checks.py::test_run_all_records_each_rung`,
  `pipeline/tests/test_checks.py::test_contract_guards_run_on_an_engine_diff`,
  `pipeline/tests/test_checks.py::test_red_reruns_once_before_it_counts`.
- `pipeline.review` [PARTIAL] (#6116) — a verdict is `verdict(issue, sha, READY|NOT_READY, by, findings)`; a short sha
  is resolved with `rev-parse`; it binds only from the reviewer role and only when the sha is the worktree's live
  head AND the sha of the item's last check AND that check was green: a red check sends a `checked` or `reviewed`
  item back to `coding`, so a READY can never bind over a red (re-review HIGH N1). A binding NOT_READY sends the item back
  to coding with the findings as its retry text and counts an attempt; `reset <issue>` zeroes attempts the runner
  itself caused; `retry <issue>` runs the item again from the start arguments its record keeps (task, base,
  from_file), with the red check's or the review's text as the brief's failure section, on the fallback list's next
  worker after a rate-limited stop; it refuses a record without start arguments and names the `repair` to run.
  `repair <issue> --base --from-file --since` corrects a record by APPENDING journal lines with a note; nobody edits
  the journal by hand. An unfiled step run from a local file is keyed `<number>@<task>`, so several steps may share
  "Part of #N" and each is its own item. Claude's verdict binds; the Qwen
  shadow runs beside it (`trial2/shadow/watch-reviews.sh`); once Qwen's precision passes the bar over 30 items
  (counted by hand until it matters: no missed HIGH, 90 % agreement), small items pass on the machine checks plus
  Qwen and Claude reviews the batch diff at the gate. The reviewer applies the ponytail lens (shortest working diff,
  no speculative code) as one named check, from `pipeline/pi-agent/rules/ponytail-reviewer.md`, beside correctness,
  the spec diff and security. `python -m pipeline review <item>` runs it: a Pi window (role reviewer) told a brief with
  the item's diff range, spec lines and check results, blocking until its `pipeline_verdict` for the checked head is
  in the journal; its cost counts toward the item's cap. Tests: `pipeline/tests/test_core.py::test_verdict_only_from_reviewer_for_current_sha`,
  `pipeline/tests/test_core.py::test_new_commit_voids_the_verdict`.

### Landing, closing, building, releasing
- `pipeline.nightly-gate` [PARTIAL] (#6116) — reviewed items merge into the night's candidate; the full engine gate runs on
  the M4 overnight; green → push integration → the nightly targets (dev DMG plus both TestFlights; Mac, iPhone and
  iPad get the build); red → nothing is pushed or built and the page says which part and which item; nothing pushes
  main except the weekly release. Tests: `pipeline/tests/test_nightly.py::test_red_gate_pushes_nothing_and_names_the_part`,
  `pipeline/tests/test_nightly.py::test_nightly_build_only_after_green_gate`.
- `pipeline.closes-issues` [MISSING] (#6116) — the runner closes issues and milestones, properly, and never a second
  closer: when an item's commit lands on integration with its checks green, `scripts/close_fixed_issues.py` (the one
  closer, also the close-fixed-issues Action's) closes the issue with a comment naming the sha and the checks; a
  dry-run line goes in the journal before each close; a worker-reported residue (part of the issue not done) updates
  the issue body with what is left and leaves it open; a milestone closes when its last open issue closes; the page
  shows what was closed today. Tests: `pipeline/tests/test_core.py::test_landing_closes_through_the_one_closer_after_a_dry_run_line`,
  `pipeline/tests/test_core.py::test_a_residue_leaves_the_issue_open_with_what_is_left`.
- `pipeline.rebase-after-push` [MISSING] (#6116) — every live coder rebases on integration after a push; a conflict
  after the rebase stops that coder and goes to the queue (resolved by the Opus session with the maintainer). Test:
  `pipeline/tests/test_core.py::test_rebase_conflict_stops_the_coder_and_queues`.
- `pipeline.xcode-cloud-builds` [PROPOSED, not now] (ruled 2026-10-25: not now; if tried later, with a prebuilt engine
  artifact from the M4, iOS TestFlight only, since a Briefcase engine rebuilt per cloud build eats the 25 hours) —
  Xcode Cloud builds and runs the Swift unit tests on every push to integration, archives Mac and iOS nightly, and
  delivers the dev build to TestFlight.
- `pipeline.build-targets` [MISSING] (#6116) — each build target is its own schedule job wrapping the existing
  release scripts (`release-all.sh` and its parts): the dev DMG (notarized, `--dev`); iOS/iPad TestFlight; Mac
  TestFlight / the App Store build (#6112: its archive's engine sits in Contents/Resources, not Helpers); the
  Developer ID DMG and Sparkle; the GitHub release; the site. Each target's result (uploaded, build number,
  processed, or failed with the reason) shows on the Builds page; a failed target files a bug through bug-intake,
  de-duplicated, and never blocks the other targets. Test:
  `pipeline/tests/test_nightly.py::test_failed_target_files_one_bug_and_the_others_run`.
- `pipeline.weekly-release` [PARTIAL] (#6116) — on its schedule the weekly release runs every target and stops for the
  maintainer's yes (on the page or the CLI, never over MCP) before anything public: the GitHub release, Sparkle, the
  product site (tubb.ca/apps/fichero, appcast, release page), the App Store submission; the pre-release scan checks
  private docs as well as keys and paths. The docs site (MkDocs) is its own schedule job: it refreshes after a green
  push, built from a clean checkout of the pushed sha, never a working tree (a prior deploy published untracked
  private docs/ pages), after the scan for private paths. Tests:
  `pipeline/tests/test_nightly.py::test_weekly_release_waits_for_the_yes_before_public_targets`,
  `pipeline/tests/test_nightly.py::test_docs_deploy_builds_from_a_clean_checkout_of_the_sha`.

### Following along
- `pipeline.dashboard-minimal` [OK] — one local page (127.0.0.1 only; one HTML file, plain CSS, a
  little JS, system fonts, Safari) with sections: items and their states, workers (window, task, idle or busy,
  cost, last report), the queue with an answer box, a tell box per worker, point-at-milestone, pause and resume,
  file a bug, the machine's memory. It polls `/api/state` every few seconds. Every POST carries a token minted per
  launch and embedded in the page, and an `Origin` check, so no other site open in Safari can drive it. Tests:
  `pipeline/tests/test_web.py::test_api_endpoints_return_their_shape_from_a_fixture_journal`,
  `pipeline/tests/test_web.py::test_command_endpoints_call_the_same_functions_as_the_cli`,
  `pipeline/tests/test_web.py::test_post_without_token_or_with_foreign_origin_is_refused`.
- `pipeline.dashboard-pages` [MISSING] (#6116) — the site grows pages with plain links and filterable tables:
  Specs (status, milestone, counts by tag; a spec opens to behaviours, linked issues, build order with step states);
  Milestones (open and closed, closed-of-total, the step being coded, which is pointed at); Issues (filters:
  open/closed, milestone, label, from-user, claimed, runner state; links to GitHub and the spec line, journal
  history); Tests (tests added per item, red-on-base, latest checks, the nightly gate part by part with times,
  verify_all); Reviews (binding and shadow verdicts, agreement); Builds and releases (last nightly, next weekly, the
  schedule with last results); Workers; Queue (option buttons, triage, "review spec draft", close-a-milestone
  proposals). An item longer than `stuck_minutes` (profile, 45) in one state is flagged. Commands: start or stop a
  worker, file a bug with an optional screenshot saved locally, approve a spec draft, approve the weekly release.
  GitHub data is cached by the runner, refreshed every few minutes and on each transition. Tests:
  `pipeline/tests/test_web.py::test_page_loads_and_every_link_resolves`,
  `pipeline/tests/test_core.py::test_item_past_stuck_minutes_is_flagged`.
- `pipeline.point-at-a-milestone` [PARTIAL] (#6116) — the maintainer sets which milestone runs next, and can pause
  or resume one; the feeder follows that before its own order. Test:
  `pipeline/tests/test_core.py::test_point_is_journaled_and_read_by_the_feeder`.
- `pipeline.maintainer-queue` [PARTIAL] (#6116) — every question for the maintainer is one queue item with options;
  the answer is written back (told to the worker, or into the spec or issue) and the work it unblocks resumes; no
  lane messages him for status. Test: `pipeline/tests/test_core.py::test_ask_queues_and_answer_is_told_to_the_right_window`.
- `pipeline.retire-fs-skills` [MISSING] (#6116) — the old skills system leaves the repo once the runner runs work:
  `agents/` (manager-loop and worker-loop prompts, the session-start-* skills, `fs_session_start_manager`,
  `choose-next`, gardener-agent) is deleted after each skill's unique rules still in force are moved into AGENTS.md
  or this spec; AGENTS.md describes the runner (CLI, MCP, page, states, checks) and keeps the hard rules, with no
  reference to `agents/skills` or `agents/prompts`; `scripts/verify_python.sh`'s "autoloop" comment is fixed;
  `architecture/pi_agent_harness.md` is updated or marked superseded by this spec. Done outside the repo already:
  the fs_* Pi skills moved to `~/.pi/agent/skills.retired-2026-10-25/`, the Claude `fs_session` plugin disabled.
  Test: a `test_no_agents_dir` pytest under `fichero-server/tests/unit/scripts/`, written with Step 4.1.

### Merged ids (2026-10-25, for readers of the earlier drafts)
`journal-lock` → `resume-from-journal` · `gate-runs-in-the-worktree` → `pinned-checks` · `build-order-readable` →
`build-order-shape` · `spec-is-the-input` → `brief-lint` · `page-files-bugs` → `bug-intake` · `one-claim-label` →
`issues-and-milestones-kept-current` · `every-issue-has-a-milestone`, `close-on-push`, `actions-engine-free-checks`
→ `github-actions` · `key-per-lane` → `jailed-agent` · `fallback-list`, `model-per-role`, `worker-kinds` →
`worker-roles` · `cost-recorded` → `cost-cap` · `ponytail-review` → `review` · `contract-current`, `test-queue` →
`quick-checks-per-item` · `nightly-build` → `nightly-gate` · `site-updates` → `weekly-release` · `runs-unattended` →
`schedule` · `stuck-is-flagged` → `dashboard-pages`.

## States

| From | To | Transition | Check the code runs | Test |
|------|----|-----------|---------------------|------|
| — | queued | `start` | brief lint passes; author allow-listed; not paused; coder cap and free memory | `test_core.py::test_outside_issue_never_reaches_start`, `test_paused_runner_starts_nothing` |
| queued | coding | `start` | worktree made off the base; worker window up; brief told | `test_core.py::test_worktree_is_made_off_base_and_removed_with_git` |
| coding | checked | `check` (or `done` → `check`) | ready check, red-on-base, named tests, gate part, fast guards, contract guards — all green, from the pinned checkout, in the worktree | `test_core.py::test_done_never_moves_state_without_checks` |
| coding | coding | `check` red | attempt < retries: failure text told to the coder | `test_core.py::test_failed_check_retries_twice_then_needs_maintainer` |
| coding | needs-maintainer | `check` red | attempts exhausted; or the diff changes a pinned check, adds a file that would run before the checks (`sitecustomize.py`, `.pth`, a stray `conftest.py`, a stdlib-named module at `scripts/` or any `python_path` root), or rewrites the item's own acceptance in the spec (a `[TAG]` flip or an added `(#N)` is not a rewrite) | `test_checks.py::test_diff_touching_check_paths_needs_maintainer` |
| coding | rate-limited | worker log | quota / credit / usage-limit line; the role's list moves on | `test_coder.py::test_one_fallback_list_serves_cost_quota_and_retries` |
| coding | waiting | budget | memory or cap refused; reason journaled | `test_budget.py::test_item_waits_with_reason_when_memory_is_short` |
| checked | reviewed | `verdict` | READY from the reviewer role, sha = live head = checked sha | `test_core.py::test_verdict_only_from_reviewer_for_current_sha` |
| checked, reviewed | coding | `verdict` NOT_READY (binding) | the findings become the retry text; counts an attempt; `start` resumes | `test_core.py::test_not_ready_sends_the_item_back_to_coding_with_the_findings` |
| checked | checked | `check` | a re-check at a new head; a commit landing mid-check is red (`head-moved`) | `test_core.py::test_a_commit_landing_mid_check_is_red` |
| checked, reviewed | coding | `check` red | a red check at a new head demotes the item; READY cannot bind over it | `test_core.py::test_a_red_check_demotes_checked_and_ready_does_not_bind` |
| reviewed | checked | new commit | the verdict is voided | `test_core.py::test_new_commit_voids_the_verdict` |
| reviewed | candidate | `candidate` | reviewed; range cherry-picks cleanly onto the night's candidate (Stage 3) | `test_nightly.py` |
| candidate | gated | `gate` | the full gate green on the M4 (Stage 3) | `test_nightly.py::test_red_gate_pushes_nothing_and_names_the_part` |
| gated | pushed | `push` | gated; the push is its own step | `test_nightly.py` |
| pushed | closed | close-on-push | `Fixes #N` on integration | `test_workflows.py` |
| (runner) | paused | `pause` | — (running steps finish; nothing new starts) | `test_core.py::test_paused_runner_starts_nothing` |
| needs-maintainer, failed, rate-limited | coding | `start` | the maintainer resumes; the brief carries the retry text; `reset` zeroes runner-caused attempts | `test_core.py::test_reset_zeroes_attempts_but_keeps_the_retry_text` |
| any | failed | — | a transition's own error, journaled with the text | `test_core.py` |

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
Stage 1 on, the runner builds the rest of itself and Fichero through coders, one step per issue, one stage per coder
context, one coder at a time. A step starts only when its dependencies are closed; `Depends on` defaults to the step
before within the stage. The shape of this section is `pipeline.build-order-shape`; a step's issue number is written
into its heading once filed. Stage 0's proof is Step 1.2 taken through the checks by a Pi coder, review pending,
nothing pushed. Every behaviour below is in exactly one step; the runner's own guard checks this spec.

### Stage 0 — the smallest safe runner (by hand)

#### Step 0.1 — the state machine, the journal and its lock
- Behaviours: `pipeline.one-state-machine`, `pipeline.resume-from-journal`, `pipeline.pause-all`, `pipeline.project-profile`
- Tests: pipeline/tests/test_core.py, pipeline/tests/test_journal.py, pipeline/tests/test_config.py
- Size: M

#### Step 0.2 — the worktree and the checks, pinned and inside it
- Behaviours: `pipeline.worktree-per-task`, `pipeline.pinned-checks`, `pipeline.test-red-on-base`, `pipeline.retry-with-the-failure`
- Tests: pipeline/tests/test_checks.py, pipeline/tests/test_core.py
- Size: M

#### Step 0.3 — one Pi coder in tmux, jailed, with its key, tools and rules
- Behaviours: `pipeline.workers-in-tmux`, `pipeline.jailed-agent`, `pipeline.tools-in-the-right-places`, `pipeline.cost-cap`
- Tests: pipeline/tests/test_coder.py
- Depends on: 0.1
- Size: M

#### Step 0.4 — messages, the verdict, the CLI and the per-role MCP tools
- Behaviours: `pipeline.messages`, `pipeline.review`, `pipeline.three-faces`, `pipeline.one-coder-per-milestone`
- Tests: pipeline/tests/test_core.py, pipeline/tests/test_faces.py
- Depends on: 0.2, 0.3
- Size: M

#### Step 0.5 — the minimal page and the hard-coded caps
- Behaviours: `pipeline.dashboard-minimal`, `pipeline.point-at-a-milestone`, `pipeline.maintainer-queue`, `pipeline.machine-budget`
- Tests: pipeline/tests/test_web.py, pipeline/tests/test_budget.py, pipeline/tests/test_core.py
- Depends on: 0.4
- Size: M

### Stage 1 — GitHub and the spec become the input

#### Step 1.1 — the three GitHub workflows
- Behaviours: `pipeline.github-actions`
- Tests: fichero-server/tests/unit/scripts/ (a test_workflows pytest, written with the step)
- Depends on: 0.5
- Size: S

#### Step 1.2 — the build-order guard (the Stage 0 proof step)
- Behaviours: `pipeline.build-order-shape`
- Tests: pipeline/tests/test_specs.py, fichero-server/tests/unit/scripts/test_check_spec_build_order_shape.py
- Depends on: 0.5
- Size: S

#### Step 1.3 — the feeder and the brief lint
- Behaviours: `pipeline.feeder-picks-the-milestone`, `pipeline.brief-lint`
- Tests: pipeline/tests/test_feeder.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — spec-to-issues and reconciliation with the existing issues
- Behaviours: `pipeline.spec-to-issues`, `pipeline.uses-what-exists`, `pipeline.issues-and-milestones-kept-current`
- Tests: pipeline/tests/test_specs.py, pipeline/tests/test_gh.py, pipeline/tests/test_core.py, pipeline/tests/test_feeder.py
- Depends on: 1.3
- Size: M

#### Step 1.5 — spec changes flow to issues
- Behaviours: `pipeline.spec-change`
- Tests: pipeline/tests/test_specs.py
- Depends on: 1.4
- Size: S

#### Step 1.6 — bugs, from inside and outside
- Behaviours: `pipeline.bug-intake`, `pipeline.outside-bugs`
- Tests: pipeline/tests/test_feeder.py, pipeline/tests/test_core.py, pipeline/tests/test_coder.py, pipeline/tests/test_web.py
- Depends on: 1.4
- Size: M

#### Step 1.7 — worker roles: kinds, models and the fallback list
- Behaviours: `pipeline.worker-roles`
- Tests: pipeline/tests/test_coder.py
- Depends on: 0.5
- Size: M

#### Step 1.8 — the batch session, caching and closing
- Behaviours: `pipeline.batch-session`, `pipeline.prompt-cache`, `pipeline.closes-issues`
- Tests: pipeline/tests/test_core.py, pipeline/tests/test_coder.py, pipeline/tests/test_feeder.py
- Depends on: 1.3
- Size: M

### Stage 2 — the page and the checks, whole

#### Step 2.1 — the pages
- Behaviours: `pipeline.dashboard-pages`
- Tests: pipeline/tests/test_web.py, pipeline/tests/test_core.py
- Depends on: 1.4
- Size: M

#### Step 2.2 — the quick checks, whole
- Behaviours: `pipeline.quick-checks-per-item`
- Tests: pipeline/tests/test_checks.py
- Depends on: 0.5
- Size: M

### Stage 3 — nights and weeks

#### Step 3.1 — the schedule, unattended
- Behaviours: `pipeline.schedule`
- Tests: pipeline/tests/test_schedule.py
- Depends on: 0.5
- Size: M

#### Step 3.2 — the nightly gate on the M4, push, the build targets
- Behaviours: `pipeline.nightly-gate`, `pipeline.build-targets`
- Tests: pipeline/tests/test_nightly.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — rebase after push
- Behaviours: `pipeline.rebase-after-push`
- Tests: pipeline/tests/test_core.py
- Depends on: 3.2
- Size: S

#### Step 3.4 — the weekly release and the sites
- Behaviours: `pipeline.weekly-release`
- Tests: pipeline/tests/test_nightly.py
- Depends on: 3.2
- Size: M

#### Step 3.5 — the manager drafts specs
- Behaviours: `pipeline.spec-writing-mode`
- Tests: pipeline/tests/test_core.py
- Depends on: 1.5
- Size: S

### Stage 4 — the old system leaves

#### Step 4.1 — retire agents/ and rewrite AGENTS.md
- Behaviours: `pipeline.retire-fs-skills`
- Tests: fichero-server/tests/unit/scripts/ (a test_no_agents_dir pytest, written with the step)
- Depends on: 1.3
- Size: S

Not in a step, by ruling: `pipeline.xcode-cloud-builds` (not now). `pipeline.ready-check` is [OK] already.

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
