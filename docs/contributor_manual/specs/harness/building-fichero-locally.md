# Building Fichero with local models, reliably — the one harness spec — Design Spec

> Milestone: Builder
> (One milestone. It absorbs `dev-workflows`, `dev-orchestration-harness`,
> `Builder: agent profiles and generic workflows`, `builder-mac-app`, `performance-sweep`, `spec-pipeline` and
> `git-worktree-workflow`; see "Merge list". The name stands alone on the line above because `builder triage`,
> `builder steps` and `builder milestone` read that line.)
> Manual: docs/contributor_manual/how-fichero-is-built.md

> **Status: DRAFT — written 2026-11-17 and corrected 2026-11-18 from the owner's direction and his answers of that day (paraphrased), for the supervising
> manager to complete in Phase 0.** Tags: [OK] built and tested by name · [PARTIAL] exists, not wired · [GAP] not built ·
> [BROKEN] built, wrong today. This file is the frame and the map. It does not yet carry the text of every behaviour
> it absorbs: Phase 0 moves each one in under its existing id and tag, and nothing built loses its [OK].
> Read against `origin/integration` at `b56999b2` (2026-11-18, 17:44). Corrected 2026-11-18 after the owner's review.

## Intent

**The goal is to build Fichero, with local models, reliably.** The harness is in aid of that and is not the goal.

What the owner observes when this is done: Fichero's issues are built, checked and landed overnight by open models
running on one Mac Studio in his office; a nightly dev build appears when everything is green; a short page of numbers
says how it went; nothing depends on a cloud model; and the lanes spend their time on Fichero, not on the harness.

## The pipeline (the basic idea, in the owner's words, 2026-11-17)

Scripts turn a spec into issues and milestones. A worker in a harness goes through each one. Each piece of work is
tested thoroughly, tested for performance, tested for bugs and reviewed. Release notes are written, issues are
closed, and the whole build is verified. Everything else in this spec exists to make these nine stages run on local
models without a person.

| # | Stage | By | Today |
|---|---|---|---|
| 1 | Spec → issues and milestones | `builder steps`, `builder milestone`, `builder triage` | in use; tagged [PARTIAL] |
| 2 | A long-running worker takes each step | `builder queue`, `builder run` | in use on Claude Code; Pi [PARTIAL] |
| 3 | Tests | the ladder: pytest rungs, guards, a test that fails on the base | engine: built. Swift: compile only, tests [GAP] |
| 4 | Performance | the perf rung, the sweep | runs report-only; budgets [GAP]; one rung [BROKEN] |
| 5 | Bugs and security | red-on-base, the security rung, the scanners | built, report-only; UI smoke nightly only |
| 6 | Review | a fresh reviewer with the diff, the ladder result and the lenses | built; read-only; a cloud model |
| 7 | Land and close | the land gate, `builder landed` | built: closes the issue, marks [OK], re-pins |
| 8 | Release notes and release | `RELEASE_NOTES.md`, `CHANGELOG.md`, the release script | notes lag the tags (see `local.notes-with-every-tag`) |
| 9 | Verify all | `builder verify-all`, the nightly | [PARTIAL] |

A stage that is report-only, compile-only or lagging is where a local model's mistakes would get through. Phase 2
closes stages 4 and 5 and the engine side of stage 3 before any open model builds real work. Swift tests per batch
need the Studio (Phase 8); until they are green, Swift steps are not given to an open model.

### One step, today

```
SPEC  (approved, tagged)
  |
  v
ISSUES + MILESTONE      [script]
  | one issue per step
  v
WORKER BUILDS A STEP    [model] <-+
  | long-running, in the jail     |
  | handoff at 85% -> new session |
  v                               |
CHECKS                  [script]  |
  | tests, guards, perf, security |
  |-- fail ---------------------->+
  v                               |
REVIEW                  [model]   |
  | fresh model, read-only        |
  |-- not ready ----------------->+
  v                  (2 fix rounds)
LAND AND CLOSE          [script]
    push, close issue, mark OK
```

### A release, today

```
LANDED WORK  (on integration)
  |
  v
NIGHTLY FREEZE          [script]
  | one commit, at midnight
  v
VERIFY ALL              [script]
  | every guard, the full tests
  |-- red --> nothing ships
  v
BUILD + SMOKE TEST      [script]
  | the app, on a clean Mac
  |-- red --> nothing ships
  v
DEV PRE-RELEASE         [script]
  | only when all green
  v
PUBLIC RELEASE          [needs a yes]
    notes, signing
```

Under this spec the nightly dev build stays automatic, a promotion to alpha, beta or release is prepared by script
and approved by the owner, and a step that fails two fix rounds escalates to the next tier or parks.

## The test every behaviour must pass

A behaviour stays in this spec only if it does at least one of these, and says which:

1. **Builds Fichero** — it moves a Fichero issue from spec to landed.
2. **Local** — it makes a role run on a local model, or removes a cloud dependency.
3. **Reliable** — it stops bad work landing, or lets the system recover without a person.

Anything else is deferred (see "Deferred"). A harness feature that serves none of the three is not built.

## Decisions (owner, 2026-11-17, paraphrased)

1. **Local models are the target, not an option.** Every role must be able to run on a local server by config alone.
   Qwen3-Coder-Next is the first builder candidate; others that fit the machine are compared by measurement.
2. **The machine is one always-on Mac Studio M5 Max, 128 GB** (confirmed 2026-11-17), which also serves Fichero and
   runs writing projects. The owner works on his laptop. Assume about 85 GB for all loaded models at once.
   **Until it arrives the 16 GB M1 Pro stays the Builder's main machine, with the helpers it has today**: no model is loaded locally, every role runs through
   OpenRouter, and the heavy checks move to CI (see `local.interim-16gb`).
3. **OpenRouter is the bridge.** Roles run through OpenRouter first, set up so pointing them at the local server is a
   config change. Numbers that decide anything are taken on the compressed build on Mac hardware.
4. **Pi is the worker harness for open models.** The worker stays replaceable by config; the other adapters wait.
5. **A supervising cloud manager (Fable) builds this, decides at each stop, and then leaves.** It gives its own yes
   at every stop in the build order, writes its reasons in the journal, and tells the owner afterwards. While it builds it turns each of its rulings
   into a guard, a rule or a routing entry. It is done when the system runs two weeks without it.
6. **A local manager runs the loop day to day**, within rules. It escalates; it does not relax checks.
7. **Escalation is automatic and mechanical.** Scripts decide, never the worker. During the build the tiers may end in
   a cloud model; at handover they end locally and then in PARKED.
8. **The reviewer is a different model from the builder.** An open model starts as a shadow beside the binding
   reviewer and is promoted on its agreement record.
9. **Dev releases are automatic; the owner approves the rest.** A dev build is published every night when every
   stage is green. Promoting a build to alpha, beta or release is the owner's yes, and stays his after handover.
   Scripts prepare each promotion (conditions checked, notes drafted) so the yes is one step.
10. **Nightly builds and CI run unattended.** GitHub Actions for what needs only the repo; the Studio as a self-hosted
    runner for Mac builds.
11. **State is a journal plus one SQLite database.** The JSONL journal stays the append-only record; one database is rebuilt
    from it and feeds the console and the reports. Reports are queries, not a model's summary.
12. **Specs and milestones are combined** into this spec and one milestone. After handover the harness is frozen:
    fixes only.

13. **Specs are critiqued before they are approved.** A script lints the spec and a different model reads it
    sceptically. Everything is derived from the spec, and a weaker builder follows a flawed one faithfully.
14. **Measure, do not review, what can be measured.** Speed, memory and disk are numbers taken by scripts on every
    batch and held to budgets. A model is asked only to explain a number that went out of bounds.
15. **Questions reach the owner by script,** in one list, each with a proposed answer and a deadline.
16. **The loop moves onto LangGraph.** The owner's ruling (2026-11-18): the Builder may use outside packages where
    they make it work better, and LangGraph will be more reliable than a home-made loop. See § H.
17. **Low-risk questions answer themselves after 24 hours** with their proposed answer; risky ones wait.
18. **Spend:** OpenRouter is capped at 50 US dollars a week. The supervising manager runs on the owner's Claude Max
    plan, so its use is counted in tokens, not dollars, and it must not crowd out the owner's own use.

## Rulings this overturns (the owner said yes to these on 2026-11-18)

These are written in specs the owner approved or ruled on. Phase 0 amends each spec and cites this table.

| Where | Says today | Becomes |
|---|---|---|
| `dev-workflows.models.by-config` | a role changes model only by a person editing the file | tiers and routing are config; scripts move a step between declared tiers |
| `dev-workflows.models.by-config` | a missing provider is a question, never a silent fallback | unchanged for a MISSING provider; escalation is a declared tier, never silent |
| `dev-workflows` Deployment profiles | cloud for the binding review until the log says otherwise | the same rule, with the bar and the handover written down (§ D, § G) |
| `pipeline.weekly-release`, `release-and-versioning` Intent | a release waits for the maintainer's yes | kept for alpha, beta and release; the nightly dev build is automatic (§ E) |
| `dev-workflows` (push) | only `builder landed --push`, typed by a person, pushes | the loop pushes after a READY verdict and a green gate; the journal row is the record |
| `agent-profiles.role.manager` | supervised by the human manager | supervised by the supervising manager, then by rules and the parked list (§ C) |
| `fichero-builder` (stdlib only, no outside package) | the Builder imports nothing outside the standard library | outside packages are allowed where they make the Builder work better; LangGraph is the first (§ H) |
| `builder-console.store.one-database` | DuckDB, `<state>/harness.duckdb` (owner 2026-11-16) | SQLite, for the harness only (owner 2026-11-17) |

## What exists (counted on `integration`, 2026-11-17; the harness specs, `harness.toml` and `fichero-builder/` were
unchanged at the 2026-11-18 head)

- `docs/contributor_manual/specs/harness/` holds 19 files, about 930 KB. Ten are about the Builder; nine are about
  Fichero's engine, releases and code layout and stay separate (see "Not part of this spec").
- The spec `dev-workflows.md` is APPROVED (2026-11-01), 388 KB, 165 tagged behaviours: 9 [OK], 93 [PARTIAL], 46 [GAP],
  16 [PROPOSED], 1 [BROKEN]. Most of the harness is partly built.
- The spec `deterministic-conductor.md` (DRAFT 2026-10-25): 45 behaviours, 12 [OK], 22 [PARTIAL], 11 [MISSING]. Largely
  superseded by `dev-workflows`.
- The spec `agent-profiles.md` (DRAFT 2026-11-16): 30 behaviours, 3 [OK], 6 [PARTIAL], 21 [GAP].
- The spec `builder-console.md` (DRAFT 2026-11-16): 18 behaviours, 1 [OK], 4 [PARTIAL], 11 [GAP], 2 [BROKEN].
- The spec `performance-sweep.md` (DRAFT 2026-11-15): 20 behaviours, 4 [OK], 8 [PARTIAL], 7 [GAP], 1 [BROKEN].
- The spec `builder-mac-app.md` (DRAFT): 12 behaviours, all [GAP].
- The code: `fichero-builder/` (stdlib Python), `harness.toml`, five workflows in `.github/workflows/`. Every lane
  today runs Claude Code; the Pi driver and policy extension exist without a finished adapter.
- In `harness.toml` both the security rung and the perf rung are report-only (`enforce = false`).

## Merge list for the supervising manager

This list was read from the spec files in the checkout, not from GitHub. The milestone names come from each spec's
`> Milestone:` line and the issue numbers are the ones each spec cites. **Confirm every name, count and open/closed
state against live GitHub before changing anything**, and report what differs.

### Specs to merge into this file (10), then mark superseded

| Spec | Size | Status today | Tagged behaviours |
|---|---|---|---|
| `dev-workflows.md` | 388 KB | APPROVED 2026-11-01 | 165 |
| `deterministic-conductor.md` | 72 KB | DRAFT 2026-10-25 | 45 |
| `performance-sweep.md` | 49 KB | DRAFT 2026-11-15 | 20 |
| `agent-profiles.md` | 47 KB | DRAFT 2026-11-16 | 30 |
| `builder-console.md` | 31 KB | DRAFT 2026-11-16 | 18 |
| `spec-pipeline.md` | 22 KB | DRAFT | none tagged |
| `git-worktree-workflow.md` | 16 KB | DRAFT | 1 |
| `builder-mac-app.md` | 15 KB | DRAFT | 12 (all deferred) |
| `dev-orchestration-harness.md` | 15 KB | DRAFT, ratified 2026-09-12 | 4 (all superseded) |
| `issues-and-labels.md` | 9 KB | DRAFT 2026-11-01 | 6 |

Plus `performance-sweep-REVIEW.md` (5 KB), folded in as notes. "What is brought in, spec by spec" below says what to
keep from each.

### Milestones to merge into `Builder` (7)

| Milestone | Named by | What to do |
|---|---|---|
| `dev-workflows` | `dev-workflows.md`, `issues-and-labels.md` | becomes `Builder` (rename it, so its history stays) |
| `Builder: agent profiles and generic workflows` | `agent-profiles.md`, `builder-console.md` | move open issues, close |
| `dev-orchestration-harness` | `deterministic-conductor.md`, `dev-orchestration-harness.md` | move what is still wanted, close the rest as superseded, close |
| `performance-sweep` | `performance-sweep.md` | move open issues, close |
| `builder-mac-app` | `builder-mac-app.md` | move its issues under a `deferred` marker, close |
| `spec-pipeline` | `spec-pipeline.md` | move or close as superseded, close |
| `git-worktree-workflow` | `git-worktree-workflow.md` | move open issues, close |

Check also `ui-test-harness` (build-order entry 36, "testing and release"): say whether it is harness or product, and
merge it only if it is harness. Leave every product milestone and the ops buckets (`Bugs - *`, `Performance - *`,
`Lint - *`) alone.

### Issues to move (the numbers each spec cites; check which are still open)

- From `agent-profiles.md` (22): #6589, #6622 to #6642. The ones this spec builds first: #6631 (Pi adapter),
  #6638 (manager role). Deferred with their adapters: #6632, #6633 and the other adapter issues.
- From `builder-console.md` (16): #6627, #6628, #6643 to #6656. #6644 is the one database.
- From `dev-workflows.md` (65 cited, #6116 the parent): among them #6379 and #6387 (the ledger), #6380 (the bake-off),
  thirteen between #6369 and #6391, #6466, #6467, #6495 to #6507, #6524, #6547. Older numbers it cites (#1234 to #6107) are likely
  closed or product issues; check each and do not move a product issue.
- From `deterministic-conductor.md` (21): #6100, #6101, #6112, #6116, #6140, #6148 to #6161, #6166, #6179. Most are
  superseded; close each with a link to the issue that replaced it, or move it if nothing did.
- From `dev-orchestration-harness.md` (28): #2561 to #6007, all older. Expect most closed; close the rest as
  superseded unless this spec still wants the behaviour.
- From `performance-sweep.md`: #6600, #6610, #6614 (and #6369, #6589, shared with other specs).
- From `builder-mac-app.md`: #6345 (deferred).
- From `issues-and-labels.md`: #6336, #6337. From `spec-pipeline.md`: #5112, #5461. From `git-worktree-workflow.md`:
  #4813, #4814, #5997, #6658, #6659.

Issues cited by more than one spec (#6100, #6116, #6166, #6369, #6589, #6600, #6627, #6628) are moved once.

### What must not break when the specs move

- **Behaviour ids stay exactly as they are.** 92 Python files cite `dev-workflows.*` ids, and `builder landed` marks
  behaviours [OK] by id. Rename no id; a behaviour that is superseded keeps its id and says what replaced it.
- **Spec paths are read by code.** Files outside the specs refer to `harness/dev-workflows.md` (10 files),
  `deterministic-conductor.md` (9), `issues-and-labels.md` (9), `spec-pipeline.md` (4) and the others (1 to 3 each).
  Either keep each old file as a short pointer to this one, or update every reference in the same batch.
- **`build-order.md` entry 1** names `dev-workflows` and its spec path; update it in the same batch.
- **`builder triage`** reads each spec's `> Milestone:` line; run `builder triage --milestones` as a dry run first and
  report what it would change.
- **Duplicates** are closed with a link to the survivor, never deleted. Nothing is deleted until the combined spec
  has landed.

## Behaviours

New behaviours carry the prefix `local.` and are all [GAP]. Absorbed behaviours keep their ids. Each new behaviour cites #6116, the harness's
parent issue, until `builder steps` files one issue per step. The absorbed behaviours follow § H, one "Absorbed from"
section per spec, word for word.

### A. Workers and models

**The worker model is kept as it is: one long-running worker per lane.** A lane is a milestone. The worker stays
open across steps and keeps what it has read; the loop feeds it one step at a time, runs the checks and the review on
the owner's side, and sends the next brief into the same session. A new session starts only when the worker is gone
or at its handoff. This is the owner's ruling of 2026-11-01 and nothing in this spec replaces it.

- `local.long-running-kept` [GAP] (#6116) — `dev-workflows.tool.queue`, `dev-workflows.worker.handoff`,
  `dev-workflows.run.loop`, `dev-workflows.run.loop-chain`, `dev-workflows.run.loop-fix-rounds`,
  `dev-workflows.run.loop-rolls-on` and `dev-workflows.run.loop-survives` are absorbed whole and unchanged in
  meaning. `agent-profiles.worker.small` is read as "one step per BRIEF", not one step per worker: the session
  continues. If Phase 0 finds the two in conflict, the long-running worker wins and the owner is told.
  Serves: builds Fichero.
- `local.handoff-per-model` [GAP] (#6116) — the handoff point is set per model, not once. Today `harness.toml` has
  `window = 200000`, `handoff_at = 0.85` and `handoff_tokens = 175000`, chosen for Sonnet. Each model in the slate
  declares its usable window on this machine (a local model's is bounded by memory and by how slowly it re-reads a
  long prompt, not only by its trained length), and the 85 % rule applies to that. Serves: reliable.
- `local.handoff-before-compaction` [GAP] (#6116) — the harness's handoff is the mechanism that is built and in use: the
  worker is told at the mark, writes `HANDOFF.md`, ends with `HANDOFF READY`, and a successor (generation plus one)
  starts from that file through the same start path (`run.py`, `watcher.py`). For Pi the watcher delivers the word
  itself. Pi's own auto-compaction stays on only as a safety net, set to fire later than the handoff mark, so the
  two never race; the existing note that Pi's compaction errors with a 35B model is fixed or the net is turned off
  for that model. The bake-off compares handoff alone against handoff with the net. Serves: reliable.
- `local.worker-sandboxed` [GAP] (#6116) — the Pi worker process starts inside a sandbox profile as well as in the worker
  account: it may write only its worktree and scratch, read its own install and the checkout, and reach only the
  model endpoint, the package registries and read-only GitHub. The checks and the review already run outside the
  worker's session, so the profile does not have to admit them. Pi has no permission system of its own, so this and
  the policy extension (`pi/policy.ts`, which blocks any tool call not answered ALLOW) are the limits. The start
  probes prove the wall before each worker runs. Serves: reliable.
- `local.handoff-measured` [GAP] (#6116) — the bake-off scores a model on handoffs as well as steps: whether the successor
  carries on correctly from the handoff file, redoes finished work, or loses the thread. A model that builds one step
  well and cannot survive a handoff does not pass. Serves: reliable.
- `local.xcode-worker` [GAP] (#6116) — a Swift step goes to an Xcode worker: a Pi worker with Xcode's own tools, reached
  through Xcode's MCP server (`xcrun mcpbridge`, with "Allow external agents to use Xcode tools" on). It builds,
  reads structured build errors, runs named tests and renders SwiftUI previews through Xcode, not through a bare
  `xcodebuild`. This mirrors what works today with Claude inside Xcode (the release holds commits written "using
  Xcode using Fichero Builder"). Xcode must be open on the lane's worktree in a logged-in session, so this worker
  runs in the GUI test user, one Xcode per lane; Phase 0 says how that sits with the jail, since the bridge talks to
  Xcode inside one user's session. Rendered previews and test results are attached for the reviewer, who today sees
  only the diff. Also try the other direction once: Xcode 27 accepts outside agents through the Agent Client
  Protocol; record whether Pi can be brought in that way and which works better. Serves: builds Fichero, reliable.
- `local.escalation-by-handoff` [GAP] (#6116) — escalating a step to another tier ends the session through the same handoff
  path: the next tier starts from the handoff file plus the failed diff, the ladder output and the findings. When the
  step lands, the lane's own worker resumes from a fresh handoff. Serves: reliable.


- `local.target` [GAP] (#6116) — every role (builder, reviewer, manager, helper) names a local provider it can run on; a role
  that works only with a cloud model is a named exception with its reason and what would remove it. The weekly report
  lists the exceptions. Serves: local.
- `local.memory-budget` [GAP] (#6116) — `harness.toml` states the machine's model budget (85 GB on the 128 GB Studio) and each
  model's loaded size; a slate that does not fit beside the gate and a build is refused at start. Serves: reliable.
- `local.interim-16gb` [GAP] (#6116) — until the Studio arrives the 16 GB M1 Pro is the main machine and the helpers
  (`[check].remote`, the nightly runners) stay as `harness.toml` has them: no local model server; lanes capped to
  what the machine holds; engine tests, guards and scans also run on GitHub's hosted runners so the Pro is not the
  only place they run; the full nightly check (budgeted at 14 GB) stays on its remote runner. Swift steps stay with
  the cloud builder until `local.swift-tests-per-batch` is green. Nothing built now is machine-specific: moving to
  the Studio is config, and `pool.*` is retired only then. Serves: builds Fichero.
- `local.bridge-openrouter` [GAP] (#6116) — OpenRouter is a Pi provider; the key comes from the environment and is written
  nowhere; the model id, the serving provider and its quantization are recorded per run. Serves: local.
- `local.compressed-is-the-measure` [GAP] (#6116) — a decision to adopt a model cites runs on the compressed build on Mac
  hardware, not only the hosted full-precision one. Serves: reliable.
- Absorbed: `agent-profiles.adapter.interface` [OK], `agent-profiles.adapter.claude-code` [OK],
  `agent-profiles.adapter.pi` [PARTIAL] (#6631), `dev-workflows.models.by-config` [PARTIAL],
  `agent-profiles.worker.small` [GAP], `dev-workflows.worker.handoff` [PARTIAL] (the handoff follows the model's
  real context window).

### B. Gates — what makes it reliable

With no stronger model on call, quality is whatever the gates enforce. These are the core of the spec.

- `local.gates-enforce` [GAP] (#6116) — the security rung enforces after one clean week; the perf rung stays report-only
  until budgets and noise bands exist, and the report says so on every run. Serves: reliable.
- `local.swift-tests-per-batch` [GAP] (#6116) — Swift unit and UI tests run per batch in a dedicated GUI user on the Studio,
  so a test run never quits the owner's app. Absorbs `dev-workflows.run.swift-tests` [GAP],
  `agent-profiles.ladder.swift-tests` [GAP], `agent-profiles.ladder.ui-smoke` [GAP]. Serves: reliable.
- Absorbed unchanged: `dev-workflows.run.land-gate`, `dev-workflows.run.policy-hook`, `dev-workflows.run.jail-home`,
  `dev-workflows.run.auto-rules`, `dev-workflows.run.presubmit`, `dev-workflows.ladder.*`,
  `dev-workflows.quality.never-weakens-a-gate`, `dev-workflows.quality.rung-not-run-is-truthful`,
  `dev-workflows.quality.security-scan-rung`, `dev-workflows.quality.scan-thresholds-and-waivers`,
  `dev-workflows.security.untrusted-text`, `pipeline.test-red-on-base` [OK], `pipeline.pinned-checks` [OK],
  `perf-sweep.rung.not-run-is-visible` [BROKEN] (fix first), `perf-sweep.ratchet.budgets`,
  `perf-sweep.ratchet.baseline-from-n-runs`, `perf-sweep.ratchet.noise-band`.

- `local.resources-measured` [GAP] (#6116) — every batch records peak memory during the checks, the size of the state
  folder and of the test database before and after, and disk free; each has a budget in `harness.toml`; over budget
  is a red rung once enforcement is on. No model judges these. Absorbs `perf-sweep.output.row`. Serves: reliable.
- `local.wall` [GAP] (#6116) — the wall around a worker, proved by probes before each start: standard accounts with no
  administrator rights; every home closed to the others; no GitHub login, ssh key or keychain item in the worker's
  reach; the model key either capped by a hard spend limit or added by a relay on the loop's side so the worker never
  holds it; network limited to the model endpoint, the package registries and read-only GitHub; nothing sensitive in
  the shared and temporary folders; limits on disk and run time; signing keys in a keychain only the release script
  unlocks. A probe that gets through refuses the start. Absorbs `agent-profiles.isolation.baseline` [PARTIAL],
  `dev-workflows.run.jail-home`, `dev-workflows.security.untrusted-text`. Serves: reliable.

### B2. Specs are checked before anything is built from them

- `local.spec-lint` [GAP] (#6116) — a script refuses a spec for approval unless every behaviour has a unique id, a tag, a
  named test or an owed-test note, a size, and a "serves" line; it lists every sentence that contradicts another
  spec's ruling by id. Absorbs what `spec-pipeline.md` asks of the spec ↔ issues ↔ tests check. Serves: reliable.
- `local.spec-sceptical-read` [GAP] (#6116) — before approval a model that did not write the spec reads it against the code
  and writes a review file beside it: what is claimed built and is not, what cannot be tested as written, what is
  missing. `performance-sweep-REVIEW.md` is the pattern: that read found two rungs reporting green without running.
  Serves: reliable.

### C. The manager and escalation

- `local.manager` [GAP] (#6116) — the manager role runs on a local model in Pi. It may feed lanes, pause, resume, requeue,
  park, file issues and answer routine worker questions. It may not relax a check. Absorbs
  `agent-profiles.role.manager` [GAP] (#6638). Serves: builds Fichero.
- `local.escalation-tiers` [GAP] (#6116) — tiers are config: local builder → second local model → PARKED. During the build
  a cloud tier may sit above; it is removed at handover. Serves: reliable.
- `local.escalation-triggers` [GAP] (#6116) — only mechanical triggers escalate: two failed fix rounds, the same rung red
  twice, a false DONE, a turn cap with no commit, repeated tool-call failures. The worker's opinion is not a trigger.
- `local.pre-routing` [GAP] (#6116) — the brief routes a step before any attempt: size L, routes, entitlements, pinned or
  judging files, and any step kind whose recorded local failure rate is over half go to the tier that can do them.
  The rules are rewritten weekly from the escalation rows.
- `local.escalation-row` [GAP] (#6116) — one journal row per escalation: step, kind, trigger, from, to, cost. A daily dollar
  cap; past it, steps park.
- `local.must-escalate` [GAP] (#6116) — a weakened or deleted test, an excused red-on-base, any change to a pinned file, a
  guard, the ladder or `harness.toml`, anything on routes or entitlements, a step blocked twice, spend over cap.

- `local.question-list` [GAP] (#6116) — scripts decide what is a question (the escalation triggers, a refused start, a
  contradiction the lint found); a model only drafts the wording and a proposed answer. Questions sit in one list on
  the console, each with its proposed answer, its risk and a deadline. A low-risk question takes its proposed answer
  when its deadline (24 hours) passes and says so in the journal; a risky one (anything in `local.must-escalate`) waits.
  Absorbs `dev-workflows.node.human-question` [PARTIAL]. Serves: builds Fichero.

### D. Review

- `local.reviewer-differs` [GAP] (#6116) — the reviewer is never the builder's model. Serves: reliable.
- `local.shadow-reviewer` [GAP] (#6116) — an open model's verdict is recorded beside the binding one and decides nothing;
  agreement is reported weekly; promotion needs the numbers and a yes. Absorbs `pipeline.review` [PARTIAL] (Claude
  binding, Qwen shadow), `dev-workflows.models.review-by-path` [PARTIAL], `dev-workflows.review.performance-lens`
  [OK], `dev-workflows.review.security-lens` [OK].
- `local.bug-hunt-per-milestone` [GAP] (#6116) — when a milestone's last step lands, and before any release, a model other
  than the builder reads the milestone's changes together, looking for faults between steps that a per-step review
  cannot see; each finding is an issue with a failing test owed. Not run per step. Absorbs
  `dev-workflows.quality.bug-review-stream` [GAP]. Serves: reliable.
- `local.judging-files-reviewed` [GAP] (#6116) — a change to the harness's own judging files is reviewed by the strongest
  model available, and after handover needs the owner.

### E0. Issues and milestones stay current, on GitHub

Issues and milestones live on GitHub; the spec is their source and `builder` is their only writer.

- `local.issues-close-on-landing` [GAP] (#6116) — an issue closes only by `builder landed`, once its commit is on
  `origin/integration`; the behaviour it built is marked [OK] and the rules are re-pinned in the same act. Absorbs
  `issues.harness-closes-after-integration` [OK] (#6337), `dev-workflows.run.issues-close-when-done` [PARTIAL],
  `pipeline.closes-issues` [PARTIAL], and the workflows `close-fixed-issues.yml` and `issue-milestone.yml`.
- `local.push-or-nothing-closes` [GAP] (#6116) — `builder landed` refuses a commit `origin` lacks, so a loop that does not
  push blocks every step and closes nothing. The owner said yes to this on 2026-11-18, so the loop runs
  with the push enabled; the report still shows any step waiting on a push.
- `local.milestone-closes-when-empty` [GAP] (#6116) — a milestone with no open issue that no spec still needs is closed by
  `builder triage`; one a spec still needs stays open. Absorbs the six `issues.*` behaviours and
  `pipeline.issues-and-milestones-kept-current` [MISSING].
- `local.drift-is-reported` [GAP] (#6116) — the weekly report lists every disagreement between the spec, GitHub and the
  code: an [OK] behaviour with an open issue, a closed issue whose behaviour is not [OK], an issue with no milestone,
  a landed commit that closed nothing.

### E. Nightly, CI and release

- `local.ci` [GAP] (#6116) — GitHub Actions run engine tests, guards and the security scans on every lane push (the repo is
  public; standard runners cost nothing). Mac builds run on a self-hosted runner limited to this repo's own branches,
  never fork pull requests. Absorbs `pipeline.github-actions` [PARTIAL].
- `local.nightly` [GAP] (#6116) — the nightly runs on a schedule and publishes a dev pre-release only when every stage is
  green. Absorbs `dev-workflows.run.nightly-build` [PARTIAL], `pipeline.nightly-gate` [PARTIAL].
- `local.notes-with-every-tag` [GAP] (#6116) — no tag without notes. At `v2026.11.18` the newest entry in
  `RELEASE_NOTES.md` is 2026.11.12; tags 11.13, 11.14, 11.17 and 11.18 have none, and `docs/_latest.md` still points to
  2026.10.30. The release script drafts the entry from the landed issues since the last tag (their titles and
  `type:` labels, grouped by area, in plain words for a user), writes `RELEASE_NOTES.md`, `CHANGELOG.md` and
  `docs/_latest.md`, and refuses to tag if any of the three is stale. Serves: builds Fichero.
- `local.one-trailer` [GAP] (#6116) — every commit names its model, harness and builder in one format; the release held
  about ten spellings. Absorbs `agent-profiles.trailer.one-line` [PARTIAL]. Needed before models are compared.
- `local.release-channels` [GAP] (#6116) — four channels: dev, alpha, beta, release. Dev is automatic (`local.nightly`).
  A promotion to alpha, beta or release is prepared by script and approved by the owner: the script checks that the
  build's nightly was green at every stage, the smoke test passed on a clean machine, no escalation is open, no check
  was relaxed since the last promotion without a recorded review, and the notes are written; it then puts one
  question in the owner's list ("promote build X to beta?") with the evidence. This question never answers itself.
  On his yes the release script runs, with one journal row. Signing keys are used only by that script. Absorbs
  `pipeline.weekly-release` [PARTIAL]; `release-channels-and-feature-tiers.md` stays the source for what each
  channel means. Serves: builds Fichero, reliable.

### F. State and reporting

- `local.journal-is-the-record` [GAP] (#6116) — nothing edits `journal.jsonl`; the database is rebuilt from it by one command.
  Absorbs `builder-console.store.one-database` [GAP] (#6644), `dev-workflows.ledger.one-row-per-unit` [GAP] (#6379).
- `local.report-by-query` [GAP] (#6116) — the weekly report is produced by queries: steps landed on Fichero versus on the
  harness; share READY within two fix rounds, by model; cost per landed step by role; escalations and how many asked
  to relax a check; shadow agreement; the parked list; the cloud exceptions. Absorbs
  `dev-workflows.ledger.comparison-view`, `dev-workflows.ledger.break-even-view` (#6387),
  `dev-workflows.bakeoff.decision-table` (#6380), `agent-profiles.bakeoff.measured`, `agent-profiles.run.record`.
- `local.console-reachable` [GAP] (#6116) — the existing web console is reachable from the owner's phone and laptop, read-only
  by default. Absorbs `dev-workflows.console.tailnet-read-only`, `dev-workflows.console.phone-layout`,
  `builder-console.step.one-state` [BROKEN], `builder-console.numbers.labelled` [BROKEN] (fix both first).

### G. Handover

- `local.rulings-become-rules` [GAP] (#6116) — each escalation the supervising manager answers also files the guard, rule or
  routing entry that would have decided it. An escalation answered twice is a defect.
- `local.promotions-stay-with-owner` [GAP] (#6116) — handover changes nothing about promotions: alpha, beta and release
  stay the owner's yes.
- `local.handover` [GAP] (#6116) — the supervising manager is done when, for two consecutive weeks: no escalation reached it,
  the parked list stayed short, shadow agreement held, and no check was relaxed. It writes a handover note and stops.
- `local.freeze` [GAP] (#6116) — after handover the harness takes fixes only; a new harness feature needs the owner.

### H. The loop moves onto LangGraph

The loop's state machine is about 3,200 lines of the Builder's own Python (`queue.py`, `work.py`, `run.py`). This
spec adds escalation tiers, a manager, a shadow reviewer, parked-step retries and a question list: all orchestration.
Fichero's engine already uses LangGraph. The owner has ruled that the Builder adopts it.

- `local.orchestration-on-langgraph` [GAP] (#6116) — the step state machine (queued, sent, checking, reviewing, fixing,
  landed, blocked, parked, escalated) runs as a LangGraph graph with its state saved in SQLite. The jail, the worker
  sessions, the handoff, the ladder, the GitHub writes and the release script stay the Builder's own code, called
  from the graph. The JSONL journal stays the record: every state change still writes a row. Serves: reliable.
- `local.migration-one-lane-first` [GAP] (#6116) — the move is made one lane at a time, the first beside the current loop
  on the same steps. A lane has moved when the existing crash, restart and resume tests pass unchanged against it,
  and a worker that runs for hours and hands off at its mark carries on correctly. The old loop is deleted only when
  every lane has moved. If the long-running worker or the handoff cannot be kept, stop and report: that design
  outranks the library. Serves: reliable.
- `local.pinned-dependency` [GAP] (#6116) — the package version is pinned and recorded with the rules; an upgrade is a step
  like any other, with the full ladder. The Builder still does not import the engine it judges. Serves: reliable.
- `local.new-orchestration-on-the-graph` [GAP] (#6116) — escalation, the manager's moves, parked-step retries, the question
  list and the reviewers (binding, shadow, bug hunt) are built as graph nodes and pauses, never as more hand-written
  state code. LangChain is not adopted for this: it assembles model calls, and the Builder runs whole agents.

## What is brought in, spec by spec

| Spec | Bring in | Leave |
|---|---|---|
| `dev-workflows.md` | all of A (workers), B (review, landing, gates, watches), D (models); the ledger, bakeoff, quality, ladder and security groups; the tools (`check`, `work`, `steps`, `milestone`, `landed`, `queue`, `build`, `triage`); the rulings on isolation and landing | F (Researcher and the web) → Deferred; `pool.*` (six behaviours for routing across machines) → retired once the Studio runs; Stage 0 history |
| `agent-profiles.md` | the adapter interface, the Pi adapter, the common prompt and assembly, `worker.small`, the Swift rungs, `role.manager`, `bakeoff.measured`, `run.record`, `isolation.baseline` | five adapters (opencode, Qwen Code, Codex CLI, Gemini CLI, goose) → Deferred; `workflow.text-project` → Deferred |
| `deterministic-conductor.md` | `test-red-on-base`, `pinned-checks`, `cost-cap`, `retry-with-the-failure`, `github-actions`, `nightly-gate`, the shadow-reviewer idea, `resume-from-journal`, `pause-all` | the rest: superseded by `dev-workflows`; `retire-fs-skills`; the Bernstein and tool survey (keep as history) |
| `builder-console.md` | `store.one-database`, `step.one-state`, `numbers.labelled`, `stale.acted-on`, `step.moves-on`, `read-only-by-get`, the Runs and Compare pages as queries | `edit.both-ways`, `repo.split-held`, `work-store.host-agnostic` → Deferred |
| `performance-sweep.md` | `rung.not-run-is-visible` (fix), the three `ratchet.*` behaviours, `output.row`, `output.table`, the `warnings.*` behaviours | app profiling, MetricKit and field sources, automatic "speed up" issues → Deferred until budgets exist |
| `issues-and-labels.md` | all six behaviours (the milestone is the spec; the closed label set; pick order) | — |
| `spec-pipeline.md` | the state check of spec ↔ issues ↔ tests, if `builder triage` does not already cover it; say which | whatever `builder triage` and `builder steps` replaced |
| `git-worktree-workflow.md` | `shared-venv` [OK] and the worktree rules the loop relies on | hand-run procedures the loop replaced |
| `dev-orchestration-harness.md` | nothing: four [PROPOSED] behaviours about roles and routing, all superseded | the file, marked superseded |
| `builder-mac-app.md` | nothing now | all 12 behaviours → Deferred (see below) |
| `performance-sweep-REVIEW.md` | its findings, as notes under § B | the file |

## Deferred (written down, not built until the goal is met)

- **The Builder as a Mac app** (`builder-mac-app.md`, 12 [GAP]). The web console reachable from the phone covers
  watching. An app is more harness to sign, sandbox and maintain.
- **Five more adapters.** Pi is enough to reach the goal; add one only when a bake-off needs it.
- **The Researcher and text projects.** The same harness on research projects is a second product.
- **Machine pooling.** Built for one overloaded laptop and three helpers; one Studio removes the need.
- **Perf automation beyond budgets.** Profiling the app and filing issues automatically wait for a working baseline.
- **Console editing in both directions, and host-agnostic work stores.**

## Not part of this spec (they stay separate; they are about Fichero, not the harness)

`audited-action-layer.md`, `engine-startup-lifecycle.md`, `observable-data-layer.md`, `surfaces-from-openapi.md`,
`version-and-contract-integrity.md`, `code-organization.md` (APPROVED 2026-11-14), `release-and-versioning.md`,
`release-channels-and-feature-tiers.md`. Phase 0 should propose moving these out of `specs/harness/` so the folder
holds one harness spec. § E keeps the owner's yes for alpha, beta and release and makes the dev build automatic; `release-and-versioning.md` is amended only where it says otherwise.

## Absorbed decisions and rulings

The decisions, rulings and open questions of the specs this one absorbs, moved in Phase 0 word for word. Where one of them
disagrees with "Decisions" or "Rulings this overturns" above, the text above wins; the Phase 0 review lists each case.

## Build order

Each step is one issue under the one milestone. Sonnet builds and Opus reviews the harness's own code until the
bake-off says otherwise. Sizes are for Phase 0 to set.

- **Phase 0 — combine, answer, report. Nothing is built.** Move the absorbed behaviours into this file under their
  ids; mark the old specs superseded; merge the milestones and move the open issues; run `local.spec-lint` by hand
  and a sceptical read on this spec; answer "Questions Phase 0 must answer"; list every overturned ruling for the
  owner. The manager decides whether to go on, records why, and tells the owner.
- **Phase 1 — Pi on OpenRouter, and CI.** `agent-profiles.adapter.pi`, `local.bridge-openrouter`,
  `local.memory-budget`, `local.interim-16gb`, `local.ci`. CI is here because a 16 GB machine cannot carry the checks
  and the lanes together.
- **Phase 2 — the gates.** Fix the two [BROKEN] rungs and the two [BROKEN] console behaviours;
  `local.resources-measured`; `local.gates-enforce`; `local.wall`; `local.spec-lint`;
  `local.spec-sceptical-read`. This comes before any open model builds real work.
- **Phase 3 — state and reports.** `local.journal-is-the-record`, `local.report-by-query`,
  `local.console-reachable`, `local.one-trailer`, `local.notes-with-every-tag`, § E0.
- **Phase 4 — the bake-off.** Qwen3-Coder-Next on Pi against Sonnet on Claude Code: same briefs, same base, same
  ladder, same reviewer; three kinds of step (an engine change owing a red-on-base test, a Swift change, a
  `fichero-builder` change); handoffs scored. The manager chooses a builder and records why.
- **Phase 5 — the loop moves onto LangGraph.** § H, one lane first.
- **Phase 6 — manager, escalation, questions, reviewers.** § C and § D, built on the graph.
- **Phase 7 — nightly and release.** `local.nightly`, `local.release-channels`.
- **Phase 8 — the Studio (128 GB).** Move to the machine; point the roles at the local server; repeat the bake-off
  on the compressed build; `local.swift-tests-per-batch`, `local.xcode-worker`, `local.worker-sandboxed`; the
  isolation trial; retire `pool.*`.
- **Phase 9 — handover and freeze.** § G.

## Stop rules

Stop and report if: more than a third of steps end blocked or parked; the supervising manager's tokens exceed what
Sonnet used for the same work, or its use crowds the owner's own on the Max plan; OpenRouter passes 50 dollars in a week; relaxed checks rise week over week; or the harness's share of landed steps stays above
half for two weeks after the freeze.

## Behaviour tests

The test tables of the absorbed specs, moved in Phase 0. A behaviour's own bullet names its test; these tables are the
index each spec kept.

## Answers from the owner (2026-11-17 and 2026-11-18, paraphrased)

1. **The one database is SQLite,** for the harness only. Fichero itself keeps DuckDB.
2. **The overturned rulings: yes** (see the table). The loop pushes; scripts move a step between tiers.
3. **Releases:** a dev build every night, automatically. The owner approves alpha, beta and release.
4. **The manager decides at every stop** in the build order (after Phase 0, the bake-off, each lane's move to
   LangGraph, promoting a shadow reviewer). It records its reasons and tells the owner afterwards.
5. **Accounts: three, plus a sandbox.** The owner, the worker, the GUI test user; a sandbox profile on the worker;
   the signing keys in a separate keychain only the release script unlocks. The production Fichero server and the
   real data stay under the owner's account, which the worker cannot read.
6. **Outside packages are allowed** where they make the Builder work better. LangGraph is adopted.
7. **Spend:** OpenRouter up to 50 US dollars a week. The supervising manager runs on the owner's Claude Max plan.
8. **The machine:** the 128 GB Studio when it arrives; until then the M1 Pro stays main.
9. **Low-risk questions** take their proposed answer after 24 hours. Promotions and anything in
   `local.must-escalate` never do.
10. **Parked steps are picked up automatically.** A parked step is retried when something that could change the
    outcome has changed: a new or updated model in the slate, a changed routing rule, a fix to the step's brief, or
    a landed step it depended on. Parked through two such retries, or for more than a week, it becomes an issue
    saying what the local models could not do. It is never retried unchanged in a loop.
11. **After handover the judging rules** (guards, the ladder, `harness.toml`) are changed only by a one-off
    supervising session the owner starts, with a journal row. Nothing local changes them.

## Still open

1. **Stronger isolation for the worker** beyond three accounts and a sandbox profile (a virtual machine per lane).
   `agent-profiles.isolation.research-and-choice` [GAP] asks for a measured trial; run it on the Studio and choose.

## Questions Phase 0 must answer (the manager reports these; nothing is built first)

1. **What is on GitHub?** Every harness milestone with its open and closed counts, against the merge list here.
   Which cited issues are open, closed, duplicated or product issues.
2. **Which spec governs each topic,** and every disagreement between specs, with how each was resolved.
3. **Does `agent-profiles.worker.small` conflict with the long-running worker?** Quote both.
4. **Which `local.*` behaviours repeat an existing behaviour?** Cut each one and keep the existing id.
5. **The control numbers on Sonnet today,** from the journal: share of steps READY within two fix rounds, share
   blocked, handoffs per lane, cost per landed step, steps landed per night. Every later comparison rests on these.
6. **Can a Pi worker start today?** What is missing from the adapter, by file.
7. **Pi and Xcode:** can Pi use Xcode's tools through `xcrun mcpbridge`, and can Pi be brought into Xcode through
   the Agent Client Protocol? How does an Xcode worker sit with the jail, when the bridge talks to Xcode inside one
   user's session?
8. **The model slate:** exact OpenRouter ids, the serving provider and quantization, each model's size at 4-bit,
   its usable context window on the Studio, and whether the slate fits in 85 GB.
9. **What does not fit on the 16 GB M1 Pro,** and where each such job runs until the Studio arrives.
10. **Why do tags have no release notes** (11.13, 11.14, 11.17, 11.18), and why are there about ten spellings of
    the commit trailer?
11. **The plan for moving onto LangGraph:** which lane goes first, which existing tests are the acceptance, and how
    a worker that runs for hours fits a graph.
12. **The steps to file,** in order, with sizes; what will not be built; the spend expected.
