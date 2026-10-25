# Deterministic Conductor — scripts run the lanes, models do the work — Design Spec (#TBD)

> Milestone: dev-orchestration-harness
> Manual: TBD (contributor manual, "How the agent team works").
> **Status: DRAFT 2026-10-25, for the maintainer's review.** Extends `dev-orchestration-harness.md`; where they differ,
> this one wins for who CHOOSES and who CHECKS.

## Why

Today an LLM lead chooses the next issue, starts the worker, decides when it is done, merges, and is supposed to close
the issue. Every one of those is judgement, so it drifts: 739 open issues are cited by fix commits on integration, 123
open issues have no milestone, and the lead's choices cost Opus tokens. A small open model (Qwen in Pi or OpenCode)
cannot be trusted with those choices: the 2026-10-18 trials showed false "done" reports, commits outside the worktree,
and loops.

The pieces were built a year ago and never joined: `choose_next.py` (pick work), `dispatch_advisor.py` (size an issue),
`file_issue.sh` (file with a valid milestone), `close_fixed_issues.py` (close what a pushed commit fixes),
`start-lane.sh` (preflight), `agent-work/trial2/run.sh` (a jailed headless run with a score).

## The rule

**Scripts choose and check; models only write code.** Every choice (which milestone, which issue, which model, is it
done, may it merge, close the issue) is a script reading GitHub and the repo, deterministic and logged. A model's own
report is never evidence. An LLM is called only to do one issue, to review a diff, or to handle an exception.

## Who does what

- **The maintainer + Claude Opus (interactive, a personal plan):** talk, decide, write and approve specs, handle
  exceptions. The only place judgement is spent.
- **Pi + Qwen (OpenRouter now, a local model on a 128 GB Mac later):** one issue at a time, inside the harness.
- **Scripts and GitHub Actions:** everything else (choose, check, close, log). No OpenCode, no LLM lead in the loop.

## Version 1, and nothing more

Four pieces, each a short script with a self-test, so the process runs the same on the Pro today and on a laptop with
local models later (only the model endpoint changes):
1. `lane_ready_check.sh`: the machine check (built; the red-on-base proof is next).
2. Close on push: a GitHub Actions workflow runs `close_fixed_issues.py --apply` on every push to integration.
3. `brief_lint.py`: refuses an issue a small model cannot do (no spec id, acceptance line or test path).
4. `conductor.py --once --issue N`: brief, jailed Pi + Qwen run, ready check, named tests, PASS/FAIL, one log line.
Everything else in this spec (the loop, several lanes, resume, the web page, the launchd service, escalation tables)
waits until v1 has done ten real issues and the numbers say it is worth building.

## Where judgement stays, and where it stops

1. **The maintainer has an idea** and says it (chat, an issue, or the web page's input box).
2. **Fable or Opus writes the spec** with the maintainer: one line per behaviour, tagged, a build order, open
   questions. The maintainer rules on the questions and approves. This is the last step that needs judgement.
3. **From the approved spec on, everything is mechanical:**
   - a script files one issue per untagged-or-`[GAP]`/`[BROKEN]` behaviour that has none, in the spec's milestone,
     ordered by the spec's build order (`check_spec_broken_has_issue` and `check_spec_milestones` already hold half
     of this binding);
   - the conductor works the milestone (the loop below);
   - a behaviour's tag flips to `[OK]` in the same commit as the test that proves it, and the issue closes when that
     commit is pushed;
   - the spec is done when no behaviour is left untagged-OK, and the milestone closes with it.
4. **The maintainer's input is a queue, not a conversation:** the page lists every open question in a spec, every
   `needs-your-decision` issue and every on-screen check owed, each with its options; an answer is written back to
   the spec or the issue by the script, and the lanes it unblocks resume.

## The loop (one script: `scripts/conductor.py`, one state file per lane)

1. **Choose a milestone.** `choose_next.py` walks the priority spine and returns the next milestone with ready issues.
   One lane per milestone, so a worker keeps one context. At most N lanes at once (N from the machine-memory rule).
2. **Order its issues.** Ready = open, in the milestone, not `needs-design` / `needs-your-decision` / `needs:human`,
   not claimed. Order: the milestone's spec build order if it has one, else issue number.
3. **Pick the harness and model.** `dispatch_advisor.py` sizes each issue; a table in `agents/lanes.toml` maps the size
   to a harness and model, so swapping models is one edit:
   `mini` → Pi (tight: rules + checklist) + Qwen 3.8 27B or Flash; `regular` → the same, retried once with the failure; `frontier` → not dispatched: it goes back to the spec with Opus. (2026-10-18 trial: Qwen 3.8 in tight Pi wrote the right tests 6/6–7/7 and caught 3/3 planted bugs; Qwen3-coder-next missed one in Claude Code, OpenCode and Pi alike, so the model matters more than the harness.)
4. **Launch, jailed.** Worktree `m-<milestone>` from origin/integration; the harness may write only inside it (sandbox
   + deny rules, as `run.sh` does); no push rights. The brief is generated from a template plus the issue: its spec
   ids, its acceptance lines, and the tests to run. The harness session id is saved in the lane state.
5. **One issue, then stop.** The worker writes the spec line, a red test, the code, green; commits with `Fixes #N`
   (all of it done) or `Part of #N`; writes `.lane/done-<N>.json` (sha, tests run). Then the run ends: the worker is
   spun down, its session kept so it can resume.
6. **Machine check.** `scripts/lane_ready_check.sh`: the branch is on current integration history, no private files,
   ruff / swiftlint clean on the diff, author is the agent, every commit cites an issue, a source change has a test
   change. Then the brief's tests run on the test machine (the Air by day, the M4 by night). Red → the same session is
   resumed with the failure text (twice at most) → then the next model up the table.
7. **Review.** The Claude reviewer's verdict binds; the Qwen shadow review runs beside it. NOT OK → back to step 6 with
   the findings.
8. **Integrate in batches.** OK items merge into the day's candidate. A full gate runs at K items or at a set hour;
   green → push integration → `close_fixed_issues.py --apply` closes every `Fixes #N` that landed → the lane's
   next issue resumes the same session (same milestone); a drained milestone ends the lane.
9. **Exceptions go to an LLM lead**, and only these: merge conflicts, a red gate not traced to one item, a design wall
   recorded on an issue, anything needing the maintainer. The lead acts and returns control to the script.

## Later, only after v1 has run ten issues: a small local web app

The process today fails by being forgotten: a lane finishes and nobody notices, a check-in prompt goes stale, an
issue is never closed. So the conductor runs as one long-lived local process (a launchd agent, restarted if it dies),
not as a prompt someone has to remember, and serves one page on localhost (stdlib `http.server`, no framework):
- each lane: milestone, issue, model, state (running / checking / in review / waiting / spun down), time in state,
  tokens and dollars so far;
- the queue: next milestones and their ready issues; what is waiting on the maintainer (`needs-your-decision`,
  on-screen checks);
- the last gate, the last push, the issues closed by it;
- buttons that write to a control file the loop reads: pause a lane, resume, retry, skip an issue, approve a push.

This page is how the maintainer follows the work: what each lane is doing, what is queued, what waits on the maintainer and
what landed, without asking in chat. Chat is for talking, not for status.

A lane stuck in one state past a limit (an hour by default) is flagged on the page and wakes the LLM lead. The page
reads the same state files and log the loop writes, so it can never show something the loop is not doing.

## What GitHub does instead of the conductor

The repo is public, so Actions minutes are free; anything that needs only GitHub and the repo runs there, not in the
local loop, and so cannot be forgotten:
- push to `integration` → `close_fixed_issues.py --apply` (closing becomes an event, not a step);
- an issue opened or edited → no milestone means a label and a comment (later: the milestone taken from the spec
  that cites it);
- a pull request → `lane_ready_check.sh` and the guard scripts that need no engine, the result as a check run;
- nightly → spec tags vs issues (`check_spec_broken_has_issue`, `check_spec_milestones`), stale `status:in-progress`
  claims released.

The engine gate, the Mac build and anything with models stay local (the Air by day, the M4 by night): hosted macOS
runners are slow and paid, and the gate needs local models.

## Behaviours

- `conductor.github-closes-on-push` [GAP] — an Actions workflow on push to integration runs `close_fixed_issues.py --apply`.
- `conductor.github-milestone-triage` [GAP] — a workflow flags an issue with no milestone.
- `conductor.github-pr-ready-check` [GAP] — a workflow runs the ready check and the engine-free guards on every PR.

- `conductor.runs-as-a-service` [GAP] — a launchd agent keeps the loop alive; no prompt or person has to start it.
- `conductor.status-page` [GAP] — the localhost page above, read-only except for the control buttons.
- `conductor.maintainer-follows-on-the-page` [GAP] — status and decisions live on the page; no lane or lead messages
  the maintainer for status.
- `conductor.stuck-lane-flagged` [GAP] — a lane past its time limit is flagged and wakes the lead.

- `conductor.choose-milestone-by-spine` [PARTIAL] — `choose_next.py` exists and is deterministic; today it finds no
  ready issue because the spine and the labels have drifted.
- `conductor.one-lane-per-milestone` [GAP] — a lane owns one milestone; two lanes never share one.
- `conductor.every-issue-has-a-milestone` [GAP] — a guard fails when an open issue has no milestone; new issues go
  through `file_issue.sh`, which already refuses a closed milestone.
- `conductor.size-picks-the-model` [PARTIAL] — `dispatch_advisor.py` sizes; the size → harness/model table
  (`agents/lanes.toml`) does not exist.
- `conductor.jailed-launch` [PARTIAL] — `run.sh` jails Claude Code, Qwen Code, OpenCode and Pi runs; not used for real
  lanes.
- `conductor.brief-from-template` [GAP] — the brief is generated from the issue's spec ids, acceptance and tests.
- `conductor.done-is-a-file-not-a-claim` [GAP] — done means the done file plus a passing machine check.
- `conductor.ready-check` [GAP] — `lane_ready_check.sh` as in step 6, with a self-test that proves each check can fail.
- `conductor.retry-then-escalate` [GAP] — two resumes with the failure text, then the next model up.
- `conductor.resume-by-milestone` [GAP] — the saved session resumes for the same milestone's next issue.
- `conductor.close-on-push` [PARTIAL] — `close_fixed_issues.py --apply` exists and works (dry run 2026-10-25 would
  close #5807, #5811, #5814, #5816); nothing calls it after a push.
- `conductor.batch-gate` [PARTIAL] — the full gate exists; the trigger (K items or the hour) does not.
- `conductor.exceptions-only-lead` [GAP] — the LLM lead is woken by the script, with the exception and its evidence.
- `conductor.every-step-logged` [GAP] — one line per decision in `agent-work/status/conductor.log`, so a run can be
  replayed and audited.
- `conductor.cost-recorded` [GAP] — tokens and dollars per issue, per model, so the open-model share can be measured.

## Build order (revised after the Fable review, 2026-10-25)

1. `lane_ready_check.sh` with a red-on-base / green-on-branch proof for the new test, and its self-test; the push step
   runs `close_fixed_issues.py --apply` (a GitHub Actions workflow on push to integration).
2. One claim convention (the `claimed` label) read by the chooser, the check and the conductor; `choose_next.py --json`
   returns a real milestone on today's board (milestone due dates if the spine stays stale); `brief_lint.py` refuses
   an issue with no spec id, no acceptance line or no named test path.
3. `conductor.py --once --milestone X --issue N`: generate the brief, launch Pi + Qwen jailed via `run.sh`, run the
   ready check, run the named tests on the Pro, print PASS/FAIL, append one log line. No resume, no web page.
4. Run it on ten `mini` issues of a guard/lint milestone; score claims vs reality and the reviewer's load.
5. Only then: the loop, a second lane, the test-machine queue, the web page (or a GitHub Projects board as the page).

## What the review changed

- **Done must be earned:** the new test must FAIL on origin/integration and PASS on the branch, run by the check in a
  scratch worktree; "a test file changed" is not enough (`conductor.test-red-on-base` [GAP]).
- **Issues must be written for a small model:** `brief_lint.py` refuses under-specified issues; the Claude budget the
  conductor saves goes into writing the spec id, the acceptance line and the test path for each (`conductor.brief-lint` [GAP]).
- **Build orders become machine-readable:** each build-order line ends with its issue `(#N)`, held by a guard; until
  then order by priority label, then number (`conductor.build-order-readable` [GAP]).
- **The test machine is a queue:** one FIFO lock per machine; `mini` items test on the Pro; a red reruns once before it
  counts, so a flaky suite does not burn a retry (`conductor.test-queue` [GAP]).
- **Lanes rebase after every push**, and a conflict after the rebase stops that lane instead of calling an LLM
  (`conductor.rebase-after-push` [GAP]).
- **Resume, v1:** re-launch with the failure text appended to the brief; session resume comes later, per harness.
- **Secrets and spend:** the worker gets a per-lane OpenRouter key with its own credit limit, never the main key; a lane
  stops when its issue passes a dollar cap (`conductor.cost-cap` [GAP]).
- **The milestone guard is a ratchet:** the count of issues with no milestone may only go down.
- **Review tiers, later:** once Qwen's adjudicated precision is measured, `mini` items pass on the machine check plus
  the Qwen review, and Claude reviews the batch diff at the gate, one call per K items.

## The same shape inside Fichero

The conductor is the pattern Fichero's own recipe runner already follows for archive work: a plan fixed in advance
(the recipe's stages / the spec's behaviours), a model doing one bounded step (a stage on a page / one issue), a
machine check of the result (a gate / the ready check), resume without redoing finished work, and one place to follow
it (Activity / the status page). The in-app agent for research tasks (EPIC #2056, #2067, the Research surface) can take
the same rule: a deterministic plan and checks around small local models, the model never the judge of its own result.
Shared first as a design, not as code: the dev conductor stays a repo script, so a bug in it can never reach a user's
library.

## Open questions

1. N (lanes at once) and K (items per gate): proposed N = 2 by day on the Pro/Air, K = 5.
2. Which milestone first for the Qwen lane: proposed a guard/lint/docs milestone, where a machine check proves most of
   the work.
3. Does the Claude reviewer stay binding for every item, or can a `mini` item pass on the machine check plus the Qwen
   review alone? Proposed: Claude stays binding until Qwen's adjudicated precision is measured over 30 items.
4. Adopt or build: build the thin conductor around the existing scripts, or adopt an existing orchestrator Survey 2026-10-25: no tool does all of it. Worktree GUIs (Conductor, Superset, Claude Squad,
   vibe-kanban, the last shut down 2026-04) are chat-driven with no machine check; issue-driven ones (OpenAI's Symphony
   and its Pi port, Kata Symphony, the OpenHands resolver, OpenCode's GitHub action) assume Linear, Codex or a cloud
   runner. Proposed: build v1 thin over Pi; borrow Symphony's idea (poll the board, one workspace per issue, restart a
   stalled agent) and look again at Kata Symphony when the loop is built.
5. Should the conductor and Fichero's in-app agent later share one runner? Proposed: not before both have run for a
   month; share the design now.
