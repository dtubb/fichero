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
through coders. One behaviour sits in exactly one build-order step.

### Specs and issues
- `pipeline.spec-is-the-input` [PARTIAL] — work starts only from an APPROVED spec (or a bug issue); the spec
  guards (`check_spec_behaviors_are_tagged`, `check_spec_broken_has_issue`, `check_spec_milestones`) already hold
  the spec↔issue↔test binding. Test: `pipeline/tests/test_feeder.py::test_only_approved_spec_or_bug_is_dispatched`.
- `pipeline.spec-to-issues` [MISSING] (#6116) — one issue per build-order STEP (never per behaviour): title
  `<spec short name> N.M: <title>`; body = the step's behaviour lines verbatim with their acceptance, the test paths,
  the dependencies and a link to the section; the spec's milestone; label `stage:<spec>-<n>`. Filing writes `(#N)`
  into the step heading as a commit on a branch for review, never straight to integration. Before filing it searches
  open and closed issues by behaviour id, then by title, and reuses or reopens with a comment. Test:
  `pipeline/tests/test_specs.py::test_spec_to_issues_files_one_issue_per_step_and_reuses_existing` (dry run).
- `pipeline.build-order-shape` [MISSING] (#6116) — a spec's build order has one fixed shape so spec-to-issues is
  deterministic: `## Build order`, optional `### Stage N — title`, then `#### Step N.M — title (#NNNN)` with
  `- Behaviours:` (ids), `- Tests:` (paths), optional `- Depends on:` (earlier steps; the default is the step
  before, stopping at the stage boundary) and `- Size: S | M | L`. Acceptance: `scripts/check_spec_build_order_shape.py`
  fails an APPROVED spec when a non-[OK] behaviour is in no step or in two, a step has no Behaviours or no Tests, a
  step is Size L or has more than five behaviours, or Depends-on points forward; a DRAFT spec only warns. The cut
  into stages and steps is Opus's judgement with the maintainer, by the rules in `specs/_TEMPLATE.md` ("Build
  order"). Existing specs are not rewritten; the self-test parses `source/source-model.md`'s slices and reports the
  distance. Tests: `pipeline/tests/test_specs.py::test_build_order_parses`,
  `pipeline/tests/test_specs.py::test_build_order_guard_fails_on_orphan_behaviour`.
- `pipeline.build-order-readable` [MISSING] (#6116) — a step heading carries its issue number `(#N)` once filed;
  the feeder follows the steps in order; a spec without a build order falls back to priority label then number.
  Test: `pipeline/tests/test_specs.py::test_step_issue_numbers_are_read_from_headings`.
- `pipeline.brief-lint` [MISSING] (#6116) — an issue without a spec id (or the bug label), an acceptance line or a
  test path is not dispatched; it goes to the maintainer's queue as "write it up" (Opus with the maintainer, later
  the Qwen manager). Test: `pipeline/tests/test_feeder.py::test_brief_lint_names_each_missing_field`.
- `pipeline.every-issue-has-a-milestone` [MISSING] (#6116) — a ratchet: the count of open issues with no milestone
  only goes down (123 on 2026-10-25); a GitHub Action labels a new issue that has none `no-milestone`. Test:
  `fichero-server/tests/unit/scripts/test_workflows.py::test_issue_milestone_workflow_labels_when_none` (the
  workflow's YAML is parsed and its condition and command are asserted).
- `pipeline.bug-intake` [MISSING] (#6116) — a bug filed on the page, from MCP or on GitHub gets a milestone: the
  one the maintainer picked, else one the runner proposes and the maintainer confirms in the queue. A bug needs no
  spec id; it needs what was seen, the expected result and a test path, or it becomes a "write it up" queue item.
  A bug in the milestone being coded joins that list ahead of the feature issues; the `urgent` label puts it
  before the current milestone. A bug filed by a failed build target or by `verify_to_issues.sh` is de-duplicated by
  title before filing. Tests: `pipeline/tests/test_feeder.py::test_bug_without_test_path_goes_to_queue`,
  `pipeline/tests/test_feeder.py::test_urgent_bug_is_ordered_first`.
- `pipeline.outside-bugs` [MISSING] (#6116) — an issue, or a comment, by anyone not on the config allow-list (the
  maintainer, the agent, GitHub's bots) is labelled `from-user` and goes to the queue as "triage". It is never given
  to a coder, and its text never enters a model prompt: the prompt builder takes only the body and the comments of
  allow-listed authors, so an outsider's comment on a triaged issue is dropped too. The maintainer or Opus rewrites
  it into a triaged issue (seen, expected, test path, milestone) that links back; closing the triaged issue comments
  on the original. Reason: outside text in a prompt is a prompt-injection path. Tests:
  `pipeline/tests/test_core.py::test_outside_issue_never_reaches_start`,
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
  Milestones page; the no-milestone count only goes down. On GitHub: `claimed` is set while an item codes and removed
  on `failed` or `needs-maintainer`; a short comment with a `<!-- pipeline:<event>:<task> -->` marker on checked
  (check summary), reviewed (verdict) and pushed (sha), so resume can see which comments exist; the issue closes only
  through close-on-push from `Fixes #N`; `Part of #N` leaves it open with what is left. Every write goes through one
  function, `--dry-run` by default in tests. Tests:
  `pipeline/tests/test_gh.py::test_every_write_goes_through_one_function_and_dry_run_writes_nothing`,
  `pipeline/tests/test_core.py::test_claimed_label_follows_the_state`.
- `pipeline.one-claim-label` [MISSING] (#6116) — one claim convention (`claimed`) read by the feeder, the gates and
  the page; `status:in-progress` and assignees are retired as locks. Test:
  `pipeline/tests/test_feeder.py::test_claimed_issues_are_skipped`.

### Running the work (the runner + the feeder)
- `pipeline.one-state-machine` [MISSING] (#6116) — an item moves only by the runner's transitions, each in the
  states table below with its check; the transition writes one journal line; a model's report never moves an item;
  `start`, `check`, `verdict`, `candidate`, `gate`, `push`, `close` are the only paths. Test:
  `pipeline/tests/test_core.py::test_states_table_is_the_only_transition_path`.
- `pipeline.project-profile` [MISSING] (#6116) — everything specific to Fichero lives in ONE file,
  `pipeline/projects/fichero.toml` (stdlib `tomllib`): the repo path and branches (integration, main); the spec
  folder and the build-order rules; the check ladder naming the scripts per rung (ready check, red-on-base, `gate
  part`, the fast guards, the nightly gate, verify_all); the build targets and the schedule; the milestone and label
  names; the worker roles and their models; the machine names. The runner's code names no Fichero path, script or
  label; the self-test greps `pipeline/*.py` for "fichero" outside comments and fails on a hit. Another project is
  another file (`pipeline/projects/example-writing.toml`: a writing project whose ladder is a word count, a
  citation check and proofreading; it loads and validates, nothing more is built for it). Tests:
  `pipeline/tests/test_config.py::test_runner_code_names_no_project_specifics`,
  `pipeline/tests/test_config.py::test_example_writing_profile_loads_and_validates`.
- `pipeline.journal-lock` [MISSING] (#6116) — one `flock` on the journal, taken by whoever dispatches (launchd's
  runner or the CLI), so two runners never dispatch the same work. Test:
  `pipeline/tests/test_journal.py::test_second_dispatcher_waits_on_the_journal_lock`.
- `pipeline.resume-from-journal` [MISSING] (#6116) — the journal has an intent line before each side effect
  (commit, gh write, tell, worktree) and a done line after; on restart, an item with an open intent is reconciled
  against the world (the `Fixes #N` commit exists on the branch; the marker is in the GitHub comment; the worktree
  exists) before anything is redone, so nothing is lost or doubled; finished issues and existing model results are
  never redone. Tests: `pipeline/tests/test_journal.py::test_replay_gives_the_same_state`,
  `pipeline/tests/test_core.py::test_resume_after_kill_between_intent_and_done`.
- `pipeline.pause-all` [MISSING] (#6116) — a kill switch: `python -m pipeline pause` (and `resume`) writes a journal
  line after which no transition starts a coder, a check or a job; running work finishes its current step. The page
  shows PAUSED. Test: `pipeline/tests/test_core.py::test_paused_runner_starts_nothing`.
- `pipeline.pinned-checks` [MISSING] (#6116) — the checks (`scripts/lane_ready_check.sh`, `scripts/check_*`,
  `scripts/gate`, `pipeline/`) run from the runner's own pinned checkout AGAINST the task's worktree, never from the
  worktree's copies, so a coder cannot edit the check it is judged by (the runner builds itself, so this matters
  most). A diff that touches those paths goes to `needs-maintainer`. The runner moves to a new sha only on the
  maintainer's command, after the push. Tests: `pipeline/tests/test_checks.py::test_checks_run_from_the_pinned_checkout`,
  `pipeline/tests/test_checks.py::test_diff_touching_check_paths_needs_maintainer`.
- `pipeline.gate-runs-in-the-worktree` [MISSING] (#6116) — every check takes the task's worktree as its working
  directory (the trial's engine ran it in the project root and failed a correct fix). Test:
  `pipeline/tests/test_checks.py::test_checks_cwd_is_the_worktree`.
- `pipeline.three-faces` [MISSING] (#6116) — the CLI, the MCP server and the page call the same functions
  (`core.API`) and nothing skips a check. MCP tools are per role: the coder gets `report`, `ask`, `done`; the
  reviewer gets `verdict`; the manager gets `status`, `next`, `start`, `check`, `tell`, `file_bug`, `point`. Approve
  (a spec draft, the weekly release) and `answer` exist on the page and the CLI only, never over MCP: a model cannot
  answer its own question. Tests: `pipeline/tests/test_faces.py::test_cli_mcp_and_page_call_the_same_function`,
  `pipeline/tests/test_faces.py::test_mcp_has_no_approve_or_answer_tool`.
- `pipeline.feeder-picks-the-milestone` [PARTIAL] — the milestone the maintainer pointed at, else the first
  milestone with an open step whose dependencies are closed (`choose_next.py` is retired with `agents/ROADMAP.md`);
  within it urgent bugs, bugs, then steps in build order, then priority label, then number. Test:
  `pipeline/tests/test_feeder.py::test_pointed_milestone_wins_then_build_order`.
- `pipeline.one-coder-per-milestone` [MISSING] (#6116) — one Pi context takes several issues in a row (a stage's
  steps, or bugs grouped by the files or spec they touch). Each issue gets its own commit range on the branch and its
  own per-item checks; a failed item blocks the later ones on that branch until it is fixed or dropped, and the
  candidate lands the green ranges without the red one (cherry-picked, in order). The context carries on to the next
  issue with what it learned; a fresh context starts when the stage or batch ends or the session passes
  `context_tokens_max` (measured). The next context starts from a short handoff the runner writes from the journal
  (issues done, files touched, failures), never from the model's own summary. Test:
  `pipeline/tests/test_core.py::test_batch_of_three_issues_gives_three_commits_and_three_check_lines`.
- `pipeline.worktree-per-task` [MISSING] (#6116) — each task is a worktree off origin/integration at
  `.worktrees/pipeline/<task>` (`git worktree add`, removed only with `git worktree remove`). Test:
  `pipeline/tests/test_core.py::test_worktree_is_made_off_base_and_removed_with_git`.
- `pipeline.jailed-agent` [PARTIAL] — Pi runs with `--no-extensions` plus only the adapter path, in an
  allow-listed environment (PATH, HOME, TERM, the agent dir, the one key); the worktree is the only writable path
  (the Pi sandbox or the wrapper's deny rules). Tests: `pipeline/tests/test_coder.py::test_env_allow_list_drops_everything_else`,
  `pipeline/tests/test_coder.py::test_write_outside_worktree_fails`.
- `pipeline.key-per-lane` [MISSING] (#6116) — the coder's key is a lane key with its own credit limit (a separate
  OpenRouter key file, `~/.config/openrouter/key-lane`), never the main key; it reaches Pi only as an environment
  variable read by the worker wrapper from the key file; the runner never holds, prints, logs or writes it. Test:
  `pipeline/tests/test_coder.py::test_runner_never_reads_the_key_and_prefers_the_lane_key`.
- `pipeline.workers-in-tmux` [MISSING] (#6116) — every worker (each coder, the reviewer, later the Pi + Qwen
  manager) is an INTERACTIVE Pi session in its own window of one tmux session `pipeline` (windows `coder-<milestone>`,
  `reviewer`, `manager`, `jobs`), so the maintainer can attach, watch or type. Pi gets `--session-dir` per task so
  the runner reads cost, replies and idleness from its JSONL; pane text is never scraped for state; a lock per
  window serialises `tell` with anyone typing. Test: `pipeline/tests/test_coder.py::test_worker_window_command_names_session_dir`.
- `pipeline.messages` [MISSING] (#6116) — the runner sends a worker its next issue, a check's failure text, a
  verdict or the maintainer's answer with `tell` (lifted from `agent-work/status/briefs/tell.sh`: tmux send-keys,
  text, pause, Enter); long text goes in a brief file the message points at; one message, then wait for idle. Idle =
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
- `pipeline.tools-in-the-right-places` [MISSING] (#6116) — the coder and the reviewer find and read code through
  the jcodemunch MCP and docs and specs through the jdocmunch MCP (indexed on `docs/`). Pi loads MCP through the
  `pi-mcp-adapter` extension, so the runner gives Pi its own agent directory (`PI_CODING_AGENT_DIR=pipeline/pi-agent`)
  that loads only that adapter, those two servers, the `_shared` principles and a ponytail rules file: the coder gets
  ponytail FULL; the reviewer gets the ponytail review lens as one named check. The coder's prompt says to start
  with jcodemunch `plan_turn` and jdocmunch for the spec lines. Tests:
  `pipeline/tests/test_coder.py::test_pi_command_loads_only_the_pipeline_agent_dir`,
  `pipeline/tests/test_coder.py::test_session_fixture_shows_jcodemunch_and_jdocmunch_calls`.
- `pipeline.fallback-list` [MISSING] (#6116) — one ordered worker list per role in config; a cost-cap stop, a
  credit or quota error (402, 429, "insufficient"), two failed retries and a Claude Code usage limit all move the
  role to the next entry; after the last entry the item goes to the queue, which asks for budget, never assumes it.
  Test: `pipeline/tests/test_coder.py::test_one_fallback_list_serves_cost_quota_and_retries`.
- `pipeline.cost-cap` [MISSING] (#6116) — the runner sums `message.usage.cost.total` from Pi's session JSONL per
  task while the coder runs and stops the task at `cost_cap_usd`; the lane key's own OpenRouter limit is the
  backstop. Tests: `pipeline/tests/test_coder.py::test_cost_parser_on_redacted_real_sample`,
  `pipeline/tests/test_coder.py::test_cost_cap_stops_the_task`.
- `pipeline.cost-recorded` [PARTIAL] — tokens and dollars per issue and per model from the session logs, so the
  open-model share is measured; a Claude Code worker records tokens with no price. Test:
  `pipeline/tests/test_coder.py::test_cost_is_recorded_per_issue_and_model`.
- `pipeline.retry-with-the-failure` [MISSING] (#6116) — a failed check is told to the coder with the failure text;
  `retries` (2) retries, then the fallback list, then the queue. Test:
  `pipeline/tests/test_core.py::test_failed_check_retries_twice_then_needs_maintainer`.
- `pipeline.machine-budget` [MISSING] (#6116) — Stage 0 hard-codes: coders 1, one test run at a time (a FIFO
  `flock`), and a free-memory check (`vm_stat` pages free + speculative + purgeable, `memory_pressure` not critical)
  before a coder, a check or a test run; below the job kind's need the item waits with its reason in the journal.
  Later: `sysctl vm.swapusage` and load; per-kind needs in config (a cloud coder small, a local model its RSS, `gate
  part` measured); the maintainer's engine first — the signal is a `Fichero Server` process above 0 % CPU in `ps`
  while pressure is not normal, and then the runner holds new heavy work and never kills his; a cloud provider gets a
  requests-per-minute cap and backoff with full jitter on 429 and 5xx; everything spawned is capped and
  de-duplicated. Tests: `pipeline/tests/test_budget.py::test_item_waits_with_reason_when_memory_is_short`,
  `pipeline/tests/test_budget.py::test_429_backs_off_with_growing_delays`,
  `pipeline/tests/test_budget.py::test_second_test_run_waits_on_the_lock`,
  `pipeline/tests/test_budget.py::test_never_spawns_past_the_cap`,
  `pipeline/tests/test_budget.py::test_owner_engine_busy_signal`.
- `pipeline.model-per-role` [MISSING] (#6116) — the model is a config entry per role: provider (`openrouter`,
  `anthropic`, or `omlx` at its local OpenAI-compatible endpoint, declared to Pi in `pipeline/pi-agent/models.json`)
  plus model id, so the end state — every role local through oMLX, one small model on a 16 GB Mac, several on the
  128 GB Mac — is a config change. The budget counts each loaded oMLX model's RSS against free RAM, one request in
  flight per model unless config says more. oMLX is not run now: config carries an example and the self-test loads
  nothing. Test: `pipeline/tests/test_coder.py::test_model_per_role_from_config`.
- `pipeline.worker-kinds` [MISSING] (#6116) — the worker kind is a config entry per role: `pi` or `claude-code`, so
  the Claude Max subscription's tokens are used beside Pi. A `claude-code` worker is an interactive `claude` in its
  own tmux window with cwd the task worktree; its project-local `.claude/settings.json`, written into the worktree,
  sets the model, the MCP servers (jcodemunch, jdocmunch, the runner's own for report/ask/done), the ponytail plugin
  and the lanes' permission mode. Replies and idleness are read from its session JSONL under
  `~/.claude/projects/<encoded cwd>/`, never the pane. Token counts are recorded without a price; a usage-limit line
  is journaled `rate-limited` and the fallback list moves on. Both kinds get the same prompt, tools, checks and
  journal. Tests: `pipeline/tests/test_coder.py::test_worker_kind_selection_and_fallback_on_rate_limit`,
  `pipeline/tests/test_coder.py::test_idle_state_from_fixture_jsonl_of_each_kind`.
- `pipeline.schedule` [MISSING] (#6116) — the runner takes over everything the lead sessions did by hand, on
  schedules and triggers: a `schedule` table in config, each entry a name, a when (cron, or `on:push`,
  `on:gate-green`, `on:idle`), the job (an existing script, run through the runner so it gets the budget, the
  journal and the page) and a machine (pro, air, m4 over ssh). launchd starts the runner; the runner fires the
  schedule; a missed run fires once on wake, never N times; output goes to the `jobs` tmux window; the page lists the
  schedule with each job's last result. Watchers are schedule entries too: a hung gate part, a stalled worker, a CI
  failure on Actions, disk and memory pressure. Tests: `pipeline/tests/test_schedule.py::test_missed_run_fires_once_on_wake`,
  `pipeline/tests/test_schedule.py::test_event_entries_fire_on_their_event`.

### Checking the work
- `pipeline.ready-check` [OK] — `scripts/lane_ready_check.sh` (self-tested): current integration history, no
  private folders, agent author, every commit cites an issue, lint on the diff, a source change has a test change.
  Test: `scripts/lane_ready_check.sh --self-test`.
- `pipeline.test-red-on-base` [MISSING] (#6116) — the branch's changed or new test files are copied into a scratch
  worktree at origin/integration and must fail there, and must pass on the branch; a test that passes on the base
  proves nothing. Test: `pipeline/tests/test_checks.py::test_red_on_base_fails_a_test_that_passes_on_base`.
- `pipeline.quick-checks-per-item` [PARTIAL] — each item: the ready check, the test files the spec's Test matrix
  and the issue name (red on base, green on the branch), `scripts/gate part` for the areas the diff touches, and the
  fast guards; minutes on the Pro or Air. Test: `pipeline/tests/test_checks.py::test_run_all_records_each_rung`.
- `pipeline.contract-current` [MISSING] (#6116) — the per-item checks fail when generated contract files
  (OpenAPI, CLI surface, Swift identity) are stale: `check_openapi_route_set_current`,
  `check_contract_identity_current`, `check_mcp_generated_current` run on a diff under `fichero-server/src`. Test:
  `pipeline/tests/test_checks.py::test_contract_guards_run_on_an_engine_diff`.
- `pipeline.test-queue` [MISSING] (#6116) — one FIFO lock per test machine; small items test on the Pro; a red
  reruns once before it counts (a flaky suite does not burn a retry). Test:
  `pipeline/tests/test_checks.py::test_red_reruns_once_before_it_counts`.
- `pipeline.review` [PARTIAL] — a verdict is `verdict(task, sha, READY|NOT_READY, findings)`, accepted only from the
  reviewer role and only for the task's current head sha; a new commit voids it. Claude's verdict binds; the Qwen
  shadow runs beside it (`trial2/shadow/watch-reviews.sh`); once Qwen's precision passes the bar over 30 items
  (counted by hand until it matters: no missed HIGH, 90 % agreement), small items pass on the machine checks plus
  Qwen and Claude reviews the batch diff at the gate. Tests: `pipeline/tests/test_core.py::test_verdict_only_from_reviewer_for_current_sha`,
  `pipeline/tests/test_core.py::test_new_commit_voids_the_verdict`.
- `pipeline.ponytail-review` [PARTIAL] — the reviewer applies the ponytail lens (shortest working diff, no
  speculative code) as one named check in every review, from `pipeline/pi-agent/rules/ponytail-review.md`. Test:
  `pipeline/tests/test_coder.py::test_reviewer_prompt_carries_the_ponytail_lens`.

### Landing, closing, building, releasing
- `pipeline.nightly-gate` [PARTIAL] — reviewed items merge into the night's candidate; the full engine gate runs on
  the M4 overnight; green → push integration → the nightly build; red → nothing is pushed and the page says which
  part and which item; nothing pushes main except the weekly release. Test:
  `pipeline/tests/test_nightly.py::test_red_gate_pushes_nothing_and_names_the_part`.
- `pipeline.rebase-after-push` [MISSING] (#6116) — every live coder rebases on integration after a push; a conflict
  after the rebase stops that coder and goes to the queue (resolved by the Opus session with the maintainer). Test:
  `pipeline/tests/test_core.py::test_rebase_conflict_stops_the_coder_and_queues`.
- `pipeline.close-on-push` [PARTIAL] — a GitHub Action on push to integration runs `close_fixed_issues.py --apply`
  (the script exists and works); a `Part of #N` leaves the issue open with a comment. Test:
  `fichero-server/tests/unit/scripts/test_workflows.py::test_close_on_push_workflow_runs_the_script_with_apply`.
- `pipeline.actions-engine-free-checks` [MISSING] (#6116) — GitHub Actions runs ruff, the guard scripts that need
  no Mac tool, the unit tests that need no models, and `lane_ready_check.sh` on every PR, on pushes to integration
  as well as main. Swift unit tests stay on the Macs until an unsigned `xcodebuild test` without the embedded engine
  is shown to work on a free macOS runner. Test:
  `fichero-server/tests/unit/scripts/test_workflows.py::test_ci_runs_on_integration_pushes_with_guards_and_ready_check`.
- `pipeline.xcode-cloud-builds` [PROPOSED, not now] (ruled 2026-10-25: not now; if tried later, with a prebuilt engine
  artifact from the M4, iOS TestFlight only, since a Briefcase engine rebuilt per cloud build eats the 25 hours) —
  Xcode Cloud builds and runs the Swift unit tests on every push to integration, archives Mac and iOS nightly, and
  delivers the dev build to TestFlight.
- `pipeline.build-targets` [MISSING] (#6116) — each build target is its own schedule job wrapping the existing
  release scripts (`release-all.sh` and its parts): the dev DMG (notarized, `--dev`); iOS/iPad TestFlight; Mac
  TestFlight / the App Store build (#6112: its archive's engine sits in Contents/Resources, not Helpers); the
  Developer ID DMG and Sparkle; the GitHub release; the site. Nightly runs the dev DMG plus both TestFlights to
  internal testers. Each target's result (uploaded, build number, processed, or failed with the reason) shows on
  the Builds page; a failed target files a bug through bug-intake, de-duplicated, and never blocks the other
  targets. Test: `pipeline/tests/test_nightly.py::test_failed_target_files_one_bug_and_the_others_run`.
- `pipeline.nightly-build` [MISSING] (#6116) — on the green nightly gate the M4 runs the nightly targets; Mac, iPhone
  and iPad get the build; a red gate sends nothing and says why on the page. Test:
  `pipeline/tests/test_nightly.py::test_nightly_build_only_after_green_gate`.
- `pipeline.weekly-release` [PARTIAL] — on its schedule the weekly release runs every target and stops for the
  maintainer's yes (on the page or the CLI, never over MCP) before anything public: the GitHub release, Sparkle, the
  site, the App Store submission; the pre-release scan checks private docs as well as keys and paths. Test:
  `pipeline/tests/test_nightly.py::test_weekly_release_waits_for_the_yes_before_public_targets`.
- `pipeline.site-updates` [MISSING] (#6116) — website updates are their own schedule job for both sites: the docs
  site (MkDocs) refreshes after a green push, built from a clean checkout of the pushed sha, never a working tree
  (a prior deploy published untracked private docs/ pages), after the pre-release scan for private paths; the
  product site (tubb.ca/apps/fichero, appcast, release page) updates only in the weekly release after the yes.
  Test: `pipeline/tests/test_nightly.py::test_docs_deploy_builds_from_a_clean_checkout_of_the_sha`.

### Following along
- `pipeline.dashboard-minimal` [MISSING] (#6116) — one local page (127.0.0.1 only; one HTML file, plain CSS, a
  little JS, system fonts, Safari) with sections: items and their states, workers (window, task, idle or busy,
  cost), the queue with an answer box, a tell box per worker, point-at-milestone, PAUSED, the machine's memory. It
  polls `/api/state` every few seconds. Every POST carries a token minted per launch and embedded in the page, and an
  `Origin` check, so no other site open in Safari can drive it. Tests:
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
  proposals). Commands: start or stop a worker, file a bug with an optional screenshot saved locally, approve a spec
  draft, approve the weekly release. GitHub data is cached by the runner, refreshed every few minutes and on each
  transition. Test: `pipeline/tests/test_web.py::test_page_loads_and_every_link_resolves`.
- `pipeline.page-files-bugs` [MISSING] (#6116) — the maintainer files a bug from the page (title, words,
  screenshot), picks or is offered its milestone, and it becomes a GitHub issue the feeder can take. Test:
  `pipeline/tests/test_web.py::test_file_bug_from_the_page_goes_through_bug_intake` (dry run).
- `pipeline.point-at-a-milestone` [MISSING] (#6116) — the maintainer sets which milestone runs next, and can pause
  or resume one; the feeder follows that before its own order. Test:
  `pipeline/tests/test_core.py::test_point_is_journaled_and_read_by_the_feeder`.
- `pipeline.maintainer-queue` [MISSING] (#6116) — every question for the maintainer is one queue item with options;
  the answer is written back (told to the worker, or into the spec or issue) and the work it unblocks resumes; no
  lane messages him for status. Test: `pipeline/tests/test_core.py::test_ask_queues_and_answer_is_told_to_the_right_window`.
- `pipeline.stuck-is-flagged` [MISSING] (#6116) — an item longer than `stuck_minutes` (config, 45) in one state is
  flagged on the page. Test: `pipeline/tests/test_core.py::test_item_past_stuck_minutes_is_flagged`.
- `pipeline.runs-unattended` [MISSING] (#6116) — a launchd agent starts the runner at login and keeps it running;
  the schedule does the rest; no chat prompt has to remember a step. Test:
  `pipeline/tests/test_schedule.py::test_launchd_plist_runs_the_runner`.
- `pipeline.retire-fs-skills` [MISSING] (#6116) — the old skills system leaves the repo once the runner runs work:
  `agents/` (manager-loop and worker-loop prompts, the session-start-* skills, `fs_session_start_manager`,
  `choose-next`, gardener-agent) is deleted after each skill's unique rules still in force are moved into AGENTS.md
  or this spec; AGENTS.md describes the runner (CLI, MCP, page, states, checks) and keeps the hard rules, with no
  reference to `agents/skills` or `agents/prompts`; `scripts/verify_python.sh`'s "autoloop" comment is fixed;
  `architecture/pi_agent_harness.md` is updated or marked superseded by this spec. Done outside the repo already:
  the fs_* Pi skills moved to `~/.pi/agent/skills.retired-2026-10-25/`, the Claude `fs_session` plugin disabled.
  Test: `fichero-server/tests/unit/scripts/test_no_agents_dir.py`.

## States

| From | To | Transition | Check the code runs | Test |
|------|----|-----------|---------------------|------|
| — | queued | `start` | brief lint passes; author allow-listed; not paused; coder cap and free memory | `test_core.py::test_outside_issue_never_reaches_start`, `test_paused_runner_starts_nothing` |
| queued | coding | `start` | worktree made off the base; worker window up; brief told | `test_core.py::test_worktree_is_made_off_base_and_removed_with_git` |
| coding | checked | `check` (or `done` → `check`) | ready check, red-on-base, named tests, gate part, fast guards, contract guards — all green, from the pinned checkout, in the worktree | `test_core.py::test_done_never_moves_state_without_checks` |
| coding | coding | `check` red | attempt < retries: failure text told to the coder | `test_core.py::test_failed_check_retries_twice_then_needs_maintainer` |
| coding | needs-maintainer | `check` red | attempts exhausted, or the diff touches a check path | `test_checks.py::test_diff_touching_check_paths_needs_maintainer` |
| coding | rate-limited | worker log | quota / credit / usage-limit line; fallback list moves on | `test_coder.py::test_one_fallback_list_serves_cost_quota_and_retries` |
| coding | waiting | budget | memory or cap refused; reason journaled | `test_budget.py::test_item_waits_with_reason_when_memory_is_short` |
| checked | reviewed | `verdict` | READY from the reviewer role for the current head sha | `test_core.py::test_verdict_only_from_reviewer_for_current_sha` |
| reviewed | checked | new commit | the verdict is voided | `test_core.py::test_new_commit_voids_the_verdict` |
| reviewed | candidate | `candidate` | reviewed; range cherry-picks cleanly onto the night's candidate (Stage 3) | `test_nightly.py` |
| candidate | gated | `gate` | the full gate green on the M4 (Stage 3) | `test_nightly.py::test_red_gate_pushes_nothing_and_names_the_part` |
| gated | pushed | `push` | gated; the push is its own step | `test_nightly.py` |
| pushed | closed | close-on-push | `Fixes #N` on integration | `test_workflows.py` |
| any | paused | `pause` | — (running steps finish; nothing new starts) | `test_core.py::test_paused_runner_starts_nothing` |
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
- Behaviours: `pipeline.one-state-machine`, `pipeline.journal-lock`, `pipeline.resume-from-journal`, `pipeline.pause-all`, `pipeline.project-profile`
- Tests: pipeline/tests/test_core.py, pipeline/tests/test_journal.py, pipeline/tests/test_config.py
- Size: M

#### Step 0.2 — the worktree and the checks, pinned and inside it
- Behaviours: `pipeline.worktree-per-task`, `pipeline.pinned-checks`, `pipeline.gate-runs-in-the-worktree`, `pipeline.test-red-on-base`, `pipeline.retry-with-the-failure`
- Tests: pipeline/tests/test_checks.py, pipeline/tests/test_core.py
- Size: M

#### Step 0.3 — one Pi coder in tmux, jailed, with its key, tools and rules
- Behaviours: `pipeline.workers-in-tmux`, `pipeline.jailed-agent`, `pipeline.key-per-lane`, `pipeline.tools-in-the-right-places`, `pipeline.cost-cap`
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

#### Step 1.1 — GitHub Actions on pushes to integration
- Behaviours: `pipeline.actions-engine-free-checks`, `pipeline.close-on-push`, `pipeline.every-issue-has-a-milestone`
- Tests: fichero-server/tests/unit/scripts/test_workflows.py
- Depends on: 0.5
- Size: S

#### Step 1.2 — the build-order guard (the Stage 0 proof step)
- Behaviours: `pipeline.build-order-shape`, `pipeline.build-order-readable`
- Tests: pipeline/tests/test_specs.py, fichero-server/tests/unit/scripts/test_check_spec_build_order_shape.py
- Depends on: 0.5
- Size: S

#### Step 1.3 — the feeder and the brief lint
- Behaviours: `pipeline.feeder-picks-the-milestone`, `pipeline.brief-lint`, `pipeline.spec-is-the-input`, `pipeline.one-claim-label`
- Tests: pipeline/tests/test_feeder.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — spec-to-issues and reconciliation with the existing issues
- Behaviours: `pipeline.spec-to-issues`, `pipeline.uses-what-exists`, `pipeline.issues-and-milestones-kept-current`
- Tests: pipeline/tests/test_specs.py, pipeline/tests/test_gh.py, pipeline/tests/test_core.py
- Depends on: 1.3
- Size: M

#### Step 1.5 — spec changes flow to issues
- Behaviours: `pipeline.spec-change`
- Tests: pipeline/tests/test_specs.py
- Depends on: 1.4
- Size: S

#### Step 1.6 — bugs, from inside and outside
- Behaviours: `pipeline.bug-intake`, `pipeline.outside-bugs`, `pipeline.page-files-bugs`
- Tests: pipeline/tests/test_feeder.py, pipeline/tests/test_core.py, pipeline/tests/test_coder.py, pipeline/tests/test_web.py
- Depends on: 1.4
- Size: M

#### Step 1.7 — worker kinds, the fallback list and the model per role
- Behaviours: `pipeline.worker-kinds`, `pipeline.fallback-list`, `pipeline.model-per-role`, `pipeline.cost-recorded`
- Tests: pipeline/tests/test_coder.py
- Depends on: 0.5
- Size: M

### Stage 2 — the page, whole

#### Step 2.1 — the pages
- Behaviours: `pipeline.dashboard-pages`, `pipeline.stuck-is-flagged`
- Tests: pipeline/tests/test_web.py, pipeline/tests/test_core.py
- Depends on: 1.4
- Size: M

#### Step 2.2 — the reviewer's named checks and the quick checks, whole
- Behaviours: `pipeline.ponytail-review`, `pipeline.quick-checks-per-item`, `pipeline.contract-current`, `pipeline.test-queue`
- Tests: pipeline/tests/test_coder.py, pipeline/tests/test_checks.py
- Depends on: 0.5
- Size: M

### Stage 3 — nights and weeks

#### Step 3.1 — the schedule, unattended
- Behaviours: `pipeline.schedule`, `pipeline.runs-unattended`
- Tests: pipeline/tests/test_schedule.py
- Depends on: 0.5
- Size: M

#### Step 3.2 — the nightly gate on the M4, push, nightly build
- Behaviours: `pipeline.nightly-gate`, `pipeline.nightly-build`, `pipeline.build-targets`
- Tests: pipeline/tests/test_nightly.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — rebase after push
- Behaviours: `pipeline.rebase-after-push`
- Tests: pipeline/tests/test_core.py
- Depends on: 3.2
- Size: S

#### Step 3.4 — the weekly release and the sites
- Behaviours: `pipeline.weekly-release`, `pipeline.site-updates`
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
- Tests: fichero-server/tests/unit/scripts/test_no_agents_dir.py
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
