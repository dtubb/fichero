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

- **Bernstein** (sipyourdrink-ltd/bernstein, Apache-2.0) is the engine: a plain-Python scheduler with no model in
  the coordination loop, YAML run graphs (phases, roles, dependencies, conditions), a git worktree per task, quality
  gates (shell commands), retry or another model on failure, GitHub/Linear/Jira ticket import, cron schedules,
  PR automation, a hash-chained signed journal, a terminal and a browser dashboard, and adapters for Pi, Qwen,
  Ollama and 50+ agents. Trialled 2026-10-25 on #6100 (see "Trial findings").
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
          dashboard ◀── Bernstein journal ◀── Bernstein run ◀── milestone feeder (next milestone, next issues)
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

### Running the work (Bernstein + the feeder)
- `pipeline.feeder-picks-the-milestone` [PARTIAL] — `choose_next.py` (deterministic) picks the next milestone; it
  finds nothing today because the roadmap spine drifted; fall back to milestone due dates.
- `pipeline.one-coder-per-milestone` [MISSING] — one Bernstein task per milestone holds several of its issues in
  order, so one context does related issues; the next milestone starts a fresh context.
- `pipeline.one-claim-label` [MISSING] — one claim convention (`claimed`) read by the feeder, the gates and the
  dashboard; `status:in-progress` and assignees are retired as locks.
- `pipeline.worktree-per-task` [OK] — Bernstein gives each task a worktree (trial 2026-10-25).
- `pipeline.jailed-agent` [PARTIAL] — Pi runs with `--no-extensions` and a filtered environment (Bernstein's
  adapter); the worktree is the only writable path (sandbox backend or `run.sh`'s deny rules).
- `pipeline.key-per-lane` [MISSING] — the coder gets an OpenRouter key with its own credit limit, never the main
  key, passed only by environment.
- `pipeline.cost-cap` [PARTIAL] — Bernstein's budget, once the model has a price entry (it reported $0 in the trial).

### Checking the work
- `pipeline.ready-check` [OK] — `scripts/lane_ready_check.sh` (self-tested): current integration history, no
  private folders, agent author, every commit cites an issue, lint on the diff, a source change has a test change.
- `pipeline.test-red-on-base` [MISSING] — the new test fails on origin/integration and passes on the branch, run
  in a scratch worktree; a test that passes on the base proves nothing.
- `pipeline.gate-runs-in-the-worktree` [BROKEN] — in the trial Bernstein ran the gate in the project root, not
  the task's worktree, and failed a correct fix; worked around in config or a gate wrapper (round 2).
- `pipeline.contract-current` [MISSING] — the gate fails when generated contract files (OpenAPI, CLI surface, Swift
  identity) are stale; the trial's correct fix did not regenerate them.
- `pipeline.test-queue` [MISSING] — one FIFO lock per test machine; small items test on the Pro; a red reruns once
  before it counts (a flaky suite does not burn a retry).
- `pipeline.retry-with-the-failure` [PARTIAL] — Bernstein retries; the retry carries the gate's failure text;
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
- `pipeline.resume-from-journal` [MISSING] — after a restart of Bernstein, the Pro or a test Mac, an unfinished task
  continues from its journal and worktree; finished issues and existing model results are not redone.
- `pipeline.nightly-build` [MISSING] — on the green nightly gate, built on the M4: dev DMG (notarized) and dev TestFlight; the Mac, iPhone and
  iPad get it; a red gate sends nothing and says why on the page.
- `pipeline.weekly-release` [PARTIAL] — `release-all.sh` on a schedule prepares the release (version, notes check,
  DMGs, TestFlight, GitHub release, Sparkle, site) and stops for the maintainer's yes before anything is public;
  the pre-release scan checks private docs as well as keys and paths.

### Following along
- `pipeline.dashboard` [PARTIAL] — Bernstein's browser dashboard (127.0.0.1:8052/ui) shows tasks, agents, diffs
  and cost; the page also shows the maintainer's queue (open spec questions, `needs-your-decision`, on-screen checks).
- `pipeline.maintainer-queue` [MISSING] — every question for the maintainer is one queue item with options; an
  answer is written back to the spec or issue and the work it unblocks resumes; no lane messages him for status.
- `pipeline.stuck-is-flagged` [MISSING] — a task past its time limit in one state is flagged on the page.
- `pipeline.runs-unattended` [PARTIAL] — Bernstein's schedules and a launchd agent keep it running; no chat prompt
  has to remember a step.
- `pipeline.cost-recorded` [PARTIAL] — tokens and dollars per issue and per model (Bernstein's cost lines, once
  priced), so the open-model share is measured.

## Who does what

- **The maintainer + Claude Opus** (interactive): ideas, specs, rulings, exceptions. Later, the same role through a
  Pi + Qwen manager and the dashboard.
- **Pi + Qwen 3.8** (27B or Flash, in tight Pi with rules + checklist): coding, tests, docs, first reviews. In the
  2026-10-18 trials it wrote the right tests (6/6–7/7) and caught 3/3 planted bugs; Qwen3-coder-next missed one in
  every harness, so the model matters more than the harness.
- **Bernstein + scripts + GitHub Actions + Xcode Cloud**: everything else.

## Rulings

- 2026-10-25: build on what works, not reinvent: Bernstein is the engine; Fichero adds a feeder, its gates, Actions
  and release schedules. Bernstein's bugs are worked around in configuration or a small wrapper, never forked, and
  not filed upstream for now.
- 2026-10-25: Fichero first, in this repo; a shared home (fichero-skills or a new name) only after it runs Fichero
  reliably, for the other projects in use (assistant, research_assistant).
- 2026-10-25: no OpenCode; Pi is the harness.
- 2026-10-25: never rerun a model pass whose result already exists for the same input and model; a resumed task
  continues from Bernstein's journal and the repo's state, it does not redo finished work.
- 2026-10-25 (pipeline questions): one coder at a time while the pipeline beds in; each item gets the quick checks
  (ready check, its own tests, the test folders it touches, on the Pro or Air, minutes); the full engine gate runs
  once a night on the M4, integration is pushed after that green gate, then the nightly dev build goes out (Mac,
  iPhone, iPad) — the nightly build is in effect a nightly release to the testers; the public release stays weekly.
  The first milestone for the Qwen coder is a guards/lint/docs one. The Claude reviewer stays binding until Qwen's
  reviews are measured over 30 items (bar: no missed HIGH, at least 90% agreement on verdicts). Xcode Cloud: not now.
  Onboarding work leaves the 230-issue `source-model` milestone; it goes with the Recipe Designer spec's milestone.

## Trial findings (Bernstein 3.23.0, 2026-10-25, #6100, Pi + Qwen 3.8 27B via OpenRouter)

- Worked: ticket import, a worktree per task, Pi on OpenRouter (model id `openrouter/qwen/qwen3.8-27b`), the
  signed journal; the agent's fix was correct (lint clean, 10 tests pass, red on base, green on the change) in
  226 s for US$0.09.
- Broke: the gate ran in the project root and failed the correct fix; a spawn-cooldown loop and 75 stray
  "Upgrade" tasks after the failure; no price for the model, so no budget; dashboard token auth rejected issued
  tokens (run with auth off, bound to 127.0.0.1). Round 2 works around these in configuration.

## Build order

The first two weeks are steps 1–3 only; each step gets an issue (filed when this spec is approved) and its line
here ends with that number, as `pipeline.build-order-readable` asks of every spec.

1. GitHub Actions: `ci.yml` on pushes to integration as well as PRs (ruff, engine-free guards and pytest, Swift unit
   tests on macOS, the ready check); close-on-push; a label for an issue with no milestone.
2. Bernstein workarounds in config or a gate wrapper (the gate in the task's worktree, no stray tasks, a price for
   the model), with red-on-base inside the wrapper.
3. The feeder (milestone → Bernstein tasks, several issues per task) and `brief_lint.py`, writing exactly the fields
   `spec-to-issues` writes; ten issues from one guards/lint/docs milestone through Pi + Qwen.
   **Success:** at least 8 of 10 merged without a human edit, under US$5, no false "done".
4. The nightly gate on the M4 → push → nightly dev build.
5. The maintainer's queue on the page; resume from the journal.
6. The test-machine queue, rebase-after-push; a second coder.
7. The weekly release on a schedule.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Scripts (self-test) | y | each check can fail | `scripts/lane_ready_check.sh --self-test`, feeder `--self-test` |
| Backend (pytest) | y | close-on-push, spec-to-issues, brief lint | `fichero-server/tests/unit/scripts/` |
| Actions | y | workflows run on a PR | `.github/workflows/*.yml` (run on a test PR) |
| Swift / UI / MCP / CLI | n | — | — |

## Open questions

1. Who resolves a merge conflict a rebase leaves: proposed the Opus session with the maintainer, with the coder's
   diff and the conflicting commit in front of it.
