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

Phase 0 (2026-11-18) cut sixteen `local.*` behaviours that repeated an existing id; each existing bullet carries the cut one's new sentence as a
"Phase 0 amendment" line, and the review file lists the pairs. Absorbed behaviours sit under "From `<spec>`" headings below § H, each under its own id and tag.

New behaviours carry the prefix `local.` and are all [GAP]. Absorbed behaviours keep their ids. Each new behaviour cites #6116, the harness's
parent issue, until `builder steps` files one issue per step. The absorbed behaviours follow § H, one "Absorbed from"
section per spec, word for word.

### A. Workers and models

**The worker model is kept as it is: one long-running worker per lane.** A lane is a milestone. The worker stays
open across steps and keeps what it has read; the loop feeds it one step at a time, runs the checks and the review on
the owner's side, and sends the next brief into the same session. A new session starts only when the worker is gone
or at its handoff. This is the owner's ruling of 2026-11-01 and nothing in this spec replaces it.

- `local.handoff-per-model` [GAP] (#6116) — the handoff point is set per model, not once. Today `harness.toml` has
  `window = 200000`, `handoff_at = 0.85` and `handoff_tokens = 175000`, chosen for Sonnet. Each model in the slate
  declares its usable window on this machine (a local model's is bounded by memory and by how slowly it re-reads a
  long prompt, not only by its trained length), and the 85 % rule applies to that. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.worker-sandboxed` [GAP] (#6116) — the Pi worker process starts inside a sandbox profile as well as in the worker
  account: it may write only its worktree and scratch, read its own install and the checkout, and reach only the
  model endpoint, the package registries and read-only GitHub. The checks and the review already run outside the
  worker's session, so the profile does not have to admit them. Pi has no permission system of its own, so this and
  the policy extension (`pi/policy.ts`, which blocks any tool call not answered ALLOW) are the limits. The start
  probes prove the wall before each worker runs. Serves: reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.handoff-measured` [GAP] (#6116) — the bake-off scores a model on handoffs as well as steps: whether the successor
  carries on correctly from the handoff file, redoes finished work, or loses the thread. A model that builds one step
  well and cannot survive a handoff does not pass. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.xcode-worker` [GAP] (#6116) — a Swift step goes to an Xcode worker: a Pi worker with Xcode's own tools, reached
  through Xcode's MCP server (`xcrun mcpbridge`, with "Allow external agents to use Xcode tools" on). It builds,
  reads structured build errors, runs named tests and renders SwiftUI previews through Xcode, not through a bare
  `xcodebuild`. This mirrors what works today with Claude inside Xcode (the release holds commits written "using
  Xcode using Fichero Builder"). Xcode must be open on the lane's worktree in a logged-in session, so this worker
  runs in the GUI test user, one Xcode per lane; Phase 0 says how that sits with the jail, since the bridge talks to
  Xcode inside one user's session. Rendered previews and test results are attached for the reviewer, who today sees
  only the diff. Also try the other direction once: Xcode 27 accepts outside agents through the Agent Client
  Protocol; record whether Pi can be brought in that way and which works better. Serves: builds Fichero, reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.escalation-by-handoff` [GAP] (#6116) — escalating a step to another tier ends the session through the same handoff
  path: the next tier starts from the handoff file plus the failed diff, the ladder output and the findings. When the
  step lands, the lane's own worker resumes from a fresh handoff. Serves: reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)


- `local.target` [GAP] (#6116) — every role (builder, reviewer, manager, helper) names a local provider it can run on; a role
  that works only with a cloud model is a named exception with its reason and what would remove it. The weekly report
  lists the exceptions. Serves: local.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.memory-budget` [GAP] (#6116) — `harness.toml` states the machine's model budget (85 GB on the 128 GB Studio) and each
  model's loaded size; a slate that does not fit beside the gate and a build is refused at start. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.interim-16gb` [GAP] (#6116) — until the Studio arrives the 16 GB M1 Pro is the main machine and the helpers
  (`[check].remote`, the nightly runners) stay as `harness.toml` has them: no local model server; lanes capped to
  what the machine holds; engine tests, guards and scans also run on GitHub's hosted runners so the Pro is not the
  only place they run; the full nightly check (budgeted at 14 GB) stays on its remote runner. Swift steps stay with
  the cloud builder until `dev-workflows.run.swift-tests` is green. Nothing built now is machine-specific: moving to
  the Studio is config, and `pool.*` is retired only then. Serves: builds Fichero.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.bridge-openrouter` [GAP] (#6116) — OpenRouter is a Pi provider; the key comes from the environment and is written
  nowhere; the model id, the serving provider and its quantization are recorded per run. Serves: local.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.compressed-is-the-measure` [GAP] (#6116) — a decision to adopt a model cites runs on the compressed build on Mac
  hardware, not only the hosted full-precision one. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- Absorbed: `agent-profiles.adapter.interface` [OK], `agent-profiles.adapter.claude-code` [OK],
  `agent-profiles.adapter.pi` [PARTIAL] (#6631), `dev-workflows.models.by-config` [PARTIAL],
  `agent-profiles.worker.small` [GAP], `dev-workflows.worker.handoff` [PARTIAL] (the handoff follows the model's
  real context window).

### B. Gates — what makes it reliable

With no stronger model on call, quality is whatever the gates enforce. These are the core of the spec.

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
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### B2. Specs are checked before anything is built from them

- `local.spec-lint` [GAP] (#6116) — a script refuses a spec for approval unless every behaviour has a unique id, a tag, a
  named test or an owed-test note, a size, and a "serves" line; it lists every sentence that contradicts another
  spec's ruling by id. Absorbs what `spec-pipeline.md` asks of the spec ↔ issues ↔ tests check. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.spec-sceptical-read` [GAP] (#6116) — before approval a model that did not write the spec reads it against the code
  and writes a review file beside it: what is claimed built and is not, what cannot be tested as written, what is
  missing. `performance-sweep-REVIEW.md` is the pattern: that read found two rungs reporting green without running.
  Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

- `local.spec-screen-evidence` — **[OK]** (#7067) a screen is done only when it exists: a spec behaviour tagged [OK] or [BUILT]
  whose text after the tag contains the word `app` (matched as a whole word, so "application" does not count) must cite a Swift test file under fichero/Tests (a UI test included);
  citing only pytest files fails as "engine done, the screen is not". Offenders at landing are in
  `scripts/check_spec_app_evidence_baseline.json`, which fails when a listed line now passes. Wired by the `check_spec_*.py`
  glob in CI. Test: `fichero-server/tests/unit/scripts/test_check_spec_app_evidence.py::test_an_ok_app_behaviour_citing_only_pytest_is_engine_done_the_app_part_is_not`,
  `test_a_swift_test_path_or_a_ui_test_satisfies_it_and_a_non_app_or_gap_line_is_not_judged`,
  `test_a_new_offender_fails_a_baselined_one_passes_and_a_listed_line_that_now_passes_fails`.
- `local.spec-ux-section` — **[OK]** (#7067) a spec file with a behaviour that contains the word `app` (any live tag) has a "What the person sees" (or "UX")
  section that says, for each screen, where the person opens it (menu, window, pane or shortcut), what it shows, its controls,
  the empty, loading and error states with how each is tested, and an acceptance line; a spec without one is in the same
  shrinking baseline. Test: `fichero-server/tests/unit/scripts/test_check_spec_app_evidence.py::test_a_spec_with_app_behaviours_needs_a_ux_section_naming_opener_states_and_acceptance`.
- `local.engine-ux-coverage-report` — **[OK]** (#7067) `scripts/report_engine_ux_coverage.py` prints, for the operations frozen in
  `check_endpoint_coverage_matrix_known_gaps.json`, how many no spec names, how many a spec names with no `app` behaviour, how
  many have an `app` behaviour still [GAP], and how many `app` features have no UX section, with the first 20 of each. First run
  (2026-11-23): 221 / 58 / 33 / 111. Test: `fichero-server/tests/unit/scripts/test_report_engine_ux_coverage.py::test_each_known_gap_lands_in_one_bucket_no_spec_no_app_behaviour_or_app_behaviour_still_gap`,
  `test_the_report_prints_the_three_counts_the_ux_count_and_the_top_twenty`.
- `local.new-route-has-a-spec` — **[OK]** (#7067) `check_endpoint_coverage_matrix.py` fails a route whose path or operation id no spec
  names, unless it is in `check_endpoint_coverage_matrix_no_spec_baseline.json` (694 at landing). Test:
  `fichero-server/tests/unit/scripts/test_report_engine_ux_coverage.py::test_the_matrix_fails_a_route_no_spec_names_unless_it_is_baselined`.
- `local.review-screen-lens` — **[OK]** (#7067) the reviewer prompt's third lens (`review_lenses.APP_SCREEN`) makes a step whose
  behaviours contain the word `app` NOT READY when the diff adds no Window/openWindow id, menu command or pane kind reaching the feature.
  Test: `fichero-builder/tests/test_perf_sweep.py::test_the_reviewer_refuses_an_app_step_whose_diff_adds_no_screen_reaching_the_feature`.

### C. The manager and escalation

- `local.escalation-tiers` [GAP] (#6116) — tiers are config: local builder → second local model → PARKED. During the build
  a cloud tier may sit above; it is removed at handover. Serves: reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.escalation-triggers` [GAP] (#6116) — only mechanical triggers escalate: two failed fix rounds, the same rung red
  twice, a false DONE, a turn cap with no commit, repeated tool-call failures. The worker's opinion is not a trigger.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.pre-routing` [GAP] (#6116) — the brief routes a step before any attempt: size L, routes, entitlements, pinned or
  judging files, and any step kind whose recorded local failure rate is over half go to the tier that can do them.
  The rules are rewritten weekly from the escalation rows.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.escalation-row` [GAP] (#6116) — one journal row per escalation: step, kind, trigger, from, to, cost. A daily dollar
  cap; past it, steps park.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.must-escalate` [GAP] (#6116) — a weakened or deleted test, an excused red-on-base, any change to a pinned file, a
  guard, the ladder or `harness.toml`, anything on routes or entitlements, a step blocked twice, spend over cap.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)

- `local.question-list` [GAP] (#6116) — scripts decide what is a question (the escalation triggers, a refused start, a
  contradiction the lint found); a model only drafts the wording and a proposed answer. Questions sit in one list on
  the console, each with its proposed answer, its risk and a deadline. A low-risk question takes its proposed answer
  when its deadline (24 hours) passes and says so in the journal; a risky one (anything in `local.must-escalate`) waits.
  Absorbs `dev-workflows.node.human-question` [PARTIAL]. Serves: builds Fichero.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### D. Review

- `local.reviewer-differs` [GAP] (#6116) — the reviewer is never the builder's model. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.judging-files-reviewed` [GAP] (#6116) — a change to the harness's own judging files is reviewed by the strongest
  model available, and after handover needs the owner.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### E0. Issues and milestones stay current, on GitHub

Issues and milestones live on GitHub; the spec is their source and `builder` is their only writer.

- `local.push-or-nothing-closes` [GAP] (#6116) — `builder landed` refuses a commit `origin` lacks, so a loop that does not
  push blocks every step and closes nothing. The owner said yes to this on 2026-11-18, so the loop runs
  with the push enabled; the report still shows any step waiting on a push.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.drift-is-reported` [GAP] (#6116) — the weekly report lists every disagreement between the spec, GitHub and the
  code: an [OK] behaviour with an open issue, a closed issue whose behaviour is not [OK], an issue with no milestone,
  a landed commit that closed nothing.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### E. Nightly, CI and release

- `local.notes-with-every-tag` [GAP] (#6116) — no tag without notes. At `v2026.11.18` the newest entry in
  `RELEASE_NOTES.md` is 2026.11.12; tags 11.13, 11.14, 11.17 and 11.18 have none, and `docs/_latest.md` still points to
  2026.10.30. The release script drafts the entry from the landed issues since the last tag (their titles and
  `type:` labels, grouped by area, in plain words for a user), writes `RELEASE_NOTES.md`, `CHANGELOG.md` and
  `docs/_latest.md`, and refuses to tag if any of the three is stale. Serves: builds Fichero.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.release-channels` [GAP] (#6116) — four channels: dev, alpha, beta, release. Dev is automatic (`dev-workflows.run.nightly-build`).
  A promotion to alpha, beta or release is prepared by script and approved by the owner: the script checks that the
  build's nightly was green at every stage, the smoke test passed on a clean machine, no escalation is open, no check
  was relaxed since the last promotion without a recorded review, and the notes are written; it then puts one
  question in the owner's list ("promote build X to beta?") with the evidence. This question never answers itself.
  On his yes the release script runs, with one journal row. Signing keys are used only by that script. Absorbs
  `pipeline.weekly-release` [PARTIAL]; `release-channels-and-feature-tiers.md` stays the source for what each
  channel means. Serves: builds Fichero, reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)

### F. State and reporting


### G. Handover

- `local.rulings-become-rules` [GAP] (#6116) — each escalation the supervising manager answers also files the guard, rule or
  routing entry that would have decided it. An escalation answered twice is a defect.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.promotions-stay-with-owner` [GAP] (#6116) — handover changes nothing about promotions: alpha, beta and release
  stay the owner's yes.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.handover` [GAP] (#6116) — the supervising manager is done when, for two consecutive weeks: no escalation reached it,
  the parked list stayed short, shadow agreement held, and no check was relaxed. It writes a handover note and stops.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.freeze` [GAP] (#6116) — after handover the harness takes fixes only; a new harness feature needs the owner.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)

### H. The loop moves onto LangGraph

The loop's state machine is about 3,200 lines of the Builder's own Python (`queue.py`, `work.py`, `run.py`). This
spec adds escalation tiers, a manager, a shadow reviewer, parked-step retries and a question list: all orchestration.
Fichero's engine already uses LangGraph. The owner has ruled that the Builder adopts it.

- `local.orchestration-on-langgraph` [GAP] (#6116) — the step state machine (queued, sent, checking, reviewing, fixing,
  landed, blocked, parked, escalated) runs as a LangGraph graph with its state saved in SQLite. The jail, the worker
  sessions, the handoff, the ladder, the GitHub writes and the release script stay the Builder's own code, called
  from the graph. The JSONL journal stays the record: every state change still writes a row. Serves: reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.migration-one-lane-first` [GAP] (#6116) — the move is made one lane at a time, the first beside the current loop
  on the same steps. A lane has moved when the existing crash, restart and resume tests pass unchanged against it,
  and a worker that runs for hours and hands off at its mark carries on correctly. The old loop is deleted only when
  every lane has moved. If the long-running worker or the handoff cannot be kept, stop and report: that design
  outranks the library. Serves: reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.pinned-dependency` [GAP] (#6116) — the package version is pinned and recorded with the rules; an upgrade is a step
  like any other, with the full ladder. The Builder still does not import the engine it judges. Serves: reliable.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)
- `local.new-orchestration-on-the-graph` [GAP] (#6116) — escalation, the manager's moves, parked-step retries, the question
  list and the reviewers (binding, shadow, bug hunt) are built as graph nodes and pauses, never as more hand-written
  state code. LangChain is not adopted for this: it assembles model calls, and the Builder runs whole agents.
  Superseded: owned by docs/contributor_manual/specs/harness/ (the builder specs) (Spec-change: manager 2026-11-23)

### I. What the night of 2026-11-19 taught (#6589)

Ten lanes ran through one night. Each line below is a rule the loop broke or was missing that night, or one the owner
ruled on 2026-11-19 and 2026-11-20 (paraphrased). "Built" names the code that already does it; "left" is the gap.
Spec-change: owner 2026-11-20.

- `local.done-needs-delivery` [GAP] (#6589) — a worker's DONE ends a step only when it came after the step's message
  was delivered. The message is delivered when the pane shows it submitted; a DONE printed before that, or left on the
  pane from the step before, ends nothing. Today `tell.send` in `fichero-builder/fichero_builder/tell.py` returns success
  with a warning when it cannot see the text leave the input box, and the loop moves the step to `sent` either way.
  Acceptance: a step whose message was not seen submitted stays undelivered, and a DONE row older than the delivery is
  not read as that step's. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.undelivered-is-redelivered` [GAP] (#6589) — a message with no proof of delivery is kept and delivered again, to
  whichever session holds the lane next: a managed worker, an external session, or a new pane after a restart. It is
  dropped only when the step ends or is parked, with a row. Acceptance: a brief, a finding and a LANDED note sent to a
  pane that did not submit are each delivered once to the lane's next session, in order. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.no-commit-is-never-landed` [PARTIAL] (#6589) — a step with no commit of its own never reads `landed`. Built: a
  DONE from a tree with nothing past the land branch is blocked as a DONE with no commit
  (`fichero-builder/fichero_builder/queue.py`; test
  `fichero-builder/tests/test_loop.py::test_a_done_with_no_new_commit_this_session_still_counts_when_the_tree_is_ahead_of_origin`).
  A worker lane's step whose chain finds no commit over the land branch is blocked, never landed; only an external lane's
  batch with no commit over origin reads `landed` (`dev-workflows.run.loop-already-landed`). Test
  `fichero-builder/tests/test_loop.py::test_a_worker_step_with_no_commits_over_origin_is_blocked_never_landed`.
  Left: a worker step whose own commits are all on the land branch by patch is not yet told apart from one that made
  none. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.approve-remembered-per-head-and-reason` [PARTIAL] (#6589) — an approve is remembered for the head and the reason
  it was given, so the same head is not blocked again for the same reason. Built: the content bindings of
  `dev-workflows.ladder.approve-is-fingerprinted` and `dev-workflows.run.loop-approval-by-diff`; for red-on-base,
  needs-maintainer, weakened-tests, pinned-new and guard-data the approve is saved under the 9-character head the alert
  names (the refusal's `judged`), and the same head and reason go on by themselves once (one `auto-approve` row, no
  alert); if the same refusal comes back after that, it blocks and alerts again, so an approve that did not take effect
  cannot loop. Test `fichero-builder/tests/test_loop.py::test_an_approved_red_on_base_is_remembered_for_its_head_and_the_same_head_is_not_blocked_again`.
  Left: every other refusal kind, which asks again each time it is raised. Acceptance: an approved refusal raised again at
  the same head with the same reason is one `auto-approve` row and no alert the first time; a new head or a new reason is
  an alert as before. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.already-built-is-declared` [PARTIAL] (#6589) — a test that already passes on the base is declared, never slipped
  in: the commit holds tests only and its message carries `Already built: #N path::test`. Built: the red-on-base rung
  owes such a file no red and refuses it when it fails on base (`fichero-builder/fichero_builder/check_tool.py`), the
  landing comments the issue with the test (`fichero-builder/fichero_builder/landed.py`), and the step brief's head says
  it (`fichero-builder/fichero_builder/brief_tool.py`). Left: the common prompt (`fichero-builder/agents/common/common.md`)
  does not say it; the fix brief sent after a NOT RED ON BASE refusal does not say it; and the rung does not check that
  the declaring commit touches tests only. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.diff-bound-splits-the-step` [GAP] (#6589) — a batch over the diff bound is split by the loop, not sent back to a
  person: a core that fits the bound stays the step, and the rest becomes a new step `<lane>-part2` queued behind it on
  the same lane, each with its own tests. Today `check_tool.diff_bound` only refuses with the count. Acceptance: a
  batch of two commits whose sum is over the bound becomes two steps that each pass the bound; one commit over the
  bound alone is a question for the manager, never a silent pass. Serves: reliable, with little supervision.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.removed-tree-is-not-a-moved-tree` [OK] (#6589) — the check that no tree outside a step's own moved reads a tree
  that was removed since the step started (a landed lane's cleanup) as removed, and says nothing: `queue.tree_check` skips
  a path that no longer exists, and a landed lane's tree is not snapshotted (tests
  `fichero-builder/tests/test_loop.py::test_a_tree_removed_during_the_step_did_not_move_by_a_stray_write` and
  `fichero-builder/tests/test_loop.py::test_a_landed_lanes_worktree_is_not_in_the_snapshot_list`; a tree that changed
  still alerts in `fichero-builder/tests/test_loop.py::test_a_step_that_moves_another_lanes_tree_or_the_jail_root_alerts`). Acceptance: a tree
  snapped at the start and removed by `dev-workflows.run.loop-cleanup` raises no alert; a tree whose head or status
  changed still does. Serves: reliable.
- `local.dismiss-never-parks-in-flight` [PARTIAL] (#6589) — dismissing an alert never parks a step that is being worked
  on. Built: `queue.park_blocked` parks only a step still `blocked` (`dev-workflows.run.loop-dismiss-parks` and its
  tests). Left: on 2026-11-19 a dismissed alert parked a step whose session was at work on the finding; no test covers
  an alert whose step has since been sent back or retried, or a blocked step with a live session. Acceptance: Dismiss
  and Dismiss All leave such a step where it is and say so in the row. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.restart-resumes-the-night` [PARTIAL] (#6589) — after a crash or a restart of the machine the loop starts by
  itself and carries on: steps keep their state, a live session is adopted, and a session that was lost is queued again
  from its tree. Built: the LaunchAgents of `dev-workflows.run.loop-launchd`, and for a managed lane the adopt-or-queue
  rule in `fichero-builder/fichero_builder/queue.py` (`dev-workflows.run.restart-adopts-live-window`). Left: an external
  lane whose session died gets one alert a day and waits (`dev-workflows.run.loop-no-session`); a chain, a check or a
  release stage that was running at the crash has no test that it starts again. Serves: reliable, with little supervision.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.network-outage-is-infra` [PARTIAL] (#6589) — a network outage during a fetch, a rebase, a check or a GitHub call
  is infra: the step waits and the call is tried again until the network is back, with one row. It is never a conflict,
  a red or an alert for a person. Built: the rebase tries once more after 20 seconds on a network error
  (`fichero-builder/fichero_builder/work.py`), and a base run that cannot start is infra, not a verdict
  (`fichero-builder/fichero_builder/check_tool.py`). Left: an outage longer than that one retry blocks the step with the
  git error as if it were a conflict. Acceptance: with the remote unreachable for ten ticks a step in rebase stays in
  one `infra-wait` state with one row and no alert, and goes on by itself when the remote answers. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

#### Workers and scale: what ten workers showed

Measured on the night of 2026-11-19: ten worker lanes landed about one step an hour, the same rate as three to five
lanes. The limit was not the number of sessions. It was the checks, the review and the rebase each landing forces on
every other lane, and the processor and disk of the one Mac that runs the loop. More lanes past five added waiting
steps and disk use, not landings.

- `local.scale.lanes-follow-the-landing-rate` [GAP] (#6589) — the number of lanes that run at once is set from the measured
  landing rate, not from how many sessions the plan allows: the loop adds a lane only while the last hours show that
  a lane more landed more. Today the counts are fixed numbers in `harness.toml` (`[queue] workers`, `[loop] lanes`,
  `[check] parallel`). Acceptance: the nightly report gives landings an hour beside the lane count, and a lane count
  that did not raise the rate over a night is named in it. Serves: reliable, with little supervision.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.checks-run-on-other-macs` [PARTIAL] (#6589) — the checks are carried by check runners on other Macs so the
  loop's Mac keeps its processor and disk for the workers: one runner keeps its trees on an external disk, another is
  a desktop Mac. Built: `harness.toml` `[check] remote` lists the runners in order, a runner under
  `remote_min_free_gb` is skipped, and the nightly names its own `check_runner`. Left: which rung goes to which Mac is
  the list's order, not a placement by capability (`dev-workflows.pool.placement-and-fallback`). Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### J. What the day of 2026-11-21 showed (#6589)

Fourteen lanes ran through a day and a night. Each line below is something the loop did wrong or could not do, read from
that day's journal and placed in the code. The owner asked for them to be specified so the builder builds them
(paraphrased). Caps read once per session, and the disk floor's rows and alert, are specified by the performance review of
the same day (#6851, #6852) and are not repeated here. Spec-change: manager 2026-11-21.

- `local.run.reexec-adopts-by-window-or-pid` [PARTIAL] (#6589) — a loop that starts with no handle for a lane (a re-exec, a
  crash, a login) adopts every session that is alive, and stops none. A session is alive when the tmux window the lane
  recorded at its start still runs more than an idle shell, or when the process id it recorded is running. The loop
  watches it again (a watcher that died is started again on the same session and feed), writes one `adopted` row, and
  the step keeps its state. Only a lane with neither a live window nor a live process is queued again, and the lost-track
  branch never ends a window that runs more than a shell: that is an alert with the window's id. Today
  `queue.adopt_session` in `fichero-builder/fichero_builder/queue.py` adopts only when the lane still holds its feed path
  and `pgrep` finds a `builder run` on that feed; any miss falls to `procs.stop` in `queue.tick_lane`, which writes the
  stop marker, ends the lane's windows and queues the step again ("stopping the session this loop lost track of"). On
  2026-11-21 that row was written fourteen times, five of them within two minutes of one re-exec while the sessions were
  at work, and no `adopted` row was written all day. The lane does not record its window id or its process id at start.
  **Built** 2026-11-23, the half that ends no session: a window that runs more than a shell is never ended by the
  lost-track branch (`procs.live_windows`); one alert names the window id, the lane and the step, and the step keeps its
  state. A step that was `checking` before a restart still gets the file-bound split. Tests
  `fichero-builder/tests/test_builder_restart.py::test_a_live_window_the_loop_cannot_adopt_is_one_alert_with_its_id_and_is_never_stopped`,
  `fichero-builder/tests/test_builder_restart.py::test_a_step_that_was_checking_before_a_restart_still_gets_the_automatic_split`.
  Left: the window id and process id recorded at start, and a watcher started again on the same feed.
  Test (owed): `test_builder_restart.py`, a re-exec with five live windows and no watcher adopts five and stops none; a
  live process id with a renamed window is adopted; a lane with neither is queued once. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
  Built: the process id is recorded at start (`session_pid`) and a window or that process makes a lane alive, while its `builder run` still watches the feed (an unwatched session is the #6850 alert). Not built: the window id recorded at start, and a watcher started again on the same feed. Tests
  `fichero-builder/tests/test_builder_restart.py::test_a_re_exec_with_five_live_windows_adopts_five_and_stops_none`,
  `fichero-builder/tests/test_builder_restart.py::test_a_live_process_id_with_a_renamed_window_is_adopted`,
  `fichero-builder/tests/test_builder_restart.py::test_a_lane_with_neither_a_live_window_nor_a_live_process_is_queued_once`.
- `local.run.drain-expired-one-row` [OK] (#6589) — when the wait for a re-exec passes its limit, the loop says so once
  for each lane and head, and the re-exec then happens at the first tick with no chain running, before another chain
  starts. Today the branch after `DRAIN_MAX_S` in `queue.tick_lane` appends a `drain-expired` row every time it is
  reached and lets every chain start on the old code, so the quiet tick `queue.restart_due` waits for may never come:
  725 `drain-expired` rows on 2026-11-21 against 9 `drain-held`, and about 35 minutes of them before the re-exec.
  Test (owed): `test_loop_survives.py`, ten ticks past the limit write one row a lane and head, and the loop re-execs
  after the running chain ends with a second batch still waiting. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
  Built: `fichero-builder/tests/test_loop_survives.py::test_ten_ticks_past_the_drain_limit_write_one_row_a_lane_and_head_and_the_loop_re_execs_after_the_running_chain`.
- `local.run.sent-needs-a-live-session` [GAP] (#6589) — a step is `sent` only while a session is at work on it. At every
  tick the loop checks each `sent` step: the window runs more than a shell, and the session file has changed within
  `[spend].silent_s` or the session is idle after a delivered message. A `sent` step that fails the check for two ticks
  is one `queue` row `sent-no-session` and goes back to `queued` from its tree (counted as a restart, so the existing
  limit still blocks a step that keeps losing its session); a `sent` step older than `[loop].sent_hours` (default 3)
  with no row of its own in that time is one alert with retry and park. Today a live handle whose pane holds no agent
  reaches `procs.row(lane) is None` in `queue.tick_lane` and returns, tick after tick, with no row; one step sat `sent`
  that way for hours on 2026-11-21. Test (owed): `test_loop.py`, a `sent` step whose window runs a shell is queued again
  after two ticks with one row; a quiet `sent` step past the limit alerts once. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.run.turn-ended-without-done-alerts` [GAP] (#6589) — a worker whose turn ends after a delivered message with no
  DONE line and no handoff line is noticed within one tick, whether or not its branch moved. The watcher writes one
  `watch` row `turn-ended-no-done` with the last 300 characters the worker wrote. When that text ends in a question, it
  is one `question` alert for the manager (answer, send back, park), and the answer is told to the same session. When
  it does not, the worker is nudged once with the exact line to end on, and two ticks later the same alert is raised.
  This replaces "left alone while its branch has not moved" in `dev-workflows.rollout.dry-run`. Today the loop in
  `fichero-builder/fichero_builder/run.py` counts `unsaid` only when the head moved, and `watcher.assess` in
  `fichero-builder/fichero_builder/watcher.py` alerts only on a session that is not idle; a small-model worker sat idle
  on a question for an hour and a half on 2026-11-21. The signal comes from Claude Code's own `Stop` hook, not from
  reading the tmux window: the worker's settings.json the builder writes carries a `Stop` hook, which receives the turn's
  `last_assistant_message` and writes it to the lane's feed when it has no DONE or handoff line. An adapter whose harness
  has no such hook falls back to the window. Test (owed): `test_dry_run.py`, an idle worker with an unmoved
  branch and a last line ending in a question mark is one alert in one tick; one with no question is nudged, then
  alerted. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.disk.thin-snapshots-before-holding` [GAP] (#6589) — before the loop holds a new lane for disk, it frees what
  the system's local backup snapshots pin and measures again. On macOS, space freed by a sweep stays held by local Time
  Machine snapshots until they are thinned. Once in a low-disk episode, and at most once an hour, the loop runs
  `tmutil thinlocalsnapshots / <bytes> 4` (no sudo; bytes from `[loop].disk_thin_gb`, default 8), writes one
  `disk-thinned` row with the free space before and after, and holds the lane only if the floor is still not met. A
  machine without `tmutil`, or a command that fails, is a row and the hold goes on as before. Today the hold in
  `queue.tick_lane` reads `procs.free_gb` and returns; on 2026-11-21 it wrote 934 `disk-hold` rows, and the same command
  run by hand freed 10 to 14 GB twice. Test (owed): `test_loop.py`, a fake thin that frees space lets the lane start
  with one `disk-thinned` row; one that frees nothing holds; a second low reading within the hour does not thin again.
  Serves: reliable, with little supervision.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.run.waiting-is-one-ask-alert` [OK] (#6855) — a worker whose last line is `WAITING: <question>` is one ask alert
  for the manager. The step row records `waiting=<question>`, the step is `blocked` with that one alert, and
  `console.status()["open_questions"]` lists each open question with its lane and step (a Questions section in the
  console page). Only the WAITING alert's send-back with no `--text` is refused; a retry, an approve or a send-back clears the
  question, so a later alert on the step never asks it again. With text, the answer goes into a
  `sendback-<id>.txt` resume brief and the step is `queued` again; a live session gets it as its next message, and a new session reads it otherwise. Tests
  `fichero-builder/tests/test_loop.py::test_a_worker_that_ends_with_waiting_is_one_ask_alert_with_the_question_and_the_step_waits`,
  `fichero-builder/tests/test_loop.py::test_a_send_back_of_a_question_with_no_answer_is_refused_and_with_one_the_answer_reaches_the_session`,
  `fichero-builder/tests/test_loop.py::test_the_console_lists_each_open_question_with_its_lane_and_step`,
  `fichero-builder/tests/test_loop.py::test_a_retry_of_a_question_clears_it_so_a_later_send_back_of_another_alert_needs_no_answer`,
  `fichero-builder/tests/test_dry_run.py::test_a_waiting_end_message_is_one_step_row_with_the_question_and_the_session_stays`.
  Serves: reliable, with little supervision.
- `local.run.worker-starts-in-its-own-directory` [OK] (#6869) — a queued lane's worker command starts in
  `<workroot>/work-<lane>`, which the worker makes itself and which must be a directory, not a link, that it owns (the
  workroot is world-writable), and `TMPDIR` and pytest's `--basetemp` (through `PYTEST_ADDOPTS`) point inside it at
  `tmp/`. `start_tool.prepare` also puts `env TMPDIR=… PYTEST_ADDOPTS=…` in front of claude's argv, because a window
  opened in a running tmux server gets the server's environment, not the starter's. Tests
  `fichero-builder/tests/test_lane_role.py::test_a_workers_command_starts_in_a_directory_it_made_with_tmpdir_and_pytest_basetemp_inside_it`,
  `fichero-builder/tests/test_adapters.py::test_the_workers_tmpdir_and_pytest_basetemp_reach_the_session_command_not_the_tmux_servers_environment`.
  Serves: reliable.
- `local.queue.batch.one-step-many-parts` [GAP] (#6589; owner 2026-11-24: one landing costs about 10 minutes of checks, a review and a rebase) — `[queue].batch_max`
  (default 4). `builder queue add` with a brief that names one issue, on a lane whose next queued step has fewer than `batch_max` issues,
  appends the brief to that step as a new part instead of making a step: the step's one brief file gains a `## PART <n> (#<issue>)`
  heading and the new text (the first append adds `## PART 1 (...)` above the old text), the step's `issues` list gains the
  issue, one `part-added` row is journaled, and the verb prints `joined <lane> <step> as part <n>`. `--alone` keeps a step of its own (an
  urgent hang or crash). The loop marks a step `sent` in the queue file, under the queue lock, before it reads the step's brief, and `queue add` joins only a step it finds `queued` under that same lock, so a join is either in the brief the worker gets or a new step. A step that is not `queued`, or has a resume brief, a round or a head, is never changed; an issue the step already
  has, a brief that names several issues, and a milestone's `--enqueue` make steps as before. The fix brief and the review read the whole
  batch, because they read the one brief file and the step's `issues`. Acceptance: test
  `fichero-builder/tests/test_queue_batch.py::test_a_one_issue_brief_joins_the_next_unstarted_step_as_a_part` and its neighbours there.
- `local.queue.batch.parts-left` [GAP] (#6589) — a batch's worker ends with `PART <n> left: <why>` lines for the parts it did not do. The
  step's `step` row carries them; the step lands with only the parts done in its `issues`, and the loop queues `<step>-left` as the lane's
  next step with a brief of only the parts left, the owner's part text as written; the worker's reasons are never in a brief (it is inlined with the owner's allowlist) and are in the `queued` row's detail. A part number the brief does not have blocks the step with the question.
  Acceptance: `fichero-builder/tests/test_queue_batch.py::test_parts_the_worker_left_are_requeued_alone_as_the_lanes_next_step`,
  `fichero-builder/tests/test_dry_run.py::test_a_done_step_row_carries_the_sessions_context_model_window_and_the_parts_left`.
- `local.queue.session.keep-across-steps` [GAP] (#6589; owner 2026-11-24: a worker does more when it keeps what it learned) — `[queue].session`
  = `"lane"` (default) or `"step"`. With `lane`, when a step lands and the lane has a next step, the loop sends the next brief into the
  same live session, as it sends a fix brief. A fresh session starts instead when: the session is gone, the lane's model (its `[models]`
  role) is not the one the session runs, the session's context use (the step row's `context` over its `window`) is over
  `[queue].session_max_context` (default 0.70), or `[queue].session_max_steps` (default 5) steps have landed in it. `step` ends the
  session at every landing. A bad value is refused by `queue add` and `queue run`, and ignored with a `queue-cfg-refused` row by a running
  loop. One `session-kept` or `session-fresh` row per landing with a next step names the reason; each step carries `session` = `kept` or
  `fresh` for how it was started. Acceptance: `fichero-builder/tests/test_queue_batch.py::test_the_next_brief_goes_into_the_same_session_and_one_row_says_why`,
  `::test_a_fresh_session_starts_when_the_reason_holds`, `::test_a_gone_session_is_a_fresh_one_with_its_own_row`,
  `::test_batch_max_and_session_come_from_the_queue_table`.
- `local.queue.session.console-shows-parts-and-session` [GAP] (#6589) — the console's lane rows list each step with its issues, "<n> parts" when it
  has more than one, and "session kept" or "session fresh". Acceptance:
  `fichero-builder/tests/test_queue_batch.py::test_the_lanes_steps_on_the_console_carry_their_parts_and_session`.
- `builder.client.installs-as-a-package` [GAP] (#6589) — `fichero-builder/pyproject.toml` makes the builder installable with no dependencies: package
  `fichero_builder`, `console.html` as package data, and the console script `builder = fichero_builder.__main__:main`. The install is editable
  (`pip install -e fichero-builder`), because `pi/`, `agents/` and `prompts/` are read relative to the folder. Running from the folder with
  `PYTHONPATH=. python -m fichero_builder` is unchanged. Acceptance: `fichero-builder/tests/test_install.py` (the entry function and package data
  exist, `--help` runs from the folder, and, marked `slow`, `pip install -e` in a scratch venv gives `python -m fichero_builder --help` and `builder --help`).
- `builder.client.config-hooks` [OK] (#6589) — a second client sets eight things in its own `harness.toml`, and a file that sets none changes nothing: `[land].repo` (the gh slug, default `dtubb/fichero`), `[land].release_branch` (default `main`; empty = no unreleased count, tag or release PR), `[policy].product` (the end of the `Written-By` trailer, default `Fichero Builder`), `[harness].scripts_dir` (default the checkout's `scripts`), `[check].rungs` and `[[check.rung]]` (pick, order and add ladder rungs; default every built-in rung), `[harness].name` and `label_prefix` (state variable and directory, launchd labels; default `fichero`, `local.builder`), `[harness].package_dir` (the builder package inside a pinned copy) and `[check].python` for `builder machines sync`. A pinned copy whose rules lack `[check].engine_repo` or `[land].pinned_dir` is refused with a message naming them. Test: `fichero-builder/tests/test_client_hooks.py` (a default test and a set-value test per hook).
- `builder.client.scripts-live-with-the-package` [OK] (#6589) — the harness scripts (`harness_*.py`, `harness_setup.sh`, `lane_ready_check.sh`) live in
  `fichero-builder/fichero_builder/scripts/` and ship as package data. `scripts/<same name>` stays as a thin wrapper that execs the package copy with the same
  argv, stdin and exit code, so every path in `harness.toml`, hooks and docs works. `[harness].scripts_dir` still wins; with none set the default is the checkout's
  `scripts/` when it holds the wrappers, else the package's own `scripts/`, so an install outside a Fichero checkout finds its scripts. The guard scripts
  `check_*.py` and `perf_trial.py` stay in `scripts/`. Acceptance: `fichero-builder/tests/test_client_scripts.py` (each wrapper and its target give the same
  result; the package finds its scripts when copied to a tmp dir with no `scripts/` beside it).
- `builder.client.jail-optional` [OK] (#6589) — `[jail].enabled = false` is the one explicit way to run with no wall: workers, the ladder and
  tests run as the invoking user (a pass-through stands in for `sudo`, the probe proves nothing and is skipped), `[jail].workroot` is still
  needed, and every run (a check, a test run, a worker start) writes one `unjailed` journal row naming the user. An ABSENT `[jail]` still
  refuses everywhere, and Fichero's own file keeps its jail. With no probe, an `engine_repo` inside a home folder is allowed. Built:
  `fichero-builder/tests/test_client_unjailed.py` (the jail section).
- `builder.client.empty-rungs` [OK] (#6589) — `[check].ready`, `contract_guards`, `check_paths`, `contract_paths` and `pytest_config` may be
  declared EMPTY (`ready = []`); left out they still refuse. An empty `ready` or contract key makes that rung a NOT RUN row naming the key,
  an empty `check_paths` adds one `pinned-paths` NOT RUN row to every ladder (nothing is pinned), and an empty `pytest_config` runs
  pytest with its own config search (pinned names still stop a batch changing it). Never a green, never a crash. Built:
  `fichero-builder/tests/test_client_unjailed.py` (the empty-keys section).
- `builder.client.land-boundary-default` [OK] (#6589) — the land boundary's patterns come only from `[land].boundary`; left out, they are
  today's four (an owner's home path, an Anthropic key, a GitHub token, a private key block: `land_tool.DEFAULT_BOUNDARY`, tested equal to
  Fichero's file); declared empty is refused, so the boundary is never off. Built: `fichero-builder/tests/test_client_unjailed.py`.
- `builder.client.scripts-from-the-root` [OK] (#6589) — every script lookup takes the configured root, so `[harness].scripts_dir` resolves
  against the client's root: the start hooks, `harness_start.py`, the review script and the build-order guard (`milestone.guard_for`, the
  package's copy when the client's folder has none). Built: `fichero-builder/tests/test_client_unjailed.py` (the scripts section).
- `builder.client.brief-template` [OK] (#6589) — `[brief].template` names a file (relative to the root) whose text, with `{numbers}`,
  `{branch}` and `{base}` filled, replaces the code-shaped part of a cluster brief's preamble ("Fixes #N", "Test first, see it fail",
  "Already built"); the first line with the branch and base stays. None set = today's words. A named file that is missing refuses.
  Built: `fichero-builder/tests/test_client_unjailed.py` (the brief section).
- `local.approve.keyed-by-content` [OK] (#6589; one step looped 13 times) — an approve is never asked again only because the head moved.
  A red-on-base approve binds each test file the red rung names (the alert's one line often names none: the ladder file's red rung
  text is read too) by its blob at base and head, so a rebase that leaves the file alone carries it. A pinned-checks approve also
  binds each file of its diff by that file's own patch-id: a later refusal whose named files have the same per-file diff is approved
  by itself, whatever other files (the batch's tests, the base) changed. Tests: `fichero-builder/tests/test_loop.py::test_a_red_on_base_approve_binds_the_test_the_ladder_file_names_when_the_alert_line_names_none`,
  `::test_a_pinned_approve_holds_when_only_files_the_refusal_does_not_name_changed`, `::test_refused_files_reads_every_named_path`.
  Fixed 2026-11-25 (step nightly-green-1 of a worker lane, approved as alert -1863 and asked again as -1869 at the same head f8dd07262): a
  worker lane's step has no head until a chain is green, so the binding is read at the tree's HEAD; the approved file set is read
  from the ladder's red rows before the alert's cut-off line, at full paths (a name that is the tail of a longer one found is
  dropped); a path in neither tree binds nothing. Tests: `::test_a_worker_lanes_red_on_base_approve_holds_at_the_same_head_from_the_ladders_file_names`,
  `::test_named_files_drop_a_cut_off_copy_of_a_longer_name`.
- `local.check.stale-base-guards` [OK] (#6589) — when every red guard is a shrink-only allowlist's "no longer occurs" and the lane's
  base is older than the pinned copy's commit (integration now), the guards run again over head merged with that commit (a throwaway
  merge commit, never a branch); green there is green with the reason said and one `stale-base-guards` row. A lane already on the
  tip, a conflict, or any other kind of red keeps its red. Tests: `fichero-builder/tests/test_stale_base_guards.py`.
- `local.pin.prune-keeps-live-pins` [OK] (#6589) — a landing's re-pin never removes a `pinned-<sha>` copy that a step not landed or
  parked names (the copy its session started from, recorded as the step's `pinned`, or its brief's `(base <sha>)`), nor the newest
  three by commit date. Tests: `fichero-builder/tests/test_landed_verb.py::test_a_pin_prune_keeps_the_newest_three_and_every_pin_a_live_or_queued_step_names`
  (and `::test_a_second_landing_replaces_the_previous_pinned_branch_and_worktree`, now keeping the previous pin).
- `local.nightly.detached` [OK] (#6589) — the loop starts the night as its own process (`builder nightly-run`, a new session, a
  `nightly.pid` lock under the state dir): a loop re-exec neither waits for it nor ends it, a second start while it runs is a row,
  a restarted loop adopts it by pid (one `adopted` row), and a dead one whose night has no result is one alert. `[nightly]` is a
  known table. Tests: `fichero-builder/tests/test_nightly.py` (the detached section).
- `local.watchdog.slow-work` [OK] (#6589) — every tick the loop looks for work taking too long, in the lanes it is running only:
  in `[loop].only`, not paused, the cursor step sent, done, checking, reviewing or fixing (a parked, held, queued or blocked step
  is never judged). Three causes: a running step past twice its lane's median land time (`nightly.median_land_s`, from its LATEST
  `sent` row, so a retry or restart starts the clock again), a working session whose tmux window has shown no output for 20
  minutes, and a rung of the lane's CURRENT check (its key ends in the cursor step's head) that started after this loop did and
  has run past its timeout: the rung's own whole-rung figure (`build_timeout_s`, `[check.security].timeout_s`), one hour when it
  has none (`guard_timeout_s` is per guard, perf's figure is not passed to its run), and never under one hour, since a rung's
  wall time includes its wait for a lock. A rung-start from a check that died with an earlier loop never ends and is never a
  timeout. The first strike raises ONE alert with the evidence and the action taken (the session is nudged with a line asking
  for WAITING or DONE; a hung rung is only named). A nudge that reaches no session is the `local.run.sent-needs-a-live-session`
  case: the alert says there is no live session and the cause never escalates. Otherwise the same cause one period later is the
  second strike: the session is stopped (a hung rung's ladder cancelled) and the alert answered with retry, once, with one
  `watchdog` row naming the alert; after that the cause is the person's. A cause that ends is forgotten. An error in the
  watchdog is a `watchdog-error` row, never a stopped tick. Fixed 2026-11-25 after its first live tick raised 22 false alerts
  (paused and parked lanes, rung-starts of checks dead for days). Tests: `fichero-builder/tests/test_watchdog.py`, the real
  cases in `::test_the_dead_rows_of_2026_11_25_and_lanes_the_loop_does_not_run_raise_nothing_and_one_live_slow_step_does`.
- `local.nightly.notarize-own-timeout` [OK] (#6589) — `[nightly].notarize_timeout_min` (default 90) is each notarization's own
  budget: `scripts/notarize.sh` submits and polls (never `--wait`) that many minutes, and the DMG part's timeout is the build's two
  hours plus two such budgets (the bundle inside, then the disk image). Tests: `fichero-builder/tests/test_nightly.py::test_notarization_has_its_own_budget_and_polls_never_waits`.
- `local.queue.add-refuses-a-repeated-brief` [OK] (#6589; built 2026-11-25, `queue.repeated_brief` and `queue.continuation`: a continuation lists each step the lane landed since the continued one was first sent, its landed head commit with subject and files; test `fichero-builder/tests/test_queue_verb.py::test_add_refuses_a_repeated_brief_by_name_and_a_continuation_appends_the_landed_and_the_left`) — two steps of one lane never share one brief. `queue add`
  compares the brief's content with the kept brief of every step the lane has, landed or not, and refuses a repeat,
  naming the step that has it. With `--continues <step>` it takes the repeat and appends to the kept copy what a
  continuation needs: the commits the lane has landed since that step began (sha and subject), the files they
  changed, and what is left (the text of `--left`, required with `--continues`). Today the `add` action of `queue.main`
  copies the file to the manager's briefs folder under the lane and step and compares nothing; on 2026-11-21 five
  continuation steps of one lane were queued on one file, and the worker, shown nothing new, said DONE with no commit.
  Test (owed): `test_queue_verb.py`, a second step on the same text is refused with the first step's name; with
  `--continues` and `--left` the kept brief ends with the landed commits and the left text; `--continues` with no
  `--left` is refused. Serves: builds Fichero, reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.queue.drop-takes-a-queued-step` [OK] (#6589; built 2026-11-25: a queued step with a round, a head, a restart, a resume brief or a pinned copy has started and is refused; test `fichero-builder/tests/test_queue_verb.py::test_a_queued_step_that_never_started_is_dropped_with_its_reason_and_a_sent_one_is_refused`) — `builder queue drop --lane L --step S --text WHY` removes a step
  that has not started: `queued` with no round, no head and no session, at the cursor or behind it. It writes the same
  `dropped` row as for a parked step. A step in flight, blocked or landed is refused as before. Today `queue.reorder`
  takes `drop` for a `parked` step only, so a step queued by mistake has to be parked first. Test (owed):
  `test_queue_verb.py`, a queued step that never started is dropped with its reason in the row; a `sent` one is
  refused. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.check.guard-timeout-is-not-red` [OK] (#6589; built 2026-11-25) — a guards rung whose every failed guard timed out (its
  own re-run included) judged nothing, so it is never a fix round: the chain runs the ladder once more, and a second such red is a
  `timed-out` question for the manager (retry when the machine is quieter), never a red with a `Fix:` line. A timed-out guard
  also gets no `Fix:` line beside a real red. On 2026-11-25 at 12:27 builder-fixes reliab-1's check_openapi_route_set_current
  printed every contract [ok], timed out twice at load 66, and the worker was told to regenerate the contracts; it could not, and
  said WAITING. Tests: `fichero-builder/tests/test_work_verb.py::test_a_guards_red_that_is_only_timeouts_runs_the_ladder_once_more_and_is_never_a_fix_round`,
  `::test_a_timeout_that_passes_the_second_time_goes_on_green`, `::test_a_timeout_beside_a_real_red_is_the_real_red_with_no_fix_for_the_timed_out_guard`.
- `local.run.worker-knows-its-test-python` [OK] (#6589; built 2026-11-25) — every fix round and send-back names the interpreter
  that has pytest, `[check].python` (`Run tests with <python> -m pytest <files> -q`); with no `[check].python` nothing is said.
  On 2026-11-25 at 13:55 builder-fixes reliab-1 said WAITING because no interpreter in its worktree had pytest. Test:
  `fichero-builder/tests/test_loop.py::test_a_fix_round_and_a_send_back_name_the_interpreter_that_has_pytest`.
- `local.run.sessions-survive-watchers` [OK] (#6589; built 2026-11-25) — a worker session outlives its `builder run` watcher (a
  loop restart, or a watcher that exits on its own: on 2026-11-25 run-seg-tools.log ended at 11:24 with `seg-tools: gone` while the
  session lived, with no restart), and the loop watches it again instead of alerting. A live window named for the lane whose step
  is sent gets a new `builder run --attach <pane>` on the lane's existing feed and seq, with the head the step was sent at as its
  base; it starts no session and reads a `DONE <sha>` already on screen at its first idle tick (2026-11-25 13:46: seg-tools and
  builder-fixes sat at the prompt after `DONE eab0a2072e` and `DONE 23462609bb`, unread). A step past sent (done, checking,
  reviewing, fixing, red) whose session has no watcher gets one with `--idle`, so its fix round is typed into the session. A
  watcher that exits while its window lives is re-attached in the same tick, with no restart counted and no second session
  started. A kept session with no step in flight and no watcher is closed and the step starts afresh. The "this loop cannot watch
  it" alert stays only for a session that cannot be attached (another step's, a tree that moved, or an attach that fails).
  `builder queue said-done --lane L --step S --sha SHA` records a managed lane's missed DONE by hand: the cursor step, sent, whose
  tree's HEAD is that sha, goes to done (`builder done` stays the external lanes' verb). Tests:
  `fichero-builder/tests/test_builder_restart.py::test_a_restarted_loop_attaches_a_new_watcher_to_a_live_window_instead_of_alerting`,
  `::test_a_watcher_that_exits_while_its_session_lives_is_re_attached_with_no_restart`,
  `::test_a_kept_session_with_no_step_out_and_no_watcher_is_closed_and_the_step_sent_afresh`,
  `::test_said_done_records_a_managed_lanes_missed_done_at_its_trees_head_only`,
  `fichero-builder/tests/test_dry_run.py::test_an_attached_watcher_starts_nothing_and_reads_a_done_already_on_screen`,
  `::test_an_attached_watcher_with_no_step_out_waits_for_the_next_message`.
- `local.run.rebase-conflict-fix-round` [OK] (#6589; built 2026-11-25) — when the loop's rebase of a lane onto origin's land
  branch stops on a conflict it cannot resolve itself (anything beyond the generated identity), it aborts the rebase as before
  and hands the conflict to the lane's worker instead of blocking: one fix round whose text names the conflicting files, the
  commit it stopped applying, every commit on origin since the branch's base that touched those files (sha and subject), and
  the instruction to rebase itself keeping both sides, then end on the DONE line. A live session gets it as its next message; a
  lane with none starts a session on the step's brief plus the round. A conflict found before a step is sent into a kept session
  goes with that step's brief (`conflict-told` row). Only when the worker's round also ends in a conflict is it an alert; a
  rebase that goes through resets the count, so a later conflict has its own round. On 2026-11-25 four steps blocked on
  "conflict left to a person" (seg-tools hands-5161, seg-finish seg-4, builder-batch ci-actions-1 twice). Tests:
  `fichero-builder/tests/test_work_verb.py::test_a_rebase_conflict_names_the_files_and_the_commits_that_touched_them_for_the_worker`,
  `fichero-builder/tests/test_loop.py::test_a_rebase_conflict_is_one_fix_round_for_the_lanes_worker_then_an_alert`,
  `::test_a_conflict_with_no_live_session_starts_one_for_the_round`,
  `::test_a_conflict_the_round_resolved_resets_so_a_later_one_gets_its_own_round`,
  `::test_a_conflict_when_the_next_step_is_sent_goes_to_the_live_session_not_a_block`.
- `local.run.recorded-move-is-not-a-stray-write` [OK] (#6589; built 2026-11-25: `queue.tree_check` excuses a landing, a `tree-moved` row at the state the tree has now, and a clean jail root whose head is origin's land tip with the old head its ancestor; the verb is `builder queue moved --worktree P --text WHY`; `queue.stray_alert` keeps one alert per move and a `stray-write-seen` row for each other step; tests `fichero-builder/tests/test_loop.py::test_a_jail_root_fast_forwarded_to_origins_tip_and_clean_raises_nothing`, `::test_a_dirty_or_off_origin_jail_root_still_alerts`, `::test_a_tree_moved_row_excuses_its_tree_at_the_state_it_recorded`, `::test_a_move_that_still_alerts_is_one_alert_for_every_step_that_saw_it`) — the check that no tree outside a step's own moved
  excuses a move the loop or the manager made and recorded. A tree is excused when a `landed` row for the jail root, or
  a `tree-moved` row naming the tree, the old head and the new head, was written since the step's snapshot; and the
  jail root is excused without a row when it is clean and its new head is the land branch's tip on origin with the old
  head an ancestor, which is what a refresh does and a stray write does not. The manager's hand refresh of the jail
  root after a pushed rules change goes through a verb that writes the `tree-moved` row. A move that is still an alert
  is one alert for the move, naming every step that saw it, not one a step. Today `queue.tree_check` excuses the jail
  root only for a `landed` row of step `jail-root`; on 2026-11-21 one hand refresh, clean on both sides, raised seven
  alerts, one for each live step. Test (owed): `test_loop.py`, a jail root fast-forwarded to origin's tip raises
  nothing; a `tree-moved` row excuses its tree; a dirty or off-origin jail root is one alert for three steps.
  Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.autofix.loop-applies-the-printed-fix` [GAP] (#6589) — where a check prints the exact fix, the loop applies it
  to a managed lane, commits and checks again; no worker is asked. The classes are opted in by name in
  `[check].autofix` (an unknown name refuses the rules file). The fix runs in the lane's worktree as the worker, the
  commit carries the lane's trailers and may touch only the files its class names (anything else is undone and the
  red goes to the worker), and each is one `autofix` journal row: class, rung, head before and after, files. A class
  is tried once for a head; the same red again goes to the worker as today. An external lane is never committed to:
  its red names the fix. Every other red still goes to the worker. Built: the `Fix:` line for three of these reds
  (`autofix.fix_hints` in `fichero-builder/fichero_builder/autofix.py`) and the regeneration after a rebase
  (`dev-workflows.run.rebase-rebakes-generated`). Left: nothing applies a `Fix:` line; on 2026-11-21 52 fix briefs
  went to workers (guards 14, build 10, ready 10, red-on-base 7, not READY 7, diff bound 4). Test (owed):
  `test_autofix.py`, a red with a fix of a named class is one commit, one `autofix` row and a second check with no
  message to the worker; a class not named, a second red at the fixed head, and an external lane each go the old
  way. Serves: builds Fichero, reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.autofix.classes` [GAP] (#6589) — the four first classes, each decided by the check's own output and nothing
  else. `known-gaps-now-clean`: `scripts/check_endpoint_coverage_matrix.py` says entries of its known-gaps list are now
  clean; the loop removes exactly those entries. `ratchet-baseline-lower`: a ratchet prints a count below its baseline;
  the loop writes the lower number and never a higher one. `openapi-regen`: a contract guard says a generated copy is
  stale; the loop runs the `[check].regen` lines and commits the tracked files they changed. `spec-change-trailer`:
  `scripts/check_spec_acceptance.py` asks for a `Spec-change:` trailer; the loop adds one only when the step's brief
  carries a `Spec-change:` line, copied word for word, because the trailer must name a ruling and a script cannot make
  one up; with none in the brief the red is a question for the manager, not a fix brief. Test (owed):
  `test_autofix.py`, one fixture red for each class gives the expected one-file commit; a baseline that would rise, an
  entry the check did not name, and an acceptance red with no line in the brief change nothing. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.models.effort-per-role` [GAP] (#6589) — a `[models]` role row may carry `effort = "low" | "medium" | "high"`,
  and the worker, reviewer or spec writer started on that role runs at that level: low for lint and mechanical
  batches, medium for workers, high for reviewers and spec writers. The adapter passes it in the form its harness
  takes. For Claude Code that is `"effortLevel"` in the settings.json the builder writes for the worker (the same level
  as the `--effort` flag and the `CLAUDE_CODE_EFFORT_LEVEL` variable, which win over it; the builder sets neither, so
  the row decides). Claude Code takes `low`, `medium`, `high` and `xhigh` there; an adapter that cannot take a level says so, and a row asking it for one refuses the start as a question.
  Any other value refuses the rules file. A row with no `effort` starts the command it starts today, byte for byte,
  and the run's `worker` row records the level. Today `models.Model` holds provider, model and context, and
  `start_tool` builds the Claude Code command with `--model` alone. Test (owed): `test_model_config.py` and
  `test_adapters.py`, a row with `effort = "low"` puts the level in the start command; no row leaves the command
  unchanged; `effort = "max"` refuses. Serves: builds Fichero (the same work for fewer tokens).
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)


### K. Small models: cheaper and faster, and as reliable (owner 2026-11-21)

The owner asked what else would let Qwen3-Coder and other small models carry more of the work (paraphrased). The
records of 2026-11-14 to 2026-11-21 were read for it. What they say: 182 Sonnet sessions cost a median 1.60 USD
metered and 124 Opus sessions a median 11.07; no session in the week ran on a small model, so nothing yet measures
one; the model is set for a lane, whatever its steps are; of 903 commits landed in the week, 261 changed only docs or
specs, 107 only tests and 25 only data or generated files (44% together); 50 of 306 sessions ended with no commit; a
session read a median 1.5 million tokens (cache reads counted) over 33 turns before its first commit; and on 2026-11-21
52 fix rounds went to workers, 14 of them for a `ready` or diff-bound red a local command reports in seconds. Only what
those numbers support is below. Already specified, and not repeated: escalation (§ C), the per-model comparison
(`dev-workflows.ledger.comparison-view`), the short brief and the diff bound for each role (`agent-profiles.worker.small`),
a review that reads only new commits (`dev-workflows.tool.check`), and a verdict kept for an unchanged range (the
performance review of 2026-11-21). The rebase already runs before the check. Spec-change: manager 2026-11-21.

- `local.small.step-kind-is-recorded` [GAP] (#6116) — every step has a kind, decided by rule from the files and tests its
  brief names and never by a model: `docs` (only docs and specs), `tests` (only test files), `lint` (a lint or warnings
  batch), `mechanical` (only data and generated files, or a rename), `feature` (anything else), and `design` (a spec to
  write, or anything `local.must-escalate` names). The kind is on the step's record, its `queue` rows and the `cost`
  row of every session that worked on it, so the comparison can be read for each kind. A brief that names no files is
  `feature`. Today `queue.add` in `fichero-builder/fichero_builder/queue.py` keeps the step, brief, issues and waits,
  and the `cost` row in `fichero-builder/fichero_builder/run.py` carries the task and the model. Test (owed):
  `test_queue_verb.py`, a brief naming two test files is `tests`; one naming a spec and a source file is `feature`; the
  kind is on the cost row. Serves: local, builds Fichero.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.small.kind-has-its-lane-and-role` [GAP] (#6116) — a kind can be given to a cheaper role, by measurement. A
  `[models.kinds]` row names a role for a kind; `builder milestone` and `builder steps` then place steps of that kind on
  the kind's own lane, whose worker runs on that role. The worker stays one long-running session for its lane (§ A):
  the lane changes, never the model inside a lane. A row is a trial until it has passed: a trial takes at most one step
  in five of its kind, and it passes when the comparison shows at least 20 landed steps of that kind on that role with
  no more fix rounds a landed step, and no lower share of first checks green, than the lane's own role (`builder ledger
  --compare --kind K` writes one `kind-passed` or `kind-failed` row; a failed kind goes back to the lane's role). A step
  on a kind lane that meets an escalation trigger (`local.escalation-triggers`) goes back to its milestone's lane with
  the failed diff and the findings. No row means today's behaviour. Today the role is the lane's
  (`lane["role"]` in `queue.add`) and is chosen by hand with `--role`. Test (owed): `test_queue_verb.py` and
  `test_milestone_verb.py`, a `tests` step goes to the kind lane on its role; a trial takes one in five; a kind with no
  `kind-passed` row is never past trial; a step red twice at one rung returns. Serves: local, builds Fichero.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.small.worker-prechecks-before-done` [GAP] (#6116) — a managed worker ends a step with one command, not a line it
  composes. The brief's DONE instruction names it. Run in the worker's own tree, inside the jail, with no network, it
  checks in under a minute: the trailer on each new commit, the pinned ready lint, the role's diff bound, the linter
  over the changed files, and the tests the brief names. Green, it prints `DONE <sha>` for the worker to end its turn
  on. Red, it prints the findings in the form of `local.small.fix-brief-has-one-form` and no DONE line. The ladder
  still judges everything afterwards; this only stops a red a script could have told the worker. Today
  `builder precheck` runs on the owner's side, as the caller (`dev-workflows.run.presubmit-lints`, item 8), and a
  managed worker has only the brief's sentence about the DONE line. Test (owed): `test_presubmit.py`, a tree with a bad
  trailer prints the finding and no DONE line; a clean tree prints the line with its head; the command opens no
  socket. Serves: reliable, local.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.small.fix-brief-has-one-form` [GAP] (#6116) — every finding sent to a worker has the same fields in the same
  order: `RUNG`, `HEAD`, `FILE:LINE`, `SAID` (at most 20 lines of the check's own output), `FIX` (the exact command,
  when the check printed one), `RERUN` (the command that shows it green) and `END` (the command of
  `local.small.worker-prechecks-before-done`). One block for each finding, nothing before the first block, 60 lines at
  most, the rest in a file the last line names. A reviewer's NOT READY is cut into the same blocks, one for each
  finding. Today the fix briefs the loop writes in `queue.py` (the step's `resume_brief`) are the check's tail and a
  sentence, different for each kind of red. Test (owed): `test_loop.py`, a guards red, a build red and a NOT READY each
  become blocks with every field in order; a 200-line output is cut to the cap and names its file. Serves: reliable.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.small.brief-carries-the-symbols` [PARTIAL] (#6116) — a step brief gives a small model its place in the code, so
  it does not search for it. For each file the brief names, the brief lists the symbols the step's spec bullets cite
  and the tests named, each with its first and last line from the code map, 40 lines at most; a brief queued by hand
  with `queue add` gets the same list as one `builder milestone` wrote. The measure is the `reading` row: the median
  tokens before a first commit, for each model, is in the nightly report, and the target is half of the week's 1.5
  million. Built: a milestone brief's where list gives each file found by the step's words with the first twelve
  symbols of its outline and a line each (`milestone.write_briefs` and `codemap.outlines`; test
  `fichero-builder/tests/test_milestone_verb.py::test_the_where_list_is_the_spec_the_designs_directory_and_the_files_found_by_the_steps_words_with_their_outlines`).
  Left: the symbols the spec bullets cite come first, the spans, the list on a hand-queued brief, and the measure in
  the report; an owed test in `test_codemap.py` (a step citing two functions lists both with spans; the list never
  passes the cap). Serves: local.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.spend.metered-provider-needs-a-cap` [OK] (#6116) — no session starts on a provider that bills by use unless
  that provider has a cap. `[spend].metered` lists such providers (OpenRouter is the first) and `[spend.week_usd]`
  gives each a weekly figure in USD; a listed provider with no figure refuses the rules file, and a role on it
  refuses to start. Every `cost` row names its provider; the watcher adds the week's rows for the provider and parks a
  session that would pass the cap, with one alert. A subscription login is not metered and keeps the session and day
  caps it has. Built (2026-11-25): `watcher.Spend` reads `metered` and `week_usd`; `openrouter` counts as metered even when
  the file does not list it, so it never starts without a figure; the week is the ISO week (Monday to Sunday) of the
  journal's timestamps; `builder run` takes the provider from the lane's `[models]` role (else `claude-code`, or `--provider`
  for `--kind pi`), refuses a metered one with no figure, parks before the start when the week's rows already reach it, and
  parks a live session (one `watch` row) when the week's rows plus its own cost reach it; `models.for_role(cfg, role, spend)`
  is a Question for such a role. The Qwen3-Coder-Next trial through Pi on OpenRouter is configured like this (an example, not
  the live file):
  `[models]` `providers = [..., "openrouter"]`, `qwen-trial = { provider = "openrouter", model = "qwen/qwen3-coder-next", context = 262144 }`;
  `[spend]` `metered = ["openrouter"]`, `prices = { ..., "qwen/qwen3-coder-next" = [<in>, <out>] }`; `[spend.week_usd]` `openrouter = 25`.
  Tests: `fichero-builder/tests/test_watcher.py` (a metered provider with no figure refuses; the week's rows reach the
  figure and the session parks; a subscription session is not counted), `fichero-builder/tests/test_model_config.py::test_a_role_on_a_metered_provider_with_no_weekly_figure_is_a_question`,
  `fichero-builder/tests/test_dry_run.py::test_a_metered_role_parks_before_the_start_when_the_weeks_rows_reach_its_cap`.
  Serves: reliable (no spend without a cap), local.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### L. A review is a step kind (owner 2026-11-21, #6847)

On 2026-11-20 and 21 the manager ran area reviews by hand: one session read an area's code and specs, measured it, wrote
a report and spec changes on a branch, and the manager then filed the issues, mapped the `#NEW-n` tags, added the
milestone to `build-order.md`, gave the spec a Build order and queued its steps. The audit of 2026-11-21 found what a
hand does badly: a tag with no number mapped by order, ranked fixes with no issue (four reports: #6863 to #6866), owner
questions left in the report, and "existing issues that gained evidence" never commented. `builder review` does the
steps a program can do and leaves the judgement (the review, the owner's answers) where it was. The review rules a
session reads are `fichero-builder/prompts/review-common.md`. A report has these headings (a number before the title
is allowed, the case is not checked): **What exists**, **Measured**, **Ranked fixes** (a numbered list; each item cites
the issue it belongs to as `NEW-n` or `#N`, and its spec step as `[1.2]` when the spec's Build order has it),
**Issues to file** (a list: `NEW-n title (behaviour ids)`), **Open questions** (a numbered list, or the word "none"),
and optionally **Existing issues that gained evidence** (a list: `#N text`). Spec-change: owner 2026-11-21 a review incorporates itself.

- `local.review.start-queues-a-session` [OK] (#6847) — `builder review start <area> --repo-dir R --written-by TEXT
  [--base REF] [--scope TEXT]` makes the review worktree `<[jail].workroot>/wt-review-<area>` on branch `review-<area>` from the base
  (default `origin/<[land].branch>`), writes the brief (the review rules, the area, the report path
  `review-<area>.md` in the worktree, kept out of the commits by `.git/info/exclude`) and queues it as the one step
  `review` of lane `review-<area>`, so the loop runs it like any step. An area that is not a word of letters, digits and
  dashes, whose worktree or branch exists, or with no `--written-by`, is refused. Test: `fichero-builder/tests/test_review_verb.py`, on a scratch repo: the
  worktree, the branch, the exclude line, the queued step and the brief text; a second start is refused.
  Serves: local, builds Fichero.
- `local.review.report-is-checked` [OK] (#6847) — `builder review check <area>` reads the report and refuses one that
  lacks a heading above, whose Issues list is empty, whose `NEW-n` run has a gap or a repeat, or in which a ranked fix
  cites neither a listed `NEW-n` nor a `#N`. It names each fault with its heading or fix number and exits 1. Test:
  `fichero-builder/tests/test_review_verb.py`, one report per fault, and one whole report passes. Serves: reliable.
- `local.review.approve-files-and-maps` [OK] (#6847) — `builder review approve <area> --milestone M --spec FILE
  --written-by TEXT`
  runs the check first, then files one issue per `NEW-n` in milestone M through `gh` (title `[M] title`, the behaviour
  ids and the report's text in the body) and writes the map `NEW-n -> #N` to `<state>/review-<area>-issues.json` after
  each issue, so a second run files only what the map lacks. It rewrites the spec's tags: `#NEW-n` and `#NEW-Sn` become
  the filed number; a bare `#NEW` is mapped by the behaviour id of the bullet it is on, through the issue's behaviour
  ids, never by its place in the file; a bare tag on a bullet whose id no issue names, or two issues name, refuses the
  whole approve before anything is filed. Test: `fichero-builder/tests/test_review_verb.py`, on a fake `gh` that numbers from 7000: the
  map, the idempotent second run, `NEW-S2`, a bare tag mapped by id, and an unmapped bare tag refused with nothing
  filed. Serves: reliable.
- `local.review.every-fix-has-an-issue` [OK] (#6847) — the spec's Build order keeps the steps the review wrote; each
  step heading that a ranked fix cites as `[N.M]` takes `(#N, #M)` of the issues that fix cites. A fix whose step the
  spec lacks, and a step no fix cites, are listed and refuse the approve (a step with no issue is how #6863 to #6866
  were missed). The approve adds the milestone's line to `build-order.md` under `## In order` (after `--after
  <milestone>`, else last) with its `Spec:` path, or sets the `Spec:` path of the line that is there. Test:
  `fichero-builder/tests/test_review_verb.py`: headings take their numbers; a fix pointing at a missing step refuses; the line is added once.
  Serves: reliable.
- `local.review.evidence-and-questions` [OK] (#6847) — each "existing issues that gained evidence" item becomes a
  comment on that issue, once. Each owner question becomes an `alert` row on lane `review-<area>`, step `question-n`,
  answered by `ask-owner` (the question goes as a `needs-your-decision` comment on the first filed issue) or `park`;
  a question already alerted is not alerted twice. Test: `fichero-builder/tests/test_review_verb.py` and `fichero-builder/tests/test_alerts_clear.py`: the
  comments on the fake `gh`, the alert rows, `ask-owner` on a lane-less alert. Serves: reliable.
- `local.review.approve-lands-then-enqueues` [OK] (#6847) — the approve commits the spec and `build-order.md` in the
  review worktree (message from a file; the trailers `Written-By` and `Spec-change`), writes
  `<state>/review-<area>-issue-list.txt` (number, milestone, title of each filed issue) for the landing step to be
  given, and prints the sha: a landing step needs no `gh` in the jail. `builder review approve <area> --enqueue` runs
  after that commit has landed (it is an ancestor of `origin/<[land].branch>`; else refused) and calls `builder
  milestone M --spec FILE --enqueue`. Test: `fichero-builder/tests/test_review_verb.py`: the commit holds only the spec and
  `build-order.md`; `--enqueue` before the land is refused; after it, the lane has a step. Serves: local.
- `local.review.tests-touch-nothing-real` [OK] (#6847) — the review tests run on a scratch repo, a scratch state
  directory and a fake `gh` that records its calls and numbers its issues; no test reads the real git config, the
  real journal or the real issues. Test: `fichero-builder/tests/test_review_verb.py` sets `GIT_CONFIG_GLOBAL` and `HOME` to the scratch
  directory and asserts the fake `gh` is the only issue client called. Serves: reliable.


### From `dev-workflows.md` — Behaviours


#### A. Workers (the loop is the harness's)

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
  row and a question), not left to the model. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_check_tool_runs_the_ladder`. **Rung rows** (manager 2026-11-04, built): every `rung-start` and `rung` activity row of a ladder or a `verify` run carries `load` (the 1-minute load average), and every `rung` row its own `wall_s`, measured around the rung, so the multi-result rungs (guards, build) have a time too and a parallel change can be checked against the machine's load (test `::test_every_rung_row_carries_wall_time_and_load`). **Build** (owner 2026-11-01, built): a diff under `[check].build_paths` runs `[check].build` (a build-only compile, never a test run) in the scratch tree, one build at a time under `[check].build_lock` (a file in the owner's own state dir, taken by the owner's check process; the build itself runs as the worker user with signing off), after the contract rung; red refuses. Proven 2026-11-01: the rung's exact command (Dev Local scheme, signing off, derived data under the shared area) run as the worker user compiled the app; the Dev Embedded scheme fails at its embed-the-engine script phase, so the rung names Dev Local. The check tree is owner-made and read-only to the worker user and `Package.resolved` is tracked, so `[check].build` carries `-disableAutomaticPackageResolution`: resolution reads the file and writes nothing (a first real Swift check failed with exit 74 writing it, 2026-11-01; proven the same day: the rung's argv as the worker user over a read-only copy ended BUILD SUCCEEDED). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_rung_runs_only_for_build_paths_and_reports_red`, `::test_the_build_rung_never_resolves_packages_so_a_read_only_check_tree_builds`. **Check row** (built 2026-11-01): `builder check` appends a `check` row (repo, since, the head's full sha, ok, failed, maintainer) to the owner's journal, and `builder land` refuses a head with no green row there (Step 2.1: check before review and land; the row lives in the owner's journal, never the worker's, so a worker cannot forge one). `builder run` journals under `[jail].workroot/state` by default so the owner reads the worker's rows without sudo. A red rung's tail keeps pytest's failure section whatever follows it (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_red_pytest_tail_keeps_the_failure_when_warnings_follow_it`). A test file owes no red only when every commit touching it is test-only and carries `Already built: #N <path>::<test>` naming a file in that commit; the worker writes the message, so a line on a commit that changes source earns nothing; such a test must pass on base, which is what "already built" claims; a range that changes source (under `[check].red_paths`) with every changed test excused is refused, so another test must go red for that change, though the check cannot tell that this test is the one that proves it; and the excused test still runs in the green run (tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_already_built_exempts_only_a_test_only_commit_that_names_its_test`, `::test_already_built_must_pass_on_base_so_a_source_commit_before_it_cannot_skip_the_red`, `::test_a_source_change_whose_every_test_is_excused_is_refused`, `::test_a_source_change_with_another_test_that_goes_red_may_also_carry_an_excused_one`, `::test_an_already_built_test_that_goes_red_on_head_is_refused_by_the_green_run`). A pytest rung's sys.path entries and its `-c` config are resolved to real paths on the machine that runs it, because a gate dir that is a link (the M4's and the iMac's `~/fichero-gate`) gives pytest a real cwd, while a `-c` named through the link rooted test ids outside their folders and let one folder's autouse conftest fixture run under every test (#6589, 2026-11-15; tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_tree_reached_through_a_symlink_keeps_each_folders_conftest_to_its_folder`, `::test_a_whole_tests_dir_reached_through_a_symlink_still_loads_its_own_conftest`). A pytest rung runs with a throwaway pycache prefix, because `python -I` ignores `PYTHONDONTWRITEBYTECODE` and pytest's rewrite cache keys on mtime seconds and size, so a same-size edit in the same second would run the previous rung's bytecode (test `::test_a_commit_that_says_already_built_owes_no_red_on_base_but_its_test_still_runs_green`). The rules checks accept `[queue]`, `[triage]`, `[jail].code_map` and `[land].pinned_dir` before the code that reads them, because a check in pieces overlays the batch tip's `harness.toml` on each piece; a misspelt name still refuses (test `fichero-builder/tests/test_main.py::test_the_rules_checks_accept_the_settings_later_commits_add_and_still_refuse_a_misspelt_one`). The reviewer reads every commit of the range whole, never truncated. An image under `docs/assets/` (png, jpeg, gif, webp, pdf, ico, icns, heic, tiff) is the one binary a range may carry: it leaves the review text and is named at its end for the manager to look at, since the reviewer cannot read it; a NUL byte in any other file still refuses (2026-11-15, batch-21's screenshots; test `fichero-server/tests/unit/workflows/test_land_tool.py::test_a_docs_asset_image_leaves_the_review_text_and_is_named_and_any_other_binary_still_refuses`). Its cap is 40% of the reviewer model's window (`[models].reviewer` `context` in `harness.toml`, 200000 tokens when absent) at 3.5 bytes a token (`land_tool.review_cap`); a range over it is reviewed in consecutive commit groups that each fit, and the READY verdict for the whole range is written only when every group's last line is READY; a single commit over the cap is refused (`land_tool.review_groups`, `scripts/harness_review.py`; tests `fichero-server/tests/unit/workflows/test_land_tool.py::test_the_review_cap_refuses_one_byte_past_it_and_the_default_takes_a_step_a_big_worker_writes`, `::test_a_range_over_the_cap_splits_into_consecutive_groups_that_each_fit_and_lose_nothing`, `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_range_over_the_cap_is_reviewed_group_by_group_and_ready_only_if_every_group_is`, `::test_one_group_not_ready_writes_no_verdict`, `::test_a_diff_over_the_cap_is_refused_not_truncated`). Every group runs even after one is not READY, so all findings go back at once; each group's prompt says the batch lands whole at its head, names every file the whole batch changes, and makes a finding the head fixes (a red mid-range, a spec line a later commit adds) a note, not a blocker (2026-11-02; test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_group_not_ready_still_lets_every_later_group_run_and_each_prompt_frames_the_whole_batch`). **Delta review** (manager 2026-11-02): each group's range and verdict (a blocking reply's text with it) go into `<verdicts>.groups` under the base; when the last run's head is an ancestor of this head, its READY groups are kept and only last-head..head is reviewed, its prompt naming the kept groups and quoting what blocked before for the reviewer to check at the head; a READY delta writes the one verdict for the whole range, a blocked one carries the earlier findings forward. A rewritten head (folded or rebased commits; the last one no longer its ancestor) groups the whole range afresh and keeps a READY for every group whose **content key** is unchanged: each group's key is a hash of its commits' diff and message hashes in order, never their shas, recorded with the group, so only a changed group is reviewed and the same input is never reviewed twice (owner 2026-11-02: five full rounds re-read READY groups after fixes were folded into earlier commits; `dev-workflows.run.review-group-key`). A READY group is reused only when the commits BEFORE and AFTER it are unchanged too (recorded prefix and suffix keys: with both, a reused READY means the whole range is the one judged): its READY was judged against the head tree, so a dropped or changed later commit sends it back to review. A fix made as a new commit on top leaves every earlier group's key as it was. No record or `--full` reviews the whole range (test `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_a_rerun_after_a_fix_reviews_only_the_new_commits_and_keeps_the_ready_groups`, its last cases: a rewritten head reviews only the changed group, and the same content under a new sha makes no model call). **Remote runner** (manager 2026-11-02, optional): `[check].remote = "host:dir"` sends the engine pytest runs (the changed files, the whole-tests dirs, red-on-base's base runs) over ssh: the check tree's files (`git ls-files -co`, never `.git`) are shipped once per tree into a fresh `dir/run-*`, the same command runs there with `[check].remote_python` (default `dir/venv/bin/python`) and the rung's env, and the copies are removed when the ladder ends. Each ladder thread removes only the trees it shipped and clears the runner-down flag only when no ladder is left, so with `[check].parallel = 2` the first to end never deletes the copy the other is running in (review 2026-11-02; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_one_ladders_end_keeps_the_other_running_ladders_remote_copy`). Guards, ready and build stay here. An unreachable runner (ssh's own exit 255, or the copy failing) is one `alert` row per ladder (step `remote`), and the tests run here: progress never waits on that machine. The remote runs tests unjailed as the ssh user, so it holds nothing but its gate dir (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_remote_runner_runs_the_engine_pytest_there_and_an_unreachable_one_alerts_and_runs_it_here`; not yet: a real run on the iMac). The ready check's cap on commits ahead of origin/integration is `[check].max_commits` of the harness.toml in the tree it checks (the pinned copy's under the ladder, so a worker cannot raise it), default 100: it was a hard-coded 60 in the pinned script, and a reviewed 66-commit batch needed the pinned copy hand-edited (2026-11-03; fixed here, test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_ready_checks_commit_cap_is_max_commits_from_the_trees_harness_toml_default_100`). The ready rung runs `scripts/lane_ready_check.sh --no-guards HEAD`: the guards rung runs every guard from the pinned copy, so the ready check's own copy of them (60 s each) only doubled the time and refused a green batch on a timeout under load (2026-11-02; a bare run still runs them; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_ready_check_skips_its_guard_copy_with_no_guards_because_the_guards_rung_runs_them`). Its lint of the changed files is a ratchet (manager 2026-11-02: a 997-line store cut to 919 was refused for file_length it already broke): per touched file, `fichero-builder/fichero_builder/lint.py` counts ruff's and swiftlint's findings by rule on base (the base copy on stdin, the repo's config) and on head, and refuses only a rule whose count grows, or any finding in a new file (test `fichero-builder/tests/test_lint.py`); a linter that crashes, or prints nothing where it owes JSON, is a refusal (`lint.LintError`), never zero findings, and `fichero-builder/fichero_builder/lint.py` is a pinned path run under `python -I`, so a batch never edits the copy that judges it (test `fichero-builder/tests/test_lint.py::test_a_linter_that_fails_or_prints_nothing_is_a_refusal_never_zero_findings`). `[check].since_guards` maps a guard to a path prefix: a diff under the prefix runs it in the scratch tree with `--since <base>`, its question about this range only; Fichero runs the SwiftLint ratchet so for `fichero/` (#6318; swiftlint is a copy in the worker's bin; test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_since_guard_runs_with_the_range_base_only_when_the_diff_touches_its_prefix`; not yet: a real Swift item through it). An empty range (since equals head) is refused, never judged green: a landing branch that never received its commit passed once (2026-11-02). Test: `fichero-builder/tests/test_main.py`. **Whole tests** (built 2026-11-02): `[check.whole_tests]` maps a path prefix to a tests directory; a diff under the prefix (a deletion too) runs that directory whole, not only the changed test files (a Builder source change broke an old Builder test its own new test never imported). Each listed directory runs as its own pytest from its package (the directory's parent): `-c <package>/pyproject.toml` when it exists (every pytest config name, `pyproject.toml`, `pytest.ini`, `.pytest.ini`, `pytest.toml`, `.pytest.toml`, `tox.ini`, `setup.cfg`, is a pinned name anywhere in the tree, so a worker cannot add one that changes what either run collects), the package first on the path, so its `from tests import x` finds its own `tests` and not the engine's; the engine-shaped run keeps only the changed test files; both must be green, and the row records both commands and tails (`runs`). Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_change_under_a_whole_tests_prefix_runs_that_tests_dir_whole_in_the_green_run`. The engine-shaped green run is one pytest per top-level package (changed test files grouped by their first path part), so two packages' `tests` dirs never shadow each other (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_green_run_is_one_pytest_per_package_so_two_tests_dirs_never_shadow_each_other`). **Maintainer batch** (built 2026-11-02): `builder check --maintainer` records a changed pinned file in the pinned-checks row instead of refusing, so a harness change is judged by the same ladder (pointed at its own rules with `--pinned`); only a changed or deleted pinned check file is recorded; a symlink, a `sitecustomize`/`.pth` file, the agent settings directory, a new file under a pinned path, a weakened test and a rewritten acceptance still refuse. A maintainer batch is not held to the diff bound (`[check].max_files`/`max_lines`): its diff-bound row shows the size and stays green; a jailed worker's range keeps the bound. Test: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_maintainer_batch_records_the_pinned_change_and_runs_the_rest`, `::test_a_maintainer_batch_skips_the_diff_bound_and_a_worker_range_keeps_it`. **Pinned copies judge, they are not the code under test** (manager 2026-11-02): the pytest rungs (red-on-base's head runs, the changed tests, the whole-tests dirs) and `builder test` run on head's own tree, unmodified; the ready, guards, contract, since-guards and build rungs, and the ladder's config, run on the tree with the pinned copy's check files laid over it. A batch that changes a guard and its test, or `harness.toml` and the code that reads it, is tested as it will land and judged by the pinned guards; a changed pinned file still takes pinned-checks (needs-maintainer) and the full reviewer (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_guard_and_its_test_changed_together_are_tested_on_head_and_judged_by_the_pinned_guard`). A pytest rung's safe path is `python -I` (it implies `-P`: the cwd is off `sys.path`, so a worker's `pytest.py` shadows nothing), never a `PYTHONSAFEPATH` env var: `-I` ignores it for pytest, and every child a test starts inherited it, so a guard script a test ran lost its own dir from `sys.path` (2026-11-05: `test_guardrails_scan_floor` red in every safe-path rung, `No module named _check_floor`; tests `fichero-server/tests/unit/workflows/test_pinned_names.py::test_pytest_runs_with_pinned_config_no_autoload_and_safe_path`, `::test_a_guard_script_a_test_starts_still_imports_the_helper_beside_it`). Was (2026-11-16, #6589): the remote run briefly kept the runner's own `TMPDIR` (the M4's Dev Disk) through its `env -i`; reverted the same night, because the Dev Disk's name holds spaces and builder tests build shell lines from unquoted tmp paths (38 red), and the engine's built-in library roots do not include it. `tmp_path` stays on the runner's default temp until those are quoted; test `fichero-builder/tests/test_remote_tmpdir.py::test_the_remote_script_does_not_carry_the_runners_tmpdir`.
  Built 2026-11-06 (lane-sharing batch-27: a NOT RED that did not reproduce, and nothing said where the base had run): a NOT RED ON BASE refusal names the runner, the base tree and pytest's last lines, and one `red-on-base-base` journal row keeps the whole output tail (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_red_on_base_needs_a_test_that_fails_on_base_and_passes_on_head`).
- `dev-workflows.tool.milestone` [PARTIAL] (#6116; owner 2026-11-01) — `builder milestone <name>` reads the milestone's open
  issues (`gh`), places each under the build-order step of the spec that names it (the issue body's step line, or the
  milestone's spec by its `> Milestone:` line), orders steps by `Depends on`, and prints one cluster brief per step
  through the brief tool; an issue under no step, or a step whose dependency is still open, is a **question**, never a
  guess; nothing is picked by hand. Built 2026-11-01: `fichero_builder/milestone.py` and `builder milestone <name>
  --spec FILE --out DIR`: `gh issue list --milestone`, the step from the issue title (`Step 1.3`) or a `Step: 1.3`
  body line, the build order from the spec guard's own parser, one brief per step through the brief tool, questions on
  stderr and exit 2 when any. Still owed: `builder steps` files issues in that title shape. Test:
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
  `fichero-builder/tests/test_landed_verb.py::test_making_the_new_pinned_copy_waits_for_a_running_ladder`, `fichero-builder/tests/test_work_verb.py::test_the_chain_finds_its_pinned_copy_again_inside_the_ladder_lock`). The `rebase` step runs before the lock, so a copy a landing removed is pinned again from the current base when the chain next reads its rules, and a rules file with no `[jail]` names the file it read (2026-11-05, batch-25's `JailMissing`; test `::test_a_pinned_copy_removed_before_the_rebase_is_pinned_again_and_the_error_names_the_file_it_read`). The `land` step and
  `builder land` check `--log` first (a path it cannot append to refuses before anything runs, here and in the hand-run
  ladder; test `fichero-builder/tests/test_main.py::test_land_refuses_a_log_it_cannot_write_before_anything_with_a_row`), and run the verdict and the boundary only once a green check row over exactly `<[land].branch>..<head>` exists (`land_tool.gate`; test `fichero-builder/tests/test_main.py::test_land_refuses_a_green_row_that_does_not_cover_the_range`);
  the ladder is not run a second time (it doubled the pytest load against the one-pytest rule); `scripts/harness_land.py`
  keeps the ladder for a hand run. Tests: `fichero-builder/tests/test_work_verb.py::test_rebase_puts_the_worktree_on_top_of_the_branch_another_lane_moved`,
  `::test_a_rebase_conflict_is_aborted_and_said_never_resolved`,
  `::test_a_github_blip_in_the_rebase_is_retried_once_not_called_a_conflict` (a fetch or rebase that fails with a network error (unable to access, could not resolve host, failed to connect, connection timed out or reset, early EOF) is retried once after 20 s, never reported as a conflict left to a person; #6116, manager 2026-11-08),
  `fichero-builder/tests/test_main.py::test_land_with_a_green_check_row_runs_the_verdict_and_boundary_only_never_the_ladder_again`.
- `dev-workflows.tool.spec` [PARTIAL] (#6116) (owner 2026-11-01) — `builder spec <issue>` starts the **spec-writer** role from
  `[models]` as a worker whose brief is the spec template, the issue and the spec guards' rules; the result is one spec
  file under `spec_dir` on a branch with `> **Status: PROPOSED**`; the guards run on it; the owner approves by editing
  the status line, and nothing in the spec is built before that. **Built** (2026-11-01): `builder spec --issue N --out FILE [--gh gh]` writes the brief (the spec template, the issue through the brief tool, the guards' rules in words, the instruction to write ONE spec with `> **Status: PROPOSED**`) and prints the `[models].spec-writer` model; it does not start the worker, `builder run` does (the spec's first wording said the verb starts it; the verb stays a brief writer so one start path exists). A missing role model is a `QUESTION:` (exit 2). The steps verb refuses a PROPOSED spec. Test: `fichero-builder/tests/test_spec_verb.py::test_the_brief_names_the_template_the_issue_the_guards_and_the_proposed_status`.
- `dev-workflows.tool.file` [PARTIAL] (#6116) (owner 2026-11-03) — `builder file --milestone M --title T --body-file F [--label L ...] [--gh gh] [--dry-run]` creates the milestone if the repo lacks it and files one issue under it, or edits the issue in that milestone with the exact same title instead of filing another; missing labels are created first; every write is a `file` journal row; `--dry-run` writes nothing and prints what it would do and the body; it never pushes; an empty milestone, title or body, or a failing `gh`, is `REFUSED` (exit 1). Test: `fichero-builder/tests/test_file_verb.py::test_a_second_run_edits_the_issue_and_a_dry_run_writes_nothing`.
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
  for the sha, the journal has a green check row over exactly `<[land].branch>..<sha>` (or over `origin/<[land].branch>..<sha>`, which `builder landed` also accepts for its verdict and check row, after resolving a short sha; test `fichero-builder/tests/test_landed_verb.py`) (a `--maintainer` row counts, because a
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
  needs-your-test; a behaviour id on a `Behaviour: <id>` trailer line of a commit (an id the message only mentions does not count) is proposed [OK] with the commit's
  test files (manager 2026-11-04: never written into the loop's checkout, which a landing twice left dirty so refresh_live stopped
  following origin): one `spec-ok-proposed` row each, naming the lane (`--lane`), the landing sha, the file, the id and the tests, which the
  lane folds into its next batch; `builder auto` lists every proposal whose line still has an open tag; a spec
  file it would propose for that has uncommitted changes still refuses before the push;
  `--no-issues` skips both. A `Fixes` or `Closes` line may name several issues. The `done` row's `left_open` names every cited issue with no
  such line, and the verb prints it: a row, not a close. Every step is a journal row (event `landed`); a red step stops the rest with exit 1.
  **Built** 2026-11-01: `fichero_builder/landed.py`. Tests:
  `fichero-builder/tests/test_landed_verb.py::test_the_happy_path_without_push_pins_and_refreshes_but_leaves_origin_alone`,
  `::test_refuses_a_sha_that_is_not_a_fast_forward_of_origin`, `::test_the_cited_issues_are_closed_or_commented_through_gh`,
  `::test_a_range_over_the_boundary_is_not_pushed`, `::test_a_journal_landed_does_not_own_or_others_can_write_refuses_before_anything`,
  `::test_a_green_row_counts_only_for_the_range_being_landed`, `::test_issues_are_untouched_until_the_sha_is_on_origin`, `::test_the_spec_behaviour_line_a_landed_commit_names_is_proposed_ok_never_written`, `::test_a_dirty_spec_file_it_would_edit_refuses_before_the_push_and_nothing_else_does`, `::test_a_fixes_line_naming_several_issues_closes_each_and_the_done_row_names_what_stayed_open`. Not yet: a run with the real jail user and the real `gh`; both are faked in every test.
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
  `fichero-builder/tests/test_milestone_verb.py::test_no_name_takes_the_first_ordered_milestone_with_open_issues_and_its_spec`. **Close with a reason** (manager 2026-11-04: #6025 was closed by hand as not reproducible, there being no harness way): `builder triage --close N --reason TEXT [--as not-planned|completed|duplicate] --owner-approved` is the one close outside a landing: refused without `--owner-approved` or a reason, one `gh issue close` with the reason word for word as its comment (and that it was owner-approved), one `triage` row (`what: close`); `--dry` calls no gh. Tests `fichero-builder/tests/test_triage_close.py::test_close_is_refused_without_owner_approval_or_a_reason_and_calls_no_gh`, `::test_an_approved_close_is_one_gh_call_with_the_reason_as_the_comment_and_one_row`.
  Built 2026-11-05 (#4917 and #5759 belonged in other milestones and the only verbs were a bulk re-milestone and a close): `builder triage --move N --to MILESTONE --reason ...` moves one issue to a milestone that exists, comments the reason word for word, writes one `triage` row and never closes it (test `fichero-builder/tests/test_triage_close.py::test_a_move_is_a_milestone_edit_and_a_comment_with_the_reason_and_one_row_never_a_close`).
  Phase 0 amendment (owner 2026-11-17/18, from the cut `dev-workflows.tool.triage`): a milestone with no open issue that no spec still needs is closed by triage; one a spec still needs stays open.
- `dev-workflows.tool.queue` [PARTIAL] (#6166; owner 2026-11-01) — `builder queue [add|run|pause|resume] [--push] [--once]`: one
  long-running worker per lane (a milestone), fed step by step, so it keeps what it has read and never re-reads the tree.
  `<state>/queue.json` holds the lanes: worktree (stored absolute, test `fichero-builder/tests/test_queue_verb.py::test_a_relative_worktree_is_stored_absolute`), cursor, message number, the steps in build order (`builder milestone
  --enqueue` puts them there; a waiting step is a brief and a queued step, and the plan says all the waits in one line; such a brief names the lane's branch and head, not a fixed base).
  A step goes queued, sent, done, checking, reviewing, landed, or blocked. The worker side is `builder run --feed DIR`, as
  the jail user: a good `DONE <sha>` ends the step, not the session: one `step` row for the owner, then idle until
  `msg-<seq+1>.txt` appears in the folder (the owner's, made exclusively under a name no worker can plant a link at, so a worker cannot write its own next brief; test `fichero-builder/tests/test_queue_verb.py::test_a_planted_inbox_cannot_turn_the_owners_chmod_or_writes_on_another_folder`) and is typed into the
  same pane, or `stop` appears. The owner side is one loop: it sees the `step` row, runs `work.after_run` (rebase, patches,
  fetch, the ladder under the `ladder` lock, review, reused when this exact range already has READY, the land gate; the sha comes from the fetch, never from the worker's
  row), then `builder landed --keep-worktree --lane <lane>` (push only with `--push`; the session is still working there; `--lane` names the lane on the landing's spec-ok-proposed rows), moves the cursor, rebases the worktree and sends the next brief. A
  red check (each red guard named, test `fichero-builder/tests/test_work_verb.py::test_a_red_guard_is_named_in_what_goes_back_to_the_worker`), a NOT READY review or a refused land goes back into the same session as a fix brief with the findings, `[loop].rounds`
  rounds (a gone session gets a new one on the fix brief), then blocked with `<state>/question-<lane>-<step>.txt`; a DONE with no commit, a refused landing or a chain error
  blocks at once. A new session only at the worker's own handoff (`[spend].handoff_tokens`, an absolute token count) or when it is gone (three times on a step blocks); a
  parked worker blocks. After a landing the queue reconciles each of the step's issues (an `issue-reconcile` row, written when it finishes: the reconcile runs on a thread, never on the queue's loop),
  and the lane goes on: the reconcile closes it when it is done (`dev-workflows.run.issues-close-when-done`), else comments what is left; `gh` failing or timing out here counts as unread, never a traceback (test `fichero-builder/tests/test_queue_verb.py::test_a_gh_that_times_out_or_is_missing_counts_as_unread_and_the_lane_goes_on`). Without `--push` a step stops there: `builder landed` refuses a sha origin lacks, so the step blocks until a person pushes. Pause = idle with nothing sent; resume = send the next brief, and clears a block. At most
  `[queue].workers` lanes at a time; every transition is a journal row (event `queue`); the console (`builder status`) shows the steps.
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
  machine. A blocked step is an alert row; only `builder alert <id> ask-owner` labels each of its issues `needs-your-decision` and comments the QUESTION (#6343; a `gh` that fails
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
  first commit, per generation), the cost row repeats them (none when nothing was committed); both stay in the journal (the old `builder watch` page that showed them per run is gone, owner 2026-11-03).
  Tests: `fichero-builder/tests/test_codemap.py::test_provide_copies_the_install_and_the_wrapper_runs_it_past_the_owner_only_shebang`,
  `::test_prepare_registers_only_the_copied_server_and_keeps_the_strict_config`,
  `::test_the_worker_side_command_indexes_the_worktree_first_and_a_failed_index_does_not_stop_it`,
  `fichero-builder/tests/test_dry_run.py::test_a_run_records_what_it_read_before_its_first_commit`.
- `dev-workflows.tool.build` [PARTIAL] (#6344; owner 2026-11-02) — `builder build --dev` is the owner's dev DMG as one command, so nobody
  re-derives the procedure. It runs the project's own `scripts/build-release-dmg.sh` from `--root` and rewrites none of it: the dev
  tier, the current `MARKETING_VERSION` so the script's auto-stamp leaves the tree alone, the running venv first on `PATH` for the
  engine preflight, no notarizing. One journal row (event `build`: tier, sha, dirty, ok, rc, dmg, log, seconds), the log in the
  state directory, and `PASSED <dmg>` or `FAILED` with the log's tail. A green script with no new DMG is a failure. Without `--dev`
  it refuses: a full release needs the owner's yes. The jail user is refused. **Built** 2026-11-02 against a fake script: `fichero_builder/build.py`.
  Not yet: a run of the real script. Tests: `fichero-builder/tests/test_build_verb.py::test_dev_runs_the_projects_script_for_the_dev_tier_without_a_stamp_or_notarizing_and_prints_the_dmg`,
  `::test_a_red_script_fails_with_the_log_and_the_row_says_so`, `::test_a_green_script_that_leaves_no_new_dmg_is_a_failure`,
  `::test_without_dev_it_refuses_a_full_release_needs_the_owner`. **Lock scope and when** (owner 2026-11-03: a post-landing dev build held the heavy lock 54 min through codesign and the DMG while checks waited): the heavy lock is held only for the script's app build (`FICHERO_DMG_STOP_AFTER_APP_BUILD=1` ends the script after its version check), and the packaging (staging, codesign, the DMG) runs after it with `--skip-app-build`, outside the lock; the loop builds nothing at a lane's end or a landing: only the nightly dev release builds, and `builder build --dev` by hand stays (tests assert no `built`/`build-failed`/`build-skipped` rows: `fichero-builder/tests/test_loop.py::test_an_external_lanes_landing_records_product_and_builds_nothing`). Test `fichero-builder/tests/test_build_verb.py::test_the_heavy_lock_is_held_only_for_the_app_build_and_packaging_runs_outside_it`.
- `dev-workflows.run.done-after-delivery` [PARTIAL] (#6589) — a run's DONE counts only after the step's message was delivered (a turn started, or the screen text changed since the send); a message that started no turn within `REDELIVER_S` (60 s) is delivered again, up to 3 tries (`redeliver` watch row). Tests `fichero-builder/tests/test_dry_run.py::test_an_old_done_on_screen_never_marks_a_new_step_done_before_its_message_is_delivered`, `::test_a_message_that_started_no_turn_within_sixty_seconds_is_delivered_again`, `::test_a_delivered_message_is_not_delivered_again`, `::test_the_real_redeliver_presses_enter_when_the_words_sit_in_the_box_and_types_them_again_when_a_turn_never_started`.
- `dev-workflows.queue.disk-floor` [PARTIAL] (#6589) — no new lane starts under `[loop].disk_floor_gb` free (`disk-hold` row); removing a lane's tree drops its jcodemunch index; the worker's uv cache is pruned once a week (`uv-prune` row). Tests `fichero-builder/tests/test_loop.py::test_a_new_lane_does_not_start_under_the_disk_floor_and_the_row_says_why`, `::test_removing_a_lanes_tree_drops_its_jcodemunch_index`, `::test_the_workers_uv_cache_is_pruned_once_a_week`.
- `dev-workflows.queue.split-brief` [PARTIAL] (#6589) — a step red only on the file-size bound gets a split brief (`split` row); any other red gets the plain fix brief. (#6849) The rest of a split is pushed to origin as `<lane>-part2` before the core lands (a failed push blocks the step) and queued as the next step `<step>-part2` of the same lane, with a brief naming the branch and its commits, so the lane is not landed while it is unlanded. Tests `fichero-builder/tests/test_loop.py::test_a_step_red_only_on_the_file_bound_gets_a_split_brief_and_its_rest_is_a_queued_step_on_a_pushed_branch`, `::test_a_split_whose_part2_cannot_be_pushed_blocks_the_step_before_it_lands`, `::test_any_other_red_still_gets_the_plain_fix_brief`.
- `dev-workflows.nightly.cleanup` [PARTIAL] (#6589) — after a published release the tree's releases and the loop's old DMGs, archives and staging are deleted, nothing before the publish; a failed clear is a row and never unpublishes the night; the report lists build-folder sizes (`du`). Tests `fichero-builder/tests/test_nightly.py::test_after_the_publish_the_releases_are_cleared_and_the_text_lists_the_build_folder_sizes`, `::test_nothing_is_cleared_while_the_release_is_not_published`, `::test_a_failed_clear_is_a_row_and_never_unpublishes_the_night`, `::test_the_real_clear_removes_the_trees_releases_and_the_loops_old_dmgs_and_the_sizes_are_du`.
- `dev-workflows.ux.lane-usage` [PARTIAL] (#6116; owner 2026-11-02, "I want to see progress") — the console's "Lane usage today" card: for each
  external lane (not held), today's tokens in (input, cache write, cache read) and out and its turns, summed from its Claude Code session
  transcripts (`~/.claude/projects/<worktree path, non-alphanumerics as "-">/**/*.jsonl`, each message counted once by id, today in local time,
  cached per file mtime), and the API-equivalent dollars in grey, "on Max, not billed" (`[spend].prices`; cache reads at 0.1x and cache writes at
  1.25x the input price). **Built** 2026-11-02: `console.lane_usage`, the card in `console.html`. Not yet: a per-model split.
  Test `fichero-builder/tests/test_status_page.py::test_lane_usage_today_sums_each_external_lanes_transcripts_once_per_message`.
- `dev-workflows.run.issues-close-when-done` [PARTIAL] (#6589; owner 2026-11-14: issues close when they are done) —
  an issue is closed by the harness once its work is done, decided deterministically by `fichero-builder/fichero_builder/issue_reconcile.py` from the spec bullets
  that own it (the `(#N)` right after a bullet's own status tag) and from `Fixes`/`Closes #N` commits: CLOSE-A = every owning bullet is `[OK]` or
  `[BUILT]` (the specs use both) and the tests it names exist on the ref; CLOSE-B = a fix commit and no owning bullet that is not done (and no named
  test missing); otherwise KEEP (an owning bullet is not done), MISSING-TEST (a named test is not on the ref) or NO-SPEC (nothing owns it).
  (a) After every landing the queue reconciles each issue the step cites: CLOSE-A/B closes it with a comment naming the landed sha, the owning
  bullets and the tests; KEEP gets one comment saying what is left (the bullets that are not done; the same list is not commented twice) and the
  issue stays open and is updated, never closed, for residue. The reconcile result is one `issue-reconcile` queue row (each issue, its class,
  whether it closed) replacing the plain `issue-open` row; it runs on a thread, reads only the tests the cited issues' own bullets name (one `git grep` for all, the specs in one `git cat-file --batch`), and is run as `python -m fichero_builder.issue_reconcile`; `gh` failing counts as unread and the lane
  goes on. The landed sha is fetched from origin first when this clone lacks it (#6848: `git ls-tree <sha>` exited 128 on every landing), and an issue left unread
  (the fetch failed, or `gh` could not read it) or a reconcile that raises is an `alert` naming that issue. Tests `fichero-builder/tests/test_issue_reconcile.py::test_a_landing_whose_sha_is_only_on_the_remote_is_fetched_and_read`,
  `::test_after_landing_fetches_the_sha_before_it_reads_and_a_sha_nobody_has_is_said_per_issue`, `fichero-builder/tests/test_queue_verb.py::test_a_reconcile_that_leaves_an_issue_unread_or_crashes_is_an_alert_naming_the_issue`.
  (b) Nightly, over every open issue: the dry-run TSV (issue-reconcile.tsv in the state dir) and ONE summary `issue-reconcile` row (counts per
  class and how many closed), closing only CLOSE-A/B. (c) Never an issue whose owning bullet is not done is closed; never a `type:bug` without a
  test (a fix commit alone, CLOSE-B, leaves a bug open). **Built** 2026-11-14 against a fake gh. Not yet: a run on the real jail user. Tests
  `fichero-builder/tests/test_issue_reconcile.py::test_self_test_passes`,
  `::test_after_a_landing_done_issues_close_with_the_sha_bullets_and_tests_and_kept_ones_get_one_comment`,
  `::test_an_already_closed_issue_is_left_alone`,
  `::test_nightly_writes_the_tsv_and_one_summary_and_closes_only_the_done`,
  `fichero-builder/tests/test_queue_verb.py::test_a_landed_steps_issues_are_reconciled_the_row_names_each_result_and_an_open_one_stays_on_the_step`,
  `::test_the_nightly_reconcile_runs_once_a_day_as_one_summary_row_and_a_failure_is_a_row`.
- `dev-workflows.run.nightly-build` [PARTIAL] (#6665; owner ruling 2026-11-17) — one fixed dev build a night, of one frozen sha, replaces the per-landing dev build. `harness.toml` `[nightly]` names `no_new_steps_at` ("22:00"), `freeze_at` ("00:00"), `check_runner`, `build_machine`, `smoke_machine`, `publish` ("dev") and `check_footprint_mb` (passed to the verify run as `GATE_FOOTPRINT_MB`); a missing key is an error, never a default. **The loop:** from `no_new_steps_at` until `freeze_at` a lane's step starts only if the lane's median land time (the `sent` to `landed` times of its last landed steps in the journal) fits before the freeze; a lane with no landed step to take the median from does not start one (a `night-hold` row names the lane). At `freeze_at` the loop journals the integration head as the night's candidate (a `nightly` row, state `candidate`, once per night; a loop that was down over the freeze starts it only until six hours after it) and starts the nightly in its own thread. Nothing in the loop's checkout is built. **The nightly:** in parallel, `builder verify-all --full` (the guards of `[check].guard_skip` too; test `fichero-builder/tests/test_verify_all.py::test_full_runs_the_guards_the_ladder_skips`) on `check_runner`, and the dev DMG (`scripts/release-all.sh --dev --skip-testflight`) on `build_machine`; each from a CLEAN clone made at the frozen sha, never the loop's checkout: one fixed dir per part (under the state dir here, under the machine's `host:dir`, default `~/fichero-nightly`, over ssh), replaced by the next night's clone, never a per-process /tmp name. The smoke runs in the DMG's tree, or on another machine in a clone of the sha with the built app copied over (then the build machine is the local one). The journal is read only inside the night window or after the freeze. Before the DMG's version stamp the nightly runs `scripts/release_guard.py auto-notes <version>` in that clean tree, so the changelog preflight never stops it. Then the smoke on `smoke_machine`; then, only if all three are green, the publish (a GitHub dev prerelease and TestFlight) and one text to the owner with the test list. A red part: no publish, one alert naming that part. The per-landing dev build is gone: a landed step builds nothing; `builder build --dev` stays for a hand build. Tests, with a fake clock and fake runners (no real build): `fichero-builder/tests/test_nightly.py::test_a_step_after_the_cutoff_starts_only_if_the_lanes_median_fits_before_the_freeze`, `::test_at_the_freeze_the_integration_head_is_the_candidate_once_a_night`, `::test_the_nightly_publishes_and_texts_only_when_every_part_is_green`, `::test_a_red_part_publishes_nothing_and_raises_one_alert_naming_it`, `::test_the_parts_run_in_clean_trees_at_the_frozen_sha_and_auto_notes_runs_before_the_dmg`, `fichero-builder/tests/test_queue_verb.py::test_a_landed_milestone_builds_no_dev_dmg`. **Not built:** a real night (the real runners are untested against the machines).
- `dev-workflows.run.release-stages` [PARTIAL] (#6726; Spec-change: owner 2026-11-19) — the nightly Mac + iOS release is a list of named stages: `sweep`, `freeze`, `verify`, `mac-dmg`, `notarize`, `ios`, `publish`, `merge`, `text` (`fichero_builder/release_run.py`; the Mac chain `mac-dmg`, `notarize` and the `ios` chain run side by side). Each stage writes a `release` row (run id, stage, green or red, the log tail) to the journal; a run resumes from the first stage not green and rebuilds none that passed. `launchd` writes a fourth agent that starts `builder release --branch <[land].branch of harness.toml>` at 03:00 with `FICHERO_NIGHTLY_TEXT_TO` in its environment; `builder release` exits 1 before any stage when that variable is unset. No model runs while the stages are green. `sweep` picks, per role (`--mac`, `--ios`, `--check-runner`, each a comma list of candidates), the first machine that is awake, reachable and over `--floor-gb` free disk (else it is red naming each), journals the choice, then removes caches, this run's own clone dirs (`<state>/nightly/release-<role>`, never the trees of `run.nightly-build`) and TM local snapshots, never `integration/.venv` nor the path it links to. `freeze` journals the sha of `origin/<branch>` and makes a clean clone of it per role (`mac`, `ios`, `check`) even when two roles pick one machine, because the Mac and iOS chains run at once and `release-all.sh` edits its tree; every later build stage runs in its role's clone, never in the loop's checkout (same rule as `run.nightly-build`). There is no separate engine stage: `release-all.sh` builds the engine once inside `mac-dmg` (a bundle reuse across nights needs the bundle kept outside the clone and a `release-all.sh` flag to skip its rebuild; not built). `merge` exists only when `--merge-branch` names the PR, and squash-merges that one. There is no separate iOS compile preflight. A red stage starts ONE manager session (`claude -p`, with a small environment) whose fixed prompt names that stage's log file as untrusted data (never instructions) and gives the stage list; if it exits 0 the run resumes at that stage, else (or if the stage is red again) one `alert` row is journalled and texted naming the stage; a text that cannot be sent is an `alert-failed` row. A run id that already has a `manager` row starts no second manager. Tests: `fichero-builder/tests/test_release_run.py::test_resume_starts_at_the_first_stage_not_green`, `::test_red_calls_the_manager_with_stage_log_and_list_then_resumes_at_that_stage`, `::test_a_manager_that_cannot_fix_it_texts_what_is_red_and_stops`, `::test_sweep_removes_only_this_runs_clone_dir_never_the_nightly_builds_trees`, `::test_the_manager_prompt_frames_the_log_as_untrusted_data_and_does_not_carry_it`, `::test_there_is_no_engine_stage_release_all_builds_the_engine_once`, `::test_the_manager_is_asked_once_per_run`, `::test_a_resumed_run_whose_manager_already_ran_starts_no_second_manager`, `::test_the_alert_is_a_journal_row_and_a_text_that_cannot_be_sent_does_not_crash_the_run`, `::test_without_a_merge_branch_the_plan_has_no_merge_stage`, `::test_the_real_stages_build_in_a_clean_clone_on_the_chosen_machine_never_the_loops_checkout`, `::test_the_mac_and_ios_chains_get_their_own_clone_when_both_land_on_one_machine`, `::test_pick_runner_takes_the_first_awake_one_over_the_floor`, `::test_sweep_never_removes_the_live_venv_or_what_holds_it`, `fichero-builder/tests/test_launchd.py::test_the_release_agent_starts_the_stage_run_nightly_with_no_keepalive`, `::test_the_agents_carry_the_text_target_so_the_text_stage_can_send`, `::test_the_release_agent_takes_the_branch_from_harness_toml_when_none_is_given`. **Not built:** a kept incremental DerivedData; one notarization ticket for app and DMG (kept as today until a test proves it); the real stage commands are untested on the machines.
- `dev-workflows.run.verify-all` [PARTIAL] (#6344; manager 2026-11-02, owner order: the dev build is of everything on origin/integration, fully verified first) —
  `builder verify-all --root R [--build]` verifies R's HEAD in three parts over scratch trees of it: every guard (`[check].guard_glob`
  minus `guard_skip`, from R's own check files), the full engine suite (every `<package>/tests` dir, plus each `[check.whole_tests]` dir as its
  own pytest, on `[check].remote` when one is set, on HEAD as it is), and the app's build rung (`[check].build`, forced on). The guards run first;
  the suite and the build then run beside each other, the build holding every ladder slot so it runs only while no check does. A red part does
  not stop the others. One `verify` row (sha, root, ok, per-part ok/seconds/detail, where the suite ran) and `VERIFIED <sha>` or `NOT VERIFIED`
  printed; with `--build` the dev DMG (`builder build --dev`) is made only after a green verdict; nothing is pushed or notarized. Overlapping
  ladders keep the jail until the last one ends (a counted `_JAIL`, and a ladder with no jail entering leaves the jail a neighbour is using in force (`::test_a_no_jail_ladder_entering_leaves_a_neighbours_jail_in_force` in `fichero-builder/tests/test_supersede_followups.py`); found while building this: the first to end unjailed the other).
  **Built** 2026-11-02 against fakes: `fichero_builder/verify.py`. Not yet: a real run, its timings. Tests:
  `fichero-builder/tests/test_verify_all.py::test_green_runs_every_part_writes_one_row_and_builds_the_dmg_only_with_build`,
  `::test_a_red_part_is_not_verified_and_no_dmg_is_built`, `::test_build_flag_makes_the_dmg_after_a_green_verdict`,
  `::test_two_overlapping_ladders_keep_the_jail_until_the_last_one_ends`.
- `dev-workflows.run.heavy-lock` [PARTIAL] (#6116; owner order via the manager 2026-11-02) — one heavy job at a time per machine: a flock
  `heavy.lock` in the owner's state dir (`journal.heavy`). xcodebuild (the build rung), the full engine suite (the pytest runs of a check,
  `builder test` and `verify-all` that run here) take it, so `builder check`, the loop's chains, `builder build --dev`,
  `builder verify-all` and `builder test` take it through them; the dev build takes it around its script. The guards rung takes its OWN `guards.lock` (one guards rung at a time), never the heavy lock: it waited 65 min behind a dev build on 2026-11-03 (speed batch 3, manager; test `fichero-builder/tests/test_heavy_lock.py::test_the_guards_rung_runs_while_a_dev_build_holds_the_heavy_lock`). A suite sent to
  `[check].remote` takes no local lock; the remote script runs under that machine's own `heavy.lock` in its gate dir (the remote python holds the flock while the script runs; test `::test_the_remote_wrapper_holds_the_machines_lock_while_its_script_runs_and_passes_the_exit_code`). The dev build YIELDS: a check waiting for the lock leaves a `heavy-wait.<pid>.<thread>` marker, and the build takes the lock only while no marker stands, so a queued ladder always outranks it (manager 2026-11-03; test `fichero-builder/tests/test_heavy_lock.py::test_a_build_yields_to_a_waiting_check_and_a_check_outranks_it`). When a MILESTONE is complete (owner 2026-11-03: not after every product landing: a worker lane's last step landed, pushed for real, and some step of it touched `[check].product_paths`; an external lane has no milestone end the loop can see, so its run is the manual verb) the loop runs `builder verify-all` ONCE when every lane is idle and no build runs (a `verify-pending` marker, consumed when it starts): the `verify` row and its activity rows are the journal and console record, a red result is an `alert` on step `verify`, nothing is pushed (tests `fichero-builder/tests/test_queue_verb.py::test_a_product_landing_earns_one_verify_all_once_every_lane_is_idle_and_a_harness_only_landing_earns_none`, `::test_verify_all_waits_while_a_lane_is_busy_and_never_runs_for_an_unpushed_landing`). A lane or the manager runs any other heavy command with
  `builder heavy -- <cmd>`: it waits, says who holds the lock after 30 s (the lock's own waiting row and a line on stderr), and its child
  passes through the lock it holds (`FICHERO_HEAVY_HELD`), so a `builder test` run inside it never deadlocks. Quick things (ruff, swiftlint,
  `swiftc -parse`, one test file) never ask. Two checks at once (`[check].parallel`) therefore overlap only in their quick rungs and the
  remote runs. **Built** 2026-11-02: `journal.heavy`, `check_tool._heavy`, `builder heavy`. Not yet: a real wait on the iMac.
  Tests: `fichero-builder/tests/test_heavy_lock.py::test_a_second_heavy_job_waits_and_a_wait_over_the_limit_names_the_holder`,
  `::test_builder_heavy_runs_the_command_under_the_lock_and_its_children_pass_through`,
  `::test_the_build_rung_and_a_local_full_suite_take_it_the_guards_and_a_remote_suite_do_not`, `::test_the_dev_build_takes_the_lock`.
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
  an owed test `test_cluster_run.py` (for the `workflows` tests).
- `dev-workflows.worker.steers` [PROPOSED] — the worker owns the task's judgement and calls the steps as tools (`brief`,
  `check`, `request-review`, `verdicts`, `land`, `ask`, `hand-off`; `close`, `update-issue` and `file-bug` only once the
  guarded writer exists; for research `search`, `fetch`, `save-source`, `note`); it stops and asks when an acceptance line
  would change, a pinned check trips, a step is paid or irreversible, a source contradicts the premise or the spec
  contradicts the code; the countable stops are `check`'s (above); never for context. Test:
  an owed test `test_cluster_run.py` (for the `workflows` tests).
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
  Phase 0 amendment (owner 2026-11-17/18, from the cut `dev-workflows.worker.handoff`): Pi's own auto-compaction stays on only as a safety net set to fire later than the handoff mark, so the two never race; the bake-off compares handoff alone against handoff with the net.
- `dev-workflows.worker.two-capability-sets` [PROPOSED] — Builder: worktree, shell, git, the step tools, scratch base path,
  `dev` tier only. Researcher: capabilities **per task**, never mixed in one session: find-sources holds web search and
  fetch and no library read; search-libraries holds read-only library and KG actions and no web; read-and-note reads only
  saved sources with no egress; writes go through the audited layer as the user's account; no shell, never a GitHub
  token. Test: an owed test `test_capability_sets.py` (for the `workflows` tests).
- `dev-workflows.security.grants` [PROPOSED] — a standing **allow-list** in the rules file per role (tools, paid providers,
  GitHub writes), checked at the tool; a paid or public step outside it is a question, answered once per task and
  logged; the full grant record (who, scope, expiry, per model) returns with #4721 when a second user needs it. Test:
  an owed test `test_grants.py` (for the `workflows` tests).

#### B. Review, landing, gates and watches

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
  an owed test `test_review_and_land.py` (for the `workflows` tests).
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
  Test: an owed test `test_land_gate.py` (for the `workflows` tests).
- `dev-workflows.run.policy-hook` [PARTIAL] (#6116; built at 98ba83507) — each worker runs with a PreToolUse policy hook and a
  `commit-msg` hook, plain scripts reading `harness.toml [policy]`, refusing with a reason and a row: a write or `cd`
  outside the worktree and scratch path, `git stash`, any `git push` (parsed from argv, so `git -C . push` is caught),
  `xcodebuild`, `pkill`/`killall` by pattern, a listing and `rm -r` in one command, a second test run (lock file),
  wrong author or missing trailers, a paid call outside the allow-list; a kind's adapter maps its tool names, and an
  unknown tool name is refused. **Layers:** the user boundary holds the hard rules; the hook is fast feedback, not a
  security boundary; guards at landing catch the rest; prose-only rules are listed as such and become hook or guard
  rules once seen twice. Test: `fichero-server/tests/unit/workflows/test_policy_hook.py::test_each_forbidden_command_is_refused_with_a_reason`.
- `dev-workflows.ledger.one-row-per-unit` [GAP] (#6379; owner 2026-11-06) — every unit of work the harness runs gets ONE ledger row in `<state>/runs/<run-id>/ledger.jsonl` (the state tree of #6357): a lane's build of a step (its Claude Code session between the step's `start` and its `done`), a check (a ladder), a review, a fix round, a spec batch, a milestone brief, a manager's answer. The row: `run`, `lane`, `batch` (the step name, `batch-3` or `spec-6365`), `sha`, `role` (builder, reviewer, reviewer_fast, spec-writer, manager, helper, researcher, or `ladder` for a model-free check), `kind` (build, check, review, fix, spec, brief, answer), `round` (0 for the first attempt, then the rework round), `model`, `provider` (claude-code, anthropic, omlx, openrouter), `tokens_in`, `tokens_out`, `tokens_cache_read`, `tokens_cache_write`, `cost_usd`, `tokens_per_usd`, `wall_s`, `outcome` (landed, sent-back, red-on-base, refused, superseded, or the review's verdict), `source` (where the numbers came from: transcript, pi, openrouter, table, none). Today the journal has the model name on about 300 rows and no tokens or cost; the row adds what is missing and the journal rows stay as they are. Acceptance: after a lane's batch lands, its run's ledger holds one row per unit (the build, the check, the review, each fix round, the landing's re-check) with every field above filled or null, and a check row carries tokens 0 and its wall time; a second build round is `round: 1`; the file is appended, never rewritten.
- `dev-workflows.ledger.numbers-from-the-cheap-sources` [GAP] (#6379) — the numbers come from what already exists, read after the fact, no model call asked to report on itself: (1) a Claude Code session's transcript (`~/.claude/projects/<cwd>/<sessionId>.jsonl`, the pane's session id is known to the loop): each assistant message's `usage` (`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`) and `model`, counted once per message id (`console._usage_rows` does this today for the lane-usage card), attributed to a unit by the journal's time window for that lane's step (the `start` and `done`/`end` rows), so a session that spans two steps splits by time; (2) the Pi runner's JSONL: `usage.input`, `output`, `cacheRead`, `cacheWrite` and `usage.cost.total` per message (`session.py` reads them); (3) OpenRouter's response `usage` (`prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens`, and `cost` when the call asks `usage: {include: true}`), kept by the Pi provider per call. Wall time is the journal's own start and end rows. A unit with no transcript and no provider usage (a check) has tokens 0 and `source: none`. Acceptance: a fixture transcript with three assistant messages inside a step's window and two outside yields a row with the three summed once each; a Pi JSONL with `cost.total` yields `cost_usd` from it and `source: pi`; an OpenRouter usage block with `cached_tokens` fills `tokens_cache_read`; a message with no usage adds nothing.
- `dev-workflows.ledger.prices-in-one-dated-table` [GAP] (#6379) — where no provider returns a cost, the cost is `tokens × price` from ONE table, `[spend].prices`, which grows from `{model = [in, out]}` to `{model = {input, output, cache_read, cache_write, source, dated}}` in USD per million tokens (the old two-number shape still reads, with cache read at 0.1× and cache write at 1.25× the input price, as the lane-usage card already does); every entry names its source and date (`source = "anthropic.com/pricing", dated = "2026-11-02"`; an OpenRouter model names `openrouter.ai/models/<id>` and its date); a provider's own cost wins over the table (`source: provider`); a model with no price gets `cost_usd: null`, one alert per model per day naming it, and the ledger still writes the row (the watcher's own refusal to start a worker with no price stands, `run.watch-tick`). `tokens_per_usd` is `(tokens_in + tokens_out) / cost_usd`, null when cost is. Acceptance: the live table's three models (sonnet 3/15, opus 15/75, haiku 1/5) price a row as the card does today; a four-number entry prices cache reads at its own figure; a row for `qwen3-coder` with no entry is written with null cost and raises exactly one alert that day; a provider cost of 0.0123 beats a table price.
- `dev-workflows.ledger.keyed-to-batch-and-lane` [GAP] (#6379) — a row is keyed by `(run, lane, batch, round, kind)` and nothing else, so a batch's cost is the sum of its rows and a lane's day is the sum of its batches; the journal's `landed` row gains `cost_usd` and `tokens` (the batch's sums) and the status digest's per-lane block says "N batches landed, $X, Y rework rounds, Z tokens per dollar" per model and role; a batch superseded by a new head keeps its rows with `outcome: superseded`. Acceptance: two batches of one lane in one run sum to the lane's figure in the digest; the `landed` row of a batch carries the sum of its build, check, review and fix rows; `builder ledger --lane sharing --run <id>` prints the rows and the sums.
- `dev-workflows.ledger.comparison-view` [GAP] (#6379) — `builder ledger --compare --role reviewer [--since 2026-11-01]` prints, per model and provider for that role: units, landed batches, cost per landed batch, mean rework rounds, mean wall time per unit, tokens per dollar, and the share of each outcome; a model with fewer than five units is marked "few" and sorted last; the console shows the same table as a view ("Models" beside "Lane usage today"); the owner reads it to pick a model per role in `[models]` (`models.by-config`), and nothing changes a role's model by itself. Acceptance: a fixture ledger with sonnet reviews (8 units, 6 landed, 1.2 rounds) and a Qwen-through-OpenRouter review (3 units) prints two rows with those figures, the Qwen row marked "few"; the same numbers appear in the console view; `--role builder` shows cost per landed batch per model.
  Phase 0 amendment (owner 2026-11-17/18, from the cut `dev-workflows.ledger.comparison-view`): the weekly report is produced by queries, never a model's summary: steps landed on Fichero versus on the harness; share READY within two fix rounds, by model; cost per landed step by role; escalations and how many asked to relax a check; shadow agreement; the parked list; the cloud exceptions.
- `dev-workflows.ledger.plan-prices-in-one-dated-table` [GAP] (#6387; owner 2026-11-07) — the price table of `dev-workflows.ledger.prices-in-one-dated-table` gains the PLANS beside the per-token prices, so a day can be priced every way the owner may buy it: `[spend].plans` holds, per option, the monthly price, the daily share (price ÷ days in the month), the plan's limits in the vendor's own units (a 5-hour window's messages or tokens, a weekly cap) and the source page with its date (Claude Max and an Ultra-class Claude plan from Anthropic's plans page; Claude API list prices; OpenAI and Google list prices; OpenRouter's per-model prices read from its `/api/v1/models` answer, the cheapest provider per model kept with the provider's name); nothing in the table is guessed: a row without a source and a date is refused by the loader. Pi's own model prices (`~/.pi/agent/models.json`, the `cost` fields a provider row carries) are read, not copied. Acceptance: the loader refuses a plan row with no `source` or `dated`; a day's token totals priced at Claude API list, OpenAI, Google and OpenRouter-cheapest give four figures, and the plan rows give a daily share each; an OpenRouter model's price is the one its models endpoint gave, with the provider named.
- `dev-workflows.ledger.plan-limit-hits` [GAP] (#6387) — every rate-limit or plan-limit hit is a ledger row of its own: when (local Atlantic), the lane and role, which limit (the vendor's words: the 5-hour window, the weekly cap, a 429, a 402, OpenRouter's credit), and how long it blocked (until the session's next turn, or the `resets` time the message named); the detection is `session.py`'s existing `QUOTA` match (`rate_limited`), extended to record the reset time when the wording carries one. Acceptance: a Claude Code transcript with "5-hour limit reached ∙ resets 2am" yields one hit row with the limit named and the block measured to 02:00; a Pi JSONL with a 429 yields one with "429" and the retry-after; a day with no hit has no row.
- `dev-workflows.ledger.daily-digest-per-role-and-model` [GAP] (#6387) — the daily digest (the status digest the console refreshes, and the per-run summary of `dev-workflows.ledger.keyed-to-batch-and-lane`) gains one block per day: items built, reviewed and reworked; tokens in, out, cached read and cached write; API-equivalent cost per role and per model (`cost_usd` where a provider billed, `tokens × list price` otherwise, each flagged `billed` or `equivalent`); cost per accepted item; plan-limit hits; and the day priced every way: each plan's daily share beside the four per-token totals. Keys, prompts and private paths never appear in a row or the digest (the strip pass of `ledger.one-row-per-unit`). Acceptance: a fixture day of 6 units (3 builds on sonnet, 2 reviews on opus, 1 review on a Qwen model through OpenRouter) prints the block with the per-role and per-model lines, the two flags, cost per accepted item, one hit row, and six prices for the day; a grep of the digest for an API key pattern or a home path finds nothing.
- `dev-workflows.ledger.break-even-view` [GAP] (#6387) — `builder ledger --plans [--since]` prints the running view the decision needs: a typical day (the median of the last 14), a heavy day (the 90th percentile), and for each option the break-even in days a month (the plan's monthly price ÷ the typical day's API-equivalent cost), so the owner sees where Max, Ultra, direct API, OpenAI, Google and OpenRouter cross; the same table is a console card beside "Lane usage today" and feeds the model bake-off (#6380) and `dev-workflows.ledger.comparison-view`. Acceptance: the fixture history gives the median and the 90th percentile and one break-even per option; an option whose daily share is above the heavy day's cost reads "never pays"; the console card shows the same numbers as the command.
- `dev-workflows.ledger.cheapest-provider-router` [GAP] (#6387) — a role whose `[models]` row says `prefer = "cheapest"` is routed, per unit, to the cheapest provider among those whose model has PASSED the role's quality bar in the comparison view (`ledger.comparison-view`: at least five units, cost per landed batch and rework rounds within the owner's bar for that role), re-read once a day from the ledger; a role without `prefer` keeps its one model as today; the router writes which provider it chose and why on the unit's ledger row, never changes a `[models]` row, and falls back to the row's own model when no provider has passed the bar or the chosen one hits a limit (`ledger.plan-limit-hits`). Acceptance: with `reviewer_fast = { provider = "claude-code", model = "sonnet", prefer = "cheapest" }` and a ledger where a Qwen model on OpenRouter has six landed reviews within the bar at a third of the cost, the next review unit goes to OpenRouter with the reason on its row; with four units it stays on sonnet; a 429 on OpenRouter sends the next unit back to sonnet and writes the hit; `[models]` is byte-identical before and after.
- `dev-workflows.run.watch-tick` [PROPOSED] — the watcher is the `builder run` process itself, reading the worker's session
  file (context, cost, idle, stuck, red), for Claude and Pi alike (`parse_session` reads both); not a session cron, not the
  engine's scheduler, not a pane regex. A worker gone with its task unfinished → a successor from the handoff, or a question
  with none; a handoff with no successor after twenty minutes → started; a cluster READY and unlanded after thirty minutes →
  `land` or its refusal as a question; a worker judged stuck by its process and its session file's age, never by a missing
  row → told once by file, then replaced; a silent worker raises an alert; an unknown price refuses to start; a per-session
  spend cap hands off to a fresh session and a daily cap parks with a question (owner ruling pending: the daily amount); on restart the journal is reconciled
  before any successor; the pinned dev engine moves to a newer sha only between clusters; each action a journal row. A
  `launchd` job only keeps the watcher itself alive. Built 2026-11-01: the judgement (`fichero_builder/watcher.py`: caps from
  `[spend]`, a missing cap or an unknown price refuses, decisions park, handoff, alert from a session state). Not yet: the
  process that starts, reads and acts. Test: `fichero-builder/tests/test_watcher.py`.
  The caps in `harness.toml [spend]` are owner settings (8 USD a session, 250 USD a day as of 2026-11-16 evening). `[spend].window` is 200000 and
  `[models].builder` is plain `sonnet` (owner 2026-11-02: every turn under 200k, handoffs often, cheap and reliable; Opus 2026-11-20, back to Sonnet 2026-11-21 11:20 after the burn; the test pins exactly this value), because a lane takes its model from the role (test `fichero-builder/tests/test_model_config.py::test_a_window_past_the_standard_one_has_a_builder_model_that_gets_it`).
- `dev-workflows.run.loop` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) (owner 2026-11-02: the harness keeps going with nobody watching; a stage that waits on a
  person is a defect) — `builder loop` runs indefinitely: `builder queue run --lanes N --push` ticking forever, one `loop` heartbeat
  row a tick. It runs as the owner (a LaunchAgent with KeepAlive), because check rows, verdicts, the push and `gh` are the owner's
  and a worker never holds them; workers stay the jail user. Killed and restarted, it resumes every lane from `queue.json` and the
  journal, never repeating a landed step. Every stage transition is deterministic code; a model is called only to code (the
  builder), to review (the reviewer) or to fix findings (the builder). Test: `fichero-builder/tests/test_loop.py`
  (fakes: a restart mid-chain resumes; a landed step is never re-run).
  **Built** 2026-11-02 against fakes: `builder loop` (lanes and rounds from `[loop]`, push on, forever, a `loop` tick row each tick; a rules file that cannot run it is a row). Tests: `fichero-builder/tests/test_loop.py::test_a_restart_mid_chain_resumes_the_step_and_never_lands_it_twice`, `::test_rounds_come_from_the_loop_table`. `builder launchd` writes the owner's two LaunchAgents (`builder loop` with KeepAlive; `builder heartbeat` every three ticks) and prints the `launchctl bootstrap` lines, never loading them; the loop runs a lane's chain beside the ticks, so a long ladder never starves the heartbeat. Tests `::test_the_launch_agents_keep_the_loop_alive_and_run_the_watchdog_every_three_ticks`, `::test_a_one_lane_chain_runs_beside_the_ticks_so_the_heartbeat_keeps_beating`. Not yet: the agents loaded on the owner's Mac.
  Built 2026-11-05: Each lane's chain runs in a pool of `[loop].lanes` workers (`--lanes`, default 1: one chain at a time, whatever `[check].parallel` says); a chain submitted while every worker is busy writes one `waiting-for-worker` queue row naming the lanes ahead of it (running or queued), so the wait shows on the console's lane row instead of a silent `done` (2026-11-05: batch-25 waited 40 min unseen; test `fichero-builder/tests/test_loop.py::test_a_chain_waiting_for_the_pools_one_worker_says_so_and_a_free_pool_says_nothing`).
  Built 2026-11-06 (owner): `[loop].lanes = 2`, so two lanes' chains run at once and `[check].parallel = 2`'s two ladder slots are used; read when the loop starts. `[check].remote_min_free_gb = 6` skips a runner under 6 GiB free.
  Built 2026-11-07 (owner): a second Qwen lane, `lane-qwen2`, in `[loop].only` and `opus_lanes` (`[loop].lanes` goes to 3 in its own change once the load allows). The ready check's fast guards run a guard that timed out once more, as the ladder's guards rung does, and only a second timeout is red (a 10 s guard timed out at load 95 and refused a green batch). Test: `fichero-builder/tests/test_presubmit.py::test_the_ready_checks_fast_guards_run_a_timed_out_guard_once_more_and_only_a_second_timeout_is_red`.
- `dev-workflows.run.loop-chain` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — per lane, with no person: the worker's DONE row → `builder check` with the
  integration tip as base → the review wrapper (in commit groups when over the cap) → on READY the land gate and `builder landed
  --push`, which closes the Fixes issues → the lane rebased on the new tip → its next step's brief into the same session. A
  worker's DONE is a claim the ladder verifies, never taken on its word. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_loop.py`
  (two steps of one lane land through fakes, each transition a row).
  **Built** against fakes (`queue.tick_lane` over `work.after_run`): test `fichero-builder/tests/test_queue_verb.py::test_a_two_step_lane_lands_the_first_then_sends_the_second_into_the_same_session_and_stops_at_the_end`. A land gate refused because the landing branch moved after the rebase (another lane landed) rebases and runs the check, review and gate again, up to six times, never a hand rebase (manager 2026-11-02; test `fichero-builder/tests/test_work_verb.py::test_a_ready_range_whose_base_moved_before_the_land_gate_is_rebased_and_checked_again`). Not yet: a real lane; a push refused by a move after the gate. **Stale base** (manager 2026-11-02: ie-batch2 was reviewed and refused on a base that had moved during its 52-minute check): after a green check, a base that moved sends the chain back to rebase before any review; when the rebased batch has the same files and the same patch (`git diff base head` equal before and after: file names alone let new content ride a green) and the base delta shares no file with the batch, touches no test the batch ran (a changed test, a `[check].whole_tests` dir), no `[check].check_paths` file and no guard, the green check stands as a `check` row for the new range that says "kept across rebase onto <sha>: base delta disjoint" and names the rungs that run again (manager 2026-11-24: 81 of 89 base deltas were file-disjoint, yet 87 full re-checks cost 25.3 slot-hours); the old ladder's other rungs are reused as they were, and only the delta's rungs run: `.md` alone = guards; `fichero/` = build; `fichero-server/src/` = the green half of red-on-base (never the base run) plus guards; a mixed delta runs the union; a delta path in none of these classes runs the ladder again; otherwise the ladder runs again (tests `fichero-builder/tests/test_work_verb.py::test_keep_green_for_a_base_delta_that_shares_no_file_test_check_file_or_guard_with_the_batch_and_names_what_to_run_again`, `::test_kept_rows_are_the_green_rows_of_the_old_ladder_for_exactly_its_head_base_and_pinned_copy`, `::test_a_partial_do_check_reuses_the_held_rows_and_runs_red_on_base_head_only`, `fichero-builder/tests/test_approve_resume.py::test_a_kept_rebase_runs_the_head_green_half_of_red_on_base_and_never_the_base_run`). A running check whose base is no longer the landing branch's tip reads "base moved; will rebase" on its console lane row (tests `fichero-builder/tests/test_work_verb.py::test_a_base_that_moved_during_the_check_is_rebased_before_the_review_and_a_disjoint_delta_keeps_the_green`, `fichero-builder/tests/test_status_page.py::test_a_check_whose_base_is_no_longer_the_landing_tip_reads_base_moved`).
- `dev-workflows.run.loop-fix-rounds` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — a red check or a NOT READY review sends its findings back to the same worker
  as a fix brief and the chain runs again, up to `[loop].rounds` rounds (default 2); after that, and on a spend cap, a dead or
  stalled worker or a refused guard, the lane parks with an alert. A parked lane never blocks the other lanes. Test (to write):
  `fichero-builder/tests/test_loop.py` (NOT READY → fix → READY lands; three reds → one alert, the lane parked, the other lane
  goes on).
  **Built** against fakes: `[loop].rounds`; a red with its session gone starts a new session on the step's brief plus the findings (`fix-<lane>-<step>-<round>.txt`), never into the dead feed. Test `fichero-builder/tests/test_loop.py::test_a_red_with_no_live_session_starts_a_new_one_on_a_fix_brief_with_the_findings`. The block after the last round is an alert like every block (`queue.py` `block`, Step 2.10).
  Built 2026-11-07 (an SSL error after the Mac woke came back as the review's text, read as NOT READY, and spent a batch's three send-backs with no review done): a review whose output is an API transport failure (connection, timeout, overload) with no READY or NOT READY line of its own is tried again after 60 s and 300 s; still unreachable, it is a `review-unreachable` alert for a person, never findings sent back to the lane. Test: `fichero-builder/tests/test_work_verb.py::test_a_review_that_never_reached_its_api_is_tried_again_and_then_is_an_alert_never_a_not_ready`.
- `dev-workflows.run.loop-rolls-on` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — when a lane's milestone has no open step left, the loop runs `builder build
  --dev` (one row, pass or fail; a failure is an alert, the roll-on goes on) - for a build-order milestone always, and for an external lane never (owner 2026-11-03: a dev build only at a milestone's end or by hand; an external lane's batches have no milestone end the loop can see, so every landing of one is a `build-skipped` row and its dev build is `builder build --dev` by hand; `product` is still recorded on the step before landing; test `fichero-builder/tests/test_loop.py::test_an_external_lanes_landing_records_product_and_builds_nothing`) - and the lane takes the first `## In order`
  milestone of `build-order.md` that no lane holds; up to N lanes at once, one ladder at a time on the machine. The order done
  is a row, and the loop keeps ticking for new issues. Test: `fichero-builder/tests/test_queue_verb.py::test_the_queue_rolls_on_to_the_next_build_order_milestone_when_a_lanes_steps_have_landed`,
  `::test_n_lanes_hold_n_milestones_and_their_chains_overlap_but_the_ladder_is_one_at_a_time`; (to write) the build after a
  milestone. **External lanes and the loop's lanes** (manager 2026-11-02): an external lane holds its milestone but does not count toward `[loop].lanes` unless the loop is checking, reviewing or landing it; a finished external lane frees its milestone; a finished lane handed new work takes that work's kind and worktree; a milestone's step-less issues are one `alert`, and a skipped brief is not planned again (test `fichero-builder/tests/test_loop.py::test_external_lanes_hold_their_milestone_but_are_not_the_loops_lanes_and_a_finished_lane_is_briefed_again`).
  **Built** 2026-11-02 (removed 2026-11-17: tests removed, no longer true) against fakes: a lane whose last step landed with push runs `builder build --dev` once (a `built` or `build-failed` queue row; a failure is an `alert` row with no action, and the next milestone is taken regardless). Test `test_a_finished_milestone_gets_one_dev_build_and_a_failed_build_is_an_alert_while_the_roll_on_goes_on`. The build runs in its own thread, never inside a tick (an inline build held every lane's check for 17 minutes and read as a stale heartbeat), and the live-code re-exec waits for it (test `test_the_dev_build_never_holds_a_tick_the_loops_other_lanes_wait_on`). Not yet: a real build.
  **Was** (removed 2026-11-17 by `run.nightly-build`, #6665: the loop builds nothing, the roll-on is unchanged): the per-milestone dev build above. Test of the removal: test `fichero-builder/tests/test_queue_verb.py::test_a_landed_milestone_builds_no_dev_dmg`.
- `dev-workflows.run.loop-alerts` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — every stop is an `alert` row: id, lane, step, what failed in one line, the path
  of its evidence (ladder JSON, review text, session file, log) and the allowed actions, a subset of `retry`, `park`,
  `ask-owner`. `builder alert <id> retry|park|ask-owner` is the manager's whole job, so a small model can do it: retry re-queues
  the step with its findings, park leaves it, ask-owner labels its issues `needs-your-decision` with the alert as the comment.
  The loop never ends silently: a heartbeat older than three ticks is itself an alert, raised by a second LaunchAgent that reads
  only the journal. Test: `fichero-builder/tests/test_loop.py` (each stop kind gives one alert with its evidence and
  actions; each action does what it says; a stale heartbeat alerts).
  **Built** 2026-11-02 against fakes: every block in the queue is an `alert` row (id `<lane>-<step>-<n>`, what, evidence: the ladder JSON, the review text or the question file, actions); `builder alert <id> <action>` answers it (an action not offered is a refused `alert-answer` row). A block no longer labels the issues by itself: `ask-owner` does (#6343's label and comment, test `fichero-builder/tests/test_queue_verb.py::test_a_blocked_step_labels_its_issues_needs_your_decision_and_comments_the_question`). Tests `fichero-builder/tests/test_loop.py::test_every_stop_is_an_alert_with_evidence_and_actions_and_retry_lands_it`, `::test_send_back_and_ask_owner`. The watchdog `builder heartbeat` reads only the journal: no `loop` tick row for more than three ticks is one `alert` row (step `heartbeat`, evidence the journal, no actions: KeepAlive restarts a dead loop), once per silence; exit 1 while stale. Test `::test_a_stale_heartbeat_is_one_alert_per_silence_and_a_fresh_one_is_none`. **Alerts never hang around** (owner 2026-11-04): an informational alert is answered by itself when its condition clears (a heartbeat alert `loop-back` at the next tick; a runner's `runner-back`; a superseded head's `superseded`); `builder alert <id> dismiss` (the console's Dismiss on every card) answers any alert and changes nothing else; the console lists only unanswered alerts, and below them, collapsed, the last 7 days' resolved ones with how each ended, newest first. **The lane set is named** (manager 2026-11-04, alerts 315 and 316: the LaunchAgent loop, a fresh process, took an old build-order milestone the hand loop had long skipped and started a worker on steps another lane had landed): `builder loop` ticks only the lanes `[loop].only` names (a lane in queue.json that is not named never starts), takes build-order milestones only when `[loop].feed_milestones = true`, and a command run as the jail user starts in the jail's workroot, never the loop's working directory (which that user cannot read: `getcwd` refused); the loop agent's WorkingDirectory is the owner's state dir. Tests `fichero-builder/tests/test_loop_lane_set.py::test_the_loop_ticks_only_the_lanes_it_names`, `::test_milestones_are_taken_only_when_feed_milestones_is_on`, `::test_a_jail_command_runs_from_the_workroot_never_the_callers_cwd_and_the_plist_works_from_the_state_dir`. Tests `fichero-builder/tests/test_alerts_clear.py::test_a_heartbeat_alert_is_answered_when_the_loop_ticks_again`, `::test_any_alert_can_be_dismissed_and_nothing_else_changes`, `::test_the_console_lists_open_alerts_and_the_last_seven_days_resolved_newest_first`. A wedged loop is restarted by `builder heartbeat --restart ROOT` (the watchdog, 2026-11-02: a tick sat 17 minutes and nobody restarted it): on a new stale alert it kills the loop named in `<state>/loop.pid` with its whole process tree (a build's scripts and xcodebuild are grandchildren) and starts `builder loop --root ROOT` detached, once per silence. The loop writes its own pid to `loop.pid` when it starts (an exec keeps the pid); with no `loop.pid` the restart refuses with a `loop` row `restart-refused` and starts nothing, so it never ticks a second loop beside a stuck one (review 2026-11-02). Tests `fichero-builder/tests/test_queue_verb.py::test_the_watchdog_restarts_a_silent_loop_once_per_silence_and_names_the_new_pid`, `::test_the_watchdog_refuses_with_no_loop_pid_and_starts_no_second_loop`, `fichero-builder/tests/test_loop.py::test_a_restart_mid_chain_resumes_the_step_and_never_lands_it_twice`.
  Built 2026-11-05 (Dismiss "did nothing": 75 identical runner alerts were open, and each click showed the next): Dismiss answers the alert and every other open alert of the same kind (lane, step, and the text before its first `;` with its numbers masked), one row each; an alert of another kind stays (test, end to end through the console's `/api/action` and the real `builder alert`: `fichero-builder/tests/test_alerts_clear.py::test_dismiss_through_the_console_clears_every_open_alert_of_the_same_kind_and_no_other`).
  **Check-run fixes** (2026-11-02, found on real batches): a green pytest run red only by ERROR lines of a load kind (a teardown/import OSError, a DuckDB CHECKPOINT TransactionException) with no FAILED test is re-run once alone, the retry a `check` row (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_load_flake_only_red_green_run_is_rerun_once_alone_and_a_real_failure_never_is`); a rung's tail keeps the first Traceback/exception lines a long run buries (`::test_the_tail_keeps_the_first_exception_when_a_long_run_buries_it_and_there_is_no_failure_section`); a test under a top-level package (`pipeline/tests`) gets the tree root on the jailed pytest's path, absolute or relative (`::test_a_test_of_a_top_level_package_imports_it_from_the_tree_root_under_the_jailed_pytest`); a maintainer approve excuses a conftest edit pinned by name (`::test_a_maintainer_approve_excuses_a_conftest_edit_that_is_pinned_by_name`); a send-back or fix brief reaches a live worker session, not the original brief (`fichero-builder/tests/test_loop.py::test_a_send_back_or_fix_brief_reaches_a_live_session_not_the_original_brief`). A build rung red on `XCBuildData/build.db ... database is locked` (another xcodebuild in the same derived dir, manager 2026-11-03) is re-run once after 30 s, the retry a `check` row, and any other red never is (`fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_rung_retries_once_on_a_locked_build_db_and_never_on_another_red`). A guard that times out is re-run once (a `check` row; the second result stands, so a real hang stays red; manager 2026-11-03: a guard printed all-ok and then hit the timeout at load 35) and a plain red never is (`fichero-server/tests/unit/workflows/test_check_tool.py::test_a_guard_that_times_out_is_re_run_once_and_a_plain_red_never_is`). A red build keeps every line naming an error (`path:line:col: error:`, `** BUILD FAILED **`, a kill, an out-of-memory) in the row's `errors`, and the whole xcodebuild output goes to `<state>/build-logs/build-<time>-<ns>.log`, named in the row's `log` (a green build writes none; a write that fails says so in `log` and the rung's result stands); the fix brief and the alert's findings carry both after the tails, so the 3000-character cut keeps them (manager 2026-11-03: bb3's red build at exit 65 after 472 s had no error line left in its 3 KB tail; `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_red_build_keeps_every_error_line_and_the_whole_log_whatever_follows_them`).
  **Superseded alerts** (manager 2026-11-02: three alerts about old heads stayed open on the console): `builder done` at a new head and a step's landing answer every open alert of that lane and step `superseded` (an `alert-answer` row; never park, which would act on the live step). A ladder that ran on an OLDER head ends silently when it is harvested (a `stale-result` row; no alert, no tell to the lane, no finding): test `fichero-builder/tests/test_queue_verb.py::test_a_ladder_cancelled_by_a_newer_head_ends_without_an_alert_a_tell_or_a_finding`. A superseded ladder's cancel marker (`cancel-<head9>`) is removed when that ladder ends, and a marker over a day old (written after its ladder had already ended) is swept when any ladder starts; tests `fichero-builder/tests/test_supersede_followups.py::test_a_ladder_that_ends_removes_its_own_cancel_marker`, `::test_old_cancel_markers_are_swept_and_a_fresh_one_stays`, `::test_cancel_requested_reads_the_calling_ladders_own_key`. Test `fichero-builder/tests/test_loop.py::test_a_new_head_or_a_landing_answers_the_steps_open_alerts_superseded_and_never_parks`. **A newer head supersedes a batch in the ladder** (manager 2026-11-02, lane-onboard): `builder done <lane> <sha>` on an external lane whose batch is being checked or reviewed takes `<sha>` when it descends from the head in the ladder or rewrites it (`git cherry` shares a patch), else refuses as before; the old check is cancelled (a `cancel-<head9>` file the ladder's running command polls, so the loop, another process, kills it within seconds), its approvals and open alerts end, a `superseded` queue row is written, and a result the old chain still returns is dropped (`stale-result`). **One compare-and-set for the whole class** (reviews -92, -94, -96: three rounds on one race, a stale chain against a newer `builder done`): every write a chain makes to its step is `queue.store(lane, expect=(step, head))`, a compare-and-set of the step's head under the queue lock, and no unlocked read decides anything. The stage writes (`checking`, `reviewing`) go through it with the head the chain started with, a refused one is neither written nor said; the chain's outcome is claimed once, the same way, whatever it is (landed, red, needs-maintainer, a fix brief): a failed claim drops the result as `stale-result` and writes nothing, and a won one marks the step `settling`, which `builder done` refuses (`one at a time`) in whatever state the chain left the step (a chain that returns before its first stage, on a rebase error, no patches, a failed fetch or an exception, leaves it `done`) until the outcome's own write ends it; each outcome is ONE write (a landing sets the step landed and advances the cursor in the same store, so no `builder done` runs between two writes; test `::test_the_landing_is_one_write_so_a_done_right_after_it_opens_the_next_batch_and_loses_nothing`), so the landing, a block or a fix brief can never overwrite a newer head (`builder done` holds the lock through its git work and saves last, so a check made before taking the lock passed and was then overwritten). Tests `fichero-builder/tests/test_loop.py::test_a_stale_chain_writes_nothing_at_any_stage_after_a_newer_done` (one chain through every stage and three outcomes against a `done` landing at each point; fails without the compare), `::test_a_stale_chain_store_waits_for_the_queue_lock_and_then_checks_the_head_under_it`, `::test_an_old_chains_stage_callback_never_writes_its_stale_step_over_a_newer_done`, `::test_a_done_while_the_batch_is_landing_is_refused_and_the_landing_keeps_its_step`, `::test_a_done_right_after_the_outcome_claim_is_refused_whatever_state_the_chain_left_the_step_in`. A `done` the land tree refuses cancels nothing: the cancel file, the ended approvals and the `superseded` row are written only once the new head is taken (test `::test_a_done_the_land_tree_refuses_cancels_nothing_and_leaves_the_running_check`). Test `fichero-builder/tests/test_loop.py::test_a_newer_head_of_the_same_work_supersedes_a_batch_in_the_ladder_and_an_unrelated_one_is_refused`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_cancel_marker_for_the_ladders_head_kills_the_running_command`. **A not-READY review names its blocking group** (manager 2026-11-02): a grouped review file ends with the last group's verdict, so the alert quotes the first `[group n of m]` whose own closing line is `NOT READY`, never the file's last line. Test `fichero-builder/tests/test_work_verb.py::test_the_alert_names_the_group_that_blocked_not_the_files_last_line`. **Guard data** (manager 2026-11-02, lane-onboard -79): a guard reads an allowlist `.json` beside itself and the guards run from the PINNED tree, so a batch that changed the list could never pass. When the guards rung is red and the batch changed a `.json` under a check path, the alert is kind `guard-data` (actions approve|send-back, evidence the diff of those files); the manager's approve, bound to the head and the file names the alert quoted, sets `approve_guard_data`, and the guards then run with HEAD's copy of exactly those files laid over the pinned tree (`check_tool._scratch_tree(data_from_head=...)`, `builder check --guard-data FILE`); the guard scripts stay pinned and a file not named keeps the pinned copy. Tests `fichero-server/tests/unit/workflows/test_check_tool.py::test_an_approved_guard_data_file_is_head_s_copy_under_the_pinned_guard_and_nothing_else_is`, `fichero-builder/tests/test_loop.py::test_a_guard_data_alert_is_approved_by_file_name_and_binds_to_the_head`.
  **Auto send-back** (manager 2026-11-03: the alerts were almost always answered `send-back`): a `red`, `not-ready` or `refused` check on an EXTERNAL lane with a land tree is sent back by the loop itself: the findings file and the `builder done` command go to the lane's pane as for an alert, the step is `blocked` until the lane's next `builder done`, and one `queue` row `auto-send-back` says "sent back automatically (N of 3): <why>" (the console's feed shows it); no `alert` row. The cap is `AUTO_SEND_BACKS` = 3 a batch (`auto_sb` on the step, kept across `done`); the fourth red is the alert as before. Refusals that need a person (`needs-maintainer`, `weakened-tests`, `red-on-base`, `pinned-new`, `guard-data`) and a worker lane's own fix rounds are unchanged. Test: `fichero-builder/tests/test_loop.py::test_an_external_lanes_red_is_sent_back_by_the_loop_three_times_a_batch_then_it_is_an_alert`.
- `dev-workflows.run.jail-home` [PARTIAL] (#6116; manager 2026-11-03: sharing bb1 went red-on-base twice when the iMac runner was down and the tests ran as the jail user) — a rung that runs as the jailed user gets a scratch `HOME` made in the jail's workroot (`check-home-*`, removed after the rung as that user), and `Jail.argv` passes it as `HOME` when it is inside the workroot; any other `HOME` is dropped and the user's own is used as before. The scratch HOME carries a `.gitconfig` (`safe.directory = *`, committer Claude <noreply@anthropic.com>), because the jail user's real one is no longer read: without it git refused the owner-made check tree ('dubious ownership') and sharing bb1's ready rung counted no commits (found 2026-11-03); `lane_ready_check.sh` now fails with git's own error when it cannot find the merge base or count the commits. Tests: `fichero-builder/tests/test_jail_git.py`. **Bootstrap rule** (manager 2026-11-03): a jail-env change must be runnable by the ladder it ships in; the loop runs LIVE code from its own worktree, so such a change is put into that tree first (the lane's worktree moved to the batch's head, the loop drains and restarts) and the batch's ladder is then retried; the pinned copy of a script stays old for that run and its change goes through the maintainer approval as usual. The jail user's real `~/Library/Application Support/Fichero` is therefore never a test's home, and the real-state guard (#5530) cannot trip on a local fallback run. The runner-change retry is `run.remote-list`. Test: `fichero-builder/tests/test_jail_home.py`.
- `dev-workflows.run.swift-tests` [GAP] (#6116; owner 2026-11-03: planned, later, not now) — Swift tests in the ladder and in `builder verify-all`: `xcodebuild test` and the XCUITests are wanted LATER, not now. Today NO rung runs Swift tests: the ladder's `build` rung is `xcodebuild build` only (`[check].build`, one rung under the heavy lock) and `verify-all` is every guard, the engine suite and that same app build. Open: which scheme, a GUI session for XCUITest, the maintainer's running app (a test launch quits it). Nothing is built until the owner asks.
  Phase 0 amendment (owner 2026-11-17/18, from the cut `dev-workflows.run.swift-tests`): Swift unit and UI tests run per batch in a dedicated GUI user on the Studio, so a test run never quits the owner's app (with agent-profiles.ladder.swift-tests and ladder.ui-smoke).
- `dev-workflows.run.remote-list` [PARTIAL] (#6116; manager 2026-11-03, the iMac was offline and the Air came online) — `[check].remote` may be a LIST (`["imac:~/fichero-gate", "air:~/fichero-gate"]`; a string still works): the engine pytest runs and the remote guards go to the first runner that answers; a runner that fails (ssh 255, a full disk, a copy error) is one `alert` row naming it and the next one tried ("trying air:..."), and it is not tried or alerted again in that ladder; with every runner down the run is here, as before. A red that appears only because the runner changed (the first choice did not run it) is retried ONCE on a runner it did not run on (a down runner is probed with `ssh true` first); a green there counts, a red there leaves the first red; one `runner-retry` journal row says what happened and nothing is told to a lane about it; a runner is alerted once per ladder even when the retry pass finds it back and it fails again. The retry also applies to the red-on-base rung's expected reds, so with the first runner down that rung runs twice (and each dead runner costs up to 15 s of probing). Test: `fichero-builder/tests/test_remote_list.py`. Not yet: a real run over both machines. **One alert per outage** (speed batch 4, manager 2026-11-03: 40 'unreachable' alerts in a day, one per ladder, while the iMac was off): a runner's outage is kept in `<state>/runners-down.json` across ladders; only its first failure alerts, and the first run that reaches it again answers that alert `runner-back`, so the next outage alerts anew (test `fichero-builder/tests/test_remote_list.py::test_one_alert_per_outage_across_ladders_and_the_runner_back_answers_it`).
  Built 2026-11-06 (manager t86: the Pro sat at load 30 to 57 under the ladders while the owner's Xcode ran): `[check].remote_guards = "auto"` sends every guard whose source names no git, subprocess, swiftlint or xcodebuild (most of the 121 when written) to the first reachable runner in ONE ssh call, each guard with its own timeout and base dir, under no heavy lock there (behind a pytest run a guard would time out); the rest run on the Pro. A guard red on the runner is re-run on the Pro before it counts (a missing .git or tool there is the runner's, not the code's), and no reachable runner runs them all on the Pro. Tests: `fichero-server/tests/unit/workflows/test_check_tool.py::test_auto_remote_guards_go_in_one_batch_a_git_guard_stays_here_and_a_remote_red_counts_only_if_red_here`, `::test_the_remote_guard_batch_runs_every_guard_with_its_own_timeout_in_one_call_and_reports_each`.
- `dev-workflows.run.loop-survives` [PARTIAL] (#6116; manager 2026-11-03: the loop died on every ladder for half an hour) — one lane's exception never stops the loop: a chain that raises anything is that step's `error` result (a `loop` row `lane-error` with the traceback's tail, then the usual alert with the exception's name), and the tick's own work on a lane that raises is the same row, a line, and the other lanes still tick. The loop runs from its own detached tree (`--root`, `../builder-live`, made 2026-11-03 at origin/integration; the lane's branch checkout was behind the rules it read, so a list in `[check].remote` landed while the running code expected a string); after each landing that tree, when detached and clean, checks out origin/<branch> (a `loop` row `live-tree`; a branch is left). A dirty (hot-patched) tree still follows origin with its edits carried when origin's change leaves the patched files alone (the `live-tree` row names them as carried; manager 2026-11-07 21:37: left behind, the tree froze the rules data and a landed known-gaps entry stayed red in every presubmit); when origin changes a patched file it is left, a `live-tree-dirty` row naming the files, and a checkout git refuses is a `live-tree-refused` row and the re-exec for new code follows at the next quiet tick. Tests: `fichero-builder/tests/test_loop_survives.py::test_a_chain_that_raises_any_exception_is_an_error_alert_and_the_loop_goes_on`, `::test_a_lane_whose_tick_raises_is_a_row_and_the_other_lanes_still_tick`, `::test_the_loops_detached_clean_tree_follows_origin_and_a_branch_or_a_dirty_tree_is_left`. Not yet: rules read by the loop are still the live tree's own harness.toml, so a rules change and its code land together or not at all. **Never a chain on old code** (manager 2026-11-04: a landing added harness.toml keys, three chains started on the old code before the re-exec, blocked on 'unknown keys' and stayed blocked 35 minutes): when the tree moves, no new chain starts until the re-exec; and a loop that starts (a re-exec included) retries, once per head and with a `rules-retry` row, every step blocked by rules newer than the code that read them (`unknown keys`, `rules file refused`); a real red is never retried. Tests `fichero-builder/tests/test_loop_survives.py::test_a_step_blocked_by_rules_newer_than_its_code_is_retried_once_when_the_loop_starts_current`, `::test_the_loop_retries_rules_blocked_steps_when_it_starts`.
- `dev-workflows.run.auto-rules` [PARTIAL] (#6116; manager 2026-11-03, speed batch 1: 25 of 56 blocks in a day were approvals the rules decide) — named rule classes the ladder resolves without a person. Each is opted in by name in `[check].auto` (an unknown name refuses the rules file) and every decision is one `auto` journal row (rule, head, file, why) the manager audits. `red-on-base-trim-only`: a changed test file whose diff adds no check line (assert, raises, fail) and no new test function (a rename is as many `def test_` added as removed) owes no red on base; it still runs green on head, and a source change still owes a red from another test. `weakened-tests-of-a-deleted-module`, narrow on purpose (reviews -63, -65, -67 each found a way round a counting rule): a changed test file is not refused only when its head IS its base with whole top-level test functions removed, each of which called a module the same diff deletes (`m.<attr>`, with m bound by the file's own `import m`, `import a.b as m` or `from a.b import m`, and the full dotted path the import names equal to the deleted file's module path, repo-relative or under a `[check].python_path` root: a same-named module in another package, a relative import or a local variable of that name never matches, review -72), with the same imports bound to the same names except the deleted module's own (an `import mod` swapped for a mock is a change, review -70); a deleted test file only when every test in it called one. A cut inside a surviving test, any change to a class, a helper or a marker, or anything else is refused as before, for the manager (tests `::test_a_weakened_test_is_excused_only_when_every_lost_check_used_a_module_the_diff_deletes`, `::test_the_deleted_module_rule_refuses_every_change_but_whole_tests_removed`, `::test_the_ladder_excuses_a_deleted_modules_tests_only_when_the_rule_is_named_and_says_so_in_a_row`, `::test_the_deleted_module_rule_matches_the_full_module_path_never_a_same_named_one`). Tests: `fichero-server/tests/unit/workflows/test_check_tool.py::test_an_unknown_auto_rule_refuses_the_rules_file`, `::test_a_test_file_that_only_loses_checks_or_renames_a_test_is_trim_only_and_any_new_check_is_not`, `::test_the_auto_rules_are_off_unless_named_and_each_decision_is_a_journal_row`. `approval-carry-same-file-diffs` (owner via the manager 2026-11-03: approvals MORE automatic): an approve bound to the files it named (red-on-base, weakened tests, guard data; never maintainer or pinned-new) holds at the step's new head when each named file has the same diff from its base (one patch-id) at both heads, which covers commits only added elsewhere and a rebase whose range-diff of those files is empty; a named file whose diff changed, or no named file, never carries, the diffs are read in the lane's own land tree against its `origin/<branch>` (it holds both heads; the engine repo gets the new head only when the chain fetches it, after the carry: two misses on 2026-11-04, 'its diff could not be read at one head'), and an older approve that does not carry writes one `carry-declined` row with the reason (tests `fichero-builder/tests/test_auto_carry.py::test_an_older_approve_that_does_not_carry_says_why_in_a_row`, `::test_the_chain_carries_in_the_lanes_land_tree_not_a_repo_that_lacks_the_new_head`). `guard-data-added-routes`: a guard-data stop on a `*_known_gaps.json` keyed by routes resolves itself when the batch only ADDS entries (no key removed, no existing text changed), each added key is a route in `[check].routes_file` at head and each added reason names an issue (#N) or a step; the ladder then runs again with head's copy of exactly those files under the pinned guards; anything else still stops for the manager. `builder auto [--day] [--root DIR]` lists the day's decisions by rule (head, file, why) for the manager's audit, and every `spec-ok-proposed` row of any day whose spec line in the checkout still has an open tag (`landed.unfolded_proposals`: lane, landing sha, file, id, tests), so no proposed [OK] is lost (test `fichero-builder/tests/test_auto_carry.py::test_builder_auto_lists_the_spec_ok_proposals_no_batch_has_folded_in`). Tests: `fichero-builder/tests/test_auto_carry.py::test_an_approve_carries_to_added_commits_and_to_a_rebase_with_the_same_file_diff_and_never_otherwise`, `::test_the_days_auto_decisions_are_one_list_by_rule`, `fichero-builder/tests/test_work_verb.py::test_a_guard_data_stop_the_added_routes_rule_clears_runs_the_ladder_again_with_heads_copy`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_known_gaps_list_that_only_adds_engine_routes_with_an_issue_resolves_itself_and_anything_else_stops`. Still the manager's: a pinned check file changed on purpose, a new file under a pinned path, a red-on-base that is a real environment difference, and a known-gaps edit that rewords an entry (one that only removes entries from a `*_known_gaps.json`, `*_allowlist.json` or a pinned guard's allowlist literal is `allowlist-entries-only-removed`'s when that rule is named).
  **Tests-only** (manager throughput review 2026-11-24: 15 manager approvals, 5 of them on consecutive haiku-tests steps blocked 9, 88, 22, 28 and 12 min): `red-on-base-tests-only` owes no red on base to a batch whose every changed path (any status, a deletion or rename too) is a test file, a file in a `tests`/`Tests` directory or a Markdown file, with none under `[check].red_paths`: nothing but tests changed, so no red has anything to prove; every changed test still runs green on head, and one `auto` row names all of them. Code outside `red_paths` (`scripts/`, `pipeline/`) is source and keeps its red; with `red_paths` unset the rule never applies. The approve already resumes the ladder where it stopped (`REUSE`, `dev-workflows.run.loop-needs-maintainer`). Tests: `fichero-builder/tests/test_tests_only_auto.py::test_a_batch_of_only_tests_and_docs_owes_no_red`, `::test_source_anywhere_keeps_the_red_owed_scripts_and_pipeline_included`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_ladder_skips_the_red_for_a_tests_only_batch_names_every_test_in_the_row_and_keeps_it_for_scripts_source`.
  **Timeout-only** (manager 2026-11-05: batch-25 raised one test's time bound and red-on-base stopped twice for it): `red-on-base-timeout-only` excuses the red for a changed test file whose every changed line is a comment, a whole `@pytest.mark.timeout(...)` line, or the same line with only its timeout numbers changed, compared hunk by hunk in order with its indentation (review 106: a moved, reordered or re-indented assert is a changed line); a new file, or any other changed line (an assert, a call, an argument), keeps the red owed, and it never excuses a source change (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_test_file_whose_diff_touches_only_timeouts_or_comments_is_timeout_only_and_any_other_line_is_not`).
- `dev-workflows.run.presubmit` [PARTIAL] (#6116; manager 2026-11-03, speed batch 2: spec-guard, lint and trailer reds cost whole ladders) — `builder done` first runs the ready check, the PINNED `[check].ready` WITH its pinned guards over a scratch tree of the lane's sha with the owner's check files laid over it (as the ladder does; manager 2026-11-04: a lane that edits its own ready script must not pass its own presubmit) (`--no-guards` dropped: every fast guard, the spec guards among them, the lint ratchet, the git checks), about 2 minutes. The pinned copy is the running loop's own checkout (`<state>/live-root`, written when the loop starts), never the code `builder done` was run from. Red, or a lane tree the overlay refuses (a check path that is a symlink out: the ladder would refuse it too; the half-made scratch tree is removed), refuses the done with what it said, and nothing goes to the ladder; green, or a sha the lane's repo lacks, or no live root recorded, or live rules this code cannot read (a key newer than the lane's code: the ladder judges with the current code), lets it through, the skip said, never a traceback; `--no-presubmit` is the manager's skip. **Guard data** (manager 2026-11-04): a red under the pinned copy of guard DATA the batch itself changed (a `.json` under a check path, e.g. a known-gaps entry for a new route) is run again with head's copy of exactly those files, as the ladder's guard-data approve does; green then lets the done through with `would need the guard-data approve for <files>` (a `guard-data` row) and the ladder raises the approve as before; red then, or a red with no such file, still refuses. The script and guards are the owner's pinned copies; the lane's code under them still runs unjailed with the caller's environment: right when the lane runs its own `done`; the manager or the loop running `done` for a lane should pass `--no-presubmit` (review -70). One `presubmit` journal row each, a skip included. Tests: `fichero-builder/tests/test_presubmit.py::test_a_red_presubmit_refuses_the_done_and_a_green_one_lets_it_through`, `::test_a_lane_that_edits_its_own_ready_script_is_judged_by_the_pinned_one_and_no_presubmit_skips_on_purpose`, `::test_a_scratch_tree_refusal_refuses_the_done_and_leaves_no_worktree`, `::test_the_pinned_copy_is_the_live_loops_checkout_never_the_code_done_runs_from`, `::test_live_rules_newer_than_this_code_are_a_skip_said_never_a_traceback`, `::test_a_batch_whose_red_is_only_its_own_guard_data_passes_with_the_line_and_any_other_red_still_refuses`, `fichero-builder/tests/test_loop_survives.py::test_the_loop_records_its_own_checkout_as_the_live_root_when_it_starts`. Not yet: the lane's changed tests and a Swift build stay in the ladder.
- `dev-workflows.run.presubmit-lints` [PARTIAL] (#6116; manager 2026-11-04: of 64 NOT READY reviews in three days, about 40 were findings a text check catches in seconds) — each recurring review finding gets a lint that the presubmit runs (a `scripts/check_*.py` guard or a line of the ready script), under 5 s together, in this order: the trailer, duplicates, test citations, stale status, the acceptance diff, then the range-diff handed to the reviewer by the loop. **Built:** (1) the ready script refuses an agent commit with no `Written-By: <model>` trailer, the ONE trailer a commit carries, naming who wrote the code (owner 2026-11-05; a commit from before that ruling, or one already queued, may carry the old `Directed-By: the maintainer` instead, and no `Co-Authored-By:` is asked for, here, in the reviewer's checklist item 10 or by the policy hook, whose `[policy].trailer_one_of` takes either and whose `required_trailers` is empty), named per commit; the pipeline's own write-up commit, its coder brief's commit line, the loop's re-bake commit and `builder order` carry it too (test `pipeline/tests/test_checks.py::test_ready_check_fails_an_agent_commit_with_no_written_by_trailer_and_takes_the_new_or_the_old_one`); (2) `scripts/check_spec_no_duplicates.py`: a behaviour id defined twice in one spec file, or two long lines in one file that open with the same 150 characters (a copy that diverged later), fails with both line numbers, and a missing or empty specs dir fails too (never a clean read of nothing); the eight duplicates already in other lanes' specs when it landed are a known-debt list that only shrinks, reported, for the manager's groom batch (tests `fichero-server/tests/unit/scripts/test_check_spec_no_duplicates.py::test_a_behaviour_defined_twice_or_a_repeated_paragraph_fails_and_a_clean_spec_passes`, `::test_known_debt_is_reported_not_failed_and_a_fixed_entry_must_leave_the_list`, `::test_a_missing_or_empty_specs_dir_is_never_a_clean_read`). (3, 4; manager 2026-11-04) `scripts/check_spec_citations.py`: every spec bullet a batch TOUCHES (a line it adds, against the merge base with origin/integration) cites only files that exist (at the root, under a package dir, or the one tracked path that ends with it) and `::names` found in them; a line tagged `[GAP]` or saying "not yet written" or "(to write)" whose cited test exists is stale, and an `[OK]` bullet citing no existing test is refused (a `Not built:` note is fine). The rest of the specs is a debt count in `docs/contributor_manual/specs/_citation_debt.json` (339 missing files and 29 missing names when it landed) that only falls: more misses than the file says fail (a citation broke outside the batch's bullets), a file raised above its copy at the base fails, fewer print the number to lower it to; under a second (tests `fichero-server/tests/unit/scripts/test_check_spec_citations.py::test_an_old_miss_in_an_untouched_bullet_is_debt_but_a_miss_in_a_touched_bullet_fails`, `::test_a_stale_status_beside_an_existing_test_fails_and_an_ok_needs_a_test_but_a_not_built_note_is_fine`, `::test_the_debt_only_goes_down`, `::test_a_missing_specs_dir_is_never_a_clean_read`). (5; manager 2026-11-05, review 105: a batch built `builder build-check` while another bullet still said "Not yet" about it) a touched bullet's id, and the `builder <verb>` its opening clause is about, are no longer named by a Not yet / Not built sentence anywhere else in the same spec; its own bullet may still say what is left of it (test `fichero-server/tests/unit/scripts/test_check_spec_citations.py::test_a_not_yet_elsewhere_naming_a_behaviour_the_batch_builds_fails_but_its_own_remaining_part_and_other_verbs_do_not`, `::test_a_not_yet_naming_the_touched_bullets_id_fails_though_ids_hold_dots`). (6; manager 2026-11-04/05) `scripts/check_spec_acceptance.py`: a behaviour bullet that exists at the base keeps its acceptance text, the bullet with its status tag, the parenthetical after the tag (issues, who ruled, why), its issue numbers and cited paths taken out, cut at its first note (`Built`, `Not built`, `Was`, `Not yet`, any case, dated or not, and `Tests:`); any other change, or a deleted bullet, fails with the line unless a commit carries `Spec-change: <what and why, naming the owner's or the manager's ruling>`. Run over the 40 spec commits of 2026-11-04/05 it flags 6, every one a real rewrite (two of them this builder's own sentences inserted into acceptance text; moved under Built notes with that trailer) (tests `fichero-server/tests/unit/scripts/test_check_spec_acceptance.py::test_a_tag_an_issue_test_paths_and_appended_notes_are_free`, `::test_a_rewritten_or_deleted_acceptance_line_fails_and_a_spec_change_trailer_lets_it_through`, `::test_a_spec_change_trailer_with_no_ruling_named_is_not_enough`). (7; owner 2026-11-14) every mechanical red carries its exact fix as a `Fix:` line in the presubmit's refusal, `builder precheck` and the chain's alert or fix brief (`autofix.fix_hints`): a stale allowlist entry ('drop from the set') as the `sed` deleting exactly its lines, given only when the entry has lines of its own (else the plain ask); a `Spec-change:` acceptance red as the `git commit --amend --no-edit --trailer` command; a stale contract or embed list as the `[check].regen` lines and the commit (tests `fichero-builder/tests/test_autofix.py::test_a_missing_spec_change_trailer_and_a_stale_embed_list_each_carry_their_exact_command`, `::test_an_entry_sharing_a_line_with_other_code_gets_no_sed_only_the_plain_ask`, `::test_the_chains_red_alert_carries_the_fix_for_a_stale_entry_read_at_the_checked_head`). (8) (the manager's hand-run guards passed and the ladder bounced the batch twice): `builder precheck <worktree> [--head] [--pinned] [--root]` runs the ladder's own guard rungs (guards, contract-current, since-guards) with the pinned check files laid over a scratch tree of the worktree's head as the ladder lays them (each script finds the repo from its own file, so a pinned script run in place judges the pinned tree), the pinned copy being the one the ladder pins for the land branch's tip now; each red with its output and its `Fix:` line; unjailed, as the caller; one `precheck` row (test `fichero-builder/tests/test_autofix.py::test_precheck_runs_the_pinned_guards_over_the_head_and_a_stale_entry_red_carries_the_exact_one_line_fix`). **Not built:** the range-diff to the reviewer.
- `dev-workflows.quality.ratchets-held-exactly` [GAP] (#6391; owner 2026-11-07) — three kinds of debt each sit under a ratchet the guards rung runs on every check, held exactly (no tolerance), whose baseline may only shrink: (1) **SwiftLint** on SwiftLint's own `--baseline` (0.63.2): `scripts/swiftlint_warning_baseline.json` becomes the baseline file SwiftLint writes (`--write-baseline`), a change fails only on violations NEW against it, and a batch that lowers it commits the smaller file; the count ratchet `scripts/check_swiftlint_warning_ratchet.py` (today at a stale 123 while the tree holds 1,612 warnings and 1 error, and skipped by `harness.toml [check].guard_skip`) becomes the guard that runs SwiftLint with the baseline and refuses a grown baseline; no pbxproj surgery: the SwiftLint build phase (`CC0011223344556677889902`) is neutered, its script skipping or running `--lenient` in the Debug configuration, in one small reviewed batch after Monday, so the ratchet runs once, in the guards rung; the guard runs only on an item touching Swift or Python paths and is cached by tree hash; ONE baseline, regenerated on integration after merges, with an `--update-baseline` path for a sanctioned move (SwiftLint's baseline matches file, rule and text, so a moved file reads as new); `line_length` (1,456 of the 1,612) is NOT a hand burn-down: first `.swiftlint.yml` gets `ignores_comments`, `ignores_urls` and `ignores_function_declarations` and its warning limit is reviewed, the noisy rules go (`todo`; `file_length` on generated and contract files), then ONE swift-format reformat commit listed in `.git-blame-ignore-revs`, then the baseline is rebased; the Monday fix of the one error is lane-onboard's `RecipeSetupStore` split, its fallback a `type_body_length` error limit of about 400, kept apart from the lint work; (2) **ruff** the same way: per-rule counts in a small committed JSON (`scripts/ruff_baseline.json`), a change fails on a count above the baseline for any rule (per file where the rule is per file), and the baseline only shrinks; (3) **compiler warnings** counted FIRST, by rule and by file, from the build rung run with `xcodebuild -resultBundlePath` and read with `xcrun xcresulttool` (1,600 against 140 a week earlier is probably one category), the count committed as `scripts/compiler_warning_baseline.json`, which only shrinks; (4) the **hang ratchet** (`scripts/check_hang_ratchet.py`, #4550: hang count, total stall, worst hang against a committed baseline, over the owner's reproducible session trace) armed in verify-all with the trace recorded by the Monday build's session, not left NOT ARMED; (5) **console and log error signatures**: the log watcher's dedupe (#6369, #6370: repeating errors by signature, one issue each, cap 10 a day) feeds a ratchet on the number of DISTINCT signatures per run of the app, against a committed baseline that only shrinks. Acceptance: a change adding one SwiftLint violation is red with the file and rule named and one fixing a violation is green with the baseline file smaller; the same for ruff per (file, rule); a build log with one more `warning:` line than the baseline reds the check naming the category; `guard_skip` naming any `check_*_ratchet.py` fails the guard-skip lint (`check_guard_skip_has_no_ratchet.py`, to write); a raised baseline in a batch is refused by the guard that reads it.
- `dev-workflows.quality.slow-path-ratchet` [GAP] (#6391; owner 2026-11-07: a ratchet for slow things in the logs, when there are errors or when things slow down) — one STANDARD SCRIPTED RUN (the app's smoke scenario `LibrarySmokeUITests` on a known fixture library, and the engine's `fichero-server/scripts/bench_reading.py --pages 20` on the same library) is run by the quality lane on a schedule and after a landing that touches the engine or the app, and its logs are counted per OPERATION: the engine's slow-path lines (operation name, duration, the threshold it passed) and the app's hang and signpost events (`LaunchProfile`, `InteractionProfile`, the Instruments trace the hang ratchet reads). The ratchet holds, per operation, the count of slow events and the p95 duration against a committed baseline (`scripts/slow_path_baseline.json`, keyed by operation name and by scenario): a NEW slow operation, a higher count or a worse p95 is red naming the operation and both figures; the baseline may only fall (held exactly, like the others; a legitimate move is an `--update-baseline` commit saying why). Errors in the same run are counted by signature by the signature ratchet above. **What exists today, reused:** the engine's per-page Kraken line `kraken page <name>: load Xs segment Xs recognise Xs total Xs | priority=.. qos=.. threads=..` (`llm/kraken_runtime.py:990`, what `bench_reading.py` already parses), the cloud-batch slow-path lines (`slow path: a batch to <provider> has waited past twelve hours`, `… cost $X, over its estimate`, `remote_read/cloud_batch.py:202,234`), DuckDB's busy evidence (`DuckDB spilled N MiB to disk for …`, `DuckDB holds N MiB of old row versions …`, `engine RSS reached N GiB …`, `db/busy_evidence.py:109-166`), the per-rung `activity` rows' seconds, the app's `LaunchProfile.milestone` lines and signposts, `InteractionProfile.begin/end` signposts on a sidebar click, and the hang ratchet's three figures (`scripts/check_hang_ratchet.py`) over the recorded trace. **What the first worker must add:** (1) one engine line shape for every slow operation, `slow path: <operation> took <s>s, over <threshold>s | <detail>`, written by the lane runner for a job over its kind's threshold (`execution/jobs.py` `_run`, thresholds from `KINDS`), by the API for a request over 1 s (one middleware line naming the route), and by the existing sites above as they are (their words are kept; the parser knows both); (2) the app's hang and signpost events exported as text at the end of the smoke run (`xcrun xctrace export` of the `.pointsOfInterest` and `potential-hangs` tables, the same export the hang ratchet reads); (3) the guard (`check_slow_path_ratchet.py` under scripts/, to write) that parses both logs, counts per operation and compares to the baseline; (4) the smoke run on the fixture library wired into verify-all's engine part and the quality lane's schedule. Acceptance (with a fake log, no app and no engine): a fixture engine log holding three `kraken page` lines at 8, 9 and 31 s and two `slow path: read-a-line took 42s, over 30s` lines, and a fixture trace export holding two `potential-hangs` rows and four `InteractionProfile` intervals, parses to a table keyed by operation (`kraken page`, `read-a-line`, `hang`, `sidebar-click`) with count and p95; against a baseline with `read-a-line: {count: 1, p95: 35}` the guard is red naming `read-a-line`, count 2 against 1 and p95 42 against 35; against one with `count: 2, p95: 45` it is green and prints the smaller p95 to lower the file to; a line for an operation absent from the baseline is red as "new slow operation: <name>"; a baseline raised in a batch is refused; the same fixture with a `--scenario` name keys the table by scenario so the smoke run and the bench run never compare with each other.
- `dev-workflows.quality.workers-one-category-per-batch` [GAP] (#6391) — three standing workers, one per kind, on cheap models (`[models].quality = { provider = "claude-code", model = "sonnet" }`; Haiku where the fix is mechanical), each batch ONE thing: one lint category in one package (30 to 50 fixes, programmatic first: `swiftlint --fix` and `ruff --fix` on the brief's RULE ALLOWLIST of syntactic rules only, Xcode fix-its where safe, a codemod for a repeated deprecation; anything touching MainActor, a force-unwrap or a rename is a reviewed hand fix, never auto-fixed), or one slow path (the worst offender by the hang ratchet, the launch budgets of `engine-startup-lifecycle.md` section H, or the engine's slow-path timings, with a before and after number in the batch's text), or one error signature (the watcher's top signature by count); the batch lowers its ratchet's baseline in the same commit, with a cap of one batch in flight per worker and a batch size the brief states; review stays Opus as today until the model bake-off (#6379's ledger decides). Acceptance: a quality batch's diff touches one category or one signature and its baseline file; a batch that touches two categories is sent back by a presubmit lint naming them; the slowdown batch's text carries the before and after figure and the check compares the after against the ratchet; the worker's brief names the batch size and the cap.
- `dev-workflows.quality.reserved-slot` [GAP] (#6391; manager 2026-11-07) — the stream holds one of the two lane slots (`[loop].lanes = 2`): the `quality` lane is always schedulable and a feature lane never takes its slot, so the stream never stalls behind features; it still obeys the heavy lock, the Pro's hold and the machine pool (Steps 2.18 and 2.19) like any lane. Acceptance: with two feature lanes waiting and the quality lane queued, the loop's next pick is the quality lane; with the quality lane idle both slots go to features; the reservation is one line in `[loop]` (`reserved = ["quality"]`) and the loop refuses a rules file that reserves more slots than it has.
- `dev-workflows.quality.baseline-falls-every-batch` [GAP] (#6391; owner 2026-11-07: the goal is to STEADILY LOWER the baseline, not freeze it) — after the cheap config changes and the one reformat, every quality batch lowers its ratchet's baseline, and the stream's weekly target is written here and read by the digest: SwiftLint warnings down by at least 150 a week and ruff by at least 40 a week until each is under 100, compiler warnings down by a tenth of the count a week until under 50, the hang ratchet's worst hang and total stall never up, distinct console error signatures down by one a week until zero; a week that misses its target is one line in the digest naming the stream and the gap, never an alert. The daily digest reports every baseline: SwiftLint by severity and by rule, ruff by rule, compiler warnings by category, the hang figures, the slow-path table's worst three operations by p95, and the signature count, each with its change since the day before. Acceptance: a quality batch whose baseline is equal to or above the one before is refused by the guard; the digest's quality block holds the five baselines with their deltas; a week under target prints the one line. *Decided here:* 150 and 40 a week, because the first config and reformat batches take the bulk at once and 30 to 50 fixes a batch at one batch a day holds the rest; the owner may set other figures.
- `dev-workflows.ladder.landed-elsewhere-detected` [GAP] (#6202; the Opus review of 2026-10-26, "an approval path"; the brief 2026-11-08: check adopt for work landed elsewhere) — before the presubmit's red-on-base and the land step's fast-forward refusal, the ladder compares each commit of the lane's range with what landed on `origin/<[land].branch>` since the lane's base by `git patch-id` (and, for a rebased or squashed landing, by the set of files and hunks the range changes against the landed diff): a commit whose patch is already on the base is "landed elsewhere as <sha>" and the step is not reworked for it; a range whose every commit is already landed raises one alert with the `adopt` action in place of a send-back. Acceptance: a fixture lane whose one commit was cherry-picked onto the base under another sha gets the alert with the landed sha named and no rework; a range with one landed and one new commit presubmits the new one alone and says which was landed; a plain fast-forward range is unchanged.
- `dev-workflows.ladder.adopt-landed-elsewhere` [GAP] (#6202) — `adopt` is an alert action beside approve, send-back, retry and park, and a verb `builder adopt <step> --sha <landed sha>` for the maintainer's own hand (patch-id equal, or the maintainer names the sha and the row says a person did): the step moves to `landed` with "landed elsewhere as <sha>", the item's issues are closed or left open with the residue named exactly as a landing does (`tool.landed`'s `left_open`), one `adopt` row names who, the step, the landed sha and the lane's own sha, and the lane's worktree is swept as after a landing. No check is faked: an adopted step has no check row of its own and the journal says so. Acceptance: `adopt` on the fixture alert lands the step, writes the row and closes the issue; a `--sha` that is not on the base is refused in words; the step's `landed` row carries `adopted: true` and the console shows it as a landing with that word.
- `dev-workflows.ladder.approve-is-fingerprinted` [PARTIAL] (#6202; built in Step 2.14: `[check].auto` has `approval-carry-same-file-diffs` and an approve of a red test binds to the test files it names (`check_tool.red`, `approve_red` as a tuple); left: the fingerprint for the other two trip causes) — an approve binds to a fingerprint of what it approved so a later edit trips again: weakened tests and red-on-base, per test file named and per kind, to that file's blob at the head's merge base with the land branch AND at the head (a base that changed the file never matches; the binding survives a newer `builder done`, which ends only the head's own approvals, and a binding that no longer matches is dropped), an acceptance rewrite to a hash of the changed acceptance lines, guard data to the hash of the data file; `run_all` skips a cause whose fingerprint still matches and refuses to carry one whose fingerprint changed; a bypass-file or `.claude/` trip is never approved by any of these. Acceptance: an approve of a weakened test carries to the next presubmit while the test file's blob is unchanged and trips again when it changes; an approve of a `.claude/` trip is refused. Built 2026-11-14 (a red-on-base approve was lost at every new head though the test file never changed): the alert's approve records `approved_test_blobs` (each .py file a red-on-base or weakened-tests alert named: its blob at the merge base and at the head the alert judged, and the approve's kind), which a newer `builder done` keeps; `queue.content_approvals` gives the chain each kind's approval as exactly the files whose two blobs still match at a later head (one `auto` row `approve-same-test-content`) and drops a binding that no longer matches, and the ladder's weakened-tests approve excuses only the files it names (test `::test_a_weakened_tests_approve_never_rides_a_head_whose_base_changed_the_file_and_never_covers_a_file_it_did_not_name`); a `.claude/` trip stays a refusal under every approve (a maintainer's approve excuses only a pinned check file's change). Test `fichero-builder/tests/test_loop.py::test_a_red_on_base_approve_is_bound_to_the_test_files_blob_and_holds_at_every_later_head_while_it_is_unchanged`. Not yet: the acceptance-rewrite hash.
- `dev-workflows.ladder.auto-pass-classes` [PARTIAL] (#6202 item 5; built in Step 2.14 as `[check].auto` rule classes: `red-on-base-trim-only`, `red-on-base-timeout-only`, `weakened-tests-of-a-deleted-module`, `approval-carry-same-file-diffs`, `guard-data-added-routes`; left: the four classes below) — four more named classes, each deterministic on the diff and journalled by name like the others: `allowlist-entries-only-removed` (judged against the PINNED copy, never the lane's merge base: a `*_known_gaps.json` or `*_allowlist.json` whose entries are only removed, every kept entry identical, none added; or a pinned guard whose top-level allowlist literal, named KNOWN, ALLOW or EXEMPT, only lost entries, every other statement identical; a ratchet's baseline never qualifies, its missing key reads as a first run: the guard is stricter, so it is no pinned-file refusal and the ladder judges with head's copy of exactly that file); `allowlist-line-moved` (the same value, and the old line's text identical at the new line in HEAD); `spec-lines-only-appended` (every old token survives in order, or a tag flip, or an added `(#N)`); `tests-not-weakened` (no `test_*` name removed without a same-file replacement, the assert count not lower, the skip count not higher, judged per file, never net across files). Acceptance: a fixture diff of each kind passes by its class name in the journal; the same diff with the one disallowed change (an added gap, a changed value, a dropped token, a removed test name) trips as today. Built 2026-11-14: `allowlist-entries-only-removed` (`autofix.allowlist_only_removed`, `check_tool.stricter_files`: one `auto` row per file; the ladder, the presubmit and `builder precheck` lay head's copy of exactly those files over the pinned ones) (tests `fichero-builder/tests/test_autofix.py::test_allowlist_only_removed_is_entries_dropped_from_a_named_literal_and_nothing_else`, `::test_a_pinned_guard_edit_that_is_not_only_removed_entries_is_still_judged_by_the_pinned_copy`, `::test_a_ratchet_baseline_json_or_a_reworded_entry_is_never_only_removed`, `::test_a_lane_copy_of_a_guard_older_than_the_pinned_one_never_replaces_it`); only the ladder writes the row. `[check].regen` with no `[check].python` refuses the rules file (test `::test_regen_without_a_python_is_refused_in_the_rules`). Not yet: `allowlist-line-moved`, `spec-lines-only-appended`, `tests-not-weakened`.
- `dev-workflows.bakeoff.held-until-the-cap` [GAP] (#6380; owner 2026-11-07, manager 2026-11-08) — the model bake-off is a measured plan (`agent-work/status/briefs/bakeoff-plan-2026-11-08.md`, the measured form of the manager's draft) and nothing in it runs until the owner confirms the OpenRouter cap; the plan's parts run in cost order (frozen ground truth and the replay selection at no cost, our usage from the ledger, the Claude tiers on the Max login, the open models on OpenRouter last with a 50 USD stop, Stage 2 only under its own cap), every run one heavy job behind the heavy lock. Acceptance: no bake-off row appears in the ledger before a `bakeoff-start` journal row the manager writes on the owner's word; a run started without it is refused by the brief's first line.
- `dev-workflows.bakeoff.public-data-only` [GAP] (#6380; owner's data rule) — a third-party run (any provider but the Max login) receives only the brief, the spec step and the public tree: every item is checked before the first call against the land boundary's own list (no corpus data, no key, no pair link, no private path, no `user_manual` private directory) and an item that fails is dropped from the third-party parts, not scrubbed. Acceptance: a fixture item whose diff carries a home path is dropped with the reason on its row; the nine trial items pass the check.
- `dev-workflows.ladder.all-cheap-reds-in-one-pass` [PARTIAL] (#6589; manager 2026-11-24 throughput review, item 6: 14 of 58 check reds were a later rung failing after the worker fixed an earlier one, and a green ladder took 13.4 min because the iMac pytest, the guards and the build ran in a row) — a red `ready`, `guards`, `contract-current` or `since-guards` rung does not end the ladder: the other rungs of that set still run, no other rung runs after a red, and a red rung outside the set ends it at once. The ladder row's `failed` is the first red and `also_failed` lists the other cheap reds; the fix brief names every red rung and carries each one's words. Red-on-base's head-green run goes at once with its base runs, each tree shipped to its own gate dir; the head run takes the first runner and the base runs take the runners after it (`_runners_for_base`), so with two runners they run on different machines at once; with one runner they wait on its heavy lock. Acceptance: a batch with a red ready check and a red guard gets one fix brief naming both. Test: `fichero-builder/tests/test_ladder_all_reds.py`, `::test_the_head_run_and_the_base_runs_start_on_different_runners_at_the_same_time`. Not built: the green ladder's measured wall time.
- `dev-workflows.queue.adopt-only-a-matching-session` [PARTIAL] (#6589; throughput review 2026-11-24 item 7) — the queue adopts a running session only when its step and head match what the lane recorded at send (`session_step`, `session_head`) and the lane tree's HEAD is the recorded `session_head` or a commit after it (read with `safe.directory=*`); a refused session gets an `adopt-refused` journal row. The work rebase runs `rebase -q --autostash` and returns a message naming the kept stash when the unstaged changes conflict with the new base. A mechanical alert is retried once per lane and step by the loop (`auto-retry` row); a second one goes to a person, and `builder queue landed --lane --step --sha` records a landing. Acceptance: a session whose step differs from the lane's recorded step is not adopted and the journal carries `adopt-refused`. Test: `fichero-builder/tests/test_adopt_sessions.py`.
- `dev-workflows.bakeoff.frozen-ground-truth` [GAP] (#6380) — before any run, each item carries a human-checked defect list with the test or check that proves each defect, plus six reviewer controls (three clean landed diffs, three with one seeded defect named in a sealed file); a reviewer is scored by precision and recall against that list and by its false-READY rate on the controls, never by agreement with another model's verdict. Acceptance: a reviewer that answers READY to everything scores recall 0 and false-READY 3 of 3 on the seeded controls.
- `dev-workflows.bakeoff.replay-corpus` [GAP] (#6380; owner's idea) — landed batches with a spec step are replayed: the parent checked out, the model given only the spec step and the brief, the result scored by the landed commit's own tests and the pinned checks; each item records its spec version and base sha and a result is reused only when both match (`never rerun a model pass`). Acceptance: a replay of a landed batch whose tests are red on the parent and green on the landed commit scores the model's commit by those same tests; an item whose spec changed since is run anew, the old result kept and marked stale.
- `dev-workflows.bakeoff.decision-table` [GAP] (#6380) — the deliverable is one table from the ledger: each builder and reviewer combination's cost per typical and heavy day priced every way (`ledger.break-even-view`), its quality bar (READY after one round, defects missed, false-READY on controls) and the break-even per plan, then a recommendation with the sample-size caveat; adoption goes only through `ledger.comparison-view`'s rule (lands clean at least as often at under a third of the cost per landed batch, five units or more) and `[models]` changes only by the owner's hand. Acceptance: the table has one row per combination run and no row for a model not run; the recommendation names the caveat; `[models]` is unchanged by anything in the step.
- `dev-workflows.console.abandoned-after-six-hours` [PARTIAL] (#6467) — a check or build whose start has no end row after `STALE_HOURS` (6 hours) reads "abandoned" (no end row: the process died), never "running"; and the Lanes card lists the lanes that are moving first, then those that need the owner, then the rest (`LANE_ORDER` in `console.html`). Test: `fichero-builder/tests/test_status_page.py` (`test_a_start_with_no_end_for_a_day_is_abandoned_not_running`; the lane order has none). Not seen in the console by eye.
- `dev-workflows.console.why-waiting-and-last-landing` [GAP] (#6388) — the desktop console's Lanes card says, per lane, what is running now (the step, its rung and how long it has run), why a waiting lane waits (the journal `queue` row's `detail`, in its words: "waiting for a chain worker (2 ahead)", the heavy lock's holder, a blocked presubmit's first red line), the last landing of that lane (sha, time, issue) and the last review verdict; a Recent events card tails the last 30 journal rows in one line each (time, lane, event, detail cut to one line) from the SSE tail the page already has; every build and check row links its log file by the `builder` route that serves it read-only (`GET /api/log/<id>`, the journal row's log path resolved under the state dir only, never a path from the request). Acceptance: a fixture journal with a lane in `waiting-for-worker` shows that lane's row with the detail text; a `check` row with a log path gives a link that serves the file; a request for a path outside the state dir is refused 404.
- `dev-workflows.console.phone-layout` [GAP] (#6388) — one page, two layouts: below 700 px (a CSS media query in `console.html`, no second page) the cards stack in the phone's order: open alerts first (the finding or the diff's first lines, the lane and the age), then lanes and their state, the queue and what is ahead of each item, machine tiles (load, free memory, the spawn cap from `budget.machine`), today's landings, and cost so far today (the spend figure `GET /api/status` already carries; the per-role digest when `ledger.daily-digest-per-role-and-model` lands). Acceptance: the page at 390 px wide shows those six cards in that order with no horizontal scroll (a headless render in the test, or the DOM order asserted from the served HTML and its CSS rule); at 1200 px the desktop layout is unchanged.
- `dev-workflows.console.tailnet-read-only` [GAP] (#6388; owner: watch from the phone; manager 2026-11-08: the phone READS, it never writes or answers) — the console stays bound to 127.0.0.1 by default; `[console].tailnet = true` (off unless set, documented in AGENTS.md) makes `builder status` print the one `tailscale serve --bg <port>` line that proxies the loopback port to the tailnet as HTTPS (tailnet-only; `funnel` is refused by name if it ever appears in the setting, and the server never binds a non-loopback address itself). A request that arrives through the proxy is recognised by its non-loopback Host or the `Tailscale-User-Login` header the proxy adds; such a request gets the page and the GET routes only, and every POST (an alert answer, a lane action, a queue add, a done) is refused 403 with "read-only from the tailnet" and one `console` row naming the login and the verb refused; the identity header must equal `[console].owner_login` or the GET is refused too, so a tailnet guest sees nothing. The served page hides the action buttons when it was served read-only. Acceptance: with `tailnet` unset, nothing is printed and a non-loopback Host is refused as today; with it set, a GET with `Tailscale-User-Login: <owner>` and the tailnet Host gets the page with no action buttons, a POST with the same headers is 403 with a `console` row, and a GET with another login is 403; `funnel` in the setting is refused at startup.
- `dev-workflows.console.nothing-private-in-the-page` [GAP] (#6388) — the page and every JSON route it reads pass the ledger's strip pass (`ledger.one-row-per-unit`): no API key or token pattern, no absolute home path (shown relative to the worktree or the state dir), no pair link (the `pair` URLs the lanes exchange); the console's own page token is the exception and is never sent to a tailnet request (the read-only page is served with an empty token). Acceptance: a fixture journal with a home path, a `sk-` key and a pair link in its rows renders a page and `/api/status` body in which none of the three appears; the read-only page's HTML carries no token.
- `dev-workflows.review.no-new-apis-rule` [GAP] (#6389; owner standing rule, restated by the manager 2026-11-07: do not invent APIs, iterate never replace, search what exists by what it does) — the review checklist (`docs/contributor_manual/review-checklist.md`) gains one rule (the issue numbers it 9; today's checklist already has eleven, so it lands as rule 13, after "Performance and Security lenses" (rule 12, Step 2.29), with the same words): an item that adds an engine route, a registry action or a schema type is NOT READY unless its commit message or its spec bullet names the existing routes, actions or schemas it searched, by capability, and says why none of them fits; the reviewer checks that claim against the TREE (does the named existing route do the thing?) and a claim that names nothing, or names something that plainly fits, is a finding. Extending an existing route or action (a field, a parameter, a new verb on the same path) is not an addition. Acceptance: a fixture diff that adds `GET /api/foo` with a commit body naming no searched route is NOT READY with the rule cited; the same diff with "searched GET /api/activity and /api/jobs: both list jobs, neither returns a per-lane total" is read against the tree, and READY when the claim holds.
- `dev-workflows.review.ponytail-lens` [GAP] (#6389; manager 2026-11-08) — the review prompt (`harness_review.py`) carries, under the CHECKLIST, one named check "Over-engineering (the ponytail lens)": does the diff reinvent the stdlib or code already in the tree, add a speculative abstraction (an interface with one implementation, a factory for one product, config for a value that never changes), or add a dependency for what a few lines do; each finding is listed under the checklist's findings like any other, named by file and line with what replaces it. The lens is text pasted into the prompt, not a tool: no MCP exists for it and none is added. Acceptance: the rendered prompt contains the named check; a fixture diff that adds a helper duplicating `shutil.copytree` draws a finding naming the stdlib call; the prompt still ends with the one READY or NOT READY line.
- `dev-workflows.review.performance-lens` [OK] (#6600; owner 2026-11-14: every batch on every lane is checked for speed, memory and disk, app and engine alike, so the app gets a little faster with each landing and an old failure never comes back unnoticed) — the review prompt (`harness_review.py`) carries, under the CHECKLIST beside the ponytail lens, one named check "Performance (speed, memory, disk)" with the things this codebase has already paid for, in two lists the reviewer reads the diff against. **App (Swift, macOS and iOS):** a `body` that observes a whole store where it reads one field (an `@Observable` object passed whole into a row, an `@EnvironmentObject` read in a leaf, a `.onChange` or `.task` whose dependency is the store itself), a `GeometryReader` or an `id:` that changes on every pass, an `onAppear` that fetches on each appearance, work on the main actor that waits on the engine or decodes an image (the sidebar re-render of #6547 and the entity freeze of #4975 are the named precedents), a full-size `NSImage`/`UIImage` decoded where a `CGImageSource` thumbnail at the view's pixel size does, an `NSCache` without `countLimit`/`totalCostLimit` or a dictionary cache that only grows, a `Task` started per row, a sort or filter in `body`. **Engine (Python, `fichero-server`):** a query inside a loop where one `IN` or a join does (the query-count ratchet in `fichero-server/tests/conftest.py` holds each endpoint's count exactly, #4443: a batch that raises a count is already red, and the lens names the N+1 the number hides), a whole table read where a page does, a model (Kraken, spaCy, an MLX or embedding model) loaded inside a request or a job step instead of the runtime's held instance, a second `duckdb.connect` or a `DuckDBSession` made per request instead of the engine's, bytes copied twice (a `read()` then a `bytes()` of it, a `PIL.Image` copied to `numpy` and back), a file written to a scratch or cache path with no removal and no cap, a log or cache that grows without a size or count cap, a `time.sleep` poll where an event or a callback exists, a `subprocess` per item where one call takes a list. A finding is listed under the checklist's findings like any other, by `file:line`, with the cheaper way named (the API, the pattern, or the existing instance to reuse); one that predates the batch (the diff touched a line beside it) is not NOT READY but a `Performance - <area>` issue the reviewer's text names, filed by the sweep stream (`quality.perf-security-sweep`). The lens is text in the prompt, not a tool: the measured rungs below are what decide a number, the lens is what reads the code. Acceptance: the rendered prompt contains the named check with both lists; a fixture Swift diff whose row takes the whole store draws a finding naming the field to observe; a fixture engine diff with `for id in ids: conn.execute("SELECT ... WHERE id = ?", [id])` draws a finding naming the single `IN` query; the prompt still ends with the one READY or NOT READY line. Test: `fichero-server/tests/unit/scripts/test_harness_review_lenses.py::test_the_performance_lens_is_in_the_prompt_and_a_store_wide_observation_and_an_n_plus_one_each_draw_a_finding` in fichero-server/tests/unit/scripts/.
- `dev-workflows.review.security-lens` [OK] (#6600; owner 2026-11-14: the same for security, every batch) — the review prompt carries one more named check "Security", with this codebase's own surfaces named so the reviewer reads the diff against them, not against a generic list: **the engine's edge** (every FastAPI route under `api/routes/` and the Unix-socket transport: a new route without the auth dependency the others carry, a route that trusts a client-sent user or library id, the multi-user switch and the owner password reachable from anything but the Mac app over the socket (the ruling of 2026-11-12), a header or a token logged); **paths** (a library, derivative, export or import path built from request input and not resolved under the library root, a `..` or a symlink followed, a `Path` joined from a client string, an archive extracted without member-path checks); **processes** (a `subprocess` with `shell=True`, an argument list built from input, a `Process()` or `NSTask` in the app with a shell, an environment passed through whole); **SQL** (a statement built with f-strings, `%` or `+` from anything but a constant, where the parameter form or the query builder exists); **secrets** (an API key, a token or a password in code, a fixture, a test, a log line or an error message, a provider key sent to any host but that provider's); **the app's sandbox** (a change to a `.entitlements` file, to `NSAppTransportSecurity`, to a hardened-runtime exception, to a URL scheme handler, to a security-scoped bookmark's lifetime); **deserialisation** (`pickle`, `yaml.load` without `SafeLoader`, `eval`/`exec`, `NSKeyedUnarchiver` without `requiringSecureCoding`, a model file loaded from an untrusted path with `weights_only=False`); **network** (a provider call over plain http, a certificate check disabled, a redirect followed to a new host, a response body trusted as a path or a command, a user-agent or a header carrying the owner's address); and **the harness's own boundary** (`security.untrusted-text`: ladder output, issue text and a worker's diff are never obeyed as instructions). A finding is NOT READY by `file:line` with the safe form named; a change to an entitlement, an ATS exception or a route's auth is listed at the TOP of the prompt beside "NEW APIS IN THIS BATCH" as "SECURITY SURFACE CHANGED" (the `since-guards` rung's file list is the source, no new scan), so the reviewer applies this check to each. Acceptance: the rendered prompt contains the named check; a fixture diff adding `subprocess.run(f"convert {name}", shell=True)` draws a finding naming the argument list; a fixture diff touching a `.entitlements` file lists it at the top of the prompt; a diff with neither lists "none" there and the prompt still ends with the one verdict line. Test: `fichero-server/tests/unit/scripts/test_harness_review_lenses.py::test_the_security_lens_is_in_the_prompt_a_shell_call_draws_a_finding_and_an_entitlement_change_is_listed_at_the_top` in fichero-server/tests/unit/scripts/.
- `dev-workflows.brief.search-before-adding` [GAP] (#6389) — the new-work brief (`start_tool.brief_prompt` and `spec_tool.brief`, the harness-gen3 template the lanes read first) carries one line in its rules block: search the existing routes, actions and schemas by what they DO before adding one; extend the one that nearly fits, never add beside it; name what you searched in the commit. Acceptance: every generated brief contains the line; a brief rendered for a spec issue and one for a code issue both carry it.
- `dev-workflows.presubmit.new-api-note` [GAP] (#6389) — `builder done` prints a NEW API note for the batch: every route the OpenAPI route set gains (the operation-set diff `check_openapi_route_set_current.py` already computes, head against base), every registry action added and every schema type added in the batch's diff, one line each (method and path, or the action or type name, and the file); the same list goes at the TOP of the review prompt (`harness_review.py`, above CHECKLIST, as "NEW APIS IN THIS BATCH" or "none") so the reviewer sees them at a glance and applies `review.no-new-apis-rule` to each. Report only: the note never blocks; the review decides. Acceptance: a fixture batch adding one route and one action prints two lines in the note and the same two at the top of the prompt; a batch with no new API prints "none" in both; the note's lines carry no home path.
- `dev-workflows.quality.first-batches-from-the-reviewed-sources` [GAP] (#6391) — the sources were read on 2026-11-07 (harness-builder, integration 24f5fd9947 against e3ae6f2503 a week before) and the first batches are fixed from them, in this order: **SwiftLint** 1,612 warnings and 1 error (1,204 and 0 a week before; the growth is `line_length`, 983 to 1,456; `cyclomatic_complexity` 15 and `function_body_length` 30 are flat): batch 1 the `type_body_length` error on `Models/RecipeSetupStore.swift` (371 lines against 350) and the baseline written; batches 2 onward `line_length` by package, the six files that grew most first (`Services/AddressChoiceModel` +18, `Models/SharingFailurePrompt` +15, `Services/PairingSequence` +15, `Views/Onboarding/Stages/CompareReadersView` +13, `Models/CompareViewModel` +9, `SharingStageSection` +9), then `cyclomatic_complexity`, then `function_body_length`. **ruff** 509 (538 a week before): F811 381, of which the test fixture re-import pattern (`from tests.unit.recipes.test_x import mac  # fixture`, then the name as a parameter) accounts for the test dirs (`tests/unit/recipes` 131, `security` 101, `transport` 54, `jobs` 35, `workflows` 32, `api` 8): batch 1 is a RULING, not fixes: a `[lint.per-file-ignores]` of F811 for `**/tests/**` in `ruff.toml` (the pattern is pytest's own fixture import, not a defect) and the baseline written from what remains; then F401 38 and F841 27 by package. **Compiler warnings**: counted at the first batch from the newest `build-<sha>.log` and written as the baseline (no figure yet; the owner's last Xcode build showed about 1,600 issues of every kind). **Slowdowns**: the first offenders are section H of `engine-startup-lifecycle.md` (#6371: engine 17 s to first health, serial library loads, the sidebar built about 25 times, the FocusedValue warning) and the hang ratchet's worst hang once the trace is recorded. **Console and log errors**: the first signatures are the owner's console of 2026-11-06 (#6375: `connect(...) Connection refused errno 61` from six callers before the engine listens, `HTTPClientError.remoteConnectionClosed` on the health probe, `FocusedValue update tried to update multiple times per frame` ×4), each one batch. Acceptance: the first SwiftLint batch lands with zero errors and the baseline file present and the guard in the guards rung; the ruff ruling lands with F811 at 0 outside tests and the baseline present; the compiler-warning baseline is committed with the count the log gave; the stream's first slowdown and signature batches cite the issue they close.
- `dev-workflows.quality.never-weakens-a-gate` [GAP] (#6391) — no quality batch weakens a gate: a ratchet baseline that grows, a rule disabled in `.swiftlint.yml` or `ruff.toml`, with ONE sanctioned exception, Step 2.20's first config batch, ruled here and named in each file's comment: in `.swiftlint.yml` the `line_length` ignores (`ignores_comments`, `ignores_urls`, `ignores_function_declarations`) and its reviewed limit, `todo` off, and `file_length` off for generated and contract files; in `ruff.toml` the F811 per-file-ignore for `**/tests/**`; the presubmit lets those lines through when the batch's message cites this bullet, and refuses every later disable (manager 2026-11-07), a `noqa` or `swiftlint:disable` added without the rule's violation fixed, or a `guard_skip` entry for a ratchet, is refused by the presubmit with the line named; a ratchet is held exactly, and a legitimate move (a SwiftLint version change) is an `--update-baseline` commit saying why. Acceptance: a batch adding `// swiftlint:disable line_length` without a fix is red naming the line; one adding `# noqa: F401` likewise; one raising any baseline is red; one disabling a rule in either config is red unless it is the one sanctioned config batch above citing this bullet; a second batch disabling any rule is red.
- `dev-workflows.quality.bug-review-stream` [GAP] (#6391; owner 2026-11-07, the fourth stream; #6389 the ponytail lens) — automated module-by-module bug reviews file deduped issues, update the spec, and Sonnet fixes a group of related ones per batch. Built on what exists and nothing else: **the reviewer** is `scripts/harness_review.py`'s restricted reviewer (`claude -p --restricted`, Read, Grep and Glob only, no MCP, an empty owner-only cwd) pointed at ONE module's files instead of a diff, its lens `docs/contributor_manual/review-checklist.md` plus the module's spec bullets and the ponytail lens of #6389; each finding names `file:line`, the spec bullet it breaks (or "no bullet", a spec gap), and a test that would fail. **Filing** goes through the log watcher's filer (`builder watch`, #6369): its dedupe key (one issue per distinct finding, with a count) and its caps (at most 3 issues a pass and 10 a day, the rest into one rolling issue); a bug review is one more source for that filer, not a second filer. **Placing:** `builder triage --move N --to <milestone>` puts each issue in its spec's milestone with a reason comment, and `builder steps` / `builder milestone` puts it under a build step, so related issues group into one batch. **Fixing:** the stream's lane takes one group per batch, tests to the spec first (red on base), the normal ladder and an Opus review; where the code was right and the spec wrong the spec line is changed with a `Spec-change` trailer. **Order:** one module per pass in a fixed rotation named here: `fichero-server/src/fichero_server/recipes/`, `execution/jobs.py` and `execution/throttle.py`, `api/routes/ingest/`, `llm/kraken_runtime.py`, then the app's `Views/Onboarding/`, `Views/Sidebar/`, `Services/`, `Models/`, then round again; the FIRST pass is a single module (`recipes/`, the most churn this month) as a trial after the Monday build, and the measure is findings per module, how many held up under the Opus review, and how many fixes landed. Acceptance: a pass over one module writes at most 3 new issues and one rolling issue, each finding with `file:line`, a bullet or "no bullet" and a failing test named; a second pass over the same module with nothing changed files nothing new and raises the counts; each issue sits in its spec's milestone with the reason comment and under a step; the trial's three figures are in the digest.
  Phase 0 amendment (owner 2026-11-17/18, from the cut `dev-workflows.quality.bug-review-stream`): run when a milestone's last step lands and before any release, never per step: a model other than the builder reads the milestone's changes together for faults between steps; each finding is an issue with a failing test owed.
- `dev-workflows.quality.perf-method` [OK] (#6600; owner 2026-11-14: proper tools, not ad-hoc timers; the standing rule: adopt tools, never write our own) — one method for every measured figure the `perf` rung and the sweep produce, and it is `scripts/perf_trial.py`'s, already written down and tested (`fichero-server/tests/unit/scripts/test_perf_trial.py`), reused as the decider and extended with the new measurement kinds rather than copied: the FIRST run is cold and discarded; the figure is the MEDIAN of the runs that follow (three a batch, five a night); the thermal state (`thermal_state`, read from `ProcessInfo` in the app and `pmset -g therm` on the runner) and whether the machine was idle are recorded, and a run under `fair` or worse is VOID, neither pass nor fail; runs that disagree by more than a tenth of their median are INCONCLUSIVE and re-run once, never best-of; a result with no machine model, no thermal state or too few runs is REFUSED (a gate that cannot read its input fails, it never passes quietly). Every figure is keyed by `machine.model` (the M4's, the Air's and the iMac's figures never compare with each other) and by scenario (as `slow-path-ratchet` keys by scenario). Tolerances are STATED per measure, in the baseline file beside the figure, not in code: wall time and CPU time 5% (pytest-benchmark's `--benchmark-compare-fail=median:5%` and XCTest's per-metric "max deviation" are the same rule in the two tools), peak RSS 3%, body-evaluation counts, hang count, leak count and the disk left behind EXACTLY (zero tolerance, like the other ratchets); a baseline may only fall, and a better median is printed as the figure to lower the file to (`baseline-falls-every-batch`). **Where it runs:** on `[check].build_remote` or the first `[check].remote` runner that declares the capability (`pool.machines-declare-capabilities`; the app measures need `xcode` and a GUI session, the engine measures need `python`), never on the manager's Mac (`pool.hold-holds-one-machine`), behind the heavy lock (one measurement at a time: two concurrent runs are noise). **Budget (per batch, wall, on the M4):** the engine perf rung and the security rung together under 6 minutes and the app perf rung under 5, each timed out at twice that and a timeout one `alert` row naming the rung, never a red; a batch whose diff touches no path under `fichero-server/`, `fichero-cli/`, `fichero-mcp/` or `pipeline/` skips the engine rung and one touching none under `fichero/` skips the app rung, each as a "not required" row like `red-on-base`'s; a docs-only batch runs neither. A rung's alert (a report-only red, a timeout, an unreachable runner) is a queue-shaped row the console can answer: id `harness-rung-<name>-<n>`, lane `harness`, step `rung-<name>`, `what`, action `dismiss`; while one with the same text is open the same rung adds no other (#6589, 2026-11-15: 69 id-less rows sat on the console that no answer could reach; rows with no id are never listed as open; test `fichero-builder/tests/test_alerts_clear.py::test_a_rung_alert_has_an_id_says_itself_once_and_dismisses`). **Nightly** (the quality lane's schedule, after `check.daily_builds`): the five-run form of every figure, the full Instruments templates and memray, which are too slow for a batch, and the release-size ratchet (`scripts/release_size_baseline.json`, which already holds the app binary, the bundle and the DMG) read from the daily build. Acceptance (`perf_trial.py`, no machine): a results file with one cold and three warm runs under `nominal` and idle passes against a baseline within tolerance; the same with the cold run included in the median is REFUSED by shape; `fair` is VOID; runs at 100, 100 and 130 ms are INCONCLUSIVE; a file for `Mac16,10` is never compared to a baseline keyed `Mac14,2`; a tolerance missing from the baseline file is REFUSED naming the measure. Test: `fichero-server/tests/unit/scripts/test_perf_trial.py::test_the_rung_s_measures_follow_the_trial_method_cold_discarded_median_thermal_void_keyed_by_machine_and_tolerance_from_the_file`. Built: the decider and `scripts/perf_baseline.json` (tolerances, no figures yet: they are written from real runs on the M4). Open: the budget is not yet measured, and the nightly form is not wired.
- `dev-workflows.quality.perf-rung-engine` [PARTIAL] (#6600) — the ladder gains a `perf` rung after `build` (`RUNGS` in `check_tool.py`; a measurement runs on code that compiles) whose engine half runs ONE standard engine run under three industry tools and compares the figures to `scripts/perf_baseline.json` by `perf-method`. **The run:** `fichero-server/tests/perf/` under **pytest-benchmark** (`pytest fichero-server/tests/perf -p pytest_benchmark --benchmark-json=<out> --benchmark-compare=<baseline> --benchmark-compare-fail=median:5% --benchmark-warmup=on --benchmark-min-rounds=3`; the seven perf tests there, the cold start, the dense page, the document pipeline, the entity list and detail, the hundred-page recipe run and the editor's edit-undo, become its benchmarks with their method unchanged, and a new hot path gets a benchmark beside them, never a timer in a test), with the whole pytest process under **pyinstrument** for the time profile (`pyinstrument -r json -o <out>.json --` the pytest line: in-process, statistical, no root; py-spy is NOT used for the rung because attaching on macOS needs root and the runner has none, it stays a hand tool for a live hang) and under `/usr/bin/time -l` for the **peak RSS** (`maximum resident set size`, the honest zero-overhead peak; **memray** `run --native` then `stats --json` is the nightly form, since its allocation tracking slows the run a third and sees the DuckDB and numpy allocations tracemalloc misses, and tracemalloc, stdlib, stays where tests already use it: `test_engine_memory.py`, `test_remove_background_memory_6384.py`). **The figures held:** per benchmark the median wall time (pytest-benchmark's own compare is the judge, its JSON the record), the process's peak RSS, the top ten self-time frames from pyinstrument (a new frame in the top ten that is ours, not a library's, is a finding printed with the rung, not a red: it names what to look at), the **DuckDB figures** the engine already logs (`db/busy_evidence.py`'s spill MiB and old-row-version MiB, read from the run's log), and the **disk left behind**: `du -sk` of the scratch library, the engine's cache dir, its log dir and the models dir before and after, the delta held exactly (a run that leaves files behind is a leak; the fixture library's own growth is subtracted by the run's declared outputs). The **query-count ratchet** (#4443, per endpoint, exact) already runs in the pytest rung and is named here as the N+1 measure: it is not duplicated. **Red** names the benchmark or measure, the baseline figure and the measured one, and the machine; green prints every figure that fell. The engine's standard reading run (`bench_reading.py --pages 20`, the `slow-path-ratchet`'s run) stays post-landing and nightly as #6391 says: it is minutes of Kraken on its own and does not fit a batch. Acceptance (fixtures, no engine): a pytest-benchmark JSON with one benchmark 8% over its baseline median is red naming the test, both medians and `Mac16,10`; one 4% over is green; a `time -l` output with a peak RSS 5% over is red; a `du` pair whose delta is 40 KiB with no declared output is red naming the directory; a pyinstrument JSON whose top ten gains a frame under `fichero_server/` prints a finding line and stays green; a raised baseline in the batch's diff is refused (`ratchets-held-exactly`). Test: `test_perf_rung.py::test_the_engine_half_reads_benchmark_rss_disk_and_profile_and_reds_only_a_worse_figure` and `test_the_rung_skips_unconfigured_unrequired_and_runnerless_batches_and_stays_green_while_report_only` in fichero-builder/tests/. Built: the readers, the rung in `RUNGS`, `scripts/perf_engine_run.py`, `[check.perf]` (report-only). Open: the seven perf tests are not converted to pytest-benchmark (they run about 50 minutes, over the budget), and the rung has not run on the M4. **Added 2026-11-23 (#6600, owner: profile every batch):** the run also records `written_kib` (the net growth in KiB of the watched directories, `du`, not block-output operations), and the report says each figure's change against the base in % (`change: <scenario>: v vs base b (+x%)`, or `no base yet`); a perf run that could not measure (REFUSED, not run, no PERF-RESULT line, exit != 0) is red even while report-only, which forgives a slow number and never a missing one; the reviewer's performance lens names RAM, disk and time risks in the diff. Tests: `test_perf_rung.py::test_the_result_carries_bytes_written_and_says_each_figures_change_against_the_base_in_percent`, `test_a_perf_run_that_could_not_measure_is_red_even_report_only_but_a_slow_number_is_not`, `test_perf_sweep.py::test_the_performance_lens_names_ram_disk_and_time_risks_in_the_diff`.
- `dev-workflows.quality.perf-rung-runs` [PARTIAL] (#6589, #6600) — the perf rung actually runs. Acceptance: with `[check].remote_python` empty the perf argv starts with the gate venv's python (`<gate dir>/venv/bin/python`, the one `_gate_python` default the other remote rungs share), never the system `python3`; `pytest-benchmark==5.3.1` and `pyinstrument==5.1.3` are pinned in the server's `dev` extra and installed into the gate venv by `scripts/install_security_tools.sh`; a run whose baseline has no figures WRITES them (`scripts/perf_engine_run.py` stores them in the baseline file, the rung prints `recorded (report-only…)` lines to commit) and does not fail. Test: `test_perf_rung.py::test_perf_argv_uses_the_gate_venv_python_when_remote_python_is_empty` and `test_perf_rung.py::test_a_run_with_no_baseline_figures_records_them_and_does_not_fail`. Open: the gate venv has not been refreshed on the M4.
- `dev-workflows.quality.perf-remote-crash` [PARTIAL] (#6589, #6600) — an unreachable runner and a remote crash are two rows: `_remote_build` returns None only when ssh or the sync fails ("not run: the build runner is unreachable"); a perf run that exits non-zero there returns a row carrying its stderr tail ("not run: the perf run crashed on <host> (exit N): <stderr>"), never "unreachable". Test: `test_perf_rung.py::test_a_remote_crash_is_a_not_run_row_with_its_stderr_never_unreachable`.
- `dev-workflows.quality.rung-not-run-is-truthful` [PARTIAL] (#6589, #6600) — a rung that was skipped, REFUSED or could not run is "not run" on the ladder and the console (a `not_run` flag on the rung row and its `activity` event; the console pill reads "not run", never green). Test: `test_perf_rung.py::test_a_refused_or_skipped_rung_is_not_run_never_green`. Not built (#6658 #6659): `check_swiftlint_warning_ratchet.py` (no `swiftlint` binary, plain and `--since`) and `check_engine_imports_bundled.py` (no staged `app_packages`) now print `not run: ...` and exit 0, but a guard's `not run:` line does not yet set the rung's `not_run` flag, so on a runner without swiftlint a `--since` check reads green with only that line in its output; `preflight-embedded-engine.sh` checks the staged directory itself and still fails on a missing bundle. Tests: `test_check_swiftlint_warning_ratchet.py::TestGoingBlind::test_swiftlint_missing_from_path_is_a_not_run_row`, `test_check_engine_imports_bundled.py::test_an_absent_bundle_is_a_not_run_row`.
- `dev-workflows.quality.security-pins-installed` [PARTIAL] (#6589, #6600) — the bandit, semgrep and gitleaks pins in `harness.toml [check.security]` are written by `scripts/install_security_tools.sh --write-pins` on the M4 from the versions it confirms (never typed by hand); until that run the pins are empty and the rung says REFUSED and "not run". Built 2026-11-15 on the M4: `--write-pins` wrote bandit 1.9.4, semgrep 1.185.0, gitleaks 8.30.1 and osv-scanner 2.7.1. The security rung runs on `[check].build_remote` through `_remote_build` (never on the manager's Mac): the remote command puts `[check.security].path` (default `/opt/homebrew/bin` and `~/.local/bin`, set in code) on PATH (a leading `~/` expands to the runner's `$HOME`) (the runner's ssh PATH is only the system dirs), runs `scripts/install_security_tools.sh --check`, then the scan over the batch's tree shipped with its `.git`; an unreachable runner or none configured is the not-run row with the reason. Test: `fichero-builder/tests/test_security_rung.py`. Open: the iMac has no scanners installed, so a security rung that runs there refuses.
- `dev-workflows.quality.perf-rung-app` [GAP] (#6600; owner 2026-11-14: the SwiftUI views that re-rendered thirty times must not come back) — the `perf` rung's app half runs ONE XCTest performance plan, `FicheroPerfTests`, on the build machine's GUI session (`m4-smoke-needs-a-gui-session`: the console user is another user; this half waits on `run.swift-tests`, Step 2.8, for the scheme and the session, and until that lands it runs nightly only), with **XCTest's own metrics and baselines** as the ratchet: each test is a `measure(metrics: [XCTClockMetric(), XCTCPUMetric(), XCTMemoryMetric(), XCTStorageMetric(), XCTOSSignpostMetric(subsystem: "app.fichero.fichero", category: "LaunchProfile", name: "launch")])` block around one scripted action (launch to the first library row, a sidebar click, opening the Reader on a 20-page document, the Library grid's first scroll, the Activity table with 200 rows), the baselines are Xcode's `.xcbaseline` plists committed beside the test target with their per-metric max deviation (5% time and CPU, 3% memory, exact storage), and `xcodebuild test -only-testing:FicheroPerfTests -resultBundlePath <out>.xcresult` fails the test itself when a metric exceeds its baseline, so the rung reads the xcresult (`xcrun xcresulttool get test-results summary`) and writes no judge of its own. The signposts are the ones that exist (`LaunchProfile.swift`'s and `InteractionProfile.swift`'s `OSSignposter` intervals; `LaunchPerformanceUITests.swift` already measures the launch with `XCTOSSignpostMetric`, and is the pattern), and a new hot path gets a signpost interval, not a timer. **Body-evaluation counts** for the named hot views (`ContentView`, `SidebarView`, the Activity row, the Reader page view, the Library grid cell) come from the counter that exists, `RenderDiagnostics.BodyCount` (`FICHERO_PRINT_CHANGES=1`, which logs one line per run-loop turn under the `BodyCount` category): the test launches the app with that environment and the rung reads the counts from the unified log (`log show --style json --predicate 'subsystem == "app.fichero.fichero" AND category == "BodyCount"' --start <t0>`), sums them per view per action, and holds them EXACTLY against `scripts/body_count_baseline.json` keyed by view and action, by `perf-method`; a view evaluated more often than its baseline is red naming the view, the action and both counts (the sidebar's thirty re-renders of #6547 are what this catches). **Nightly** (not a batch: minutes each) the quality lane records the same scripted actions under Instruments through `xcrun xctrace record --template '<T>' --launch -- <app path> --env FICHERO_PRINT_CHANGES=1 --output <out>.trace` for `Time Profiler`, `Allocations`, `Leaks`, `Hangs` and `SwiftUI`, exports the tables with `xcrun xctrace export --input <out>.trace --xpath '/trace-toc/run/data/table[@schema="<schema>"]'` (`potential-hangs` is what `scripts/check_hang_ratchet.py` already reads and holds, count, total and worst stall, and that script is the hang judge unchanged; `leaks` holds at zero, no baseline; `allocations` persistent bytes at the end of the scenario held to 3%; the SwiftUI template's view-body table cross-checks `BodyCount`), and `xcodebuild analyze` is NOT used for performance: it is the clang analyzer and sees no Swift. Acceptance (fixtures, no Xcode): an xcresult summary with one failed perf metric is red naming the test and the metric; a log export with `SidebarView` at 31 against a baseline of 4 for `sidebar-click` is red naming all three; a trace export with one `leaks` row is red; a `potential-hangs` export runs through the hang ratchet unchanged; a batch touching nothing under `fichero/` prints "not required". Test (to write): `test_perf_rung.py::test_the_app_half_reads_xcresult_metrics_body_counts_and_the_nightly_trace_tables` in fichero-builder/tests/. **Interim, built 2026-11-23 (#6600):** `perf()` also runs a Swift half when a changed path is under `fichero/` and `[check.perf].swift_test` is set (it is left unset in `harness.toml` until `run.swift-tests` gives the build remote a GUI session for the ssh user, because a UI test with no session exits non-zero and that is red even report-only; the candidate is `FicheroUITests/LaunchPerformanceUITests`): the test runs under `/usr/bin/time -l` on `[check].build_remote`, recording wall seconds and peak memory in one `Swift perf:` line; a non-zero exit or no readable figure is red. The reported peak memory is the largest process `/usr/bin/time` waited on (the build tool or the runner, not the app) and the seconds include any incremental build; the app's own figures come from the xcresult metrics above. With no `swift_test`, which is the state today, the row says "Swift perf: no workload yet (#6600)" and one alert is journalled per day. Tests: `test_perf_rung.py::test_a_swift_only_batch_runs_the_app_perf_test_on_the_remote_and_reports_time_and_memory`, `test_a_swift_batch_with_no_swift_test_says_no_workload_yet_and_alerts_once_a_day`, `test_an_engine_and_swift_batch_runs_both_halves`.
- `dev-workflows.quality.security-scan-rung` [PARTIAL] (#6600; owner 2026-11-14: every batch is checked for security issues in the code) — the ladder gains a `security` rung beside `guards` (same lock, same runner, same remote form as `remote_guards = "auto"`: no git, no build), which runs five existing scanners over the batch and reports ONLY what is new against the base, each scanner by its own diff or baseline feature, never a wrapper of ours. **Python (`fichero-server/src`, `fichero-cli/src`, `fichero-mcp/src`, `fichero-builder/`, `scripts/`):** `bandit -r <dirs> -f json -o <out> -b scripts/bandit_baseline.json --severity-level medium --confidence-level medium` (bandit's own `-b` baseline: only findings absent from the baseline are reported); `semgrep scan --config p/python --config p/secrets --config .semgrep/ --baseline-commit <since> --json -o <out> --metrics=off <dirs>` (semgrep's own `--baseline-commit`: only findings introduced by the range). **Swift (`fichero/`):** `semgrep scan --config p/swift --config .semgrep/ --baseline-commit <since> --json --metrics=off fichero/` (the repo rules under `.semgrep/` hold what the generic sets lack and the security lens names: `Process()` with a shell, `NSAllowsArbitraryLoads`, `NSKeyedUnarchiver` without secure coding, a path joined from a client string); `xcodebuild analyze` is not run: the clang analyzer analyses C and Objective-C only, and the Swift compiler's own warnings are already the compiler-warning ratchet of Step 2.20. **Dependencies:** `osv-scanner scan --lockfile fichero-server/uv.lock --lockfile fichero/fichero.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved --lockfile fichero/fichero-api-client/Package.resolved --config osv-scanner.toml --format json --output <out>` (one tool for both ecosystems; `pip-audit`, which the release doc already names, stays the release-time cross-check over `uv export --format requirements-txt`, since it does not read `uv.lock`). **Secrets:** `gitleaks git --log-opts="<since>..<head>" --redact --report-format json --report-path <out> --baseline-path scripts/gitleaks_baseline.json` over the batch's own commits, messages included (the land step's public-boundary grep stays as the last line, since it also catches home paths and pair links). The rung's output is one table, scanner, rule, severity, `file:line` (redacted for gitleaks), and the same table goes into the review prompt under "SECURITY SCAN" so the lens reads the code the scanner pointed at. Any scanner missing on the runner is REFUSED by name (never a quiet green, rule 0), and a run over the budget in `perf-method` is an `alert`, not a red. None of the five is installed on the Mac today (checked 2026-11-14: only `swiftlint` is on the PATH; `pip-audit` appears once in a release doc, `py-spy` and `tracemalloc` in tests and design notes, `xctrace` in the hang ratchet), so the first batch of the step installs them on the runner by brew and uv (`brew install semgrep gitleaks osv-scanner`, `uv tool install bandit pip-audit`) and pins each version in `harness.toml [check.security]` with the rung refusing a version it did not pin. Acceptance (fixtures, no scanner binaries: the JSON outputs are the fixtures): a bandit JSON with one `B602` not in the baseline is red naming the file and line; the same finding present in the baseline is green; a semgrep JSON of a baseline-commit run with one `ERROR` is red; an osv-scanner JSON with one vulnerability of CVSS 8 is red naming the package and the id; a gitleaks JSON with one finding is red with the secret redacted; a runner without `semgrep` prints REFUSED naming it; the table in the prompt matches the rung's table. Test: `test_security_rung.py::test_each_scanner_s_new_findings_red_the_rung_a_baselined_one_does_not_and_a_missing_scanner_refuses` and `test_the_rung_skips_unconfigured_and_unrequired_batches_and_stays_green_while_report_only` in fichero-builder/tests/, and `test_the_security_rung_s_table_is_in_the_prompt_under_security_scan_exactly_as_the_rung_made_it` in fichero-server/tests/unit/scripts/test_harness_review_lenses.py. Built: the readers, the rung, `scripts/security_scan_run.py`, `scripts/install_security_tools.sh`, `[check.security]` (report-only, pins empty). Open: osv stays off until lane deps-security clears the Dependabot alerts. Was (2026-11-16, #6589): the rung now runs on `[check].build_remote` through `_remote_build`, never on the manager's Mac, and unlike `remote_guards = "auto"` it ships git: the batch's head is pushed to a persistent bare repo `security.git` on the runner (only the objects it lacks travel, no clone a run, done before the build lock) and checked out as a worktree in its own `security-tree` folder (the build rung's tree is untouched), under the scan's own `[check.security].timeout_s`, so semgrep `--baseline-commit` and gitleaks read history; the "no git" and "runs in the scratch tree (the remote form is open)" wording above is superseded. Built: the remote form, with `[check.security].path` (default `/opt/homebrew/bin`, `~/.local/bin`); tests `test_the_security_tree_on_the_runner_holds_the_history_and_a_second_run_pushes_without_cloning` and `test_the_security_scan_times_out_at_its_own_budget_not_the_build_timeout`.
  Phase 0 amendment (owner 2026-11-17/18, from the cut `dev-workflows.quality.security-scan-rung`): the security rung enforces after one clean week; the perf rung stays report-only until budgets and noise bands exist, and the report says so on every run.
- `dev-workflows.quality.scan-thresholds-and-waivers` [PARTIAL] (#6600) — what counts, and how a false positive is set aside, in writing, for every scanner in `security-scan-rung`. **Thresholds, red:** bandit HIGH severity at MEDIUM confidence or better; semgrep `ERROR`; osv-scanner any advisory with CVSS 7.0 or above, or any in CISA's known-exploited list however scored, or any with a fix version available for a direct dependency; gitleaks any finding (a secret is never tolerated by severity). **Reported, not red:** bandit MEDIUM and semgrep `WARNING` go into the rung's table and the review prompt for the lens to judge, and into one rolling `Security - scan noise` issue through the watcher's filer with its dedupe and caps (`bug-review-stream`'s filer, one more source); osv-scanner advisories under 7.0 with no fix are the same rolling issue's lines until a fix exists. **Waivers** use each tool's own mechanism, never a wrapper file of ours, and every waiver carries a written reason and an issue number, or the presubmit refuses the batch: bandit `# nosec B602 -- <reason> (#N)` (a bare `# nosec` is refused by a presubmit lint, `presubmit-lints`), semgrep `// nosemgrep: <rule-id> -- <reason> (#N)` or `# nosemgrep: ...`, osv-scanner an `[[IgnoredVulns]]` entry in `osv-scanner.toml` with `id`, `reason` and `ignoreUntil` no more than 90 days out, gitleaks an `[allowlist]` entry in `.gitleaks.toml` by `regexes` or `paths` with a `description` carrying the reason, never a whole-file stop. **Baselines** (`scripts/bandit_baseline.json`, `scripts/gitleaks_baseline.json`, and semgrep's baseline is the base commit itself) are the repo's known-finding files, like `check_*_known_gaps.json` and `swiftlint_warning_baseline.json`: held exactly, may only shrink (`ratchets-held-exactly`), a raised one refused in a batch, and the count of in-code waivers per tool is itself a ratchet in the same files (a batch that adds a waiver without removing one is red unless the waiver names an issue labelled `security-waiver-approved`, which only the owner or the manager applies). The first run over the whole tree writes the two baselines (`bandit ... -o scripts/bandit_baseline.json` and `gitleaks git --report-path scripts/gitleaks_baseline.json` from the root commit) in their own batch, each finding in them a line in a `Security - <area>` issue the sweep works down. Acceptance: a `# nosec` with no reason is refused by the presubmit naming the line; one with a reason and `(#1234)` passes; a bandit baseline with more entries than on base is refused; a diff adding a third `nosemgrep` with two on base and no approved issue is red; an `[[IgnoredVulns]]` with `ignoreUntil` 200 days out is refused; a MEDIUM bandit finding is in the table and the prompt and the rung is green. Test: `fichero-builder/tests/test_security_rung.py::test_thresholds_red_what_they_say_and_every_waiver_carries_a_reason_an_issue_and_a_held_count`, and `test_the_waiver_lints_judge_a_real_diff`, `test_a_third_nosemgrep_is_red_unless_its_issue_is_approved`, `test_a_raised_baseline_is_red_and_a_shrunk_one_is_not` (a real git repo) in fichero-builder/tests/. Open: the two baselines are not written (the scanners are not installed), and the lints run in the rung, report-only, not yet as a presubmit lint.
- `dev-workflows.quality.perf-security-sweep` [GAP] (#6600; owner 2026-11-14: this is how the baselines move down and how what the batch rungs cannot see gets found) — the fifth stream, built exactly as `bug-review-stream` (Step 2.23) is and sharing its parts: **one module per pass**, in the rotation the bug stream names (`recipes/`, `execution/jobs.py` and `throttle.py`, `api/routes/ingest/`, `llm/kraken_runtime.py`, then the app's `Views/Onboarding/`, `Views/Sidebar/`, `Services/`, `Models/`, and `api/routes/` whole and `db/` added for security, then round again), nightly on a build machine behind the heavy lock, never a batch. **Profiling the module:** for an engine module the perf tests and the standard reading run that reach it, under pyinstrument (`-r html` for the reviewer, `-r json` for the record) and `memray run --native` with `memray flamegraph` and `memray stats --json`, plus `semgrep` and `bandit` over the module WITHOUT a baseline (everything, old and new, since the sweep is where the old gets worked down); for an app module the Instruments templates of `perf-rung-app`'s nightly form over the scripted actions that show those views, exported per table. **Reviewing it:** the restricted reviewer of `harness_review.py` in its `--module <dir>` mode (the bug stream's), its lens the two lenses of this issue plus the module's spec bullets, given the profile's top frames, the allocation table and the scanner table as files in its read-only tree; each finding names `file:line`, the figure that shows it (a frame's self time, a persistent allocation, a scanner rule) and the test or benchmark that would hold the fix. **Filing** goes through the watcher's filer (`builder watch`, #6369: one issue per distinct finding with a count, at most 3 issues a pass and 10 a day, the rest into one rolling issue) into the `Performance - <area>` and `Security - <area>` buckets (`[triage.labels]`), placed by `builder triage --move` and `builder steps` under the module's spec step so related ones group into one batch; **fixing** is the quality lane's, one group per batch with a benchmark or body-count baseline that falls, the normal ladder, an Opus review, and the lowered baseline committed in the same batch (`baseline-falls-every-batch`). The measure in the digest, as for the bug stream: findings per module, how many held up under review, how many fixes landed, and the sum of baseline figures lowered that week. Acceptance (a fake profiler, scanner and reviewer): a pass over one module writes at most 3 new issues and one rolling issue, each with `file:line`, a figure and a test or benchmark named, in a `Performance - *` or `Security - *` bucket under a step; a second pass over the unchanged module files nothing new and raises the counts; the three figures and the lowered sum are in the digest. Test (to write): `test_perf_security_sweep.py::test_a_pass_profiles_scans_reviews_and_files_deduped_issues_in_the_two_buckets_and_the_digest_counts_them` in fichero-builder/tests/.
- `dev-workflows.pool.machines-declare-capabilities` [GAP] (#6356; owner 2026-11-05) — the `[machines]` table (today `ssh`, `dir`, `min_free_gb`, read by `builder measure` and `builder install`; `run.measure`) is the one declaration of the pool: each machine, the Pro included as `pro`, declares `tags` (what it can run: `pytest`, `guards`, `swift-build`, `xcode-tests`, `dmg`, `gpu`, `models`, `public`), `ram_gb`, `cores`, `min_free_gb` and `hours` (`any` or `overnight`, the M4 Air's owner rule). `[check].remote`, `[check].remote_guards` and `[check].remote_min_free_gb` keep working as they are and are read as the pool's declaration when no machine has tags, so the rules file changes by one table and nothing stops. `builder machines` lists each machine with its tags and its live state (reachable, free GiB, load, its heavy lock's holder and for how long, held by the owner), the same data the console's machine tiles show (#6357's plan, §3). Acceptance: a rules file with `[machines].m1air = { ssh = "air", dir = "~/fichero-gate", tags = ["pytest", "guards", "swift-build"], ram_gb = 8, cores = 8, min_free_gb = 6 }` loads; one with an unknown tag refuses with the tag named; one with no tags anywhere places as `run.remote-list` does today; `builder machines` prints one line per machine with its state, and a `machines` journal row. Extends `run.remote-list` and `run.measure`'s `[machines]`; replaces nothing.
- `dev-workflows.pool.placement-and-fallback` [GAP] (#6356) — every rung names the tags it needs (the pytest rungs `pytest`; the guards rung `guards`; the build rung `swift-build`; `run.swift-tests` `xcode-tests`; `builder build --dev` `dmg`, which stays on ONE machine and never splits; a rung that touches private data never goes to a machine tagged `public` only, and a hosted runner is tagged `public` and nothing else). Before sending, the ladder reads each candidate's state (one `ssh true`, free disk at or above its `min_free_gb` and the 6 GiB floor, its heavy lock free, its `hours` now) and places the rung on the first machine, in declared order, whose tags fit and whose state allows, preferring the one with the least load when two fit; a machine that is merely busy, full or out of hours is skipped with one `placement` journal row and no alert, and is looked at again on the next rung; an unreachable one is one alert per ladder, as today. With no fitting machine the rung runs on the Pro when the Pro has the tag, else the ladder waits with a row saying which tag it waits for. Acceptance: with the iMac full and the Air free, a pytest rung lands on the Air with a `placement` row and no alert; with both busy it runs on the Pro; a `swift-build` rung never lands on the iMac (no Xcode); a `dmg` rung lands on one machine whole; a `public`-only machine never receives a rung that reads the library; a down machine is alerted once in the ladder. Extends `run.remote-list` (the first runner that answers becomes the first that fits) and `run.build-incremental` (the build's stable tree is per machine, under its root).
- `dev-workflows.pool.hold-holds-one-machine` [GAP] (#6356; manager 2026-11-06: the Pro is the owner's when they test) — the owner's hold (`builder heavy -- sleep N` today; `builder hold <machine> [--for 8h]` names it) holds only the machine it names: the Pro held means no heavy rung on the Pro and the pool keeps placing on the others; a held remote is skipped like a busy one; the tile reads "held by the owner, N min"; a rung whose only capable machine is held waits with that reason in its row. A hold ends when its process ends or its time is up; a hold by a pid that is gone clears itself. Acceptance: with the Pro held and the Air free, a pytest rung lands on the Air and a `dmg` rung waits saying "pro held by the owner"; the hold's end lets it run; `builder hold air` with the Pro free sends pytest to the Pro and the iMac.
- `dev-workflows.pool.one-heavy-per-machine` [GAP] (#6356) — each machine has its own heavy lock under its root (the Pro's `heavy.lock` in the state dir, a remote's in its gate dir, both exist); the pool never sends a second heavy rung to a machine whose lock is held, counts a machine busy while it is, and runs quick rungs (ruff, swiftlint, one test file) beside a heavy one as today; two checks in parallel therefore use two machines, not one lock twice. Acceptance: two ladders at once with two machines tagged `pytest` run their pytest rungs on different machines at the same time; with one machine, the second waits on that machine's lock with the holder named (the remote-wrapper case of `test_heavy_lock.py` extended to two machines, in `test_machine_pool.py`).
- `dev-workflows.pool.parallel-gate` [GAP] (#6356) — one check's independent rungs run at once on different machines: after `ready`, `diff-bound` and `red-on-base`, the guards rung, the pytest rungs (split by the `[check].whole_tests` groups and by test directory into shards) and the build rung are placed together and joined; a rung that depends on another's result (contract-current on the re-bake, review on everything) waits for it; the `activity` row of each rung names its machine; the check's wall time with three machines is at most the longest rung plus the copy. The chain's order and every gate are unchanged: nothing is reviewed before every rung is green. Acceptance: a check whose guards take 180 s, pytest 300 s and build 240 s on three fitting machines ends in under 360 s plus copies (today about 720 s in sequence); each rung's row names its machine; a red in any one of them reds the check as today; with one machine the rungs run in sequence as today.
- `dev-workflows.pool.no-litter` [GAP] (#6356, #6357) — every byte the pool writes on a machine lands under that machine's registered root (`[machines].<name>.dir`, `~/fichero-gate`), in `runs/<run-id>/<step>/`, and is recorded in the machine's manifest line by line (#6357 §1: `created`, `run`, `lane`, `step`, `path`, `machine`); the pool writes to no home folder, `/tmp`, `~/tmp` or worktree, the DMG and the build's derived data included; removal is the manifest sweep's alone (#6357 §1, two steps, list then delete, journaled), never the pool's. Acceptance: a fake-ssh test records every path a ladder sends to a machine and asserts each starts with that machine's root and `runs/<run-id>/`; the manifest gains one line per created path; a rung that tries to write outside the root fails the test naming the path; after the sweep the root holds only the newest two runs per lane. Extends `run.scratch-sweep` (the Pro's scratch dirs become manifest entries) and the manager's registered-root ruling; replaces nothing.
- `dev-workflows.run.build-incremental` [PARTIAL] (#6116; manager 2026-11-03: 17 builds a day, median 8.5 min, near-full because each ran in a new scratch path) — the build rung runs in ONE stable tree, `[check].build_tree` (a worktree of the engine repo in the jail's workroot, checked out at the head and cleaned), against the build's own `-derivedDataPath` there, so xcodebuild compiles only what changed. A GREEN build's key (the tree hash of each `[check].build_paths` dir, the build command and `xcodebuild -version`) is kept owner-side in `<state>/build-results.json` (the last 200); a later build with the same key is reused, never rebuilt (a `build-reused` row), so a change outside `fichero/` and a re-check of the same tree cost nothing, and another Xcode, command or Swift tree always builds. A red is never reused. An incremental red (not a timeout) is built once more from a cleared derived dir and the second result stands (`retried: clean`, a `check` row): stale build state is not the code. The clear runs only on a derived dir under the build tree's own parent (the workroot), never the owner's Xcode data. Disk: one checkout (about 115 MiB) beside the derived dir (6.4 GiB today, flat: one dir, overwritten), under the machine's free-disk guard. Tests: `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_runs_in_one_stable_tree_and_a_green_key_is_reused_for_the_same_fichero_tree`, `::test_an_incremental_red_is_built_once_more_from_a_clean_derived_dir_and_a_red_is_never_cached`. Built: `builder build-check <lane>` runs this rung from a lane before its done (`dev-workflows.run.build-check`; tests `fichero-builder/tests/test_build_check.py::test_a_red_build_check_prints_every_error_and_the_log_and_removes_its_scratch_tree`, `::test_a_green_build_check_says_whether_it_built_or_reused_and_an_unknown_lane_is_refused`).
  Built 2026-11-05: A red that names a Swift source error (`X.swift:L:C: error:`) is the code's and is never retried from clean: tonight's four reds were all real, and each clean retry rebuilt from nothing for 6 to 9 min only to say the same and left the next build cold (2026-11-05). Only a red with no source error, stale build state, gets the clean retry. Measured 2026-11-04/05 in the stable tree: a 1 to 2 file change builds in 81 to 246 s, 8 or more files in 320 to 550 s (Swift recompiles what depends on a changed type), against a median of about 510 s before the stable tree.
  Built 2026-11-06 (manager t70/t71: a docs-only batch waited hours on the owner's Xcode hold, and a held Swift rung took the only worker): the build rung decides its skip (no changed file under `[check].build_paths`) before it takes the heavy lock, so a docs, spec or harness batch never waits on a hold. While a manual hold (`builder heavy -- <cmd>`, a live `heavy: ` holder) is on, a lane whose batch touches `[check].build_paths` (the step's head, or a worker lane's worktree HEAD while its step has none) is not started: it waits as held (one `queue` row `held` per head) without taking a worker, and starts at the first tick after the hold ends. Tests: `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_batch_that_touches_no_build_path_skips_the_build_without_ever_taking_the_heavy_lock`, `fichero-builder/tests/test_loop.py::test_a_batch_that_builds_swift_waits_for_a_manual_hold_without_taking_a_worker_and_starts_once_it_ends`, `fichero-builder/tests/test_heavy_lock.py::test_a_manual_hold_is_a_live_builder_heavy_holder_and_a_dead_one_is_none`, `fichero-builder/tests/test_loop.py::test_touches_build_reads_the_build_paths_and_diffs_the_batch_and_a_worker_lane_with_no_head_uses_its_worktree`. Not yet: the digest's HELD line.
  Built 2026-11-07 (manager t88, the first step of the machine pool #6356: the Pro is the owner's while he tests): with `[check].build_remote = "air:~/fichero-gate"` the build rung runs on the M1 Air. The stable build tree is rsynced there (mtimes kept, removed files removed, no .git) to `<dir>/build-tree`, and xcodebuild runs with `<dir>/derived` as its derived data under that Mac's own one-heavy-job lock, everything under the one registered root `<dir>`; package resolution is allowed there (its first build fetches them). One build at a time across both trees (`[check].build_lock`). A green key is reused as here. The Air unreachable, or a red there that names no Swift source error (that Mac's, not the code's), builds here as before; a source error there is the code's red. With a build remote set, the owner's manual hold here holds no batch back. Tests: `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_build_runs_on_the_build_remote_with_its_own_derived_data_and_falls_back_here_when_that_mac_is_down`, `fichero-builder/tests/test_loop.py::test_a_build_remote_means_the_owners_hold_here_holds_no_batch_back`. Not yet: a real build on the Air (it was asleep when this was built); the remote clean retry; the manifest sweep (#6357) owning `<dir>/build-tree` and `<dir>/derived`.
  Built 2026-11-24 (#6589: the build runner's gate dir is a symlink to a volume whose name has a space; Xcode saw the module cache under two paths, crashed, and every build fell back here): the build rung takes the remote base from `pwd -P`, shell-quotes it everywhere it reaches a remote command (the probe, the lock and its command, the result bundle's `rm` and `mkdir`), and quotes the rsync destination for the remote shell (no `--protect-args`: macOS's stock rsync rejects it). The third env-red of that runner in a row (or a streak longer than three already in the journal) raises one `build-remote` alert per streak naming the runner and the last error; the count is read from the journal (`build-remote-env-red` and `build-remote-crash` rows since that runner's last `build-remote` row), so it holds across ladders, which are separate processes; a build that ran over there resets it. Tests `fichero-builder/tests/test_remote_build_path.py::test_the_real_path_with_a_space_survives_into_every_remote_command`, `fichero-builder/tests/test_remote_build_path.py::test_three_env_reds_in_a_row_raise_one_alert_naming_the_runner_and_the_last_error`, `fichero-builder/tests/test_remote_build_path.py::test_env_reds_of_earlier_ladders_count_because_the_count_is_read_from_the_journal`, `fichero-builder/tests/test_remote_build_path.py::test_a_streak_already_longer_than_three_on_disk_alerts_once_and_not_again_in_the_same_streak`.
  Built 2026-11-07 (#6381): a pinned copy is made by one maker at a time (a `pin` lock shared by the landing and a chain re-pinning), and a copy with no `harness.toml` (a `worktree add` cut short) is made again, so a chain never reads a half copy (JailMissing on three batches at 14:05). The scratch tree's checkout gets 600 s, not git's 60 s, and a killed checkout names its reason (2026-11-07: 'reset died of signal 9', then an empty reason, at load 100). The base tree (red-on-base) and the build tree get the same 600 s. A base tree that cannot be made is an infra error, 'the check could not run', retried like any infra failure, never a red-on-base for the manager to approve (alert 416, 2026-11-07). Tests: `fichero-builder/tests/test_loop.py::test_a_pinned_copy_cut_short_is_made_again_and_two_chains_pinning_at_once_both_get_a_whole_one`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_scratch_checkout_gets_minutes_not_gits_60_s_and_a_kill_names_its_reason`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_base_tree_that_cannot_be_made_is_an_infra_error_never_a_red_to_approve`.
  Built 2026-11-07 (#6382): `scripts/check_no_conflict_markers.py` scans only the files a batch adds or changes against its merge-base with origin/integration, each read once. The whole tree is still scanned when HEAD is integration itself (verify-all's guard loop over integration) or when `FICHERO_CONFLICT_SCAN=full`, the net for merges made outside the ladder. The whole-tree scan took over 300 s at load 70 and timed the presubmit out. Test: `fichero-server/tests/unit/scripts/test_check_no_conflict_markers.py::TestScopedToTheBatch`.
  Built 2026-11-08 (#6390, owner 2026-11-07: the iOS app and the Swift test target broke on integration and nothing saw it): what
  the build rung never compiles is built once a day. `[check.daily_builds]` names each command (`ios-sim`: the app for
  `generic/platform=iOS Simulator`; `tests`: `build-for-testing` on macOS); the loop, busy lanes or not, runs `builder
  daily-builds` once a day from the last start (`<state>/daily-builds.last`), on `[check].build_remote` only, never on this
  Mac: the stable tree rsynced as for the build rung, each command with its own `derived-<name>` there, under the same locks,
  a green key reused. A `daily-builds` row each run; a red (a Swift source error) is an alert naming the command and its first
  error; the Air down is `not-run`, never a red, and waits the day. Tests
  `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_daily_builds_run_each_named_command_on_the_build_remote_with_its_own_derived_data_and_never_here`,
  `fichero-builder/tests/test_queue_verb.py::test_the_daily_builds_run_once_a_day_busy_lanes_or_not_and_a_red_one_is_an_alert`.
  Built 2026-11-08 (manager: five tree-scanning guardrail tests sat red on integration for hours, `test_db_access_guardrail`
  among them, because a batch runs only the test files it changes): `[check.whole_tests]` may map a prefix to a LIST, and a
  `.py` entry runs engine-shaped beside the changed tests in the green run. Each of the 55 tests that scan the repo through
  `scripts/_scan_files.py` (imported, or loaded by path) is listed under the roots it passed to `scan_rglob` on a real run (recorded 2026-11-08), so an engine
  batch runs the 35 that scan `fichero_server`, a routes batch three more, a Swift batch the five that scan
  `fichero/fichero`. `[check].daily_tests` lists all 65 (the ten that walk only their own temp dirs too), run once a day by
  `builder daily-builds` on the loop's checkout, a red an alert. A test that names the helper and is in neither list fails the drift test below (review 132). verify-all runs each package's tests dir whole, so it takes only a dir value as a
  whole suite (review 130). Tests
  `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_whole_tests_list_runs_its_test_files_engine_shaped_beside_the_changed_tests_and_its_dirs_whole`,
  `fichero-builder/tests/test_verify_whole_lists.py::test_verify_takes_only_the_dir_values_as_whole_suites_and_reads_the_real_rules`,
  `::test_daily_builds_runs_the_daily_tests_on_the_checkout_and_a_red_names_its_first_failed_test`,
  `::test_every_engine_test_using_the_scan_helper_runs_daily_and_the_ones_that_scan_the_repo_run_per_batch`.
- `dev-workflows.run.build-check` [PARTIAL] (#6116; manager 2026-11-03/04, design batch ii: three Swift compile errors a day were found only after a queue and a ladder, about 25 to 30 min each) — `builder build-check <lane>` runs the app's build rung over the lane's HEAD before its `done`: the HEAD fetched into the engine repo as `check-lane` does, the pinned check files laid over a scratch tree of it, and `check_tool.build` run exactly as the ladder's rung (jailed, in `[check].build_tree`, under the build and heavy locks, the build paths themselves as the change so it always compiles). Red prints every `error:` line with its file:line and the log path and exits 1; green says whether it built or reused a green key, and stores the key, so the ladder's build rung reuses it for the same `fichero/` tree; one `build-check` row; nothing lands (tests `fichero-builder/tests/test_build_check.py::test_a_red_build_check_prints_every_error_and_the_log_and_removes_its_scratch_tree`, `::test_a_green_build_check_says_whether_it_built_or_reused_and_an_unknown_lane_is_refused`). **Not built:** a `--build` step inside the presubmit when the batch touches `[check].build_paths`.
- `dev-workflows.run.scratch-sweep` [PARTIAL] (#6116; manager 2026-11-03: about 780 scratch dirs, 1.6 GiB, left in the jail's workroot by ladders a restart or kill stopped) — the ladders' own scratch dirs (`check-tree-`, `check-base-tree-`, `check-base-`, `check-home-`, directly under `[jail].workroot`) older than 6 hours and named by no running process leave in TWO steps: `builder sweep-scratch --list` writes the list to `<state>/scratch-sweep-<ts>.txt` and deletes nothing; `--delete FILE` removes exactly the dirs that file names, each re-checked (still a scratch prefix directly under the workroot, still old, still unheld), a check tree through `git worktree remove`, the jail user's files as that user, and says the count and the size freed. Nothing else in the workroot (a worker's tree, the derived dir) is touched. The loop runs the list and then the delete at a quiet tick, at most every 6 hours; each step is a `sweep-scratch` row. Tests: `fichero-builder/tests/test_scratch_sweep.py::test_the_list_step_names_only_old_unheld_scratch_dirs_and_deletes_nothing`, `::test_the_delete_step_removes_exactly_the_list_rechecked_and_says_what_it_freed`, `::test_the_loop_runs_list_then_delete_at_most_every_six_hours`. Not yet: why a rung's `check-home-` dir outlives it today (214 of 215 are under 6 hours old). Built 2026-11-16 (#6589): the review's tree and cwd (`review-tree-`, `review-`) are swept too, from the review scratch folder of the state dir (`review_dir()`, mode 700, refused when a symlink, not the owner's or open to others), by the same list and delete steps; tests: `fichero-builder/tests/test_scratch_sweep.py::test_old_review_trees_and_cwds_are_swept_from_the_state_dir_and_a_live_one_is_kept`, `::test_the_review_dir_is_refused_when_it_is_open_to_others_or_a_symlink`.
- `dev-workflows.run.review-files-in-state-dir` [OK] (#6589 item 20) — `scripts/harness_review.py` makes its review tree and its per-review cwd (fresh, empty, mode 700, no CLAUDE.md or settings) under the owner-only review scratch folder of the builder's state dir (mode 700; REFUSED when it is a symlink, not the owner's, or open to group or others), never under `$HOME` and never in `[jail].workroot`: the reviewer runs as the owner, claude obeys a CLAUDE.md in its cwd and every ancestor, and the worker user owns the workroot. A review that ends or is killed leaves its dirs for `builder sweep-scratch` (see `run.scratch-sweep`), which removes those older than its 6 hour retention and keeps a younger one; the review has no timeout of its own, so the sweep's retention is the bound, and the sweep runs at the loop's first quiet tick, not at start. `work.do_review` starts the review with `FICHERO_BUILDER_STATE` set to the loop's own state dir (which `--state` may have set), so the review and the sweep use one folder; without an environment value the default state dir sits under `~/.local/state`, which is why it is passed. Tests: `fichero-builder/tests/test_work_verb.py::test_a_review_started_by_do_review_leaves_its_dirs_where_the_sweep_looks`, `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_the_reviewer_is_restricted_without_mcp_and_runs_in_a_fresh_dir_under_the_state_dir` (cwd and tree under the state dir, no ancestor open to another user), `fichero-builder/tests/test_scratch_sweep.py::test_old_review_trees_and_cwds_are_swept_from_the_state_dir_and_a_live_one_is_kept`, `::test_the_review_dir_is_refused_when_it_is_open_to_others_or_a_symlink`.
- `dev-workflows.run.manager-files-one-home` [OK] (#6589 item 21) — the worktrees folder holds worktrees only; manager briefs, handoffs, reports and build logs live under the state dir's `manager/{briefs,handoffs,reports,logs}` (AGENTS.md, "Where Things Live"). `builder queue add --brief F` refuses a brief that is not a file, copies it to `manager/briefs/<lane>-<step>.txt` and stores the copy's path in the step. No builder module or harness script calls `mkdtemp`, `mkstemp`, `mkdir`, `NamedTemporaryFile` or `TemporaryDirectory` with a directory under `Path.home()`. Tests: `fichero-builder/tests/test_queue_verb.py::test_add_copies_the_brief_into_state_manager_briefs_and_stores_the_copys_path`, `fichero-builder/tests/test_no_home_litter.py::test_no_builder_module_makes_a_dir_or_temp_file_under_home`. Not yet: the builder's own writes of handoffs, reports and logs into `manager/` (only briefs are written there by code).
- `dev-workflows.run.rebase-rebakes-generated` [PARTIAL] (#6116; manager 2026-11-04: every landing made the other lanes' batches conflict ONLY on the generated contract identity, redone by hand; alerts 290, 291, 308) — the loop's rebase of a lane resolves one conflict itself: when every conflicted path is one of `[check].generated` (the Python and Swift contract identity), it takes upstream's copy, runs `[check].rebake` (the project's own `export_openapi_schema.py --bake-identity-from` over the merged contract) in the worktree as the worker, adds the files and continues; a commit left empty is skipped. Any other conflicted path aborts the rebase as before and stays the lane's. After such a rebase the identity is re-baked once more at HEAD and, if that changed it, committed citing `[check].rebake_issue` (#4705) with the lane's own trailers. One `rebake` journal row per conflict and one for the HEAD check. Tests: `fichero-builder/tests/test_work_verb.py::test_a_rebase_whose_only_conflict_is_the_generated_identity_re_bakes_it_and_goes_on`, `::test_a_rebase_with_any_other_conflict_beside_the_identity_is_aborted_as_before`. Built 2026-11-14 (a rebase left the contracts and the engine embed list stale, and the guards bounced the batch): after every rebase that moved a managed lane, each `[check].regen` line (the contracts' sync with FICHERO_PYTHON_BIN, the engine embed list, the Swift client's build dir removed) runs in the worktree as the worker, and a tracked file it changed is one commit citing `[check].rebake_issue` with the lane's trailers (one `rebake` row); a line that fails is a row and the guards judge. The builder never commits to an external lane's branch (it is the lane's agent's): that lane's red names the same lines as its fix (`run.presubmit-lints` item 7). Test `fichero-builder/tests/test_autofix.py::test_a_rebase_that_moved_the_lane_regenerates_the_generated_files_and_commits_them`.
- `dev-workflows.run.loop-launchd` [PARTIAL] (#6116; owner 2026-11-03: after the Mac restart nothing started by itself) — a reboot restarts the loop and the console with no person. `builder launchd` writes four LaunchAgents as the owner: `local.builder.loop` (`builder loop`, KeepAlive, RunAtLoad), `local.builder.console` (`builder status --port 8766`, KeepAlive, RunAtLoad), `local.builder.heartbeat` (every three ticks) and `local.builder.release` (`builder release`, 03:00, `dev-workflows.run.release-stages`); `--load` also boots each out and bootstraps it into `gui/<uid>`, one line per agent, and exits 1 naming launchctl's error when one fails. Never two loops: `builder loop` refuses (exit 1, nothing ticks) while `loop.pid` names another live `fichero_builder loop`; a pid the reboot left behind, dead or reused by another program, is no loop, so KeepAlive's retry takes over once a hand-started loop ends. Pane ids change after a reboot: each tick the loop points an external lane whose registered pane is gone at the one live pane running something other than a shell in the lane's worktree (or below it); none or several leave it as it is, and no tmux on the PATH (the jail, a launchd PATH) is nothing to re-point; each move is a `queue` row `repane`. Tests: `fichero-builder/tests/test_launchd.py::test_the_console_is_a_third_agent_kept_alive_and_started_at_login`, `::test_load_boots_out_then_bootstraps_each_agent_and_names_a_failure`, `::test_a_second_loop_is_refused_and_a_pid_the_reboot_left_is_not_a_loop`, `::test_a_dead_pane_is_pointed_at_the_one_claude_session_in_the_lanes_worktree`, `::test_no_tmux_on_the_path_is_nothing_to_re_point_never_an_error`. Not yet: the agents loaded on the owner's Mac and a real reboot.
- `dev-workflows.run.loop-roles` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — the model and the worker kind are per role in `harness.toml [models]` (builder,
  reviewer, manager; today sonnet, opus, haiku), the kind from the provider: an interactive Claude Code session in tmux today,
  a Pi RPC session on OpenRouter or a local server next. The loop reads only journal rows and the DONE / QUESTION protocol, so
  nothing in it assumes Claude Code; no model name is written in code. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_loop.py`
  (a fake provider kind runs a step end to end; a role with no provider is a question).
  **Built** 2026-11-02: the `manager` role (haiku) in `[models]`; the loop takes builder and reviewer from the roles; `builder run` with no `--model` takes `[models].builder` and a rules file without one refuses as a question. Test `fichero-builder/tests/test_model_config.py::test_the_loop_has_a_manager_role_and_no_verb_names_a_model_of_its_own`. `scripts/harness_review.py` takes its model from the pinned `[models].reviewer` (a rules file without one is a refusal); `scripts/harness_review.py` run by hand no longer falls back to `--model opus`. Not yet: the Pi kind through the loop.
- `dev-workflows.run.loop-machine-checked` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) (the open-model trial of 2026-10-18 failed on these) — after each step the
  loop checks that the jail root and every other lane's worktree are unmoved and clean (HEAD and `git status`), and alerts
  otherwise; the policy hook refuses `git reset --hard`, `git checkout --`, `git clean -f` and `git stash` outside the worker's
  own worktree, and any write outside it. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_loop.py` (a step that moves another
  lane's tree alerts), `fichero-builder/tests/test_pi_policy_extension.py` and the policy hook's tests (each refused command).
  **Built** 2026-11-02 against fakes: a step snaps the jail root and every quiet lane's worktree (no live session of its own, step queued, blocked or landed) as `HEAD status-hash` before its worker starts; at the worker's DONE a changed one is one `alert` row naming each tree (no actions; the step goes on: the stray write was not in its tree). A landing meanwhile (`landed` row `jail-root`) excuses the jail root. The policy hook (both kinds: Pi's extension calls the same `check`) refuses `git -C`/`--work-tree`/`--git-dir` at another tree with `reset --hard`, `checkout --`, `clean -f` or `stash`, and a shell redirect or `tee` to an absolute path outside the worktree and scratch path. Tests `fichero-builder/tests/test_loop.py::test_a_step_that_moves_another_lanes_tree_or_the_jail_root_alerts`, `::test_a_landing_meanwhile_excuses_the_jail_root_and_a_busy_lane_is_not_checked`, `fichero-server/tests/unit/workflows/test_policy_hook.py::test_each_forbidden_command_is_refused_with_a_reason` (six new cases), `::test_ordinary_commands_pass`. A tree removed during the step (not a directory at the check) is skipped, not read as moved, and a landed lane's worktree is not in the snapshot list (#6589 2026-11-20). Tests `fichero-builder/tests/test_loop.py::test_a_tree_removed_during_the_step_did_not_move_by_a_stray_write`, `fichero-builder/tests/test_loop.py::test_a_landed_lanes_worktree_is_not_in_the_snapshot_list`. Not yet: a lane with a live session is skipped, so a write there is seen only when it is quiet.
- `dev-workflows.run.loop-status` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — `builder status`: a read-only page on 127.0.0.1 (stdlib HTTP, journal only):
  lanes, each lane's step and state, the last check and landing, issues closed today, spend today, open alerts; the same as
  JSON at `/status.json` for the app. Test: `fichero-builder/tests/test_status_page.py` (a journal of fixed rows gives
  that page and that JSON).
  **Built** 2026-11-02, the page retired 2026-11-03 (owner: only the console stays): `console.status` gives one dict (lanes with step and state, last check, last landing, issues closed today = `done` rows' issues less `left_open`, spend today = today's `cost` rows, open alerts = alerts with no answer that took). and `GET /api/status` serves it with the console's additions below; `console.rows_of` reads the owner's journal and only the run rows of the worker's shared one under `[jail].workroot/state`, skipping a line that does not parse, so a worker cannot put a check or a landing there. Tests `fichero-builder/tests/test_status_page.py::test_a_journal_of_fixed_rows_gives_that_status`, `::test_the_status_verb_serves_the_console`, `::test_the_console_reads_the_owners_journal_and_the_workers_shared_one`, `::test_a_worker_cannot_put_a_check_or_a_landing_in_the_owners_rows_and_a_bad_line_is_skipped`.
  **Console** (owner order 2026-11-02, APPROVED by the manager): `builder status` is an interactive console, the owner's main view;
  the old read-only `builder watch` page (8765) is deleted (owner 2026-11-03). A stdlib server on 127.0.0.1 (a Tailscale bind behind a token later):
  `GET /api/status` is the JSON above plus the last review and the heartbeat (the last `loop` tick); `GET /api/events` is a
  server-sent-events tail of the journal. Actions are `POST /api/action` calls onto the existing verbs and nothing else (a lane's
  pause and resume, loop start and stop through `launchctl` on the `local.builder.loop` agent, `alert <id> <action>`,
  `build --dev`, `queue add`, `done`); a verb not on that list is refused, and every action, refused or not, writes one `console`
  row naming who did it, the verb and its exit. A POST must carry the token the page was served with and a loopback Host, so
  another site in the owner's browser cannot drive it. The page is one static `console.html` with Preact and htm from a pinned
  CDN ESM URL, no npm and no build step: a lanes table with each lane's steps under a disclosure, alert cards with their action
  buttons, a Build button. Test: `fichero-builder/tests/test_status_page.py` (the API and each action against a fake
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
  and an `acquired` row when it ends, and the console shows a waiting one as a banner; a CLI that waits as long also says so on stderr (`waiting for the <lock> lock, held by <pid> <what>`; test `fichero-builder/tests/test_status_page.py::test_a_cli_waiting_on_a_lock_says_so_on_stderr`). The landing's `pinned` step never waits
  for a running check: with the ladder held it pins its copy and keeps the older ones for the next landing to remove. A lane row
  shows its check or review's running rung and since when (from the `activity` rows); views A-D are built (tests
  `fichero-builder/tests/test_status_page.py::test_a_lock_wait_over_its_limit_is_a_row_naming_the_holder_and_the_console_shows_it`).
  Console fixes (owner's 11:00 screenshot): the last landing and today's closes come from origin's land branch itself (its tip,
  and the `Fixes`/`Closes` lines of today's commits), true even for a landing run by hand; a running check is the headline
  before the last one; the lane count reads `N worker lane(s) (limit L) · M external`; a milestone whose spec an external lane
  owns shows `owned by <lane>` and no Start; a spec's empty twin of a GitHub milestone is dropped (one row per milestone); the
  milestones are read from GitHub again after each landing and every 15 minutes (test
  `fichero-builder/tests/test_status_page.py::test_console_tiles_come_from_origin_an_owned_milestone_has_no_start_and_the_spec_twin_is_one_row`).
  Remote checks (manager 2026-11-02, the Pro CPU-bound): `[check].remote` refuses a host under `[check].remote_min_free_gb`
  (default 5) free, the smaller of its base dir and its `/tmp` (pytest writes there; #6589, test `fichero-server/tests/unit/workflows/test_check_tool.py::test_the_remote_free_space_probe_takes_the_smaller_of_the_base_dir_and_tmp`), as unreachable (an alert, the run here); `[check].remote_guards` (off by default: the guards call git and the
  shipped tree has none) sends the guards too; the build rung stays on the Pro. A registered maintainer lane (`queue add
  --maintainer`, the harness builder's) runs its checks `--maintainer`. An import-only change to a test file owes no red, like a
  data-only one (test `fichero-server/tests/unit/workflows/test_check_tool.py::test_an_import_only_change_to_a_test_file_owes_no_red`).
  `builder machines sync <name>` (manager 2026-11-02): the test plugins (pytest, anyio, hypothesis, langsmith, pytest-timeout,
  pytest-asyncio) and their dependencies, at the exact versions of the jail's venv, installed into the machine's gate venv (uv
  when it has no pip), after the disk floor; one `machines` row. Proven on the iMac (33 pins; a remote check then ran 16 tests
  there in 8 s), and `[check].remote = ["imac:~/fichero-gate", "air:~/fichero-gate"]` is on for the pytest rungs (the iMac, then the M1 Air, then here: `run.remote-list`; the Air added 2026-11-03, owner: plugged in and usable).
  Speed 1 (manager 2026-11-02): every rung's time is in its `activity` row; the console's Activity view gives each rung its
  median time, and a running rung reads `usually <median>` (test
  `fichero-builder/tests/test_status_page.py::test_activity_gives_each_rung_its_usual_time_and_a_running_rung_reads_it`).
  Speed 5 (manager 2026-11-02): a guard's green is reused when its key is unchanged: sha256 of the guard's bytes, the git
  tree ids of the inputs `[check].guard_inputs` declares for it (the whole tree when it declares none), the tree's diff and
  status (the pinned overlay, anything uncommitted) and the interpreter, ruff and swiftlint versions; a red always runs again,
  and any part that cannot be read means it runs. The cache is `<state>/guard-cache.json` (the chain and `builder check` only).
  Built 2026-11-08: the repo's `[check.guard_inputs]` declares 100 of the 121 guards, read with an audit hook (what each
  opens and lists, two levels deep, `scripts/` whole); a guard that starts a subprocess or lists the root stays undeclared
  (the whole tree), and the skipped guards are left out. So a batch that touches only `fichero/` reuses the greens of the
  guards that never read it. Ceiling: a read by `.exists()` alone is not seen, so such a guard can be reused stale; the
  nightly verify-all runs every guard uncached. Test `fichero-builder/tests/test_guard_inputs.py::test_every_declared_guard_exists_and_every_input_is_in_the_tree`.
  Test `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_guard_green_is_reused_for_the_same_inputs_and_runs_again_when_one_changes`.
  Soak fixes 11:40 (manager): one approve carries every reason the refusal listed (maintainer, weakened, pinned-new, red: an
  approve had re-run with maintainer only and refused again on the weakened tests it listed); an external lane's red offers
  send-back | retry | park, and a send-back or park tells its pane what to fix and the exact `builder done <lane>` command (park
  keeps the lane: its next done re-takes); every findings tell names that command too; the landing closes its issues right
  after on-origin, before the refresh, so a jail-root failure never loses the closes; on new code the loop stops starting chains
  until it re-execs (serial chains never left it a quiet tick). An external lane's red offers send-back, retry and park (never ask-owner); send-back and park tell its pane the finding and the exact `builder done` command, or say `tell-refused` when it has no pane. Tests in `fichero-builder/tests/test_landed_verb.py`,
  `test_work_verb.py` and `fichero-builder/tests/test_loop.py::test_an_external_lanes_red_offers_send_back_retry_park_and_a_worker_lanes_keeps_its_own`, `::test_send_back_on_an_external_lane_tells_its_pane_the_done_command_and_says_so_when_it_has_none`, `::test_a_draining_loop_starts_no_new_chain_so_it_can_re_exec_between_chains`.
  A head whose every commit is already on origin by patch (`git cherry` all `-`, a pre-rebase copy of a landed batch) is never
  taken: the intake skips it and `builder done` refuses it with a row (manager 2026-11-02: the intake re-took land-ie's
  ie-batch2). Test `fichero-builder/tests/test_loop.py::test_a_head_whose_every_commit_is_on_origin_by_patch_is_never_taken`.
  Speed 2 (built 2026-11-02): the review starts in a thread once every rung before the build is green (after `since-guards`, `check_tool.ON_RUNG`; manager 2026-11-04: started after red-on-base, reviews 199, 207, 263 and 275 read no guard results and answered 'no guards ran'), with a
  partial ladder holding every guard's result, only the build running beside it; a later red kills it before any verdict; a green check takes its result (tests `fichero-builder/tests/test_work_verb.py::test_the_review_starts_once_red_on_base_is_green_and_its_verdict_is_used`, `::test_a_later_red_rung_kills_the_early_review`). The partial ladder names the rungs still running (`pending`, in the ladder's order), and the reviewer's ladder summary says they run beside it and must not be judged or called missing (reviews 199 and 207, 2026-11-03, answered NOT READY 'no guards ran'; tests `::test_the_early_review_is_told_which_rungs_still_run_beside_it`, `fichero-server/tests/unit/workflows/test_review_wrapper.py::test_an_early_reviews_ladder_names_the_rungs_still_running_so_they_are_not_judged`).
  Speed 3 (manager 2026-11-02): `[check].parallel` (default 2) ladders run at once, each in a ladder slot (`ladder`, `ladder-2`, ...) taken under a pick lock, and never two whose batches share a file (an unknown file list shares every file); a waiting chain says why after 30 s. The generated contract files (`work.GENERATED_CLASH_FREE`: the openapi.json copies, the CLI and MCP generated modules, the contract identity files, the engine embed file list) are left out of that comparison, because landing rebases and regenerates them and the contract-current rung catches a stale one (#6589, 2026-11-23); a chain that waits on a clash while a slot is free writes one `lock` row, state `clash`, naming the shared file. Rung hooks and the activity lane are per thread, the guard cache is written atomically, and a landing holds every ladder slot before it removes the older pinned copies. Tests `fichero-builder/tests/test_work_verb.py::test_two_disjoint_batches_check_at_once_and_a_batch_sharing_a_file_waits`, `::test_batches_sharing_only_generated_contract_files_get_two_slots_and_one_sharing_a_source_file_waits_with_a_row`, `::test_a_ladders_rung_hook_and_key_are_its_own_threads`, `fichero-builder/tests/test_landed_verb.py::test_a_check_in_the_second_ladder_slot_keeps_the_older_pinned_copies`.
  **Stop** (manager 2026-11-02, built): pause = no new step is fed; `builder queue stop --lane L [--grace S]` = the session
  ends: the lane is paused, a live worker is told to commit what is green and end, and the loop closes the session when the
  grace is over (default 300 s) or the worker ends first; the tree is kept, a step in flight goes back to queued with a brief
  that says to continue from the tree, and `queue resume` starts a fresh session on it. Rows `stop`, `stopped`, `stop-refused`.
  Test `fichero-builder/tests/test_loop.py::test_stop_tells_the_worker_closes_its_session_after_the_grace_and_resume_starts_a_fresh_one_from_the_tree`.
  **Landed means on origin/integration** (owner 2026-11-03: the Milestones page showed lane-done as landed): a step or issue shows `landed` only when its commit is on origin/<land branch> (a closed issue needs its Fixes commit in that branch's log; a queue step needs its head to be an ancestor of it); a step the lane finished or an issue that is closed without such a commit shows `done, not landed yet`, a status of its own below `landed` in the rank, and a Lanes row keeps both counts ("N landed on integration, M done, not landed yet") and says "step i of n" for the spec position. Tests: `fichero-builder/tests/test_status_page.py::test_a_step_is_landed_on_the_console_only_when_its_head_is_on_origin_integration`, `::test_a_finished_milestone_step_whose_issues_are_not_landed_reads_done_not_landed_yet`, `::test_a_lane_through_its_steps_reads_done_not_landed_yet_until_its_last_step_is_on_origin` and `::test_each_issue_and_step_has_one_status_from_git_and_gh_and_start_is_offered_only_where_nothing_is_built`.
  **Review page** (owner 2026-11-24: the review list is a page of the console, not a claude.ai artifact; Spec-change: manager 2026-11-24, #6589): the file `review.json` in the state dir holds `{"items": [...]}`, each item id, title, area, build, how (steps), why, issue (URL), status (`to-test`, `works`, `polish`, `bug`, `n/a`), note, order, added, and `updatedAt` once a verdict is set. `GET /review` is the console page opened on its Review tab (also a tab of `/`): items grouped by status, to-test first, highest order first, each card with title, area, build, why, the how steps, the issue link, Works / Polish / Bug / N/A buttons and a note box; it works at phone width (a `max-width: 640px` layout). `GET /api/review` returns the file's JSON; `POST /api/review {id, status, note}` (the same token and loopback-Host rule as every POST) updates one item, stamps `updatedAt` and writes one `console` row `review <id> <status>`; an unknown id is 404, an unknown status 400. `builder review add <id> --title ... [--where --build --how (repeat) --why --issue --order --status]`, `builder review set <id> [--status] [--note]` and `builder review list [--changed-since <ts>]` (items whose verdict is newer than the ts, with status and note) are the manager's side; the older `review start|check|approve <area>` actions are unchanged. Tests `fichero-builder/tests/test_review_page.py` (`::test_add_refuses_a_duplicate_a_missing_title_and_an_unknown_status_and_defaults_the_rest`, `::test_set_changes_status_and_note_stamps_updated_and_refuses_unknown_ids_and_statuses`, `::test_listing_filters_by_changed_since_and_orders_to_test_first_highest_order_first`, `::test_the_cli_adds_sets_and_lists_and_the_old_review_actions_still_parse`, `::test_get_review_serves_the_page_with_the_token_and_the_review_tab_and_api_review_the_json`, `::test_post_review_needs_the_token_and_a_loopback_host_updates_one_item_and_writes_one_console_row`). Not tested: the page's drawing in a browser (its script parses under `node --check`).
- `dev-workflows.run.loop-soak` [GAP] (#6116; APPROVED by the manager 2026-11-02, owner-delegated) — acceptance for the loop as a whole: it runs a real build-order milestone for six
  hours with no hand step; every step either lands or ends as an alert row with evidence, never as silence; the heartbeat has no
  gap longer than three ticks. Manual: the maintainer reads only `builder status` and the alerts for the six hours, and the
  journal is attached to the issue.
- `dev-workflows.run.loop-session-cap-hands-off` [OK] (#6116; owner ruling B2 2026-11-21, which retires the session cap the manager
  approved on 2026-11-02) — there is no dollar session cap: session spend alone never ends or hands off a session. A session
  ends at the context limit (a handoff) or at `[spend].day_usd` (a park); `[spend].session_usd` is read and ignored.
  **Built** 2026-11-21: `watcher.assess` gives no session-spend handoff and `watcher.refusals` needs only `day_usd`. Tests
  `fichero-builder/tests/test_watcher.py::test_only_the_day_cap_parks_and_session_spend_alone_never_ends_a_session`,
  `fichero-builder/tests/test_watcher.py::test_a_day_cap_alone_lets_a_worker_start`,
  `fichero-builder/tests/test_dry_run.py::test_session_spend_alone_neither_hands_off_nor_stops_the_worker`. (#6871)
- `dev-workflows.run.loop-handoff-tokens` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated; ie-lane2 used 17M tokens for
  three steps on a 1M window) — the handoff threshold is an absolute token count, `[spend].handoff_tokens` (175000, owner 2026-11-02), not a share
  of the window; a session whose context passes it hands off. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_watcher.py` (a session
  at 150001 tokens on a 1M window hands off).
  **Built** 2026-11-02: `[spend].handoff_tokens = 175000` (owner, was 150000); `watcher.threshold` and the in-session hook (through the registry's `handoff_tokens`) both use it. Tests `fichero-builder/tests/test_watcher.py::test_the_handoff_threshold_is_an_absolute_token_count_when_set`, `scripts/harness_handoff_hook.py`'s self-test through `fichero-server/tests/unit/workflows/test_handoff_hook.py`. A machine's own `[spend]` values go in an untracked `~/.config/fichero-builder/harness.local.toml` under the running user's home; its keys win over the tracked file's and an unknown key still refuses. It counts only when it is owned by whoever owns the checkout and is not group- or world-writable, so a jailed worker's own copy (its state dir and home are its own) is ignored (manager 2026-11-02, review 2026-11-02; test `fichero-builder/tests/test_watcher.py::test_a_machines_own_spend_caps_win_only_from_the_owners_private_file`).
- `dev-workflows.run.loop-fetches-the-lane` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated; a check refused "not a
  commit in the engine repo" until a person fetched by hand) — on DONE the loop fetches the lane's head from its worktree into
  `[check].engine_repo` and makes it readable to the jail user, before the check. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_loop.py`
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
  with `--maintainer`) and `send-back` (a fix brief). An approve of any kind RESUMES the same batch: the rungs green before the one it excused, in the last ladder file for this exact head, base and pinned copy, are not run again (the rows say `cached`); any difference starts the ladder over (`fichero-builder/tests/test_approve_resume.py`). Separately, `scripts/verify_workflows.py` reads its image-input tool list
  from the tool registry, so adding a node never edits a pinned check. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_loop.py`
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
  **Approve binding** (manager 2026-11-02: alert -36's approve excused a later head): an approve records the step's head at that moment (empty for a worker lane's step, which has none until a chain is green) and the test files the alert named; it counts only while the step still has that head, and a `builder done` at a new head clears it. A red-on-base approve that named test files excuses a refusal only if it names one of them. Tests `fichero-builder/tests/test_loop.py::test_an_approve_binds_to_its_alerts_head_and_named_tests_and_a_new_head_clears_it`, `::test_an_approve_on_a_worker_lane_whose_step_has_no_head_yet_still_counts`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_an_approve_naming_test_files_excuses_only_those`. Approves for one head ACCUMULATE: each adds the files its alert named to those already approved, kept in the queue file so a restarted loop reads them, and a new head starts empty (manager 2026-11-03: sharing bb3 was asked about one test three times; test `fichero-builder/tests/test_loop.py::test_approves_for_one_head_accumulate_and_survive_a_restart_and_a_new_head_starts_empty`).
  **The sweep's image-input list** (`scripts/verify_workflows.py`): the live registry's vision or transform tools with a `files` input port, plus a floor (`IMAGE_INPUT_FLOOR`) of the tools the sweep always counted whose image port is a JSON `documents` one; a floor name not in the registry is not invented (test `fichero-server/tests/unit/scripts/test_verify_workflows.py::test_the_floor_keeps_the_image_tools_whose_port_is_json_so_the_registry_rule_drops_none`).
- `dev-workflows.run.loop-external-lane` [PARTIAL] (#6116; APPROVED by the manager 2026-11-02, owner-delegated: the baseline comparison) — a
  lane of kind `external` is a branch in a worktree that the loop does not start a worker for; `builder done <lane> <sha>` is its
  DONE, and from there the same chain runs (fetch, check, review, landed --push, alert on a stop, findings by `builder tell` when
  the lane names a pane, else as an alert). Plain Claude Code lanes land through the loop this way. Test (to write):
  `fichero-builder/tests/test_loop.py` (`builder done` on an external lane lands it through fakes; no worker is started).
  **Built** 2026-11-02 against fakes: `builder queue add --kind external` makes the lane; the loop starts no worker for it and its step waits; `builder done <lane> <sha>` sets the step done (a `done` row; a worker lane or no waiting step is a `done-refused` row) and the chain runs; a red, NOT READY or refused is sent back to the lane by the loop itself up to three times a batch (one `auto-send-back` row each, no alert; see **Auto send-back** under `dev-workflows.run.loop-alerts`), then an alert with its evidence, never a fix round. Test `fichero-builder/tests/test_loop.py::test_builder_done_on_an_external_lane_lands_it_and_no_worker_is_started`. A paused lane is never checked (manager 2026-11-02): its `builder done` records the head and says it waits, and the loop takes it after `builder queue resume`; a held lane reads `held` on the console, never `working`, even with fresh commits in its tree (tests `::test_a_paused_external_lanes_done_is_recorded_and_waits_for_resume`, `fichero-builder/tests/test_status_page.py::test_a_held_external_lane_reads_held_even_when_its_tree_has_fresh_commits`). Still owed: findings by `builder tell` into a named pane; **Owner trees** (built; the reviewer found it unspecified): when an external lane's worktree is outside `[jail].workroot`, `work.owner_tree` runs the chain's rebase, export and bundle as the owner, with no sudo and outside the jail, and the chain's shared state moves to `<state>/owner-trees`; a lane inside the workroot still runs them as the jail user. Test `fichero-builder/tests/test_work_verb.py::test_an_external_lanes_own_checkout_runs_its_chain_steps_as_the_owner`.
- `dev-workflows.run.loop-dispatch` [PARTIAL] (#6466; owner 2026-11-10: the harness runs with no model session watching it) — an external lane named in `[loop].dispatch` whose cursor step is `queued` is taken by the loop itself: the lane becomes a managed worker lane (`kind` worker, `fresh`, its own tree kept as `own_tree`, its pane forgotten; one `queue` row `managed`) in `[jail].workroot/wt-<lane>`, and from then on the worker-lane path runs it: a session started through the start path on the batch's brief (copied into the owner-made inbox, since the owner's state dir is unreadable by the jail user; `builder run` imports `fichero_builder` from the pinned copy for the same reason), its DONE row, the chain, the landing. `fresh`: the session is closed when its batch lands (or is already on origin), so every batch is a fresh session; the tree is rebased onto origin's tip before the next one. A batch retried with a head the worker's origin lacks starts from a bundle of that head (`base-lane-<lane>`, the mirror of the fetch). A lane not in `dispatch` still waits for its own `builder done`. Tests: `fichero-builder/tests/test_loop.py::test_a_dispatched_external_lane_is_managed_by_the_loop_one_fresh_worker_per_batch`, `::test_an_external_lane_outside_dispatch_still_waits_for_its_done`, `::test_the_loop_verb_reads_dispatch_and_blocked_hours_from_the_loop_table`, `fichero-builder/tests/test_work_verb.py::test_run_cmd_takes_the_package_from_the_pinned_copy_not_the_owners_checkout`, `::test_ensure_worktree_bases_a_managed_tree_on_a_bundle_of_the_steps_head`, `fichero-builder/tests/test_queue_verb.py::test_the_real_start_makes_the_worktree_and_runs_the_worker_side_with_its_feed_as_the_jail_user`. Not yet: a real managed session on the owner's Mac.
- `dev-workflows.run.loop-brief-preflight` [PARTIAL] (#6495; review 2026-11-10: a managed session sat 4.5 h on a brief written for the owner's own session) — before a worker lane's session is started on a brief (or a resume brief), the brief is read for what the jail user cannot do: a path under the owner's home (`~/...`, `/Users/<anyone but Shared>/...`), a `gh` command (unless `[jail].gh = true` says the jail holds a token), or the lane's own `done <lane>` (refused for a worker lane; a managed worker ends with its DONE line). Any of them: no session is spent; the step is `blocked` with one alert (actions retry, park) whose text names each finding and what to put in the brief instead (the files' text, the issue text, no done line). `retry` runs the same preflight again, so a brief that failed is never re-sent unchanged; the fix is to edit the brief file. Test `fichero-builder/tests/test_loop.py::test_a_brief_a_managed_worker_cannot_carry_out_is_refused_before_a_session_is_spent_and_retry_never_resends_it`. Not yet: a `WAITING:` last pane line flagged as needs-you.
- `dev-workflows.run.loop-session-ends` [PARTIAL] (#6496; review 2026-11-10: a lost `builder run` left its session alive 4 h 48 min, and a second start made a second window of the same name) — `stop` writes the feed's stop marker (a live `builder run` TERMs its pane on it within a tick) and, when no run watches that feed any more, ends every window named the lane on the workers' tmux server BY ID (`kill-window -t @N` as the jail user); `start` refuses while a window of the lane's name is up, naming its id and `builder queue stop <lane>`; the console's latest line reads each window by id, taking the one that moved last when two share a name. Tests `fichero-builder/tests/test_queue_verb.py::test_stop_kills_the_lanes_windows_by_id_once_its_run_is_gone_and_start_refuses_while_a_same_named_window_lives`, `fichero-builder/tests/test_status_page.py::test_live_lines_capture_by_window_id_so_two_windows_of_one_name_show_the_newest`, `fichero-builder/tests/test_queue_verb.py::test_start_closes_an_idle_window_of_its_own_name_itself_and_refuses_only_one_with_a_live_session`. Not yet: the lane remembering its window id at start. **Built** 2026-11-11 (alert 540): `start` closes an idle window of the lane's name itself (its pane runs a shell: `kill-window` by id, one `queue` row `window-closed`) and goes on; it refuses only a window holding a live session.
- `dev-workflows.run.console-status-cache` [PARTIAL] (#6498; review 2026-11-10: /api/status took 3-10 s and the page asked on every journal row) — `/api/status` is computed once per 3 s (`STATUS_TTL_S`); requests that overlap wait for the compute in flight; a worktree's last commit and its waiting count are read from git once per (worktree, HEAD, landing tip) and served from memory after; the page reloads status 2 s after the last journal row, never on a tick row, and every 15 s. Tests `fichero-builder/tests/test_status_page.py::test_api_status_is_served_from_a_three_second_cache_and_git_reads_are_once_per_head`, `::test_the_page_debounces_status_reloads_to_two_seconds_and_skips_ticks`. Not yet: the journal read once per cache fill (rows_of still reads the file per compute).
- `dev-workflows.run.console-tabs-refetch` [PARTIAL] (#6499; review 2026-11-10: the tabs went stale after 20 console rows) — the Milestones, Worktrees, Activity, Landing, Issues and Release tabs fetch again when the heartbeat, the landing tip or the newest console row's time changes, never on the console row count. Test `fichero-builder/tests/test_status_page.py::test_the_tabs_refetch_on_the_heartbeat_or_a_landing_never_on_the_console_row_count`.
- `dev-workflows.run.console-gh-in-the-repo` [PARTIAL] (#6497; review 2026-11-10: every planned milestone read 'not a git repository' under launchd) — every gh call that resolves the repository (the milestone's open and closed issue lists, from the console, the loop's build-order intake and `builder milestone`) runs with the checkout as its cwd, so the console's LaunchAgent, whose working directory is the state dir, plans milestones as the terminal did. Tests `fichero-builder/tests/test_milestone_verb.py::test_list_issues_runs_gh_in_the_repo_so_a_launchd_cwd_still_resolves_the_remote`, `fichero-builder/tests/test_status_page.py::test_milestones_run_gh_in_the_root_for_open_and_closed_issues`.
- `dev-workflows.run.console-worktrees-own` [PARTIAL] (#6505; review 2026-11-10: the tab listed other sessions' scratch checkouts and took 30 s cold) — the Worktrees tab lists only trees beside the checkout (its parent folder) or under `[jail].workroot`; a checkout under `/private/tmp` or anywhere else is another session's and is not shown; the auto refresh thread fills the worktrees cache, so a page open never waits for a cold read. Test `fichero-builder/tests/test_status_page.py::test_worktrees_skip_scratch_checkouts_under_tmp_and_the_refresh_thread_fills_the_cache`.
- `dev-workflows.run.console-one-spend` [PARTIAL] (#6503; review 2026-11-10: Spend today read $0 beside a usage card saying $73) — one spend number, today's and API-equivalent: an external lane's comes from its Claude Code transcripts (a Max session writes no cost row); a managed or Pi lane's from the workers' end-of-session `cost` rows in the shared journal (the jail user's transcripts are unreadable to the owner); the Spend card is the sum of both; a lane row's USD and turns are its own sum; each message or cost row is attributed to the batch whose `sent` row it follows, so the row shows `$x this batch` for the cursor step; the Tokens column is gone (the usage card keeps in/out). Test `fichero-builder/tests/test_status_page.py::test_one_spend_number_per_lane_and_per_batch_from_transcripts_and_the_workers_cost_rows`. Not yet: a managed lane's spend mid-session (its cost row comes at the session's end).
- `dev-workflows.run.loop-no-session` [PARTIAL] (#6500; review 2026-11-10: lane-sharing sat queued a day with a dead pane and no row) — an external lane whose registered pane is gone and whose worktree holds no Claude session is marked `no_session` (its pane cleared) only while its cursor step is `queued` (a session would move it) and at most once a lane a day: one `queue` row `no-session` and one alert (actions dispatch, park) saying nobody is on it; a lane that never registered a pane (the owner's own branch) is left to the intake rule. A session that appears later in its tree is taken and the mark cleared. `dispatch` on that alert sets the lane's own `dispatch`, which `manage` honours like `[loop].dispatch`: the loop runs it from the next tick. The console reads such a lane `no-session` (since when), the Needs-you strip lists it with Dispatch and Park buttons that answer its alert through the `alert` verb. Tests `fichero-builder/tests/test_launchd.py::test_a_dead_pane_with_no_session_to_take_marks_the_lane_no_session_once_with_an_alert_and_dispatch_hands_it_to_the_loop`, `fichero-builder/tests/test_status_page.py::test_a_lane_nobody_is_on_reads_no_session_and_the_strip_offers_dispatch_and_park`, `fichero-builder/tests/test_launchd.py::test_a_no_session_alert_is_one_per_lane_per_day_and_none_for_a_lane_whose_step_is_not_queued`. Not yet: a Start session button (no console verb opens an owner-side session).
- `dev-workflows.run.loop-owner-branch-lands` [PARTIAL] (#6501; review 2026-11-10: the ux lane had 63 commits waiting and no commit met the intake rule) — a lane named in `[loop].intake_any` is taken by the intake on its commit count or age alone, whatever its subjects say; and every external lane row on the console whose tree has commits past origin carries its HEAD and a Land now button that, after a confirm, posts the allow-listed `done` verb with that HEAD (one batch through check, review and landing). Tests `fichero-builder/tests/test_loop.py::test_intake_any_takes_an_owner_branch_on_count_or_age_alone`, `fichero-builder/tests/test_status_page.py::test_an_external_lane_row_carries_its_head_and_the_page_offers_land_now_through_the_done_verb`. Not yet: `intake_any` set for a lane (the owner's rules file).
- `dev-workflows.run.daily-builds-alert` [PARTIAL] (#6502; review 2026-11-10: alert 470 was a traceback tail, alert 474 offered no retry) — a red daily build's alert carries its `: RED` lines only; a daily-builds verb that crashes (any other non-zero exit) is a `daily-builds` row `not-run` holding its output and an alert `the daily-builds verb failed: <its last line>`; both offer `retry`, which drops the day's marker so the builds run at the next tick instead of tomorrow; the page shows park on a no-action alert, and its Dismiss says a blocked step behind it is parked. Test `fichero-builder/tests/test_queue_verb.py::test_a_crashed_daily_builds_verb_is_a_not_run_row_and_a_legible_alert_and_retry_reruns_it_now`. Not yet: the alert saying a red is environmental (the M4's default.profraw).
- `dev-workflows.run.console-events-true` [PARTIAL] (#6504; review 2026-11-10: four page defects) — Last events leaves out loop ticks and the timer's refresh rows (a lane error stays); Console actions leaves out the timer's refreshes, so the person's own actions stay; a lane whose cursor step is `done` with batches behind it reads `done` with `done, waiting for the check`, and `done, not landed yet` is kept for a lane through its steps; the blocked pill reads `blocked`, with the first line of why beside it. Test `fichero-builder/tests/test_status_page.py::test_events_and_actions_hold_no_ticks_or_auto_refreshes_and_a_mid_lane_done_step_waits_for_the_check`.
- `dev-workflows.run.loop-green-first` [PARTIAL] (#6506; review 2026-11-10: two retried reds held both chain slots while the first green managed batch waited) — a batch whose chain is ready is submitted only when a chain slot is free; with every slot busy it is held in the queue (one `waiting-for-worker` row per head, naming what runs), never queued FIFO in the pool. Each tick visits lanes green-first: a lane whose cursor step is a fresh `done` (a worker's DONE or its own `builder done`) before one whose step an alert `retry` re-took (`retry_of`, cleared by a new head). A retry writes one `queue` row `retry`; when the head equals the one the red was on, it says `same head and same rules as the red at HH:MM`. Tests `fichero-builder/tests/test_loop.py::test_chain_slots_go_green_first_a_fresh_done_before_an_alert_retry_and_a_full_pool_holds_the_batch_instead_of_queueing_it`, `::test_a_chain_waiting_for_the_pools_one_worker_says_so_and_a_free_pool_says_nothing`. Not yet: `[loop].lanes = 3` when the Pro is idle (a load rule the owner sets).
- `dev-workflows.run.console-since-build` [PARTIAL] (#6524; owner 2026-11-10: what to try after a build) — the Release tab's 'Since your last build' panel lists every issue the Fixes/Closes lines after the last green `build` row's sha close on origin/<branch>: its title and number (gh, read in the refresh thread and cached in console-release.json), one line to try (the issue's 'Done looks like' line, else the Test line of the spec behaviour the commit's Behaviour trailer names), and how it was checked from the commit bodies (window test; window test written, not run; unverified; else unit tests only); commits that only say 'Part of #N' are listed as worked on, not closed. 'Copy release notes' puts the same list, grouped by milestone, on the clipboard as markdown. No build row: the panel says so. Test `fichero-builder/tests/test_status_page.py::test_since_your_last_build_lists_each_issue_closed_after_the_last_dev_build_with_what_to_try_and_how_it_was_checked`.
- `dev-workflows.run.loop-retried-batch-lands` [PARTIAL] (#6507; 2026-11-10: lane-ie batch-59's two commits were blocked as 'DONE with no commit' and `builder done` refused on dubious ownership) — a worker's DONE whose `step` row says moved=false (HEAD equals the session's start head: a retried batch whose commits an earlier session made) still counts when the lane's tree has commits past origin/<branch> (`git cherry`); a tree with nothing past origin is still the block. The scratch tree's git (the presubmit and the ladder, run as the owner with the global config off) carries `-c safe.directory=*` like every other owner-side git call, so the jail user's tree is read. Tests `fichero-builder/tests/test_loop.py::test_a_done_with_no_new_commit_this_session_still_counts_when_the_tree_is_ahead_of_origin`, `fichero-builder/tests/test_presubmit.py::test_the_scratch_trees_git_trusts_the_lanes_tree_whoever_owns_it`. Still owed: a live `builder done lane-ie` on the jail tree (the owner's call).
- `dev-workflows.run.loop-approval-by-diff` [PARTIAL] (#6466; 2026-11-11: alerts 539 and 543 asked twice for one nine-file pinned diff at two heads) — an approve of a pinned-checks refusal (needs-maintainer, weakened-tests, pinned-new) is bound to the content of the refusal's diff (`git patch-id --stable` of the evidence file), not to the head: a later refusal of the same step whose diff has the same patch-id is approved by itself (the approvals the refusal lists set, one `queue` row `auto-approve`, no alert) and the check runs again; a diff whose content changed is the alert as before. The binding survives a newer `builder done` (it is not among the approvals a new head clears). Test `fichero-builder/tests/test_loop.py::test_a_pinned_diff_approved_once_is_approved_by_itself_at_a_later_head_with_the_same_diff_and_a_changed_diff_still_alerts`.
- `dev-workflows.run.loop-guard-data-by-content` [PARTIAL] (#6466; 2026-11-11: alert 541 asked again at a new head, and the presubmit refused a head NOT READY with the approval in hand) — an approve of a guard-data refusal records each named .json file's blob at that head (`approved_guard_blobs`); at any later head of the step where every file's blob is the one approved, HEAD's copies of those files are laid under the pinned guards by themselves (one `auto` row `guard-data-same-content`) in the chain's check and review and in `builder done`'s presubmit, which is then plainly green and needs no `--no-presubmit`; a file whose content changed is the manager's call again. The binding survives a newer `builder done`. Tests `fichero-builder/tests/test_loop.py::test_a_guard_data_approval_is_bound_to_the_known_gaps_files_content_and_holds_at_a_later_head_with_the_same_content`, `fichero-builder/tests/test_presubmit.py::test_the_presubmit_honours_a_guard_data_approval_bound_to_the_files_content`.
- `dev-workflows.run.loop-retry-keeps-head` [PARTIAL] (#6466; 2026-11-11: `retry` re-queued lane-ie's step 'at no head' and a fresh session re-did finished work) — the head a check judged is kept on the step even when red (`checked_head`; a worker lane's `head` is set only when green); `retry` on a step with such a head keeps it, sets the step `done` and runs the chain again with the green rungs of the last ladder reused (`retry_rungs`: the check resumes at the failed rung, as an approve does), starting no session; a step with no check behind it (a brief refusal, a start that failed) is re-queued as before. The retry row names the head, never 'no head'. Test `fichero-builder/tests/test_loop.py::test_a_retry_keeps_the_steps_head_and_reruns_the_check_from_the_failed_rung_instead_of_a_fresh_session`.
- `dev-workflows.run.presubmit-scratch-owned` [PARTIAL] (#6507; 2026-11-11: the manager's `builder done` could not add a worktree to the worker's clone, 'Permission denied' under its .git/worktrees) — when `git worktree add` of a scratch tree is refused for permissions, the scratch tree is a shared clone of the lane's repo at the same sha (objects by alternates, the remote refs fetched, every new file the invoking user's); the presubmit, the ladder and the build check judge it as they would a worktree, and `drop_tree` removes either kind after. Test `fichero-builder/tests/test_presubmit.py::test_the_presubmit_makes_its_scratch_tree_as_a_shared_clone_when_the_lanes_git_dir_is_not_writable`. Not yet: the land tree `done` makes after the presubmit, in a repo the invoker cannot write.
- `dev-workflows.run.brief-for-worker` [PARTIAL] (#6495; 2026-11-11, alert 544: a milestone brief named a crash log in the owner's home and ended with `done <lane>`, so the preflight blocked the step) — a brief for a managed worker is made the worker's instead of refused: before the preflight (in place, one `queue` row `brief-inlined` saying what changed) and at generation (`milestone.write_briefs` with a lane), every owner path is rewritten to `<an owner path not readable by workers; paste the text into the brief: name>` and every `done <lane>` line for the lane is cut; the jail's own paths are left alone. ONE exception, for the owner's hand-written brief (the step's own `brief` file) only: a FILE whose real path lies under `[jail].inline_paths` (default `~/Library/Logs/DiagnosticReports`, `~/Desktop/crash`; a link out of those folders is not followed) has its contents put below the brief, an excerpt capped at 4000 bytes with owner paths inside it rewritten. SECURITY (review of 864a4b5134): a resume brief carries the worker's own findings and a milestone brief carries an issue's text, so those are rewritten with NO allowlist and the loop reads nothing they name: a worker cannot have the owner-side loop copy a key or a token into its brief. What remains (a `gh` command) is still the preflight's alert. Tests `fichero-builder/tests/test_milestone_verb.py::test_only_an_allowlisted_owner_file_in_a_hand_written_brief_is_inlined_never_a_key_or_a_token_and_never_from_issue_text`, `::test_a_brief_for_a_worker_lane_inlines_an_owner_file_and_drops_its_own_done_line_instead_of_blocking`, `fichero-builder/tests/test_loop.py::test_a_fix_brief_built_from_findings_never_inlines_an_owner_file_even_under_the_allowlist`, `::test_a_brief_written_before_dispatch_is_made_worker_safe_before_the_preflight_so_an_owner_file_no_longer_blocks`.
- `dev-workflows.run.loop-already-landed` [PARTIAL] (#6466) — a batch whose chain finds no commit over origin/<branch> (every commit already there by patch) on an external lane is landed as it is (a worker lane's step with no commit is blocked, `local.no-commit-is-never-landed`): the step reads `landed` (`already on origin: ...`), the cursor moves on, nothing is pushed, no alert. Test `fichero-builder/tests/test_loop.py::test_a_batch_whose_commits_are_already_on_origin_lands_without_a_chain_and_the_lane_goes_on`.
- `dev-workflows.run.loop-blocked-watchdog` [PARTIAL] (#6466) — a `blocked` step never waits forever. `block` stamps `blocked_at` (a step blocked before this code is stamped when first seen); after `[loop].blocked_hours` (default 4) it is retried ONCE: a fresh session on its brief plus the question (`retry-<lane>-<step>.txt`; a worker lane's live session is closed first; an external lane with a head is re-taken as `done`), its alerts answered `retried`, one `queue` row `blocked-retry`. Blocked again that long, it is parked: moved to the end of its lane as `parked` with ONE alert (actions retry, park), so the batch queued behind it is the cursor's and nothing freezes; a parked step at the cursor waits for `queue resume`, an alert `retry`, or `builder done`. Test `fichero-builder/tests/test_loop.py::test_a_step_blocked_longer_than_the_limit_is_retried_once_in_a_fresh_session_then_parked_behind_the_next_batch`.
- `dev-workflows.run.loop-dismiss-parks` [PARTIAL] (#6466) — Dismiss and Dismiss All never orphan a step: every dismissed alert whose step is still `blocked` parks that step (as above); a step in any other state is untouched. An auto send-back (see `run.loop-alerts`) also raises its alert (actions send-back, retry, park), superseded by the lane's next done, so a lane with no pane is never silent. Tests `fichero-builder/tests/test_alerts_clear.py::test_dismissing_a_blocked_steps_alert_parks_the_step_and_the_lane_goes_on`, `::test_dismiss_all_parks_every_blocked_step_behind_its_alerts`, `fichero-builder/tests/test_loop.py::test_an_auto_send_back_raises_an_alert_too`.
- `dev-workflows.run.loop-auto-approve-pinned` [PARTIAL] (#6466; owner 2026-11-10 approved the harness fix's pinned diffs) — a maintainer lane's `needs-maintainer` refusal (and no other approval) is approved by itself only when every file its pinned diff names is in `[loop.approved_pinned]` at exactly that blob (`git rev-parse work-<lane>:<path>`): `maintainer` set for that head, state `done` again, one `queue` row `auto-approve`, no alert. A file not listed, a different blob, or a lane without `maintainer` is the alert as before; never by name alone. Test `fichero-builder/tests/test_loop.py::test_a_maintainer_lanes_pinned_diff_is_approved_by_itself_only_when_every_blob_matches_the_approved_list`.
- `dev-workflows.run.loop-cleanup` [PARTIAL] (#6589 item 16) — when a landed step's head is an ancestor of origin/<land branch>, the loop removes that step's `land-<lane>` snapshot worktree with `git worktree remove`, never `--force`; a dirty tree stays and one `cleanup` row says why (once, not every tick). A worker lane with no queued or open step left also loses its tree `wt-<lane>` and, only when its branch is merged into origin/<land branch>, the branch (an unmerged one keeps tree and branch, with a row). Each removal is a `cleanup` journal row. Tests `fichero-builder/tests/test_loop.py::test_a_landed_lanes_snapshot_and_a_finished_worker_lanes_tree_and_merged_branch_are_removed_each_a_row`, `::test_a_dirty_snapshot_stays_with_a_row_that_says_why`, `::test_a_lane_with_steps_left_keeps_its_tree_and_branch`, `::test_an_unmerged_lane_branch_is_kept`, `::test_a_snapshot_a_later_batch_is_using_is_not_removed` (a snapshot is removed only when its HEAD is the step's head and no non-landed step names the same tree). Not yet: a real run on the manager's Mac.
- `dev-workflows.run.loop-plan` [PARTIAL] (#6467; owner 2026-11-09: order the queue from the console, no manager) — `builder queue move --lane L --step S --to N` puts a queued or parked step at index N of the lane's steps (clamped to the cursor and the end); `queue park` sends a queued or blocked step to the end as parked; `queue unpark` makes a parked step queued; a landed step or one in flight is refused. `queue drop --text <why>` takes a PARKED step out of its lane for good, one `dropped` queue row holding the reason and its head; any other state, or no reason, is refused (#6589, 2026-11-15: superseded parks sat on the console for a week; test `fichero-builder/tests/test_queue_verb.py::test_queue_drop_takes_a_parked_step_out_of_its_lane_with_a_reason_and_refuses_anything_else`). The console's Plan clicks (↑ ↓ Park Unpark on a lane's queued steps, Start on a blocked, parked or idle lane = `queue resume`) are these verbs through `/api/action`, under the queue lock, no model in the path; `/api/status` says per lane `why` it waits (paused, held, finished, or the cursor step's state and reason) and its `queued` batches, and `events` (the last 15 queue, alert, loop, landed and console rows), shown on the page. Tests `fichero-builder/tests/test_queue_verb.py::test_queue_move_park_and_unpark_reorder_the_steps_behind_the_cursor_under_the_lock_and_refuse_the_rest`, `fichero-builder/tests/test_status_page.py::test_the_console_moves_parks_unparks_and_starts_through_the_queue_verbs`, `::test_api_status_says_why_a_lane_waits_and_lists_its_queued_batches_and_the_last_events`, `::test_the_page_wires_the_plan_clicks_to_the_queue_verbs`. Not yet (#6467 items 2, 3, 5): milestones and issue priority beyond the existing build-order reorder.
- `dev-workflows.run.loop-current` [PARTIAL] (#6466) — the loop's agents run with `PYTHONUNBUFFERED=1` and the loop's stdout line-buffered, so loop.log is current; `harness.toml` of the loop's root is part of the code mark, so an edit re-execs the loop at the next quiet tick as a code change does. Tests `fichero-builder/tests/test_launchd.py::test_the_agents_run_unbuffered_so_loop_log_is_current`, `fichero-builder/tests/test_loop_survives.py::test_a_rules_edit_changes_the_code_mark_so_the_loop_re_execs`. Was: (#6589) the five `[loop]` keys of `dev-workflows.run.restart-rules-per-tick` are read at every tick and are left out of the mark, so editing them does not re-exec; every other rule is still in the mark.
- `dev-workflows.run.restart-resets-nothing` [PARTIAL] (#6589; owner 2026-11-15: restarting the builder resets nothing) — a worker's `builder run` starts in its own session (`start_new_session`) and the loop's LaunchAgent sets `AbandonProcessGroup`, so `launchctl kickstart -k local.builder.loop` does not kill the worker tmux server and no lane restarts its session. Tests `fichero-builder/tests/test_builder_restart.py::test_the_loop_agent_abandons_its_process_group_so_a_kickstart_leaves_the_workers`. Not yet: a real kickstart on the manager's Mac.
- `dev-workflows.run.restart-adopts-live-window` [PARTIAL] (#6589) — a restarted loop with no handle for a `sent` step adopts the lane's live session (its `builder run` still watches the feed and a tmux window named for the lane runs more than an idle shell): it keeps watching it, one `adopted` queue row, and stops nothing; a session it cannot adopt is stopped as before. Tests `test_builder_restart.py::test_a_restarted_loop_adopts_a_live_session_and_stops_nothing`, `::test_a_restarted_loop_still_stops_a_session_it_cannot_adopt`, `::test_adopt_session_takes_a_live_window_named_for_the_lane_with_a_fake_session`.
- `dev-workflows.run.restart-rules-per-tick` [OK] (#6589) — `[loop]` of harness.toml (`only`, `dispatch`, `rounds`, `blocked_hours`, `approved_pinned`) is re-read at every tick, so a new lane needs no restart; an unreadable file keeps the last settings; these five keys are left out of the code mark, so editing them re-execs nothing (the rules the loop reads once stay in it, see `dev-workflows.run.loop-current`). Tests `test_builder_restart.py::test_harness_toml_loop_is_read_at_every_tick_so_a_new_lane_needs_no_restart`, `fichero-builder/tests/test_loop_survives.py::test_an_edit_to_the_per_tick_loop_keys_leaves_the_code_mark_alone`.
- `dev-workflows.run.restart-on-builder-landing` [OK] (#6589) — the loop re-execs itself between ticks only when a landing changed `fichero-builder/` or an edit changed a rule the loop reads once (the code mark); an edit to the per-tick `[loop]` keys never does; a live worker session no longer holds it off, since the new loop adopts it; a running check or dev build still does. Test `fichero-builder/tests/test_builder_restart.py::test_a_rules_edit_alone_is_not_a_re_exec_and_a_changed_package_is_even_with_a_live_session`.
- `dev-workflows.run.loop-external-intake` [PARTIAL] (#6116; manager 2026-11-02, owner-delegated) — a lane that commits on its own
  branch is landed with no manager step. Trigger: `builder done <lane> [--sha S]` (S = the lane's HEAD when it runs; later commits
  go in the next batch), or the loop by itself when an external lane has `[loop].intake_commits` commits (default 8) or
  `[loop].intake_hours` (default 3) since its last landed batch and its HEAD subject is a finished step (`(Step ` or a
  `Behaviour:` trailer); a lane added with `--hold` (a milestone a person holds) is never taken. One batch per lane in the ladder
  at a time. Take: the lane's own worktree and branch are never touched (an agent works there): the loop makes or refreshes
  `land-<lane>` beside it at S and the chain rebases that onto origin/<land branch> as the owner; a conflict is a send-back.
  Check and review as for any lane, never `--maintainer` for a product lane; a rerun after a send-back is a delta review. Any red
  rung, refusal or NOT READY writes `findings-<lane>-<n>.txt` under the state dir, tells the lane's registered pane (`queue add
  --pane %N`, through `[loop].tell`) and, for the first three in a batch, is one `auto-send-back` row and no alert, then an alert (manager 2026-11-03); the lane fixes on its branch and runs `done` again, which re-takes from its new
  HEAD. Land: `landed --push` with full shas and the engine repo; then the lane is told `LANDED <sha>, rebase onto
  origin/<branch> at your next step boundary` and `land-<lane>` is swept (patch first). Console: an external lane row shows its
  stage and the commits waiting since its last landing. Test (a file of that name exists; whether it covers this behaviour is owed a check, Phase 0): `fichero-builder/tests/test_loop.py` (done snapshots the
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
  Built 2026-11-05 (Install worked for the test Macs but not this one): the console lists the dev DMGs still on disk, newest first per path, each with its size, build time, sha and whether it was built with uncommitted changes (`/api/builds`, from green `build` rows only); Download streams one (`/download/<sha>`, only a path a `build` row names, loopback only); Show in Finder (`open -R`) and Open on this Mac (`open`, which mounts it) act on this Mac (test `fichero-builder/tests/test_status_page.py::test_the_console_lists_the_dev_builds_on_disk_and_downloads_one_only_by_a_build_rows_sha`).
  Start as one lane (owner 2026-11-02): ticked open issues in the Milestones view become one lane, `builder lane <name> --issues
  N...`: one cluster brief from them (the brief tool, as `builder milestone` writes them), queued as a worker lane in the jail; a
  lane already working is refused. Test `fichero-builder/tests/test_queue_verb.py::test_ticked_issues_become_one_lane_with_one_cluster_brief`.
  Run tests (owner 2026-11-02): `builder test <paths...> [--head S]` runs the pinned pytest over those paths in a scratch tree of
  origin/<land branch> (or S), as the jail user, on `[check].remote` when one is set, one pytest per package; one `test` row; the
  console's Release view runs it. Test `fichero-server/tests/unit/workflows/test_check_tool.py::test_run_tests_runs_the_named_paths_in_a_scratch_tree_of_the_head`.
  Run check (built 2026-11-02): `builder check-lane <lane>` (the console's Run check on a lane's row) fetches the lane's HEAD into
  the engine repo as `work-<lane>-check` and runs the pinned ladder over it in a ladder slot: a `check` row and GREEN or RED printed;
  no review and no landing (an external lane's `builder done` does those). Test `fichero-builder/tests/test_loop.py::test_run_check_fetches_the_lanes_head_and_runs_the_pinned_ladder_over_it_and_lands_nothing`.
- `dev-workflows.run.tell` [PARTIAL] (#6116; manager 2026-11-02) — `builder tell <pane> <message>`: the tracked tell (the
  manager's tell.sh was untracked, so another machine lacked it): it waits for an unsent draft to leave the input box, types,
  presses Enter and again while the text sits there; a message over 400 characters is written to `<state>/tells/` and the pane
  gets `Read <path>` (a long one arrived as its last line only). The loop and `builder measure` use it unless `[loop].tell` names
  a script. Test `fichero-builder/tests/test_tell.py`.
  The worker side does the same (#6589, manager 2026-11-19): the run's own tell into its pane (`run._tell`, the feed's next
  brief and the DONE nudge) presses Enter again, up to 3 times, while the words still sit in the input line; a swallowed
  Enter left review briefs unsent for hours. Test `fichero-builder/tests/test_dry_run.py::test_tell_presses_enter_again_while_the_words_still_sit_unsent_in_the_input_line`.
- `dev-workflows.models.review-by-path` [PARTIAL] (#6116; manager 2026-11-02, speed item 6a) — the review model is
  `[models].reviewer_fast` (sonnet) by default and `[models].reviewer` (opus) when the range touches `[models].reviewer_paths`
  (the harness, land and jail paths: fichero-builder/, scripts/harness_*, scripts/lane_ready_check.sh, harness.toml), and for a
  worker lane's last step of its milestone (one opus pass per milestone); the review's `activity` row names the model. Test
  `fichero-builder/tests/test_work_verb.py::test_the_review_model_is_sonnet_unless_the_range_touches_harness_paths_or_it_is_the_milestones_last_step`.
  Built 2026-11-06 (owner, t28: a lane's half-done fast reviews cost it whole rounds): `[models].opus_lanes` names lanes whose every batch gets the full reviewer, whatever paths it touches; lane-sharing is the first (test `fichero-builder/tests/test_queue_verb.py::test_a_lane_named_in_opus_lanes_gets_the_full_reviewer_and_others_the_fast_one`).
- Soak fixes 2026-11-02 (manager): a milestone whose spec an external lane's brief names is never planned (`owned` row: the loop
  planned Sharing while lane-sharing worked it); a planned milestone's unplaced issues are ONE alert listing them (was one per
  issue) with park; an alert with no actions, or whose lane is gone, can be parked; retry or approve on an external lane's step
  re-takes its snapshot (a retry had left it waiting for a done); a lane paused after the tick loaded it never starts a step
  (the start re-reads the file); a lane's `pane` and `hold` set from outside survive the tick's write; a NEW table in
  harness.toml is a warning row at the loop's start, never a refusal (a near-miss of a known table still refuses as a
  misspelling); a run that cannot collect a test file says `could not collect <file>: <error>`; the Builder's tests import
  their siblings without a `tests.` prefix, so the ladder can run them under the engine's pytest config. Tests in
  `fichero-builder/tests/test_loop.py`, `test_main.py`, `fichero-server/tests/unit/workflows/test_check_tool.py::test_a_collection_error_says_which_file_could_not_be_collected`.
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
  an owed test `test_rules_file.py` (for the `workflows` tests),
  `fichero-server/tests/unit/workflows/test_rules_problems.py::test_each_gap_is_a_named_problem`,
  `fichero-server/tests/unit/workflows/test_brief_tool.py::test_the_brief_script_refuses_a_misspelt_brief_key_and_prints_no_brief`,
  `fichero-builder/tests/test_watcher.py::test_the_table_is_read_and_an_unknown_key_or_bad_price_refuses`.
- `dev-workflows.run.ratchet` [PROPOSED] (maintainer 2026-10-31: it only improves) — from the rows: READY to landed, first-pass
  READY rate, findings per issue by kind and severity, stall hours, false done, rework rounds, cost per landed issue, as a
  TSV per run and per week; a finding of the same kind on two issues becomes a rule in the rules file or a `check` rung
  (the spec-diff check is the first: a behaviour change touching no spec line is red in `check`, not in review); the
  backslide guard in the `check_*_ratchet.py` pattern is added once four weeks of rows exist. Test:
  an owed test `test_ratchet.py` (for the `workflows` tests).
- `dev-workflows.run.supervision` [PROPOSED] — a supervisor (the Lead, the maintainer) can stop any worker or the harness (a
  hold blocks landing and closing), inspect rows, log, handoffs and the clone, and set a task aside as needs-maintainer;
  every action a row with who and why. Test:
  an owed test `test_supervision.py` (for the `workflows` tests).
- `dev-workflows.node.human-question` [PARTIAL] (#6116) — a small **question record** (task, generation, text, options, the
  artifact, asked-at, answer, answered-by) written by the `ask` tool, which parks the task; the parked worker is ended and
  its successor resumes with the answer; a question survives an engine restart because it is a row; it is answered from
  Activity, the Research workspace, the CLI or a page; a recipe's `HumanReviewRequest` is written to the same record so
  there is one queue. Test:
  an owed test `test_pause_resume_survives_restart.py` (for the `workflows` tests).
- `dev-workflows.rollout.dry-run` [PARTIAL] (#6116) — the loop runs with no model and no money: `builder run` takes its
  process control (start, alive, stop, read the session file) as a small object, and the dry run swaps in fakes with a
  scripted sequence of session states. Built 2026-11-01: a missing price refuses before anything starts; a healthy worker
  that ends leaves one `worker` row and one `cost` row; an idle worker is ended on its DONE line and left alone without it
  while its branch has not moved; idle with the branch moved and no good DONE line (none, or one naming another sha) for two ticks it is nudged once with the
  exact line to end on, through the pane, and still idle two more ticks later, even after a reply without the line, it is ended `done-unsaid` (a `watch` row, the cost row's end, exit
  0, and `builder work` goes on to the check, because the branch holds the work; tests `fichero-builder/tests/test_dry_run.py::test_a_done_line_naming_the_wrong_sha_on_a_moved_branch_is_nudged_and_ended_too`, `::test_a_worker_that_answers_the_nudge_without_the_line_still_ends`, `fichero-builder/tests/test_work_verb.py::test_a_worker_that_committed_and_never_said_done_goes_on_to_the_check`); a hand brief that carries no DONE instruction is started on a copy in the worktree that does (built 2026-11-01,
  `fichero-builder/tests/test_dry_run.py::test_an_idle_worker_whose_branch_moved_but_said_no_done_is_nudged_once_then_ended_done_unsaid`,
  `::test_a_hand_brief_without_the_done_instruction_gets_it_added_in_the_copy_the_worker_is_started_on`);
  the session cap hands off to a fresh session (the old pane is stopped) and only the day cap parks; a silent
  worker alerts once and is not stopped; a handoff decision is recorded. Not yet: recorded hook events replayed through the
  real policy (a refused command, a weakened test, a pinned-path edit, an acceptance-line change), a question and its
  answer, a false done, a NOT_READY round, land and close against a fake `gh`. Test: `fichero-builder/tests/test_dry_run.py`.
- `dev-workflows.rollout.pipeline-frozen` [PROPOSED] (maintainer 2026-10-31) — `pipeline/` takes no new code; the engine
  calls the `scripts/` guards directly and ports what it needs; it is removed once the engine has landed real clusters
  for two weeks. Test: an owed test `test_pipeline_frozen.py` (for the `workflows` tests).
- `dev-workflows.rollout.slice-zero` [PROPOSED] (manager 2026-10-31) — § 0, as written: the cluster #6100, #6085, #6107
  within two to three days on today's tmux builder, as the second user, with the rules file, hooks, `check`, `land`
  (the Lead pushes), the brief fix, the checklist file and the B1 fix; done when the cluster is on the integration branch
  with a verdict per patch-id. The proof is the cluster itself; its rows seed the ratchet. Test:
  an owed test `test_slice_zero.py` (for the `workflows` tests).

#### C. Records, sync, surfaces

- `dev-workflows.combined.entities` [GAP] (#6116) — one model of project work: Project = `ResearchProject`, Milestone =
  `ResearchPlan`, Issue = `ResearchTask` (+ GitHub URL, plan step, behaviour ids), Comment = a `ResearchNote` **marked
  public** (a note is local until marked), Run = a job row, Question = the question record; GitHub's names in the app,
  API and CLI, storage names behind aliases. Test:
  an owed test `test_combined_model_records.py` (for the `research` tests).
- `dev-workflows.combined.github-sync` [GAP] (#6116) — pull with `gh` every five minutes and on open, **incrementally by
  `updated_at`**; Fichero's edits go out through one guarded step: a typed operation within the allow-list, the **public
  boundary**, then the journaled writer; every write, refused or made, is a row. The boundary is the same grep `land`
  runs from Slice 0 (people list, home-path shapes, secret shapes); a hash list of private page text is **deferred**: it
  would make the land path read private libraries. Conflict rule: GitHub wins on work state, Fichero on its own fields,
  a text conflict is a question. Step 2.2 pulls only; the push through the same guarded step follows in Step 2.4. Test:
  an owed test `test_github_sync.py` (for the `research` tests).
- `dev-workflows.surface.one-action-layer` [PROPOSED] — `fichero workers …` and the MCP tools (the generated surface) list
  specs, milestones, issues and tasks, start a cluster or a research task, show workers and questions, answer, approve;
  every verb is an audited action; a chat verb is added only when these prove thin. Test:
  an owed test `test_chat_dev_verbs.py` (for the `tests` tests).

#### D. Models

- `dev-workflows.models.by-config` [PARTIAL] (#6116) — the rules file names **one model per role** (builder, reviewer, spec-writer,
  helper, researcher): provider (`anthropic`, `openrouter`, `omlx`, `mlx_lm`, `claude-code`), model, precision, context cap;
  today builder Sonnet, reviewer Opus, spec-writer Fable for a rewrite and Opus for a small spec, approved by the owner; a
  missing provider is a **question**, never a silent fallback; a role changes model only by a person editing the file
  after reading the run log (READY rate, false done, writes outside the worktree, reviewer agreement per model). Test:
  Built 2026-11-01: `harness.toml` [models] (`providers` and one `{provider, model, context?}` row per role) read by
  `fichero_builder/models.py`; a missing role or a provider not in `providers` raises a Question. Still owed (Phase 0 wording): `builder run`
  and the reviewer start read their model from it (they still take `--model`). Test:
  `fichero-builder/tests/test_model_config.py::test_one_model_per_role_and_a_missing_provider_asks`. Per-lane role (owner 2026-11-18):
  `builder queue add --role <name>` records the role on the lane; its worker, and every handoff successor, starts on that
  role's model and hands off at 85 % of that role's `context`; a role missing from `[models]`, or whose provider is not in
  `providers`, is refused at add time with the reason, never replaced by `builder`; the journal's `worker` and `cost` rows
  carry the role. Tests: `fichero-builder/tests/test_lane_role.py`.

#### E. UX

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
  an owed test `test_controls_reach_the_call.py` (for the `workflows` tests).

#### F. Researcher and the web

- `dev-workflows.researcher.tasks` [PROPOSED] — three first tasks: **find sources** (search → fetch through the existing guards
  → `SearchSource` with title, URL, date, a one-line why and the quote it rests on; no quote, no save; duplicates by URL
  refused); **search the libraries** (`local_search` and KG over the person's open libraries); **read and note** (notes
  citing source and quote; one source per 16-32k session with handoff; a synthesis that does not fit goes to an allowed
  cloud model or is refused with the reason). Each task runs with its own capability set (`two-capability-sets`), keeping
  the data diode `research/tools.py` declares. The in-app loop is the chat tool loop **extracted to a task runner**: a
  detached run with an iteration budget, a context count, the handoff, a Stop and a row. One search provider (the
  existing one); another is added when it fails. Test:
  an owed test `test_researcher_tasks.py` (for the `research` tests).
- `dev-workflows.security.untrusted-text` [GAP] (#6116) — issue bodies, titles, comments, spec text and fetched pages reach a
  model only as fenced, labelled data. Researcher: the turn that reads them has no write tool; anything proposed is acted
  on by a later script step with a fixed argv. Builder: the defence is the trusted-author filter plus the user boundary,
  said plainly. No token, key or credential reaches state, rows, log or captured output: the bounded log gains a
  redaction of known shapes (today it only bounds). Test:
  an owed test `test_untrusted_text.py` (for the `security` tests).

#### G. Any project, any model

- `dev-workflows.project.neutral` [PROPOSED] (maintainer 2026-10-31) — harness code (hooks, tools, `check`, `land`, the tick, the
  templates) carries no project **string**: no branch name, path, command or guard name; all of it comes from the rules
  file and the checklist; a guard greps the harness code for the first project's branch, path and command strings and
  fails on a hit (module imports are not strings). The second project is a small Python-tested CLI repository with one
  shell guard: it runs a two-issue cluster through brief, build, check, review, land and close on a scratch remote from
  its rules file alone, and the cluster lands green. Test:
  an owed test `test_second_project.py` (for the `workflows` tests).
  Built: (2026-11-04, review 97) a harness file the guard lists that is not in the tree FAILS the guard, named, instead of being skipped, so a moved or empty tree never reads as neutral (#4382; test `fichero-server/tests/unit/workflows/test_harness_neutral.py::test_a_listed_harness_file_that_is_gone_fails_the_guard`).
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
  an owed test `test_local_parity.py` (for the `workflows` tests).
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


### From `agent-profiles.md` — Behaviours


#### A. The trailer (first, because every worker commits)

- `agent-profiles.trailer.one-line` [PARTIAL] (#6622) (owner 2026-11-05: one `Written-By:`; 2026-11-16: its shape) — every
  commit a worker makes carries exactly one trailer, the last line: `Written-By: <MODEL> using <HARNESS> using Fichero
  Builder`, MODEL the display name that `harness.toml` `[models.display]` gives the alias the worker was started with (`sonnet` is `Claude Sonnet 5.5`; a name not listed, such as `Qwen3-Coder-Next`, passes through unchanged; test: `fichero-builder/tests/test_profiles.py::test_the_trailer_names_the_model_by_its_display_name_from_models_display_and_an_unknown_name_passes_through`), e.g. `Written-By:
  Qwen3-Coder-Next using opencode using Fichero Builder`. No `Co-Authored-By`, no `Directed-By`; the one other trailer allowed is `Spec-change: <what and why>, ruled by the owner|manager` above it, on a commit that changes a behaviour's acceptance text (`dev-workflows` spec-acceptance check; manager 2026-11-24: the two rules contradicted, and reviews refused what the check demanded). The
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

#### B. Profiles: one folder, one common prompt, roles, a thin project layer

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
  the text to the adapter; the brief stays the first user message. The worktree's own `CLAUDE.md`, `.claude/`,
  `AGENTS.md`, `.gemini/`, `.codex/`, `opencode.json` and the like are **never** a worker's rules (a worker can edit
  them): each adapter passes the setting that disables project and user instruction files where the harness has one
  and says in `capabilities.md` when it has none. Acceptance: the dry run shows the assembled text in the adapter's argv
  or file; a planted `CLAUDE.md` saying "push to main" changes nothing the worker is told. Test:
  fichero-builder/tests/test_profiles.py, case test_assembly_order_and_a_planted_file_is_not_obeyed. Built: the Claude Code start. Not built: the Pi start.

#### C. Adapters

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

#### D. Required MCP servers; project profile; declared workflows

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
  row; the assembled prompt names exactly the delivered servers. Test: fichero-builder/tests/test_mcp_servers.py. Built: `mcp_servers.delivered`, written into `mcp.json` by `start_tool.prepare` (Claude Code only); a stack's `tools:` line replaces the role's whole list; the index prefix exits 71 on a failed build and `work.do_run` journals a `refused` row. The refusal of a missing server applies only when `[jail].require_index` is set; without it the server is left out and an `mcp-missing` row is journaled. Not built: the repo's `harness.toml` sets no `[jail].doc_map`, `doc_index` or `require_index`, so the requirement is off for Fichero's own workers; and `agents/roles`, `stacks`, `projects` hold no files yet, so no worker gets an optional server.
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

#### E. Small, circumscribed workers

- `agent-profiles.worker.small` [GAP] (#6625) (owner 2026-11-16) — a worker gets **one step**, a brief under 120 lines
  that names its files and its tests by path, and a diff bound **per role** (owner 2026-11-16: no single global
  number): a `diff_bound:` line in `roles/<role>.md`, lines changed with generated files excluded, smaller for
  bug-fixing and code-review, larger for the feature role; the bound is the role's whatever the stack; a role file with no bound refuses to start; the brief tool refuses a cluster with more than one step or a brief over the line cap, the policy hook
  counts the bound and the worker is told once then parked with a question; a step whose named files exceed the
  bound is split by `builder steps` before any brief. Acceptance: a two-step brief refuses; a 121-line brief refuses;
  a diff past the role's bound yields one tell and then a park row; a role file with no `diff_bound:` refuses; a brief
  with no named test is refused for a code project. Test (to write): fichero-builder/tests/test_small_worker (new).

#### F. Swift rungs and the UI smoke

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

#### G. Runs, comparison, the console, cleanup

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

#### H. The built-in manager role

- `agent-profiles.role.manager` [GAP] (#6638) (owner 2026-11-16: acts within rules) — a `manager` role the builder
  starts on the owner's side (never as the worker user; `gh` read, the journal, no push), supervised by the human
  manager. Within rules, on its own: retry a failed start, dismiss a report-only alert, write a fix brief for a
  NOT_READY verdict, queue the next step of the first unfinished milestone through `builder milestone`, start a
  successor for a parked or dead worker, re-run a `not-run` rung whose reason is known. Everything else is a
  question with its proposed answer. It never lands, pushes, edits `harness.toml`, closes an issue or spends past a
  cap; every action is a row naming the rule. Prompt `roles/manager.md`; model `[models].manager`. Acceptance (dry
  run, fake journal): a parked-at-cap row yields a successor; a NOT_READY row a brief file; a report-only alert a
  dismiss row; a question with no rule a question row and no action; a push attempt is refused. Test (to write): fichero-builder/tests/test_manager_role (new).
  Phase 0 amendment (owner 2026-11-17/18, from the cut `agent-profiles.role.manager`): the manager runs on a local model in Pi; it may feed lanes, pause, resume, requeue, park, file issues and answer routine worker questions, and may never relax a check.

#### I. The bake-off

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

#### J. Worker isolation (owner 2026-11-16: a long step of its own, after the adapters)

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
  Phase 0 amendment (owner 2026-11-17/18, from the cut `agent-profiles.isolation.implemented`): the probes also prove: no GitHub login, ssh key or keychain item in the worker's reach; the model key capped by a hard spend limit or held by a relay on the loop's side; network limited to the model endpoint, the package registries and read-only GitHub; nothing sensitive in shared or temporary folders; limits on disk and run time; signing keys in a keychain only the release script unlocks. A probe that gets through refuses the start.


### From `builder-console.md` — Behaviours


#### A. One live source of work (milestones › steps › lanes)

- `builder-console.ordered-work.one-source` [PARTIAL] (#6645) (the order is `docs/contributor_manual/specs/build-order.md`, hand-edited
  last 2026-11-04, while tonight's lanes were queued by hand around it) — the ordered list of milestones the loop works is
  a record in `<state>/work.json`, written only by verbs: `builder order` (the console's drag, `builder milestone --enqueue`,
  `builder lane`, `queue add`) and `builder triage --order` (appends, never reorders). Every lane names its milestone and
  step; a lane started by hand on issues joins the tree under its issues' milestone (or `unfiled`, shown first, never
  hidden). The list's rows are GitHub milestone titles, so a spec name with no milestone (`dev-workflows` today) is refused
  with the milestone to make, never dropped. `build-order.md` becomes a generated copy written at each landing of the
  order, marked as such, never read. Acceptance: `queue add --lane x --issues 6600` puts lane x under `performance-sweep`;
  an order edit from the page is one `order` row and the next tick feeds from it; a name with no milestone is refused by
  name; the page and `builder status --json` show the same order. Test: fichero-builder/tests/test_work_tree.py. Built: `<state>/work.json` holds the order (`work_tree.read_order`, `write_order`); `queue add --issues` writes the lane's `milestone` from its issues (`unfiled` when none is in one, refused when they span two); `builder order` refuses a title with no GitHub milestone by name and writes the record after a successful save; `work_tree.append_order` is the append-only form. Not built: the loop's intake, the console and `status --json` still read `build-order.md`; nothing generates `build-order.md` from the record; `builder triage --order`, `milestone --enqueue` and `builder lane` do not call `append_order` or write the lane's milestone.
- `builder-console.work.counts-are-live` [PARTIAL] (#6645) — each milestone row shows, from the work tree and the journal, not from
  issue counts: steps queued / running / waiting for check or review / blocked / done-not-landed / landed / closed-out,
  each with the oldest age in that state, the lane holding it, and the last failure (the newest red rung, NOT READY
  finding or question, one line). GitHub open/closed counts stay as a second, labelled pair ("GitHub: 31 open · 26
  closed"), never as a step state. "Lane running" means a lane with a non-final step; a finished lane is "last lane:
  <name>, landed <ago>". Acceptance (fixture tree): a milestone with one checking step and one blocked step shows both
  with ages and the blocked one's question; a milestone whose only lane is finished shows no running lane. Test:
  fichero-builder/tests/test_work_tree.py, case test_counts_come_from_the_tree. Built: `work_tree.counts` over the lanes' steps. `closed-out` is the `parked` group. Not built: the on-origin check no caller passes yet (without it `done-not-landed` is never produced), the console page reading it, the GitHub open/closed pair beside it, the lane's `milestone` key being written.
- `builder-console.store.one-database` [GAP] (#6644) (today: `queue.json`, `journal.jsonl`, `ladder-<lane>.json`, `review-<lane>.txt`,
  `question-*.txt`, `fix-*.txt`, read and joined by `console.py`) — the state of milestones › steps › lanes › runs › alerts
  › edits is one store, `<state>/harness.duckdb` (DuckDB, the database Fichero already uses, one file; owner 2026-11-16),
  with typed records (Pydantic models, one module, no engine import); `journal.jsonl` stays the append-only event log every change also writes, so a store rebuilt
  from the journal gives the same rows. The ladder and review results are rows (rung name, exit, seconds, tails; verdict,
  findings) keyed by lane, step and round; the text files are kept as attachments by path. `queue.json` is migrated on first
  open with a row and then never written. Every verb and every page reads the store through one module; nothing parses
  the journal to answer a page. Acceptance: a fixture journal replayed gives a store equal to one built live; the console's
  `/api/status` from the store equals today's for the fixed-rows test; a crash between a journal write and a store write
  is repaired on the next open. Test (to write): fichero-builder/tests/test_store (new).
  Phase 0 amendment (owner 2026-11-17/18, from the cut `builder-console.store.one-database`): the one database is SQLite (owner 2026-11-17), rebuilt from journal.jsonl by one command; nothing edits the journal.
- `builder-console.work-store.host-agnostic` [PARTIAL] (#6644) (today `gh api`, `gh issue` in `console.py`, `milestone.py`, `landed.py`)
  — milestones, issues (steps' items), comments and labels are read and written through one interface, `WorkStore`:
  `milestones()`, `issues(milestone)`, `comment(issue, text)`, `label(issue, …)`, `close(issue, residue)`, `create(…)`, with
  three implementations chosen in `[project].work_store`: a public GitHub repository, a private GitHub repository (same
  code, a token), and a private store inside Fichero (the engine's records, for Fichero Researcher). The harness's own
  state (§ A.3, the step states, ages and runs) is never in the work store; only the items are. A store that is unreachable
  makes the loop keep working from its last copy and raises one alert, never stops a lane. Acceptance (fake stores): the
  loop runs a lane to landed on the GitHub store and on the in-Fichero store with the same rows; an unreachable store
  yields one alert and the lane goes on. Test: fichero-builder/tests/test_work_store.py. Built: `work_store.py` with the `WorkStore` interface, `GithubStore` (over `gh`) and `open_store`. Not built: the private-GitHub and in-Fichero stores, `[project].work_store`, the callers (`console.py`, `milestone.py`, `landed.py` still run `gh`), the unreachable-store alert.

#### B. One state and an age per step; stale work is surfaced and acted on

- `builder-console.step.one-state` [PARTIAL] (#6643) (lane-qwen shows `done`, `paused`, and `blocked 4 h: retried once` at once;
  `done` means both "lane finished" and "worker said DONE, check pending") — a step is in exactly one of: `queued`, `sent`,
  `said-done` (DONE received, check not run), `checking`, `reviewing`, `fixing` (round n of 2), `blocked`
  (question, with the question), `red` (check failed, with the rung), `done-not-landed` (green and READY, not on the
  integration branch), `landed`, `parked` (`queue.STATES`). `paused` and `held` are **lane** flags shown beside the state
  ("said-done · lane paused since 11-08"), never a state; a lane is `finished` only when every step is final. `why` is the
  reason for the *current* state and is cleared on every transition (`queue.py` keeps the blocked reason on a `done` step
  today). Each state has an entered-at time; the page shows the age in words. Acceptance: a step through
  queued → sent → said-done → checking → red → fixing → said-done → checking → reviewing → done-not-landed → landed has at
  each point one state, a `why` about that state, and an age that resets; pausing the lane changes the flag and nothing
  else. Built: `queue.state_view` and the `entered_at` stamp; the console page does not show the state, age and flags yet. Test: fichero-builder/tests/test_step_state.py.
- `builder-console.stale.acted-on` [GAP] (#6646) (a week-old half-finished lane is a defect, owner 2026-11-16; 30 of 50 lanes today
  are finished-but-listed, two are 9-day-old paused trials, one is blocked on a question since 11-08) — every tick the loop
  lists each step older than `[loop].stale_hours.<state>` (defaults: said-done 1 h, checking 3 h, reviewing 3 h, fixing
  12 h, red 12 h, blocked 48 h, done-not-landed 24 h, queued 7 d, sent/working 2 × the step's usual run time) and acts,
  one action per step per tick, each a `stale` journal row naming the step, its age, the action and the result:
  `said-done` → run the check; `checking`/`reviewing` with no live activity → restart it; `red` → one re-brief with the
  rung's tail, then `blocked`; `fixing` past the rounds → `blocked`; `blocked` → ask again once (`builder ask`), then after
  `[loop].stale_hours.blocked` again file the residue as an issue and `closed-out`; `done-not-landed` → rebase and land, or
  `blocked` with the conflict; `queued` with its waits met → send; a paused or held lane past 7 d → an alert "retire or
  resume", and `retired` after 7 more unanswered. Nothing is ever silently left: a step the loop cannot move has an open
  alert, and the page's "Needs you" lists it with its age. Acceptance (fake clock, fake journal): each state past its
  hours gets its action and row; a lane paused 15 d is retired with a row; a step under its hours is untouched; the
  `stale` rows for one tick never act twice on one step. Test (to write): fichero-builder/tests/test_stale (new).
- `builder-console.step.moves-on` [PARTIAL] (#6646) (the queue feeds the next brief after a landing; a finished lane stops; a
  closed-out or retired step does not advance the cursor) — when a step reaches a final state the lane takes its next step
  itself, in the same session when one is open, else a fresh one; a lane with no step left takes the next step of its
  milestone from the work tree, and a milestone with none left frees the lane for the next milestone in order, within
  `[loop].lanes`. A `moves-on` row names the step left and the step taken. Acceptance: landing step 2 of 3 sends step 3
  within a tick; a closed-out step 2 sends step 3; the last step landed starts the next milestone's first step. Test (to
  write): fichero-builder/tests/test_moves_on (new).
- `builder-console.cleanup.is-a-step` [PARTIAL] (#6647) (`builder sweep` exists, offered by a button; `agent-profiles.cleanup.after-land`
  names the position) — cleanup is the last step of every lane and runs itself: once a step's head is on the integration
  branch its land snapshot goes; once a lane is `finished` its worker tree, feed, inbox and branch go after
  `[land].worktree_grace_hours`; a `retired` or `closed-out` lane's tree is patched to `<state>/patches/` then removed;
  stale parks older than 30 d become alerts; each removal is a `cleanup` row, and a tree whose head is not on origin is
  never removed (a row says why). The Worktrees tab lists only what cleanup could not do and why. Acceptance: a landed
  lane's tree is gone after the grace with a row; an unlanded tree stays with a row; the patch of a retired lane exists.
  Test (to write): fichero-builder/tests/test_cleanup_step (new).

#### C. The page: what is worked on, what worked, what failed and why

- `builder-console.page.work-first` [GAP] (#6650) — the first tab is **Work**: the ordered milestones (§ A) with their live counts,
  the running steps at the top with lane, model, harness, age and the live line, then **Needs you** (blocked, stale,
  alerts, each with its age), then **Failed lately** (red rungs and NOT READY verdicts of the last 7 d, one line each with
  the lane page link), then **Landed lately**. Finished lanes and final steps are folded under "History (n)". No table
  with more than one meaning per column; every table has a header row that stays visible (the scroll container is the
  table's wrapper). Acceptance (fixture): the running step is the first row; a lane finished yesterday is under History; the
  blocked step shows its question and age. Test (to write): fichero-builder/tests/test_console_page (new).
- `builder-console.numbers.labelled` [BROKEN] (#6648) (lane-qwen's "1069" and "9.76" are the sum of 22 Pi sessions of 11-07 under
  a tooltip that says "today, API-equivalent"; the header row scrolls away; per-lane USD mixes all-time cost rows with
  today's transcripts) — every number on the page carries its unit, its period and its source in the cell, not a
  tooltip: `1 069 turns · 22 sessions · 11-07`, `$9.76 billed (OpenRouter)`, `$3.10 API-equivalent (Max, not billed)`,
  `91.4 M tokens (in 88.0 M · out 1.2 M · cache read 2.1 M · cache write 0.1 M)`, `4 h 42 min wall`. Billed and
  API-equivalent money are never one sum: the Spend card shows two figures. A number with no source reads `unknown`,
  never `0` or `-`. The totals on a lane row equal the sum of its runs' rows (§ D). Acceptance (fixture runs): the lane
  row's turns, tokens, money and wall are the sums of its run rows and name the period; a Pi run and a Claude Code run on
  one lane give two money lines; a run with no price reads unknown. Test (to write):
  fichero-builder/tests/test_console_numbers (new).
- `builder-console.lane.page` [GAP] (#6649) (the disclosure shows steps, a 3 000-char brief, the worktree and two buttons; on disk
  but unshown: `ladder-<lane>.json`, `review-<lane>.txt`, `fix-<lane>-<step>-<n>.txt`, `question-<lane>-<step>.txt`,
  the verdict rows, the `worker` and `cost` rows, the commits) — every lane name links to `/lane/<id>`, served from
  `GET /api/lane/<id>` (journal, work tree, state files and git of the lane's tree; no gh). It shows: the one state with
  its reason and age; the milestone and step i of n; model, harness, role and provider of the current run; wall time
  (first sent → now or final) and per step; **Steps**: each with its state in words, age, its commits (sha, subject,
  issues, files changed), its check rounds (each rung: ok / red / not run, seconds, the tail on red), its review rounds
  (verdict, the findings text, round n of 2), its questions and answers; **Runs**: each session with generation, started,
  ended, end reason, turns, tokens in / out / cache read / cache write, money with its kind; **Brief** (whole, and each fix
  and retry brief); **Journal**: the lane's rows newest first with a filter by kind. "Commits waiting" counts the lane's
  own commits (those after the step's base), not the tree's. Nothing on the page is a Fichero name: the rung names, the
  branch and the tree paths come from the rows and `harness.toml`. Acceptance (fixture lane with two steps, one red round,
  one review round, two sessions): the page shows every item above with the numbers of § C.2; the landing count is the
  lane's commits; a lane of a text project (no rungs but `spellcheck`) renders the same way. Test (to write):
  fichero-builder/tests/test_lane_page (new).

#### D. Usage per run; comparison across models, harnesses and roles

- `builder-console.runs.page` [GAP] (#6651) (columns and data source: `agent-profiles.console.runs`; rows: `agent-profiles.run.record`)
  — **Runs** is a tab: one row per run from `GET /api/runs` (paged, filters project / milestone / role / model / harness /
  state / date), each row linking to its lane page and step; the page's totals are sums of the shown rows and say so. A
  cost row written before the run record exists (today's `cost` rows) is shown as a run with `source: cost row` and the
  fields it has, so history is kept. Acceptance: the fixture's 22 rows of one lane sum to the lane page's totals; a filter
  by harness `pi` keeps 22 and by `claude-code` keeps 0; an old cost row renders with unknown cache fields. Test (to write):
  fichero-builder/tests/test_console_runs (new) (shared with the sibling; the sibling's cases own the columns).
- `builder-console.compare.page` [GAP] (#6652) — **Compare** shows, per role, one row per model × harness over a window (7 d, 30 d,
  all) and by week: runs, steps landed, landing rate, median review rounds, median wall per landed step, median turns,
  tokens per landed step, money per landed step (billed and API-equivalent apart), refusals and stale actions; a pair
  with fewer than 3 runs is marked "too few to rank". **Bake-offs** shows the runs that share a brief id side by side with
  the same columns, the reference pair marked (`agent-profiles.bakeoff.measured`). Both read `/api/runs`; neither changes
  `[models]`. Acceptance (fixture): two pairs on `backend` rank by landing rate then money; a bake-off of two runs on one
  brief shows both; a window with no runs renders empty, not an error. Test (to write): fichero-builder/tests/test_console_compare (new).

#### E. Generic and safe

- `builder-console.project.neutral` [PARTIAL] (#6653) (`console.py` names `integration`, `fichero-server/tests`, `Fichero-dev-*.dmg`,
  the `measure_x` scripts) — every project word on the page comes from `harness.toml` (`[project]` kind, name, tools,
  `[land].branch`, the rungs, `[machines]`) or from rows. The three kinds render the same pages with their own words: a
  `code` project its rungs and build; a `text` project (steps `draft`, `edit`, `source`, `review`; a declared tool such as
  Tinderbox listed under the role that may call it) with no DMG, no "Install", no app build; a `data` project (a Fichero
  library; steps `find`, `read`, `note`, `file`) with its library name and notes count in place of commits, and the same
  lane page. A host is not a kind: the same API serves the terminal, the website and the in-app view. Acceptance: with a
  `harness.toml` for a book project and one for a library the Work, Lane, Runs and Compare pages render and contain no
  word from the Fichero code profile; the text project's lane page names Tinderbox as a tool of its `writing` role. Test
  (to write): fichero-builder/tests/test_console_second_project (new).
- `builder-console.read-only-by-get` [OK] (#6649) (`console.py` `do_GET`/`do_POST`) — every `GET` is read-only; every action is a
  `POST /api/action` with the page's token and a loopback Host, onto the verb allow-list, one `console` row each. The new
  routes `/api/lane/<id>`, `/api/runs`, `/api/work` are GET only. Test: fichero-builder/tests/test_status_page.py (extend
  with the three routes).

#### F. One API, two front ends, editable both ways

- `builder-console.api.one-engine` [PARTIAL] (#6654) (`/api/*` routes exist for the page only; the lane dict is built in the route)
  — every read and every verb is one API (`GET /api/work`, `/api/lane/<id>`, `/api/runs`, `/api/roles`, `/api/workflows`,
  `/api/alerts`; `POST /api/action {verb, args}`), served by the harness's engine module over HTTP on 127.0.0.1 and
  exposed one-to-one by the harness MCP server (one tool per verb, one resource per read). The HTML page and, later, a
  Swift view inside Fichero render the same JSON; a page shows nothing the API does not return, so the two never
  disagree. Acceptance: for each page, the test renders it from a recorded API response alone; an MCP `lane` resource and
  `GET /api/lane/<id>` return the same document. Test (to write): fichero-builder/tests/test_api_one_engine (new).
- `builder-console.repo.split-held` [GAP] (#6656; HELD, owner 2026-11-16) — the repository split (`git subtree split`
  of `fichero-builder/` with its history into a Fichero Harness repository; Fichero keeps `harness.toml` and
  `agents/projects/fichero/`; the harness pins a Fichero profile version and Fichero pins a harness version) is a step
  that exists and is not taken until the owner says; until then every harness change lands here under these guards. The
  `data` kind and the in-Fichero work store (the third `WorkStore`) go with it when Fichero Researcher starts.
  Acceptance (when taken): the harness repository's whole suite is green on the three fixture kinds with no Fichero code
  word; Fichero's gate still runs its profile. Test (to write): fichero-builder/tests/test_console_second_project (new).
- `builder-console.edit.both-ways` [GAP] (#6655) — workers, roles, prompts, workflows and controls are editable visually on the
  website and through the MCP server with the same verbs: `role add|edit` (name, prompt file, model, harness, provider),
  `prompt edit` (common, role, project layer), `workflow edit` (a project's ordered steps and their rungs), `models set`
  (model and harness per role; a move cites a bake-off or a person), `pause|resume|stop|retry <lane>`,
  `alert approve|dismiss|park <id>`, `order`. Every edit is one audited row (who: a person at the page, or the MCP client's
  name; what; before and after as a diff) and a commit of the edited file when it is a tracked prompt or `harness.toml`;
  a refused edit is a row too. The page's forms and the MCP tool schemas are generated from one verb table (today's
  `VERBS` in `console.py`, with argument types). Acceptance: editing a role's model from the page and from MCP produce the
  same file diff and the same audit row shape; an unknown verb is refused on both; the Edits tab lists the rows newest
  first. Test (to write): fichero-builder/tests/test_edit_both_ways (new).


### From `performance-sweep.md` — Sources — what is measured, with what, where


Every source produces rows of one shape (see `perf-sweep.output.row`); the readers below are the only code this spec adds
on the measuring side. Machine: **M4** for everything in this section unless a row says otherwise.

- `perf-sweep.source.app-log-phases` [PARTIAL] (#6600) — the app's existing launch and interaction timelines are read from
  every smoke, UI-test and perf run, not only from fresh profiles. `LaunchProfile.milestone` logs
  `⏱ <name> @ <ms>ms` (category `LaunchProfile`) and `InteractionProfile` logs a measured-milliseconds line per phase and
  lap (category `InteractionProfile`), both under subsystem `app.fichero.fichero`, each beside an `os_signpost` on the
  Points of Interest track. Capture is LIVE, because `.info` lines are not persisted to the on-disk log store (the trap
  recorded in `LaunchProfile.swift`): the driver starts `log stream --info --style json --predicate 'subsystem ==
  "app.fichero.fichero" AND (category == "LaunchProfile" OR category == "InteractionProfile" OR category ==
  "BodyCount")' > <run>/app-log.jsonl` BEFORE launching the app, and also launches with
  `FICHERO_LAUNCH_PROFILE_STDOUT=1` and keeps stderr, so a run with no log stream still has the launch timeline. When a
  `.trace` exists for the run, the `os-signpost` table (`xcrun xctrace export --input <t> --xpath
  '/trace-toc/run[@number="1"]/data/table[@schema="os-signpost"]'`) is the authoritative source for the same phases and
  the log is the cross-check. The reader groups by phase name (launch milestones become the gap to the previous milestone;
  interaction intervals and laps keep their names) and emits per phase: count, p50, p95, max, in ms. Acceptance (a fixture
  `app-log.jsonl` and a fixture signpost export, no Mac): 40 `sidebar expand` intervals give one row with count 40 and the
  right p50/p95; the launch milestones become ordered gaps whose sum is the last milestone's elapsed; a run with the
  stderr timeline only still yields the launch rows; the signpost export and the log for the same run agree within 5 ms or
  the row is marked `disagree` (never silently averaged). Test (to write):
  the new test_perf_log_readers file in fichero-server/tests/unit/scripts, case test_launch_and_interaction_lines_become_phase_rows_with_p50_p95_count.
  Built: the log and stderr readers. Not built: the signpost-export cross-check and the `disagree` mark (Step 8).
- `perf-sweep.source.engine-perf-lines` [PARTIAL] (#6600) — `core/perf.py::perf_span` logs `PERF <name> <k=v …>
  duration_ms=<n>` and `model_load` logs `model-lane: loaded <model> in <s> s (load <n> in this engine)` plus the
  WARNING `model loaded again`. The reader takes an engine log (the run's, or the app's embedded-engine log from a smoke
  run) and emits one row per span name with count, p50, p95, max, total (count × p50, the "how often" figure the owner
  asked for: a 4 ms span that runs 9 000 times outranks a 200 ms span that runs once), plus one row per model with its
  load count and total load seconds, and a `reload` flag when the warning fired. Context keys that vary per call
  (`doc_id`, paths) are dropped; a key named in `[perf].group_by` (e.g. `provider`, `pages`) splits the row. The
  slow-path lines `quality.slow-path-ratchet` names (the Kraken per-page line, the cloud-batch waits) are read by that
  ratchet, not here; this reader hands it the same parsed rows. Acceptance (fixture log): three names with known
  durations give three rows with exact p50/p95/total; a model loaded twice 30 s apart yields `reload: true`; a line that
  is not `PERF` or `model-lane` is ignored; an empty log gives zero rows and the run is marked `no-engine-log`, not
  green. Test (to write): test_perf_log_readers (a new test file), case test_perf_spans_group_by_name_with_count_total_and_model_reloads.
- `perf-sweep.source.engine-profiles` [PARTIAL] (#6600, #6614) — fresh engine profiles over the engine workloads (W1–W5 below),
  nightly, on the M4's gate venv, one workload at a time behind the heavy lock. **Time:** `pyinstrument -r json -o
  <run>/<w>.pyinstrument.json -r html -o <run>/<w>.html -- <driver>` is the batch and nightly default (in-process, no
  root). `sudo -n py-spy record --format speedscope -o <run>/<w>.speedscope --subprocesses --pid <the driver's pid>` (the driver starts as the gate user; root only attaches) is used when the runner's
  `sudoers` allows `py-spy` without a password for the gate user (py-spy attaches with `task_for_pid` and needs root on
  macOS); it is the only profiler that sees the worker processes the engine forks (`--subprocesses`) and native frames in
  DuckDB, numpy and MLX, which pyinstrument attributes to the calling Python line. Whether `py-spy` is permitted is a
  declared machine fact (`[machines].m4air.sudo = ["py-spy"]`), never probed by trying. Owner 2026-11-15: py-spy may run with sudo on the M4 only, through one narrow sudoers line that allows nothing but py-spy; no other machine gets it, and pyinstrument is the fallback everywhere else. **RAM:** `memray run --native
  --follow-fork -o <run>/<w>.bin <driver>` then `memray stats --json -o <run>/<w>.memray.json <run>/<w>.bin` (peak,
  top allocators by size and by count) and `memray flamegraph -o <run>/<w>.memray.html <run>/<w>.bin` for the reviewer;
  `/usr/bin/time -l` wraps every driver for the zero-overhead peak RSS (`maximum resident set size`) that the rung holds.
  **Disk:** `du -sk` of the scratch library, the engine cache dir, its log dir and the models dir before and after
  (`perf-rung-engine`'s pairs, unchanged), the delta per directory held exactly; DuckDB spill and old-row-version MiB
  from `db/busy_evidence.py`'s lines. **CPU and energy:** CPU seconds from `/usr/bin/time -l` (`user` + `sys`) and the
  ratio CPU/wall (parallel efficiency; a workload at 0.9 on an 8-core run is serial work waiting to be found); energy on
  the Mac is CPU time (no per-process energy counter is available without root; `powermetrics` is NOT used). Rows: the
  top 15 self-time frames that are ours (`fichero_server/`, `fichero_cli/`, `fichero_mcp/`), each with self ms, total ms,
  call count where the tool gives it, and share of the workload's wall; the top 10 allocation sites by peak bytes; one
  row per directory with its delta KiB; one row per workload with wall, CPU, CPU/wall, peak RSS. Acceptance (fixture tool
  outputs, no engine): a pyinstrument JSON yields our frames only, ranked by self time with the share computed against
  the root's time; a memray stats JSON yields allocator rows by peak bytes; a `time -l` text yields RSS, user and sys;
  `du` pairs yield deltas; a machine without `sudo = ["py-spy"]` never spawns py-spy and the run says
  `profiler: pyinstrument`. Test: fichero-builder/tests/test_perf_sweep.py, case test_engine_profile_readers_rank_own_frames_allocators_disk_and_cpu_efficiency.
  Built (#6614): the readers and `builder perf profile --gate <dir>` (`perf_profiles.py`); commands are argument lists, never a shell; py-spy only when declared and its sudoers line is on the machine (else a row says so), and then the workload starts as the gate user and root only attaches with `--pid`; the driver gets a minimal env and FICHERO_BASE_PATH, FICHERO_LIBRARY_PATH, FICHERO_ENGINE_LOG_PATH and FICHERO_MODEL_STORE_ROOT point at the folders `du` reads; the memray `.bin` and the temp folder are removed after each workload and the newest 7 run folders stay. Not built: the nightly schedule entry and a real run on the M4.
- `perf-sweep.source.app-profiles` [GAP] (#6600) — fresh app profiles over the app workloads (W6–W10), nightly, on the
  M4's GUI session, the Dev Local build from the daily `tests` build's derived data (`build-for-testing` output). The
  recorder is `xcrun xctrace record --template '<T>' --time-limit <s>s --launch -- <app> --env
  FICHERO_PRINT_CHANGES=1 --env FICHERO_PERF_WORKLOAD=<w> --output <run>/<w>.<T>.trace` for the templates `Time
  Profiler` (includes the Hangs instrument's `potential-hangs` table in Xcode 15+, which `scripts/check_hang_ratchet.py`
  already reads, and the `os-signpost` table), `Allocations`, `Leaks`, `SwiftUI` (view body counts and update causes),
  `File Activity` (bytes written per file and per call, the app's disk figure), `App Launch` (W6 only). `Energy Log`
  records on an iOS device only: it runs when a device is attached to the M4 and is otherwise a `not-run` row, not a
  gap; on the Mac CPU time stands in. The app drives itself through the workload (`FICHERO_PERF_WORKLOAD` selects a
  scripted scenario in the Dev Local build's test hooks, the smoke scenario's mechanism) so no XCUITest runner competes
  for the GUI during a recording. Export is `xcrun xctrace export --input <t> --toc` once (the table list is recorded
  with the run) then `--xpath '/trace-toc/run[@number="1"]/data/table[@schema="<s>"]'` for `time-profile`,
  `potential-hangs`, `os-signpost`, and the allocation, leak, SwiftUI and file-activity schemas the toc names (their
  exact names are pinned in `scripts/perf_trace_schemas.json` on the first real export and REFUSED when a toc lacks one).
  Rows: top 15 self-time symbols in our module (`Fichero`), with share of the scenario's wall; every hang over 250 ms
  with its stack's top own frame; persistent bytes at scenario end by category and the top own allocation sites; every
  leak (count held at zero); body evaluations per view per scenario (cross-checked against the `BodyCount` log lines the
  `perf-rung-app` bullet reads); bytes written per path and per scenario; the launch phases from `App Launch`. The
  xcresult of the perf test plan (`perf-sweep.source.xctest-metrics`) is a sixth input to the same rows. Acceptance
  (fixture exports, no Xcode): a `time-profile` export yields own-symbol rows with shares; a `potential-hangs` export goes
  through `check_hang_ratchet.py`'s parser unchanged and yields one row per hang; a leaks export with one row is a red row;
  a SwiftUI export with `SidebarView` at 31 bodies for `sidebar-click` yields that row; a file-activity export yields
  bytes per path; a toc missing a pinned schema is REFUSED naming it. Test (to write):
  test_perf_sweep (a new test file), case test_app_trace_exports_become_rows_per_template_and_a_missing_schema_refuses.
- `perf-sweep.source.runtime-checkers` [GAP] (#6600) — Xcode's runtime checkers run as scheme diagnostics in a dedicated
  test plan, `fichero/Tests/plans/fichero-diagnostics.xctestplan`, with two configurations because the Thread and
  Address sanitizers exclude each other: `tsan` (Thread Sanitizer, Main Thread Checker, Thread Performance Checker) and
  `asan` (Address Sanitizer, Undefined Behavior Sanitizer, Main Thread Checker, Thread Performance Checker), each toggled
  in the test-plan editor so the keys are the ones Xcode writes. It runs the existing unit and smoke tests (not the perf
  plan: a sanitized build is 2–5× slower and its timings are void) nightly on the M4 after the daily `tests` build:
  `xcodebuild test -project fichero/fichero.xcodeproj -scheme "Fichero (Dev Local)" -testPlan fichero-diagnostics
  -only-test-configuration <c> -destination platform=macOS -derivedDataPath derived-diagnostics -resultBundlePath
  <run>/diag-<c>.xcresult`. The reader takes runtime issues from the xcresult (`xcrun xcresulttool get test-results
  tests --path <x>` and the test's console log, where Main Thread Checker and TPC lines are `=== Main Thread Checker:
  …` / `Thread Performance Checker: …`) and the sanitizer reports (`SUMMARY: ThreadSanitizer: data race …`), one row per
  distinct (checker, top own frame), held at zero: a new row is a finding filed as `Performance - <area>` for TPC and MTC
  (main-thread I/O and priority inversions are performance) and as a bug for the sanitizers. Acceptance (fixture console
  logs): one TPC line yields one row with checker `tpc` and the frame; two identical MTC lines yield one row with count
  2; a clean log yields none; a plan run that did not finish is `not-run`. Test (to write):
  test_perf_sweep (a new test file), case test_runtime_checker_logs_become_rows_held_at_zero.
- `perf-sweep.source.xctest-metrics` [PARTIAL] (#6600; `quality.perf-rung-app` owns the plan) — the perf test plan
  `FicheroPerfTests` measures each app workload's scripted action with `measure(metrics: [XCTClockMetric(),
  XCTCPUMetric(), XCTMemoryMetric(), XCTStorageMetric(), XCTOSSignpostMetric(subsystem: "app.fichero.fichero", category:
  "PointsOfInterest", name: <interval>)])`, and W6 with `XCTApplicationLaunchMetric()` as
  `LaunchPerformanceUITests.swift` does today; `.xcbaseline` plists committed beside the target are Xcode's own judge
  (`xcresulttool get test-results summary` is what the rung reads). This spec adds nothing to the mechanism; it reads the
  per-metric averages out of the xcresult (`xcrun xcresulttool get test-results tests --path <x>`, the
  `performanceMetrics` of each test) as rows, so the table has one line per workload for clock, CPU, memory and storage
  even when the baseline passes. Built: `LaunchPerformanceUITests.swift` (launch only). Open: the plan, the four other
  actions, the baselines (Step 2.31). Test (to write): test_perf_sweep (a new test file), case test_xcresult_performance_metrics_become_rows.
- `perf-sweep.source.metrickit-and-field` [GAP] (#6600) — two field sources, both light. **In the app:** a
  `MXMetricManagerSubscriber` registered at launch in every channel writes each daily `MXMetricPayload` and every
  `MXDiagnosticPayload` as the JSON MetricKit itself produces (`jsonRepresentation()`) into
  `Application Support/Fichero/Metrics/<date>-<kind>.json`, keeps 30 days, and the Dev Local build's test hooks expose
  the folder; the reader takes launch (`applicationLaunchMetrics`), responsiveness/hang histograms
  (`applicationResponsivenessMetrics`), disk writes (`diskIOMetrics.cumulativeLogicalWrites`), memory (peak, average
  suspended) and CPU time, plus `MXHangDiagnostic`, `MXDiskWriteExceptionDiagnostic` and `MXCPUExceptionDiagnostic` call
  trees (top own frame), as rows tagged `field`. Which fields macOS fills versus iOS is recorded from the first real
  payload, not assumed. **From Xcode Organizer:** the Xcode MCP's `GetTopFieldPerformanceIssues` and
  `GetFieldPerformanceIssueLogs` (hangs, launch, disk writes, memory, energy for TestFlight builds) are called by the
  quality lane's nightly from any Mac signed into the team's App Store Connect; this is an API call, so it may run on the
  manager's Mac. Each reported issue is a row tagged `organizer` with its build and device class; every hang and disk-write
  exception is a filing candidate regardless of rank. Acceptance (fixture payloads): a hang diagnostic yields a row with
  the top own frame; a disk-write exception yields a row with bytes; a payload with no responsiveness metrics yields no
  hang row and the run notes the missing field; a field issue list of three yields three rows tagged `organizer`. Test
  (to write): test_perf_sweep (a new test file), case test_metrickit_payloads_and_organizer_issues_become_field_rows.
- `perf-sweep.source.machines` [PARTIAL] (#6600; `pool.machines-declare-capabilities`) — where each source runs is declared,
  not discovered: `[machines].m4air` gains `tags = ["pytest", "guards", "swift-build", "xcode-tests", "gui", "profile"]`
  and the optional `sudo = ["py-spy"]`; the sweep refuses to profile on a machine without `profile`, refuses an app
  profile without `gui`, and never places anything on the manager's Mac (`pool.hold-holds-one-machine`). The nightly
  order on the M4 is fixed so profiles never overlap a build: daily builds, the diagnostics plan, the perf plan, then the
  xctrace recordings and the engine profiles, each under the heavy lock. Acceptance: a rules file whose only `profile`
  machine lacks `gui` runs the engine profiles and marks the app profiles `not-run: no GUI machine`; a sweep configured
  with no `profile` machine refuses at load naming the tag.
  Test: fichero-builder/tests/test_perf_sweep.py::test_profiles_place_only_on_declared_machines_and_say_not_run_otherwise
  Built: tags and sudo are declared in `harness.toml [perf.machines.<name>]` (not in `[machines]`, whose line stays as it was), read by `fichero_builder/perf_workloads.py`. Not built: the fixed nightly order under the heavy lock (nothing calls `place()` yet, and there is no xctrace or sequencing code), and the rule that nothing is placed on the manager's Mac (`place()` would accept it if it carried a `profile` tag; today it holds only because that Mac is not declared).


### From `performance-sweep.md` — Workloads — the fixed, reproducible set


- `perf-sweep.workload.set` [PARTIAL] (#6600) — ten workloads, each a named scripted scenario with a fixed corpus, declared
  in `harness.toml [perf.workloads]` (name, side, driver, corpus, declared outputs, budget seconds). Engine (pytest
  drivers under `fichero-server/tests/perf/`, run one test per workload against a uvicorn engine, never `main()`):
  **W1 import** (the generated 200-page library: `scripts/perf_fixture.py` pages plus the pdf and image fixtures already
  under `fichero-server/tests/fixtures/`, imported from scratch), **W2 reader/OCR** (`fichero-server/scripts/bench_reading.py
  --pages 20` on W1's library with the bundled Kraken model; the one workload that may take minutes), **W3 search**
  (200 queries from a committed list over W1's library, text and semantic), **W4 KG** (the entity list, entity detail and
  neighbourhood perf tests, `test_entity_list_perf.py` / `test_entity_detail_perf.py`, against W1), **W5 Activity**
  (`scripts/perf_activity_store_5645.py`'s 200-job store, the jobs list and job tree routes). App (scripted in the Dev
  Local build under `FICHERO_PERF_WORKLOAD`, measured by the perf plan and recorded by xctrace): **W6 launch** (cold, to
  `launch-to-engine-ready`, on W1's library), **W7 sidebar** (click five rows, expand three folders, the
  `InteractionProfile` phases), **W8 canvas/reader** (open a 20-page document, swipe through 10 pages, five region
  presses: `preview swipe → image` and `preview region press`), **W9 library grid** (first scroll of 200 cells),
  **W10 Activity view** (the table with 200 rows updating). Each app workload runs on macOS; W6–W8 also run in the iOS
  and iPad simulators for CPU, memory and body counts (simulator timings are recorded but never ratcheted: a simulator
  is not a device). Acceptance: the table loads with ten workloads; one missing a corpus or a budget is refused by name;
  a workload's declared outputs are what the disk reader subtracts. Test (to write):
  test_perf_sweep (a new test file), case test_the_workload_table_loads_and_refuses_an_undeclared_corpus_or_budget. Built: the `[perf.workloads]` table (W1–W5 pytest and script drivers, W3 is `test_search_workload_perf.py` over `scripts/perf_search_queries.txt`, text queries only) and the `PerfWorkload` selector for W6–W10. Not built: the scripted scenario steps in the view layer, and the simulator runs.
- `perf-sweep.workload.corpus` [PARTIAL] (#6600; `ruling-2026-11-13-no-archive-names-in-specs`) — every corpus is synthetic
  or openly licensed, and none is the owner's archive material: the generated perf fixture (`scripts/perf_fixture.py`,
  deterministic by seed), the repo's own test fixtures, and at most one open HTR test set from the vetted list the project
  keeps (PAGE/ALTO with a licence that permits redistribution), pinned in `scripts/perf_corpus.json` by name, licence,
  URL, sha256 and page count. The runner holds each under `~/fichero-gate/corpus/<name>-<sha256[:12]>/`, fetched once by
  `builder install --corpus` and verified by hash before every run; a corpus whose hash differs is REFUSED (two runs
  must measure one corpus). No corpus, manifest or workload names a real archive, box, place or person; the
  public-boundary grep that guards landings covers `scripts/perf_corpus.json` and the workload table. Acceptance: a
  manifest entry without a licence or a hash is refused; a mismatched hash on the runner refuses the run naming the
  corpus; the boundary grep over a fixture manifest carrying an archive name is red. Test (to write):
  the new test_perf_corpus file in fichero-server/tests/unit/scripts, case test_the_corpus_manifest_is_open_hashed_and_names_no_archive. Built: `scripts/perf_corpus.json` (two generated or in-repo corpora) and `builder install --corpus`. Not built: the one open HTR download entry, which needs a vetted set and a hash taken by the manager.


### From `performance-sweep.md` — Output — the ranked hotspot table and the filing rule


- `perf-sweep.output.row` [OK] (#6600) — one row shape for every source: `{run, machine_model, workload, side
  (engine|app|field), area, kind (time|cpu|ram|disk|energy|hang|leak|body|efficiency), where (frame, view, span,
  phase or file:line), value, unit, count, share (of the workload's total for the kind, when it exists), source (the
  tool), trend_pct (vs the previous run on the same machine model and workload, null on the first), runs_seen,
  profile (the run-relative path of the trace, flamegraph or JSON the row came from)}`. `area` is derived from `where` by
  the same path-to-area map the review lenses use (`fichero_builder/review_lenses.py`; `recipes/` → recipes,
  `Views/Sidebar/` → sidebar, and so on) so a hotspot and a reviewer finding land in the same bucket. Acceptance: a row
  missing `where`, `value` or `source` is refused; `area` for `fichero/fichero/Views/Sidebar/SidebarView.swift` is
  `sidebar`. Test: fichero-builder/tests/test_perf_sweep.py, case test_rows_have_one_shape_and_an_area_from_the_lens_map.
- `perf-sweep.output.table` [PARTIAL] (#6600) — a run writes `<state>/perf/<run-id>/hotspots.json` (all rows) and
  `<state>/perf/latest.json` (a pointer plus the ranked top 50), where `<state>` is the builder's state dir
  (`journal.STATE`), and the profiles sit beside them for 30 days (the M4's Dev Disk; the manager's Mac holds the JSON
  only, rsynced back with the ladder's results). **Ranking:** within a kind, by `share` where it exists, else by `value`;
  across kinds the table shows the top 10 of each so a disk hog is never buried under time rows; ties by `count`. The
  **trend** column is `trend_pct` with the noise band (`ratchet.noise-band`) greyed: a move inside the band is shown as
  `~`, a worsening beyond it as `+N%` and an improvement as `−N%`. **Console:** `console.html` gains a `Hotspots` panel
  (the top 50 from `latest.json`, filter by workload, kind, area; a row links to its issue when one exists and to its
  profile path) and the daily digest carries the top 10 and the three counts of `perf-security-sweep` (findings, held
  up, fixed). `builder perf show [<run-id>]` prints the same table in the terminal; `builder perf diff <a> <b>` prints
  the rows whose trend crossed the band. Acceptance (fixture rows): the top 50 contains at most 10 per kind; a row 3%
  slower under a 6% band shows `~`; `show` prints every column; `diff` lists only band-crossing rows. Test (to write):
  test_perf_sweep (a new test file), case test_the_table_ranks_per_kind_greys_moves_inside_the_band_and_the_console_reads_latest.
- `perf-sweep.output.filing-rule` [GAP] (#6600) — a hotspot becomes a `Performance - <area>` issue when ALL hold:
  (1) it is above the kind's floor: time or CPU ≥ 5% of its workload's total, or a span whose `count × p50` ≥ 5% of the
  workload's wall; RAM ≥ 50 MB persistent or a top-10 allocator ≥ 25 MB peak; disk ≥ 10 MB written per run or ANY
  delta in a directory with no declared output; efficiency CPU/wall ≤ 1.2 on a workload declared parallel; ANY hang ≥
  250 ms, ANY leak, ANY runtime-checker row, ANY Organizer hang or disk-write exception; a body count above its
  baseline; (2) it appeared in two consecutive runs on the same machine model (field rows are exempt: one report is
  enough); (3) no open issue carries its key. **Key and dedupe:** `perf:<area>:<kind>:<where>` (where normalised: no
  line numbers for frames, the view name for bodies, the span name for spans), written as a `<!-- perf-key: … -->` line
  in the body and found with `gh issue list --search "perf-key: <key>" --state open`; a closed issue with the same key
  reopens with a comment (a regression, not a duplicate; the comment carries both runs' figures). **Through the filer:**
  the watcher's filer (`builder watch`, #6369) and its placement (`builder triage --move` into `performance-sweep`,
  `builder steps` under the area's step), so related hotspots group into one speed-up batch. Owner 2026-11-15: every
  spot over its floor is filed, with no daily cap and no rolling overflow issue; dedupe by key is the only brake. **The
  issue:** title `Performance - <area>: <where> <value><unit> (<share>% of <workload>, <trend>)`; body: the row, the
  workload and corpus, the machine model, the top 20 frames or allocators inline as text, the profile's run id and
  path (`builder perf show <run-id>` reopens it), the test or benchmark that would hold the fix (the workload's perf
  test, or "add a signpost interval around <where>"), and the ask in the owner's form: look at `<where>` and speed it
  up. Issues with no file to attach (field rows) carry the Organizer or MetricKit JSON inline instead. Acceptance
  (fixture rows, a fake `gh`): a frame at 7% in two runs files one issue with the key, the title and the inline frames; the
  same row in a third run files nothing; the same key on a closed issue reopens it with a comment; a 7% row seen once
  files nothing; a hang of 300 ms seen once files; a fourth and a tenth new key in one pass each file their own issue (no cap, owner 2026-11-15). Test (to
  write): test_perf_sweep (a new test file), case test_the_filing_rule_floors_two_runs_dedupe_by_key_reopen_and_no_cap.


### From `performance-sweep.md` — Ratchet — second goal: nothing gets slower


- `perf-sweep.ratchet.budgets` [GAP] (#6600; `quality.perf-method` is the decider) — `scripts/perf_baseline.json`
  (exists at HEAD with tolerances and empty `figures`, commit dd5e46fe3d) gains `figures[<machine.model>][<workload>]
  [<measure>] = {median, tolerance, band, since_run, runs}` for the measures the rungs hold: wall ms, CPU ms, peak RSS MB,
  disk KiB (exact), hang count (exact), leak count (exact), body count per view (exact), and the batch-level budgets from
  `perf-method` (engine perf + security under 6 min, app perf under 5 min). `perf_trial.py` stays the judge: cold run
  discarded, median of the warm runs, thermal `fair` is VOID, keyed by machine model and workload. Acceptance: a figure
  file without `band` for a tolerance-bearing measure is REFUSED; a measure held exactly carries `tolerance: 0`. Test:
  extends `fichero-server/tests/unit/scripts/test_perf_trial.py` (to write:
  `test_figures_carry_band_and_runs_and_an_exact_measure_has_zero_tolerance`).
- `perf-sweep.ratchet.baseline-from-n-runs` [GAP] (#6600) — a baseline figure is never one run: a measure is
  **report-only** until it has `N = 5` green runs on the same machine model (a week of nightlies, or five batches), then
  `builder perf baseline --write` writes the median of those five as the figure with `runs: 5` and `since_run`; the rung
  then ENFORCES that measure (`[check.perf].enforce` becomes a list of measures or `"all"`, so enforcement comes one
  measure at a time, never a flag day). A write in the same batch as code is refused (`ratchets-held-exactly`); a figure
  may only fall afterwards (`baseline-falls-every-batch`: a better median is printed as the figure to lower to, and the
  nightly lowers it by `builder perf baseline --lower`, its own commit). Acceptance: four runs and a `--write` refuses
  naming the count; five write the median; an enforced measure 8% over is red naming it, the figures and the machine; a
  report-only measure over prints the figure and stays `report-only`, never green-by-silence; `--write` with a diff of
  code in the same tree is refused. Test (to write): test_perf_sweep (a new test file), case test_a_baseline_needs_five_runs_enforces_per_measure_and_only_falls.
- `perf-sweep.ratchet.noise-band` [GAP] (#6600) — the band is measured, not guessed: over the N baseline runs, `band =
  (p95 − p5) / median`; the tolerance applied is `max(tolerance from the file, 2 × band)` for time, CPU and RSS (exact
  measures ignore the band); a measure whose band exceeds 15% is marked `noisy`, never enforced, and files one
  `Performance - measurement: <workload>/<measure> too noisy` issue (the fix is in the workload or the runner, e.g. a
  model warm-up or a dirty library, not a wider tolerance). Simulator measures and any run under `thermal != nominal`
  never enter the band. Acceptance: runs 100, 101, 99, 104, 100 ms give a band of 5% and a tolerance of 10%; runs with
  a 20% band mark the measure `noisy` and file once; a VOID run is excluded from the band. Test (to write):
  test_perf_sweep (a new test file), case test_the_noise_band_widens_the_tolerance_and_a_noisy_measure_is_never_enforced.


### From `performance-sweep.md` — Warnings — compiler, build-system and SwiftLint, listed and ratcheted the same way (#6610)


- `perf-sweep.warnings.from-the-result-bundle` [OK] (#6610) — the remote build rung and the daily builds (`[check].build`,
  `[check.daily_builds].ios-sim`, `.tests`) each pass `-resultBundlePath <run>/<name>.xcresult` (the local build rung does not: it
  never reads the bundle, and an unread bundle is tens of MB left on disk; the bundle lives beside the build on the runner, and the
  warnings JSON read from it is a temp file removed after the ratchet runs). The iPad count (a new `.ipad-sim` daily build with the
  iPad test plan's scheme) waits for a scheme that carries that plan: until then no `ipad-sim` entry exists, since a copy of `ios-sim`
  would count the same build twice, and the warnings are read with
  the platform's reader, `xcrun xcresulttool get build-results --path <x>` (JSON: every warning with its message, file,
  line and the issue type), never a regex over the log alone; the kept log (`build-logs/<name>-…log`) is the fallback
  when the bundle is missing (`^(.+?):(\d+):(\d+): warning: (.*)$` for compiler lines, `^warning: (.*)$` for
  build-system lines) and a read that is asked for a bundle or log and gets neither is BLIND (exit 2, `check_swiftlint_warning_ratchet.py`'s meaning),
  never green. Each warning is normalised to `(platform, kind, file, message)` where `kind` is: for Swift, the message
  with quoted identifiers and numbers replaced by `_` (so `'foo' is deprecated` and `'bar' is deprecated` are one kind,
  `deprecated: _`), prefixed by its family when the compiler gives one (`Sendable`, `concurrency`, `unused`,
  `deprecated`); for clang, the `[-W…]` flag; for the build system, the message with the phase or target name kept
  (`script phase without outputs: 'Validate App Store Bundle'`, `duplicate output file`, `deployment target`, `missing
  Info.plist key`, `linker`). Acceptance (fixture JSON and a fixture log): a build-results JSON with 12 warnings yields 12
  normalised rows and the right kind counts; the owner's example line yields kind `script phase without outputs` with
  the phase named; two deprecations of different symbols are one kind with count 2; a named bundle or log that is missing or unreadable is BLIND (exit 2); a run that names neither (the guards rung runs every `check_*.py` bare, before any build) prints `skipped: no build to read` and exits 0: it read nothing, so it claims nothing.
  Test: the new test_check_xcode_warning_ratchet file in fichero-server/tests/unit/scripts, case test_warnings_are_read_from_the_bundle_normalised_to_kinds_and_blind_without_input. Built: `scripts/check_xcode_warning_ratchet.py` reads and normalises, tested in fichero-server/tests/unit/scripts/test_check_xcode_warning_ratchet.py and fichero-builder/tests/test_perf_sweep.py.
- `perf-sweep.warnings.ratchet` [OK] (#6610) — the new check_xcode_warning_ratchet file in scripts, shaped exactly like
  `check_swiftlint_warning_ratchet.py` (exit 0 held, 1 grew, 2 BLIND; `--update-baseline`; `--since <base>` for one
  item), holds `scripts/xcode_warning_baseline.json` = `{platform: {kind: count}}` EXACTLY: a batch that adds a warning
  of any kind on any platform is red naming the platform, the kind, the file and line, and both counts; a batch that
  removes one lowers the baseline in the same batch or the land step lowers it (`baseline-falls-every-batch`); a raised
  baseline in a diff is refused (`--check-baseline` exists as a command-line flag; no rung or guard calls it yet, so
  the refusal is [GAP]). The rung runs it over the mac build's bundle on every batch that touches `fichero/`;
  the iOS count is held by the daily build (red there is an alert plus the ratchet's red lines); the iPad count waits
  for an iPad scheme (`ipad-sim` was removed). A warning
  that moves file is not new (counts are per kind, not per file, the SwiftLint ratchet's netting rule). Acceptance: a
  bundle with one more `Sendable` warning than the baseline is red naming it; one fewer is green and prints the lower
  count; a baseline edit that raises a count is refused; `--since` over a fixture pair reports only the item's own new
  lines. Test: test_check_xcode_warning_ratchet (a new test file), case test_the_count_per_kind_and_platform_may_only_fall_and_since_names_the_item_s_lines. Built: the ratchet and the remote build rung's hold, tested in fichero-server/tests/unit/scripts/test_check_xcode_warning_ratchet.py and fichero-builder/tests/test_perf_sweep.py.
  Baseline: `scripts/xcode_warning_baseline.json` holds no kind for `mac` and `ios` (#6610: the existing warnings were fixed in source, so any warning on either platform refuses a land); the first build after this batch confirms it.
- `perf-sweep.warnings.ranked-list-and-issues` [OK] (#6610) — one list for all three warning sources: the xcode ratchet's
  kinds, `check_swiftlint_warning_ratchet.py`'s per-rule counts (`TOP_N_RULES` already computed there; the script gains
  `--json <out>` and nothing else) and ruff's per-rule counts where the quality stream holds them, written to
  `<state>/perf/<run-id>/warnings.json` as rows `{source (xcode|swiftlint|ruff), platform, kind, count, trend, example
  file:line}`, ranked by count, shown in the console beside Hotspots (the digest's top 10 is [GAP]: nothing writes warnings to the digest yet). **One issue per kind,**
  `Build warnings - <source>: <kind> (<count>)`, with the dedupe key `warn:<source>:<platform>:<kind>` in the body, the
  example lines (up to 20) and the way to clear it; the same filer and caps as hotspots; a kind whose count reaches zero
  closes its issue with the run id. The **first issue** is already known and is filed by hand in Step 6: the `Validate
  App Store Bundle` phase (and any other `PBXShellScriptBuildPhase` with no `outputPaths` and no `alwaysOutOfDate`) runs
  on every build; the fix is a declared output file per phase (or `alwaysOutOfDate = 1` where the phase must run), which
  also shortens every incremental build and is itself a build-time hotspot. Acceptance (fixture rows, fake `gh`): the
  list ranks three sources together; one issue per kind with the key; a repeat run files nothing new; a kind at zero
  closes; the Validate phase in a fixture pbxproj is listed as `script phase without outputs`. Test:
  test_perf_sweep (a new test file), case test_warning_kinds_rank_across_sources_file_one_issue_each_and_close_at_zero. Built: `fichero_builder/perf_warnings.py` and the console Warnings table, tested in fichero-builder/tests/test_perf_sweep.py.


### From `performance-sweep.md` — Rung states — a measurement that did not happen is not green


- `perf-sweep.rung.not-run-is-visible` [BROKEN] (#6589 items 1–2; `check_tool.perf`, `check_tool.security`) — today
  `_remote_build` returns `None` for three different reasons (ssh or `mkdir` failed, rsync failed, a non-zero exit with
  no Swift source error, which is what a missing `pytest-benchmark` or a `scripts/perf_baseline.json` absent from the
  rsynced tree looks like), `perf()` turns every `None` into one alert "the build runner is unreachable", and
  `_report_only` makes a REFUSED tool a green rung; so both rungs have been green on every ladder since 22:41 on
  2026-11-14 and neither has measured anything. Wanted: `_remote_build` returns the row for an env-red (ok false,
  `remote_env_red: true`, the remote stderr tail kept) and `None` only for a runner it could not reach; `perf()` and the
  security rung map a `None` to state `not-run: runner down`, a REFUSED tool or an unpinned version to `not-run:
  <tool> refused`, and a missing baseline or workload file to `not-run: <path> missing on the runner`; a `not-run` rung
  is shown in the ladder, the journal row and the console as `not-run` (grey, never the green tick), the ladder still
  passes while `enforce` is off, and three consecutive `not-run` of the same rung file one `Builder - <rung> not
  running` issue. Every alert row gets an id (#6589 item 3) so the console can answer or dismiss one. Acceptance (a fake
  ssh and fake rows): a 255 exit yields `not-run: runner down`; a remote exit 1 with "No module named pytest_benchmark"
  in stderr yields `not-run: perf tool refused` with the stderr in the row, never "unreachable"; empty pins yield
  `not-run: bandit refused`; a journal row for a `not-run` rung carries `state: not-run` and an `id`; the third in a row
  files the issue once. Test: new cases in `fichero-builder/tests/test_perf_rung.py` and `fichero-builder/tests/test_security_rung.py`
  with `test_a_rung_that_did_not_measure_is_not_run_never_green_and_names_why`.
  **What counts as measured** (#6600, 2026-11-24: every ladder was red on "no pytest-benchmark JSON was written" because the perf tests time themselves with ratchet asserts and never use the `benchmark` fixture): `scripts/perf_engine_run.py` takes its per-test figures from pytest-benchmark's JSON when that holds any, else from the per-test durations of pytest's own junit report (plus peak RSS from `/usr/bin/time -l` and disk from `du`); a run that ran its tests measured something. It is "measured nothing" (REFUSED, red) only when pytest could not run: exit 2 to 5 (import or collection error, usage error, no tests), no readable report, or no test that ran; an unreadable RSS stays REFUSED. A test that failed has no figure: on an idle machine it is a red naming the test; on a busy or throttled one the run is VOID, an alert row and not a red. pytest-benchmark and pyinstrument are optional: a missing plugin or an unwritten profile is a `note:` line in the rung row. Tests `fichero-builder/tests/test_perf_engine_run.py::test_a_run_whose_tests_ran_measures_their_durations_with_no_benchmark_json`, `::test_a_run_where_pytest_could_not_run_is_refused`, `::test_a_ratchet_that_failed_on_an_idle_machine_is_a_red_naming_the_test_and_has_no_figure`, `::test_failing_ratchets_on_a_busy_machine_are_void_not_red`, `::test_no_pyinstrument_or_benchmark_plugin_is_a_note_not_a_refusal`, `::test_a_void_run_is_an_alert_row_and_the_rung_stays_ok_and_notes_are_said`.


### From `issues-and-labels.md` — Behaviors


- `issues.milestone-is-the-spec` [PARTIAL] (#6336) — every open issue sits in the milestone its spec names; `check_spec_milestones.py` binds spec↔milestone today, nothing yet moves issues. Test: an owed test `test_triage_tool.py` (for the `workflows` tests) → #6116
- `issues.label-set-is-closed` [PARTIAL] (#6336) — only the labels in the table exist; the one-off consolidation was done by hand 2026-11-01 (70 → 48); triage refuses an unknown label. Test: an owed test `test_triage_tool.py` (for the `workflows` tests) → #6116
- `issues.build-order-file-orders-milestones` [PARTIAL] (#6336) — the harness briefs only the first unfinished milestone of `specs/build-order.md`. Test: fichero-builder/tests/test_milestone_verb.py → #6116
  Built 2026-11-02: the owner's reorder from the console is `builder order` (tests `fichero-builder/tests/test_order_verb.py::test_rewrite_renumbers_parks_and_unparks_keeping_each_lines_text`, `::test_save_commits_on_the_build_order_branch_queues_a_tiny_batch_and_refuses_while_one_is_saving`).
- `issues.pick-order-step-bug-priority` [GAP] — within a milestone: steps in build order, then bugs, then priority. Test: an owed test in `test_milestone_verb.py` (in the `tests` tests; the file exists, the test does not) → #6116
- `issues.harness-closes-after-integration` [OK] (#6337) — an issue closes only by `builder landed` once its commit is on origin/integration. Test: fichero-builder/tests/test_landed_verb.py → #6116
- `issues.spec-less-milestone-gets-a-spec-issue` [PARTIAL] (#6336) — Test: an owed test `test_triage_tool.py` (for the `workflows` tests) → #6116


### From `git-worktree-workflow.md` — brought in

- `git.one-repo` — **[CONVENTION]** all worktrees share `~/code/fichero/.git`; only `main`
  pushes to origin. True by definition of `git worktree` (there is only one `.git`, ever) —
  not a code path that could regress independently of git itself. Challenged: a script
  COULD run `git rev-parse --git-common-dir` from every worktree and assert they agree, but
  that's checking git's own invariant, not this repo's discipline — stays CONVENTION.
- `git.branch-off-origin-main` — **[CONVENTION]** lanes branch off a fetched `origin/main`, or off the integration
  branch's HEAD sha when they need its unpushed commits. The launcher script that pinned this was removed
  (2026-10-16); the rule is now a manager decision, not a code path.
- `git.integration-gate` — **[CONVENTION]** multi-lane work gates on `integration` before
  `main`. A manager decision about WHEN to gate, not a code path — `verify_all.sh` runs the
  same way regardless of which branch invokes it. Challenged: no code path decides "2+
  lanes landing together" vs. "one lane gates alone" — genuinely a judgment call, stays
  CONVENTION.
- `git.commit-never-stash` — **[PARTIAL]** (#4814, retagged 2026-09-18 from CONVENTION — a
  cheap script CAN pin the outcome, so calling it untestable was wrong) interrupted work is
  a WIP commit, not a stash. Built: `scripts/check_no_orphan_stashes.py`, a shrink-only
  ceiling over the shared stash stack (`scripts/stash_ceiling.json`, seeded at the current
  count of 19 grandfathered maintainer entries) — a NEW stash beyond the ceiling fails
  loudly, naming the newest entries; the count going DOWN fails too (lower the ceiling
  deliberately, never absorb silently). `--update-ceiling` is itself LOWER-ONLY (plus
  first-time seeding) — it refuses to write a HIGHER count, closing the exact escape hatch
  where a worker who stashed could otherwise just re-run it and go green; raising it is a
  maintainer hand-edit of `scripts/stash_ceiling.json` with a reason. Read-only: never runs
  a mutating stash command. Auto-wired into `verify_all.sh`'s `scripts/check_*.py` sweep by
  its own filename — no separate wiring step — and it passes today (19==19). Still PARTIAL,
  not OK: the 19 pre-existing entries are accepted debt, not resolved (#4814). Pinned:
  `test_check_no_orphan_stashes.py::test_count_equal_to_ceiling_passes`,
  `::test_count_above_ceiling_fails_and_names_newest`,
  `::test_count_below_ceiling_fails_asking_to_lower_it`,
  `::test_update_ceiling_first_time_seeding_is_allowed`,
  `::test_update_ceiling_refuses_to_raise`,
  `::test_update_ceiling_lowers_when_count_drops`,
  `::test_update_ceiling_is_a_noop_when_equal`,
  `::test_never_calls_a_mutating_git_command`.
  Built (#6658 #6659): the ceiling file records a `host_id` (a hash of the hostname, never the name); a machine whose id
  differs, or a ceiling with no `host_id`, prints a `not run:` row and exits 0 instead of judging a stack it does not own;
  `--update-ceiling` stamps the id. Not built: the committed ceiling has no `host_id` yet, so the check is `not run:` on every machine,
  the owner's included, until `--update-ceiling` is run once on the owning machine; `check_tool` does not turn a guard's
  `not run:` line into a not-run row of its own. Pinned: `::test_a_ceiling_set_on_another_machine_is_not_run_here`,
  `::test_a_ceiling_naming_no_machine_is_not_run`, `::test_update_ceiling_stamps_the_host_on_an_unstamped_ceiling`,
  `::test_the_host_id_is_a_hash_not_the_hostname`.
- `git.agent-commits-authored-as-claude` — **[PARTIAL]** (#5997) a commit with an agent trailer (`Directed-By:` or a `Co-Authored-By: Claude …`) is authored as `Claude <noreply@anthropic.com>`, the maintainer credited by the trailer (AGENTS.md); 37 commits from 2026-10-19 reached integration authored as the maintainer (left there by ruling). Built: `scripts/check_agent_commits_authored_as_claude.py [BASE..TIP]` (default `origin/integration..HEAD`; stdlib and git only), which fails a push RANGE naming each offending sha and its author (exit 1), exits 2 when git cannot read a given range, SKIPs with exit 0 when run with no argument where there is no `origin/integration` (the gate runs every check bare; the M4 clones have none), compares the author exactly (name and address, case and all), and judges only the range it is given, so history already on integration never fails it (run on `c13efa580..be2cd2e12` it names those 37). It judges a range, not the tree, so the every-guard sweep lists it as machine state. Wired into the Pro push checklist (`pro-push-guards.sh <sha> <app_packages> [BASE..TIP]`). Not built: a check at commit time (a hook), or in `verify_all.sh` with the push range. Pinned: `test_check_agent_commits_authored_as_claude.py` (a good and a bad commit in a temp repo, a Co-Authored-By Claude trailer, a human co-author passes, history outside the range is not judged, an unreadable range fails).
  Built 2026-11-05: a `Written-By:` trailer (the one trailer a commit carries since the owner's ruling) counts as an agent trailer too, so such a commit must be authored as `Claude <noreply@anthropic.com>` whatever model wrote it, as for the old trailers (`scripts/check_agent_commits_authored_as_claude.py`, test `fichero-server/tests/unit/scripts/test_check_agent_commits_authored_as_claude.py::test_a_written_by_trailer_counts_as_an_agent_trailer`).
- `git.cleanup-merged-worktrees` — **[BROKEN]** (#4813, retagged 2026-09-18 from CONVENTION —
  this ONE was closer to testable than it looked, and running the new check found a real
  violation, not just a theoretical one) merged lanes removed + branch deleted; no rot. Built:
  `scripts/check_merged_worktrees.py`, cross-referencing `git worktree list --porcelain`
  against `git merge-base --is-ancestor … main` (branch or detached-HEAD commit), with a
  shrink-only allowlist for deliberately-kept worktrees; main checkout + the current
  worktree are always exempt. Read-only: prints `git worktree remove …`, never runs it.
  Run for real (2026-09-18): 3 lingering worktrees found today
  (`.gate-snapshots/snap-testready`, `impl-loove-entity`, `release-merge`) — the "no rot"
  claim is currently FALSE in this repo, not merely unproven, hence BROKEN. Now wired into
  `verify_all.sh` (it is a `check_*.py`), and all 3 are allowlisted with an honest
  "awaiting maintainer decision" reason each (`scripts/merged_worktrees_allowlist.json`) so
  the gate stays green while the maintainer decides — the allowlist has no automated write
  path, every entry is a hand edit with a reason, same one-way principle as the stash
  ceiling. This masks the symptom for the gate, not the underlying rot: still BROKEN until
  the maintainer resolves the 3 (removes them, or turns "awaiting decision" into a permanent
  reason) (#4813). Pinned:
  `test_check_merged_worktrees.py::test_merged_lane_is_flagged`,
  `::test_unmerged_lane_is_not_flagged`,
  `::test_main_checkout_and_current_worktree_are_never_flagged`,
  `::test_allowlisted_merged_lane_is_not_flagged`,
  `::test_stale_allowlist_entry_fails`,
  `::test_never_calls_a_mutating_git_command`.
- `git.abandoned-worktree-flagged` — **[GAP]** (#4813, the same worktree-rot class) a guardrail
  flags a lane worktree that is `ahead:0` of its base and abandoned, the unmerged twin of
  `git.cleanup-merged-worktrees`; read-only, with the same shrink-only allowlist and reasons.
  (Ruled 2026-10-04, design lead.)
- `git.canonical-checkout-clean` — **[GAP]** (#4813) the canonical checkout (`~/code/fichero`) is
  a clean `main` mirror and venv host only: it holds no uncommitted work, and all work happens in
  worktrees. (Ruled 2026-10-04, design lead.)
- `git.updated-via-github` — **[CONVENTION]** "what's next" comes from milestones/ROADMAP,
  not a shared branch. Describes where a human/agent looks for work — not a code path.
  Challenged: no artifact in the repo records WHERE an agent looked for its next task, so
  there is nothing to assert against — stays CONVENTION.

### From `deterministic-conductor.md` — brought in

- `pipeline.issues-and-milestones-kept-current` [MISSING] (#6116) — the runner works in the existing issues and
  milestones, never a second system. Only existing milestones are used: a new one is a queue item, never created by
  the runner; one with every issue closed is proposed for closing in the queue; progress (closed of total) is on the
  Milestones page; the no-milestone count only goes down. One claim convention: `claimed` is set while an item codes
  and removed on `failed` or `needs-maintainer`; `status:in-progress` and assignees are retired as locks. A short
  comment with a `<!-- pipeline:<event>:<task> -->` marker goes on checked (check summary), reviewed (verdict) and
  pushed (sha), so resume can see which comments exist; the issue closes only through close-on-push from `Fixes #N`;
  `Part of #N` leaves it open with what is left. Every write goes through one function, `--dry-run` by default in
  tests. Tests: `pipeline/tests/test_gh.py::test_every_write_goes_through_one_function_and_dry_run_writes_nothing`,
  `pipeline/tests/test_core.py` (its test `test_claimed_label_follows_the_state` is owed: not in that file today),
  `pipeline/tests/test_feeder.py::test_claimed_issues_are_skipped`.
- `pipeline.github-actions` [PARTIAL] (#6116) — the Macs are the only gate: no GitHub workflow runs ruff, guards or
  tests (owner ruling 2026-11-01; `ci.yml` was deleted after it had been disabled by hand and had never run on
  integration). GitHub keeps only what needs nothing but GitHub, one workflow each: `close-fixed-issues.yml` runs
  `close_fixed_issues.py --apply` after a push to integration (a `Part of #N` never closes); `issue-milestone.yml`
  labels a new issue with no milestone `no-milestone` and one by an outside author `from-user`. Anything more on
  GitHub needs a reason. Tests: a `test_workflows` pytest under `fichero-server/tests/unit/scripts/`, written with
  Step 1.1 (the YAML is parsed and each workflow's trigger, condition and command are asserted; it also asserts
  no workflow runs pytest, ruff or a guard script).
  Phase 0 amendment (owner 2026-11-17/18, from the cut `pipeline.github-actions`): engine tests, guards and the security scans run on every lane push on GitHub's hosted runners (the repo is public); Mac builds run on a self-hosted runner limited to this repo's own branches, never fork pull requests.
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
  this matters most; the trial's engine ran the gate in the project root and failed a correct fix). A diff that changes or removes a file under those paths goes to `needs-maintainer` (for the fichero profile those are `scripts/check_*`, `scripts/lane_ready_check.sh` and `scripts/gate`; the runner's own `pipeline/` code and new tests pass this rung and the reviewer is the gate, but a diff that deletes or weakens a base test, by a removed test function, fewer `assert`s or an added skip/xfail, still goes to `needs-maintainer`); adding a new guard is
  allowed, since the pinned runner does not run it until the maintainer pulls it in. The runner moves to a new sha only on the
  maintainer's command, after the push. Tests: `pipeline/tests/test_checks.py::test_a_coder_change_that_breaks_a_guard_turns_the_check_red`,
  `pipeline/tests/test_checks.py::test_checks_run_from_the_pinned_checkout`,
  `pipeline/tests/test_checks.py::test_diff_touching_check_paths_needs_maintainer`,
  `pipeline/tests/test_checks.py::test_a_new_guard_may_be_added_but_no_check_changed`,
  `pipeline/tests/test_checks.py::test_new_runner_code_and_a_new_test_pass_pinned_checks`,
  `pipeline/tests/test_checks.py::test_deleting_or_weakening_a_base_test_or_editing_a_guard_needs_maintainer`,
  `pipeline/tests/test_checks.py` (its test `test_checks_cwd_is_the_worktree` is owed: not in that file today),
  `pipeline/tests/test_checks.py::test_a_coder_sitecustomize_cannot_green_the_guards`,
  `pipeline/tests/test_core.py::test_rewriting_own_acceptance_in_the_spec_needs_maintainer`.
  The Builder compares with the merge-base (`since...head`, `work.lane_diff`): a pinned file only the base moved is no part of the lane's diff, and the lane
  stays green. Test: `fichero-builder/tests/test_pinned_merge_base.py`. Spec-change: manager 2026-11-21 pinned checks compare with the merge-base.
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
- `pipeline.test-red-on-base` [OK] — the branch's changed or new test files are copied into a scratch
  worktree at origin/integration and must fail there, and must pass on the branch; a test that passes on the base
  proves nothing. Tests: `pipeline/tests/test_checks.py::test_red_on_base_fails_a_test_that_passes_on_base`,
  `pipeline/tests/test_checks.py::test_red_on_base_passes_a_real_fix`.
- `pipeline.review` [PARTIAL] (#6116) — built: `python -m pipeline send-back <item>` re-dispatches a NOT_READY item to its coder with the findings (the scheduler does it for a binding one within the retries). a verdict is `verdict(issue, sha, READY|NOT_READY, by, findings)`; a short sha
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
  Phase 0 amendment (owner 2026-11-17/18, from the cut `pipeline.review`): an open model's verdict is recorded beside the binding one and decides nothing; agreement is reported weekly; promotion needs the numbers and a yes (the reviewer is never the builder's model).
- `pipeline.nightly-gate` [PARTIAL] (#6116) — built: `python -m pipeline land <item> [--apply]`, the manual landing of ONE reviewed READY item: every `scripts/check_*.py` (no skip list) in a scratch tree of the reviewed head, then a fast-forward push of that sha to the profile's integration branch only (never main, never a tag, never forced); a dry run unless `--apply`; the scheduler queues "ready to land" and never pushes. Not built: the night's candidate merge, the M4 engine gate and the targets. Reviewed items merge into the night's candidate; the full engine gate runs on
  the M4 overnight; green → push integration → the nightly targets (dev DMG plus both TestFlights; Mac, iPhone and
  iPad get the build); red → nothing is pushed or built and the page says which part and which item; nothing pushes
  main except the weekly release. Tests: an owed test `test_nightly.py` (for the `tests` tests),
  an owed test `test_nightly.py` (for the `tests` tests).
- `pipeline.closes-issues` [PARTIAL] (#6116) — the runner closes issues and milestones, properly, and never a second
  closer: when an item's commit lands on integration with its checks green, `scripts/close_fixed_issues.py` (the one
  closer, also the close-fixed-issues Action's) closes the issue with a comment naming the sha and the checks; a
  dry-run line goes in the journal before each close; a worker-reported residue (part of the issue not done) updates
  the issue body with what is left and leaves it open; a milestone closes when its last open issue closes; the page
  shows what was closed today. Tests: `pipeline/tests/test_core.py::test_landing_closes_through_the_one_closer_after_a_dry_run_line`,
  `pipeline/tests/test_core.py::test_a_residue_leaves_the_issue_open_with_what_is_left`.
- `pipeline.weekly-release` [PARTIAL] (#6116) — on its schedule the weekly release runs every target and stops for the
  maintainer's yes (on the page or the CLI, never over MCP) before anything public: the GitHub release, Sparkle, the
  product site (tubb.ca/apps/fichero, appcast, release page), the App Store submission; the pre-release scan checks
  private docs as well as keys and paths. The docs site (MkDocs) is its own schedule job: it refreshes after a green
  push, built from a clean checkout of the pushed sha, never a working tree (a prior deploy published untracked
  private docs/ pages), after the scan for private paths. Tests:
  an owed test `test_nightly.py` (for the `tests` tests),
  an owed test `test_nightly.py` (for the `tests` tests).

### From `spec-pipeline.md` — brought in

- `pipeline.status` — **[OK]** `spec_pipeline.py status` prints a per-spec table of
  behavior counts by tag and always exits 0 (it's a report, not a gate). Pinned by
  `test_spec_pipeline.py::test_status_counts_by_tag`, `test_spec_pipeline.py::test_status_exits_0_even_with_missing_specs_dir`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-a-broken-needs-issue` — **[OK]** a behavior tagged
  BROKEN/GAP/GAP-BROKEN/PARTIAL/MISSING with no cited issue is an illegal state, checked
  offline (delegates to `check_spec_broken_has_issue.py`'s parser). Pinned by
  `test_spec_pipeline.py::test_rule_a_broken_with_no_issue_fails`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-b-stale-tag-closed-issue` — **[OK]** a broken-family behavior citing
  a CLOSED issue is an illegal state (stale tag or wrongly-closed issue). Pinned by
  `test_spec_pipeline.py::test_rule_b_closed_issue_still_broken_fails`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-c-milestone-mismatch` — **[OK]** a behavior citing an issue whose
  GitHub milestone differs from the spec's declared `Milestone:` is an illegal state — but
  ONLY for a plain `#N` citation. An arrow citation (e.g. `→ #NNNN increment K`, a
  deliberate pointer to another tracked epic increment) is legitimately cross-milestone and
  exempt.
  Pinned by `test_spec_pipeline.py::test_rule_c_milestone_mismatch_fails`, `test_spec_pipeline.py::test_rule_c_arrow_citation_is_exempt`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-d-ok-needs-real-test` — **[OK]** a behavior tagged OK with no cited
  test, or citing a test name that resolves to no file/function anywhere under
  `fichero/Tests` or `fichero-server/tests`, is an illegal state. Pinned by
  `test_spec_pipeline.py::test_rule_d_ok_with_no_test_fails`, `test_spec_pipeline.py::test_rule_d_ok_with_nonexistent_test_fails`,
  `test_spec_pipeline.py::test_rule_d_ok_with_real_test_passes`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-e-ok-needs-closed-issue` — **[OK]** a behavior tagged OK citing an
  issue that is still OPEN is an illegal state (the fix isn't actually landed, or the tag is
  premature). Pinned by `test_spec_pipeline.py::test_rule_e_ok_cites_open_issue_fails`,
  `test_spec_pipeline.py::test_rule_e_ok_cites_closed_issue_passes`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-f-orphan-open-issue` — **[OK]** an OPEN issue on a spec's milestone
  cited by no behavior is reported as INFO by default, promoted to a failure with
  `--strict`. Pinned by `test_spec_pipeline.py::test_queue_excludes_claimed_and_closed_issues` (queue side) — the
  INFO/strict split itself is exercised structurally in `cmd_check`; see Open questions. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-g-milestone-spec-mirror` — **[OK]** a GitHub milestone shaped like a
  spec anchor with no spec, or a spec-declared milestone with no matching GitHub milestone,
  is an illegal state (mirrors `check_spec_milestones.py` from the milestone side). Uses a
  DEDICATED milestone listing (`get_milestones`, `gh api .../milestones?state=all`), not just
  milestones seen on issues — an empty milestone (zero issues) is otherwise invisible to a
  script that only calls `gh issue list`. Pinned by
  `test_spec_pipeline.py::test_rule_g_empty_milestone_with_no_spec_fails`,
  `test_spec_pipeline.py::test_rule_g_workstream_bucket_milestone_is_exempt`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-g-scope` — **[OK]** rule (g) reads a milestone's `state`/
  `open_issues` before deciding whether it's a finding at all, so a genuinely dead milestone
  never shows up as debt (creative-director cross-check, 2026-09-18 — 48 of 51 "CLOSE"
  candidates in the first triage pass were already closed with zero open issues, and rule
  (g) was baselining them as noise). Four combinations: CLOSED + 0 open → not a finding
  (dead, GitHub already keeps it out of the way); CLOSED + N>0 open → a finding ("holds N
  open issues"); OPEN + 0 open → a finding suggesting closing it; OPEN + N>0 open → the
  original "write the spec" finding. Pinned by
  `test_spec_pipeline.py::test_rule_g_closed_milestone_with_zero_open_issues_is_not_a_finding`,
  `test_spec_pipeline.py::test_rule_g_closed_milestone_with_open_issues_still_fails`,
  `test_spec_pipeline.py::test_rule_g_open_milestone_with_zero_open_issues_fails_suggesting_close`,
  `test_spec_pipeline.py::test_rule_g_open_milestone_with_open_issues_fails_asking_for_a_spec`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-g-non-spec-allowlist` — **[OK]**
  `scripts/spec_pipeline_non_spec_milestones.json` exempts a real non-spec program/
  workstream milestone (release, hygiene, lint sweeps, platform-craft — populated from
  `agent-work/spec-pipeline/legacy-milestones-triage.md`'s 34 KEEP rows) from rule (g),
  same shrink-only contract as `check_spec_broken_has_issue.py`'s `GRANDFATHERED_FILES`: an
  entry whose milestone no longer exists, or now has a real spec, or carries no `reason`, is
  itself a rule-(g) finding rather than being silently trusted. Pinned by
  `test_spec_pipeline.py::test_rule_g_allowlisted_milestone_is_exempt`,
  `test_spec_pipeline.py::test_rule_g_allowlist_stale_entry_fails_when_milestone_gone`,
  `test_spec_pipeline.py::test_rule_g_allowlist_entry_now_specced_fails`,
  `test_spec_pipeline.py::test_rule_g_allowlist_entry_without_reason_fails`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.rule-h-convention-governance` — **[OK]** `[CONVENTION]` is a real tag
  (2026-09-18, replacing the earlier unrecognized-string workaround in
  `git-worktree-workflow.md`) for a behavior that states a human/agent norm, not a claim
  about code — exempt from rule (d)'s test-citation requirement, but guarded so it can't
  become a silent escape hatch: (1) every `[CONVENTION]` behavior is itself a rule-h
  "registered" finding, so the CURRENT count is a shrink-only baseline ceiling — a NEW
  convention anywhere fails `check` until deliberately re-baselined; (2) allowed only in a
  spec under `specs/harness/` (a process/harness spec) — used elsewhere, that's its own
  rule-h finding; (3) a `[CONVENTION]` bullet with no reason clause explaining why no test
  can pin it (a cheap keyword presence check, `CONVENTION_REASON_RE`) is its own rule-h
  finding. `status`'s per-spec table carries its own `CONVENTION` column, so the tag is
  counted separately from the ordinary tag vocabulary. Pinned by
  `test_spec_pipeline.py::test_rule_h_convention_in_harness_with_reason_is_registered_only`,
  `test_spec_pipeline.py::test_rule_h_convention_outside_harness_fails`,
  `test_spec_pipeline.py::test_rule_h_convention_with_no_reason_fails`,
  `test_spec_pipeline.py::test_rule_h_compliant_convention_can_be_baselined_and_stays_green`,
  `test_spec_pipeline.py::test_rule_h_new_convention_fails_the_shrink_only_ceiling`,
  `test_spec_pipeline.py::test_rule_h_does_not_count_convention_as_a_tagged_ok_behavior`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.offline-blind-not-green` — **[OK]** `--offline` skips every
  GitHub-dependent rule (b, c, e, f, g) and prints `OFFLINE: blind to rules …` rather than
  reporting success by omission; offline-only rules (a, d) still run and can still fail.
  Pinned by `test_spec_pipeline.py::test_offline_reports_blindness_and_only_runs_offline_rules`,
  `test_spec_pipeline.py::test_offline_still_catches_offline_rule_a`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.gh-failure-exits-2` — **[OK]** without `--offline`, a missing `gh`
  exits 2 rather than silently skipping the GitHub-dependent rules; the code path mirrors
  the exact pattern `check_spec_milestones.py` already uses for its own soft-skip, just made
  hard here. Pinned by `test_spec_pipeline.py::test_get_issues_fails_when_gh_is_missing`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.missing-specs-dir-exits-2` — **[OK]** every subcommand except `status` and
  `agent-work` exits 2 when the specs directory does not exist. Pinned by
  `test_spec_pipeline.py::test_missing_specs_dir_exits_2`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.baseline-ratchet` — **[OK]** `check` fails ONLY on an illegal state not yet
  in `scripts/spec_pipeline_baseline.json`, and ALSO fails when a baselined entry no longer
  occurs (fixed but not removed — shrink-only, same contract as
  `check_spec_broken_has_issue.py`'s `GRANDFATHERED_FILES`). The OK summary line reports "N
  baselined illegal state(s) remain (by rule: …)". Pinned by
  `test_spec_pipeline.py::test_check_passes_against_its_own_baseline`,
  `test_spec_pipeline.py::test_check_fails_on_new_illegal_state_not_in_baseline`,
  `test_spec_pipeline.py::test_check_fails_when_baselined_entry_no_longer_occurs`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `pipeline.check.update-baseline` — **[OK]** `check --update-baseline` writes the current
  illegal-state set to the baseline file, sorted by `(rule, spec, key)` for stable diffs;
  re-running it with nothing changed produces a byte-for-byte identical file. Pinned by
  `test_spec_pipeline.py::test_update_baseline_writes_sorted_and_idempotent`. Test: `fichero-server/tests/unit/scripts/test_spec_pipeline.py`.
- `spec.absent-tags-agree-with-tests` — **[GAP]** (#5112) a behaviour tagged absent has no test naming it; the 27 mismatches (8 GAP) are retagged.
- `pipeline.github-hygiene-milestones-labels-needs-your-test` — **[GAP]** (#5461) remaining legacy milestones are folded into spec milestones or justified, needs-your-test issues are re-checked and stale status labels retired so every open issue has a milestone.

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

### From `dev-workflows.md` — header and intent (as written; status at the time)


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
> `ui/activity-pane.md` keeps the job model, lanes, throttling and durability; § E overrides its window
> columns and adds workers as rows. `ui/workflows.md` keeps the canvas; no graph drives a worker's loop.


### From `dev-workflows.md` — Intent


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


### From `dev-workflows.md` — 0. Slice 0 — a real cluster in two to three days (read this section alone)


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


### From `dev-workflows.md` — What exists today (paths under `fichero-server/src/fichero_server/`; measured 2026-10-31)


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


### From `dev-workflows.md` — Decisions


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

#### Deployment profiles

| Profile | Machine | Models | Runs |
|---|---|---|---|
| Builder, now | M1 Pro 16 GB | Claude Code (Sonnet builds, Opus reviews; Fable or Opus writes specs); then OpenRouter through Pi | clusters, reviews, dry runs; engine on a scratch base path, workers as the second user |
| Builder, end state | M5 Studio 128 GB | small local models pinned under a memory cap, a local server with a prefix cache; cloud for the binding review until the log says otherwise | 2-3 builder sessions + research; headroom for the gate and a build |
| Researcher | M5 MacBook Pro 24 GB | one small local model at a time, Apple frameworks, MLX readers when chosen; cloud only where the person allows, cost shown first | one task at a time, 16-32k context, handoff per source |

#### tool.triage — what `builder triage` reads and writes

`builder triage` is the one writer of GitHub metadata besides `builder steps` and `builder landed`; a person edits by
hand only to overrule. It reads three things: the spec files under `docs/contributor_manual/specs/<area>/` (which issues
each cites, its `> Milestone:` line), `harness.toml [triage.labels]` (old label → kept label or `spec:<stem>` hint; edit
there, not in code) and `docs/contributor_manual/specs/build-order.md` (the owner's order of milestones; read, proposed
to, never written). Each flag is one rule of `harness/issues-and-labels.md` and runs alone or with the others, in the
order labels → specs → milestones → assignees → order; a rerun changes nothing (idempotent), and `--dry` shows the counts
the write path would produce.


### From `dev-workflows.md` — Rulings


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


### From `dev-workflows.md` — Rulings of 2026-10-31 on isolation and landing (decided, no longer open)


- Workers and the ladder run as a second macOS user with no GitHub credential; a start refuses if the user or its clean
  probe is missing (set-up in § 0: the user outside `staff`, the owner's home `700`, a workroot, one sudoers line, the
  worker's own tools and `claude` sign-in, an anonymous clone of the public repository).
- `integration` has the ruleset `protect-integration`: no deletion, no force-push, no required status check. A later
  "restrict updates" rule waits for a GitHub App and three clusters landed by `land`.
- `main` stays at zero approving reviews until a GitHub App exists; the Lead pushes in Slice 0; the App (Contents write
  and Metadata, no Workflows) pushes later from a separate process.
- #4402 is not an owner question; `ux.controls-work` cites #5933.


### From `dev-workflows.md` — Documentation matrix


| Doc | Says |
|-----|------|
| `docs/contributor_manual/how-fichero-is-built.md` | Fichero builds itself through its harness; how to run a cluster on a scratch path as the worker user; the Researcher as the same harness |
| `docs/contributor_manual/review-checklist.md` | the reviewer's checklist (spec diff, range-diff after a rebase, tests of changed readers, the shell file cap; the performance and security lenses of #6600 point here) |
| `ui/research.md`, `ui/activity-pane.md` | the surfaces; point here for orchestration, the window's columns and worker rows |
| `harness/deterministic-conductor.md` | the frozen runner's record |

### From `agent-profiles.md` — header and intent (as written; status at the time)


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


### From `agent-profiles.md` — Purpose


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


### From `agent-profiles.md` — Terms


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


### From `agent-profiles.md` — Rulings (owner 2026-11-16, paraphrased)


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


### From `agent-profiles.md` — Open questions for the owner


All three answered 2026-11-16: the diff bound is per role in the role profile, no global number; Step 4.4 uses a scratch
test repository, a real book repository later; costs and tokens stay local on 127.0.0.1 and never reach an issue or the
repository. None open.


### From `agent-profiles.md` — Changes to dev-workflows


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


### From `agent-profiles.md` — Documentation matrix


| Doc | Says |
|---|---|
| `docs/contributor_manual/how-fichero-is-built.md` | a worker is model × harness × profile on a declared workflow; where prompts live; role × stack; tool sets per role and stack; the diff bound per role; the bake-off rule; costs stay local |
| `harness/builder-console.md` (sibling, being drafted) | the website's pages; the Runs, Compare and Bake-offs views take their columns from here |
| `AGENTS.md` | the one trailer line; the root `agents/` folder is gone; prompts live in the builder |
| `docs/contributor_manual/review-checklist.md` | item 10 is the one trailer line |

### From `builder-console.md` — header and intent (as written; status at the time)


> of work has one state and an age on the console, that a lane page shows what was done and what it cost, and that the
> loop, not a person, moves work on, retries it, asks, or closes it out.

> **Status: DRAFT — written 2026-11-16 from the console review (kept untracked with the manager's briefs as
> `CONSOLE-REVIEW.md` and `build-order-proposed.md`) and the owner's direction of that day, paraphrased.** Tags: [OK] built
> and tested by name · [PARTIAL] exists, not wired · [GAP] not built · [BROKEN] built, wrong today. Issues: one per build-order
> step below, in the sibling's milestone. Scope with other specs: `harness/dev-workflows.md` keeps the loop's verbs (`run.loop-status` is replaced by
> § A–E here), the ladder, review, land and the jail; `harness/agent-profiles.md` keeps the run record
> (`agent-profiles.run.record`) and the columns of Runs, Compare and Bake-offs (`agent-profiles.console.runs`): this spec
> owns the pages they sit on, the one work tree the queue is fed from, the state and age of every step, what the loop does
> with stale work, and cleanup as a workflow step. The sibling's links to `harness/builder-website.md` mean this file.


### From `builder-console.md` — Decisions (owner 2026-11-16)


- **Fichero Harness is its own product**, and **for now its code stays inside the Fichero repository** (owner
  2026-11-16: the spec guards, specs and tests are already set up here); the repository split is Step 4.3, kept and
  **HELD** until the owner's word. When it moves, Fichero keeps only its project profile (`harness.toml` and
  `agents/projects/fichero/`). Public today in `fichero-builder/`: machine names, gate paths, the jail layout, prices and
  spend caps; a split means two repositories to version (the harness pins a Fichero profile version, Fichero pins a
  harness version) and one place to test generically. Direction: Fichero Harness may later be embedded in the Fichero app as **Fichero Researcher**, after the Harness is
  solid and not soon (owner 2026-11-16), so its core is a library with no app, no page and no GitHub assumption.
- **One engine API** (the one the MCP server exposes, § F) is what every front end renders: the HTML website and, later,
  a native Swift view inside Fichero. No page carries logic the API does not.
- **Everything is editable the same two ways** (website, MCP) through the same verbs, every edit audited (§ F).
- **The work store is host-agnostic** (§ A.3): a public GitHub repository, a private one, or a private store inside
  Fichero, behind one interface; "forgets nothing" never depends on GitHub.
- **Three project kinds to start** (`[project].kind`, consistent with `agent-profiles.project.profile`): `code` (a
  repository: Fichero or the owner's other code; profile = repo path, checks, tools, roles), `data` (research on a
  Fichero library's own records; this is Fichero Researcher when embedded in the app), `text` (a repository of writing,
  a book; its workers may call **Tinderbox** through its scripting interface or MCP as a declared tool of the profile).
  **Hosts** (terminal verbs, the website, inside Fichero) are independent of the kind: any host runs any kind.
- **The state store is Pydantic models over DuckDB** (owner 2026-11-16): the database system Fichero already uses,
  shared by builder, researcher, writer and the generic harness; `journal.jsonl` stays the append-only event log. A
  workflow may run on LangGraph or LangChain, or on Fichero's own workflows and recipes, as options behind one
  interface (`agent-profiles.workflow.declared`).
- **Costs and tokens are local only** (127.0.0.1): never in an issue, a comment or the repository; the page shows them,
  the work store never receives them.
- **Priority**: Fichero's release comes first; the Harness is a side project with one of the three worker slots (two
  on Fichero, one on the Harness).
- **Sequencing**: Stage 1 of `agent-profiles` (trailer, role prompts, jcodemunch + jdocmunch, Swift test rungs) and
  Stage 1 here (one state and age, stale work acted on, cleanup) are built in today's `fichero-builder/`. The repository
  split (`git subtree split` of `fichero-builder/` with its history into the Fichero Harness repository; Fichero keeps its
  profile) is Step 4.3 below, held until the owner says.


### From `builder-console.md` — Intent


The owner opens one page and sees what is being worked on, what worked, what failed and why, and what it cost, from one
live state; clicks a lane and sees everything it did; compares models, harnesses and roles over time. The builder is
**autonomous and forgets nothing**: the order of work is the queue's own, not a hand file that drifts; every step has one
state and an age; nothing half done is left silently; a finished step moves the lane to the next one; cleanup is a step
of the workflow. Project-neutral: a milestone, a step, a lane, a run and a commit mean the same for code, a book or a
research project; the page names no Fichero path, rung or branch, only what `harness.toml` declares.


### From `builder-console.md` — Terms


- **Work tree** — milestones › steps › lanes › runs, one record each, in `<state>/work.json` (§ A); the queue is a view of it.
- **Step** — one unit a lane takes (a build-order step or a cluster); it has exactly one **state** and an **age** (seconds in that state).
- **Lane** — one worktree working one milestone's steps in order; a **run** is one session of one worker on one step (`agent-profiles.run.record`).
- **Stale** — a step older in a non-final state than `[loop].stale_hours` for that state (defaults below); the loop acts on it.
- **Final states** — `landed`, `closed-out` (residue filed as an issue, tree swept), `retired` (a trial or a superseded lane, with its reason).


### From `builder-console.md` — Open questions for the owner


A. Answered 2026-11-16: Pydantic models over DuckDB, the journal kept as the event log; § A.3 is written against it.
B. **Which work stores ship first.** GitHub public and private share one implementation and exist today; the in-Fichero
   store needs the engine's records and the Researcher front end. [PROPOSED: GitHub first; the in-Fichero store when
   Fichero Researcher starts, behind the interface from day one so no page or verb learns GitHub.]
1. The stale hours above: are the defaults right, and is `blocked → closed-out after 2 × 48 h unanswered` too eager? [PROPOSED: yes; a closed-out step is an issue with its residue, nothing is lost.]
2. Does a `retired` lane keep its runs on Compare? [PROPOSED: yes, flagged `retired`; a trial is data.]
3. Answered 2026-11-16: money and tokens are local only, 127.0.0.1, never in an issue or the repository.
4. Is the work tree one file (`work.json`) replacing `queue.json`, or `queue.json` plus a `milestones` record? [PROPOSED: one file; `queue.json` is read once and migrated with a row.]


### From `builder-console.md` — Changes to other specs


- In `dev-workflows` `run.loop-status`: its page text is replaced by § C; its JSON (`/status.json`) gains `work`, every lane's
  one `state`, `state_since`, `flags` and the labelled numbers, and drops `done: true` on a lane dict.
- In `dev-workflows` `tool.queue`: the step states are § B's list; `paused` is a lane flag; a finished lane takes the next
  milestone from the work tree (§ B.3), and `build-order.md` is no longer read.
- In `agent-profiles` `console.runs`, `cleanup.after-land`, its § G and Step 2.3: the sibling now names this file; the loop behaviours of § B (stale, moves-on, cleanup) may move into that spec's
  workflow section if the owner prefers one home for the loop.
- In `harness/issues-and-labels.md`: "read by `builder milestone`, `builder queue` and the loop" now names the work tree.
- In `agent-profiles` `project.profile`: `[project].kind` is one of `code`, `data`, `text` (not `code` or `text`); a `text`
  profile may declare Tinderbox as a role's tool; `[project].work_store` names the store (§ A.4); the sequencing in
  Decisions above (everything in `fichero-builder/` inside the Fichero repository; the split held) applies to both specs.

### From `performance-sweep.md` — header and intent (as written; status at the time)


> the hotspot table and the warnings list live and how a `Performance - <area>` issue is born). No user-facing surface.

> Design-led (Testing Constitution). **Status: DRAFT — awaiting the owner's approval (written 2026-11-15 from the owner's
> rulings of 2026-11-14 and 2026-11-15 on #6600, paraphrased).**
> Tags: [OK] built and tested by name · [PARTIAL] exists, not wired · [GAP] not built · [BROKEN] built, does not run.
> Scope with other specs: `harness/dev-workflows.md` keeps the ladder, the rungs and the method
> (`quality.perf-method`, `quality.perf-rung-engine`, `quality.perf-rung-app`, `quality.security-scan-rung`,
> `quality.perf-security-sweep`, Steps 2.30–2.32). This spec owns what those rungs FEED and what comes OUT: the sources, the
> fixed workloads, the ranked hotspot table, the filing rule, the ratchet's budgets and the warnings list. Where a bullet
> here changes a dev-workflows bullet, the change is named under "Changes to dev-workflows" at the end.


### From `performance-sweep.md` — Intent


The owner's first goal (2026-11-15, paraphrased): the builder finds the slow and heavy parts of the app and the engine,
and lanes speed them up; past "look at X and make it fast" asks produced the biggest wins, so the harness should produce
those asks on its own. The dimensions are time, CPU, RAM, disk, energy and efficiency (work done per unit of each), for the
Swift app on Mac, iPhone and iPad and for the Python engine. The second goal is that nothing gets slower unnoticed. The
third is that compiler, SwiftLint and Xcode build-system warnings are found, listed and worked down the same way; the
example given is the build-system line about a script phase that runs on every build because it names no outputs.
The sweep's output is a RANKED list of slow and heavy spots (time, CPU, RAM, disk, energy, warnings), each of which becomes a "speed up X" lane, and it reads the logs the app already makes (the `LaunchProfile` and `InteractionProfile` signposts, the engine's `PERF … duration_ms` lines, and Xcode Organizer and MetricKit field data).

Three rules shape everything below. **Platform tools measure, we only read:** `xctrace`, `xcresulttool`, XCTest metrics,
MetricKit, `log show`, pyinstrument/py-spy, memray, `du`; no timer of ours (`adopt-tools-dont-write-our-own`). **Heavy
work runs on the M4 build runner** (`[machines].m4air`, `[check].build_remote`), never on the manager's 16 GB Pro; an app
profile needs the M4's GUI session (`m4-smoke-needs-a-gui-session`). **A measurement that did not happen is NOT GREEN:**
a rung whose tool refused, whose runner was down or whose run printed nothing shows as `not-run`, in the ladder, the
journal and the console (rule 0 of the ladder; #6589 item 1–2 are exactly this failure).


### From `performance-sweep.md` — Changes to dev-workflows


- dev-workflows' `quality.perf-rung-engine`: py-spy is allowed when `[machines].<m>.sudo` names it, and the owner ruled 2026-11-15 that this is the M4 only; pyinstrument stays the default.
  The "not run" alert becomes the `not-run` state above.
- dev-workflows' `quality.perf-rung-app`: the nightly xctrace form gains `File Activity` and `App Launch`; the SwiftUI template's body
  table is the cross-check it already names.
- dev-workflows' `quality.perf-security-sweep` (Step 2.32): the "profile inputs handed to the reviewer" are this spec's `hotspots.json`
  rows and profile paths; the filer's buckets and caps are shared; the module rotation stays.
- Step 2.20: the compiler-warning count moves here (`perf-sweep.warnings.*`); the SwiftLint and ruff ratchets stay there.


### From `performance-sweep.md` — Open questions for the owner


Questions 1 and 2 are answered (owner, 2026-11-15). Question 4 is partly answered: the daily cap is gone. Questions 3, 4's
floors, 5 and 6 are still open; the owner has not ruled on them.

1. Answered 2026-11-15: the work lives in a new GitHub milestone named `performance-sweep`, and #6600, #6610 and the perf
   part of #6589 move into it.
2. Answered 2026-11-15: yes, on the M4 only, through one narrow sudoers line that allows exactly `py-spy` and nothing
   else. Other machines never get it. Without it the engine time profile is pyinstrument's, which does not see forked
   workers or native frames.
3. The profiles cannot be attached to a GitHub issue from the CLI: the issue carries the top frames inline and the run id,
   and the trace lives on the M4's Dev Disk for 30 days. Is that enough, or should the nightly also push a `gh gist` /
   release asset per filed issue?
4. Partly answered 2026-11-15: no daily cap (see the filing rule). Still open: floors for filing (5% of a workload's
   time, 50 MB, 10 MB written, 250 ms hang), to be accepted as the first values and tuned after the first three passes?
5. Which open HTR test set, if any, is the one corpus beyond the generated fixture; or v1 uses the generated 200-page
   library only?
6. The energy dimension on the Mac is CPU time (no per-process energy counter without root; `Energy Log` is iOS-device
   only): acceptable, or should an iOS device live on the M4 for the nightly?

### From `issues-and-labels.md` — header and intent (as written; status at the time)


> and how the harness picks the next thing.

> **Status: DRAFT — awaiting the owner's approval (written 2026-11-01 from the owner's rulings of that evening).**
> Tags: [OK] built · [PARTIAL] exists, not wired · [GAP] not built · [PROPOSED] decided here, not yet ruled.
> Scope with other specs: `harness/dev-workflows.md` owns the verbs (`builder milestone`, `steps`, `landed`, `triage`,
> `queue`); this spec owns what those verbs read and write on GitHub. `specs/_TEMPLATE.md` and
> `specs/_MILESTONE_TEMPLATE.md` point here instead of repeating it; AGENTS.md "Where state lives" points here.


### From `issues-and-labels.md` — Intent


GitHub is the record of work: an issue is a thing to do, a milestone is a spec's worth of things, a label says how an
issue is ordered and what kind it is. The harness keeps all three current on its own, after its own test and
integration; a person never closes, labels or files by hand except to overrule. Anyone, human or model, can answer
"what is next" from GitHub alone, in one listing, with no vibes.


### From `issues-and-labels.md` — The three records


**The milestone is the spec.** One milestone per spec, named by the spec's `> Milestone:` line (already the rule in
AGENTS.md: spec name = milestone name = test tag). Every open issue sits in exactly one milestone. A milestone with
open issues and no spec gets one issue titled `spec: write <milestone> spec` and nothing else runs from it until the
spec is APPROVED. A milestone with no open issues and no spec is closed. The legacy ops buckets (Bugs, Lint, Ratchets,
Performance) stay as milestones for issues that belong to no surface.

**Labels say order and kind within the milestone.** The whole set:

| Label | Meaning | Who sets it |
|---|---|---|
| `step:N.M` | the issue is Step N.M of its spec's build order; title `<spec> Step N.M: <title>` | `builder steps`, `builder triage` |
| `type:bug` · `type:feature` · `type:task` | what kind of work; one per issue | triage, the filer |
| `priority:P0` … `priority:P3` | urgency within the milestone when the build order does not decide | the owner, triage from the issue text |
| `needs-spec` | the issue describes a behaviour no spec holds yet | triage |
| `needs-your-decision` · `needs-your-test` | the owner must rule, or must try it on a real Mac | the harness on a QUESTION row, `builder landed` |
| `status:blocked` | waits on another issue, named in a comment | the harness |

No other labels. Area labels (what part of the app) are what the milestone already says; stage and phase labels
(`phase:R1`…) are what `step:N.M` says once the spec's build order carries the phases. `spec:<slug>` labels are
temporary: triage removes each one as it moves the issue into the spec's milestone.

**The order of milestones is a file**, `docs/contributor_manual/specs/build-order.md`: one milestone per line, top
to bottom, with a one-line reason and the spec path; a `## Parked` section for milestones that are not to be worked (a name or a pattern such as `UX - *`, which owes no spec and is never proposed; test `fichero-builder/tests/test_triage_verb.py::test_a_parked_line_may_name_a_pattern_and_the_milestones_it_matches_owe_no_spec_and_are_not_proposed`);
`## In order` is ONE list (owner 2026-11-02: the older `## Then` section merged into it); a milestone in neither list is
not started. The owner orders the whole list, and the console is the way to do it: `builder status`, Milestones, drag or
Move to top / Park / Unpark, then Save, which is `builder order`: one commit `docs(build-order): owner reorders …` on branch
`build-order` in its own worktree, queued as a tiny external batch the loop checks and lands like any other (shown as saving
until it lands; a second Save waits for it). The order the harness uses is the landed one; triage proposes additions at the
end as a diff. The harness refuses to brief a milestone that is not the first unfinished one in the list unless told
`--milestone` by a person.


### From `issues-and-labels.md` — How the harness picks the next thing


In the first unfinished milestone of the build-order file: the lowest open `step:N.M` whose `Depends on` steps have
landed; then open `type:bug` issues in the milestone by priority; then the rest by priority. Across milestones,
never: it finishes one before the next, which is also the Studio's constraint (one worker).


### From `issues-and-labels.md` — What the harness writes, and when


- **On landing** (`builder landed`, after the ladder and a READY verdict and the push to integration): every issue a
  landed commit cites gets one comment (sha, test, what landed); `Fixes #N` / `Closes #N` closes it; the spec's
  behaviour line is marked `[OK]` with the test. Never before the commit is on `origin/integration`, never by hand.
- **On a step issue being filed** (`builder steps`): title shape, `step:N.M`, the spec's milestone, `type:feature`.
- **On triage** (`builder triage`, direct changes, no approval step): the milestone from the spec that cites the
  issue (when several specs cite it and its current milestone's spec is one of them, it stays; else the first citing
  spec by path; test `fichero-builder/tests/test_triage_verb.py::test_an_issue_its_current_milestones_spec_cites_stays_put_though_another_spec_cites_it_too`);
  a spec with no `> Milestone:` line gets one only when the milestone most of its issues sit in is its file's stem, or that
  milestone's own spec names the file; a `build-notes-*` file gets none and places no issue (test
  `fichero-builder/tests/test_triage_verb.py::test_a_spec_line_is_written_only_for_a_milestone_whose_spec_names_the_file_or_the_files_stem`); `spec:*` removed; one `type:`; `needs-spec` where no spec holds the behaviour; the write-the-spec issue per
  spec-less milestone; empty milestones closed; assignees cleared except the owner on `needs-your-*`.
- **On a question** (a QUESTION row): `needs-your-decision` and a comment with the question; the worker stops.


### From `issues-and-labels.md` — Rulings


- Owner 2026-11-01: one lane at a time; the harness closes issues, never a person; milestone = spec; labels are
  step, kind and priority; pick order steps → bugs → priority; the order of milestones is written down, not vibes.


### From `issues-and-labels.md` — Open questions


1. Does `priority:` survive once every spec has a build order, or is it only for the ops buckets? [PROPOSED: keep]
2. The `phase:R*` labels: removed when the wide-onboarding build order carries the recipe phases, or kept as a second key? [PROPOSED: removed]

### From `performance-sweep-REVIEW.md` — header and intent (as written; status at the time)


Reviewer stance: this spec is ambitious for a harness whose perf rung has never produced one number. Judge it by whether
Step 1 and Step 2 alone would already have given the owner something, and cut the rest until they have.


### From `performance-sweep-REVIEW.md` — Gaps and weak claims

- **Unverified tool details.** The `xcresulttool get build-results` JSON shape, the xctrace table schema names beyond
  `time-profile`/`potential-hangs`/`os-signpost`, the test-plan keys for Thread Performance Checker, and which MetricKit
  fields macOS fills are all stated as "pinned on the first real run". That is honest but means Steps 6 and 8 cannot be
  fully fixture-tested before someone runs the tool on the M4 once. Each needs a 30-minute probe on the M4 before its
  lane starts, with the real outputs committed as the fixtures.
- **Root cause of #6589 is guessed, not found.** The spec names three ways `_remote_build` returns `None` and says the
  first real reason gets written into the issue. Good, but Step 1 should be the manager's own two-hour task, not a lane.
- **The stable build tree filter.** If `_stable_build_tree` excludes `scripts/` or `fichero-server/tests/`, the engine
  rung can never run remotely as written; the spec asks Step 1 to check, it should assert it with a test.
- **`FICHERO_PERF_WORKLOAD` scenarios in the app** are new app code (W6–W10 drivers) on top of the smoke scenario's test
  hooks. That is a Swift lane's work, not a harness lane's, and depends on dev-workflows Step 2.8 landing first.
- **Simulator rows** are "recorded, never ratcheted" but can still file issues via the filing rule; add "simulator rows
  never file" or they will produce noise.
- **No budget for the readers' own cost.** Parsing a 2 GB `.trace` export or a memray `.bin` on the M4 is minutes; the
  nightly window needs a total cap and an order of eviction (which workload is dropped first when the night overruns).


### From `performance-sweep-REVIEW.md` — Cost and runtime per batch / per night (estimates, M4)

- Batch (unchanged by this spec): engine perf + security ≤ 6 min, app perf ≤ 5 min, the warnings ratchet ≈ 10 s on an
  existing result bundle. `-resultBundlePath` adds ~50–200 MB per build to the Dev Disk: needs the same 30-day sweep.
- Nightly, new: engine profiles W1, W3–W5 ≈ 10–15 min; W2 (Kraken, 20 pages) ≈ 5–15 min under memray (a third slower);
  five xctrace templates × five app workloads ≈ 25 recordings × 1–3 min ≈ 40–60 min plus export; the diagnostics plan
  under TSan then ASan ≈ 2 × the unit-test time (20–40 min). Total ≈ 2–2.5 h a night on the M4 behind the heavy lock,
  on top of the daily builds. Fine while nothing else runs overnight; wrong the moment the M4 is also a batch runner at
  night. The spec should state the window (e.g. 01:00–05:00) and what is skipped when it is missed.
- Model cost: zero for measuring; the filer and reviewer are the existing ones. Issue noise is the real cost: 10 issues a
  day at the filer's cap is too many for one owner to read. Start at 3 a day for the sweep as a whole.


### From `performance-sweep-REVIEW.md` — Flaky-measurement risks

- The M4 is headless with a GUI session kept alive by hand; a locked screen voids every app recording silently
  (`locked-session-blocks-screenshots-and-cgevents`). The driver must check the session before recording and mark
  `not-run`, or the trend column will show 40% swings that are the lock screen.
- Thermal: W2 heats the machine; running app recordings after it skews them. The spec orders profiles after builds but
  should put W2 LAST of everything and require `nominal` before each recording (perf_trial's VOID rule applied per step).
- First-run effects: Kraken and spaCy model loads, DuckDB WAL replay, the simulator boot. The cold-discarded rule covers
  the engine; the app workloads need an explicit warm launch before the measured one.
- Noise band of 15% as the "never enforce" line: likely too tight for W6 launch on a machine that also runs builds;
  expect launch to be `noisy` for weeks. Acceptable if it still files hotspots; say so.


### From `performance-sweep-REVIEW.md` — Cut for v1

OVERRULED 2026-11-15: all eight build-order steps are v1 and none is deferred (see `performance-sweep.md`, Build order).
- Keep: Step 1, Step 2 (log readers + table + console), Step 5 (filing from log rows alone), Step 6 (warnings).
- Defer: py-spy (pyinstrument is enough to name the first ten hotspots), memray (peak RSS from `time -l` first), the
  diagnostics test plan, MetricKit subscriber and Organizer read, iOS/iPad simulator profiles, `Energy Log`, `builder
  perf diff`, the rolling overflow issue. Reduce xctrace to Time Profiler + SwiftUI on W6–W8 only.
- Reduce workloads to W1, W2, W3, W6, W7, W8 for the first month; W4, W5, W9, W10 once the table is being read.
- One corpus: the generated fixture. No external HTR set until the owner picks one (question 5).


### From `performance-sweep-REVIEW.md` — Open questions for the owner

1. ANSWERED 2026-11-15: new `performance-sweep` milestone (see `performance-sweep.md`, Open questions 1).
2. ANSWERED 2026-11-15: a `sudoers` line for `py-spy` on the M4 only, allowing nothing else (see `performance-sweep.md`, Open questions 2).
3. Profiles stay on the M4's disk with the run id in the issue, or are pushed somewhere attachable?
4. PARTLY ANSWERED 2026-11-15: no daily cap; every spot over its floor is filed, deduped by key (see `performance-sweep.md`, Filing rule). Filing floors (5% / 50 MB / 10 MB / 250 ms) still open.
5. Which open corpus beyond the generated one, if any; and is an iOS device on the M4 wanted for energy?
6. The nightly window on the M4 (proposed 01:00–05:00) and whether app recordings may be skipped on a locked session.







## Performance and waste (measured 2026-11-14 to 2026-11-21)

A review of the builder's own records over 7.4 days (the owner-side journal, the worker-side journal, 289 worker session
files, the queue and the rules file), asked for by the owner. The numbers below are what the records say; the behaviours
after them are what the fixes need. "Metered" is what the builder's `cost` rows say. "Real" is the same sessions priced
with each API message counted once. Both are USD-equivalent under a subscription login, not a bill. Reviewer calls are in
neither: nothing records them.

### What was measured

| Measure | Value |
|---|---|
| Steps landed | 128, or 17.3 a day |
| Spend, metered | 1,483 USD over 254 sessions |
| Spend, real | 875 USD (the meter reads 1.89 times high) |
| Per landing | 11.58 USD metered, 6.84 USD real |
| Best days (Sonnet, two or three workers) | 20 to 28 landings at about 1.5 USD real each |
| One night on Opus under an old session cap | 9 landings, 1,059 USD metered, 118 USD a landing |
| Steps green on their first check | 14 of 128 (11%) |
| Checks per landed step | 6.2 (4.6 messages, 3.0 reviews, 2.9 blocks, 3.0 alerts) |
| Checks run | 881, 148.1 h of ladder; 43% green; 55.6 h on red checks |
| Queued to landed, median | 330 min (p90 914) |
| Queued to first message, median | 123 min (p90 409); no row says why |
| First DONE to landed, median | 113 min; 33 min for steps that needed two checks or fewer |
| Handoffs | 66: 55 on the session spend cap, 12 on the context mark |
| Spend before a session's first commit | 539 USD metered (36%) |
| Context at a session's first turn | 38,263 tokens, median |
| Alerts | 591; the manager's median answer took 11 to 20 min |

Lane-hours of steps in flight (1,150 h): a session holds the step 23%, queued 21%, blocked on the manager 17%, checking
14%, waiting for a ladder slot 8%, held by the disk floor 6%. On the night of 2026-11-20 the disk floor held 32% of all
lane time.

The ladder's rungs by wall time: red-on-base 78.9 h in 692 runs (58% of rung time; median 386 s), guards 40.3 h in 581
runs (median 205 s), build 11.0 h, security 3.8 h, ready 1.3 h, the rest under an hour together. The ladder lock was
waited on 282 times for 46.5 h (median 7.6 min, longest 104 min). 180 red pytest runs were run again on a second runner
and 169 stayed red. Runners were unreachable for 45 h in 42 outages.

Red checks by rung: guards 157, red-on-base 140, pinned-checks 84, ready 49, build 34, diff-bound 31. 164 of them (32%)
came from rungs that take under 20 seconds, and each still cost a full round. 120 ranges were checked more than once at
an unchanged base and head (155 extra runs). 28 pinned-checks reds named the rules file in lanes that never changed it.

What the worker is sent is small: a 3.5 KB brief, a 5.7 KB prompt, a 456-byte successor brief, typed messages of a
median 140 characters. The tokens go to the start of every session and to searching: 13,300 grep and `sed -n` calls in
the week against one call of the code index the prompt requires.

Disk: the worker root holds 22 to 24 GB, of which about 12 GB is never removed (scratch of landed lanes, derived data,
pytest base temp dirs three weeks old, lane trees the owner's user cannot read). The remote test path made 509 small
scratch dirs in one morning. The journal is 46.6 MB and 83% of it is loop tick rows.

### Owner rulings on spend (2026-11-21)

- B1: once the spend meter counts a message once (#6870), the caps are real dollars. Its 25 USD a session is retired by B2.
- B2: there is no dollar session cap. A session ends on the day cap and the context limit only; `[spend].session_usd` is
  read and ignored.
- B3: reviewer spend counts against the day cap, once `local.perf.reviewer-spend-recorded` (#6882) writes its rows.
- B5: the day cap is 300 USD.

### The ten largest wastes, in order

1. The spend meter counts an API message once per content block, so every cap fires at about half its figure.
2. Caps are read once per worker run, from a second copy of the rules: 48 Opus sessions, 413 USD and 29 handoffs in six
   hours under a cap the owner had already raised.
3. Nine in ten steps fail their first check, and a failure a 20-second rung could report costs a whole round.
4. red-on-base is 58% of ladder time: one pytest per file per ssh, expected reds run twice, guards wait behind it.
5. A queued step waits a median two hours to start, and nothing records why.
6. 200 lane-hours blocked on the manager for reds a rule could answer (a stale base, an approve that does not stick).
7. 46.5 hours waiting for one of two ladder slots.
8. The disk floor held every lane for a third of a night with no alert.
9. 155 ladders re-run on a range that had not changed.
10. A third of the spend is reading before the first commit; successors find their place again by search.

### Behaviours

- `local.perf.spend-counts-a-message-once` [OK] — a session's tokens and cost count each API message once, whatever
  number of lines the session file gives it; the last line of a message wins. **Built** 2026-11-21: `session.parse_session`
  keeps one usage per `message.id`, the last line's (before, it added every assistant line, and a Claude Code file writes one
  line per content block: 25,962 lines for 17,530 messages, cost 1.89 times high). Tests
  `fichero-builder/tests/test_session.py::test_a_claude_code_message_written_as_one_line_per_block_costs_once`; a Pi file is unchanged:
  `fichero-builder/tests/test_session.py::test_cost_parser_on_a_redacted_real_pi_session`. (#6589) → #6870
- `local.perf.caps-reread-each-tick` [OK] — the watcher reads `[spend]` at every tick from the one rules file the
  loop reads, and a park checks the current figure first. **Built** 2026-11-21: the loop publishes the owner's `[spend]` and
  `[models]` as `<feed>/rules.json` every tick and starts a run with `--rules` naming it; `run.run` reads it (or the root's
  rules file when none is named) at the start and at every tick, and an unreadable read keeps the last figures with one
  alert. Tests `fichero-builder/tests/test_dry_run.py::test_a_raised_cap_in_the_published_rules_reaches_a_running_session_on_the_next_tick`,
  `fichero-builder/tests/test_dry_run.py::test_a_lowered_cap_in_the_root_rules_parks_on_the_next_tick`,
  `fichero-builder/tests/test_dry_run.py::test_unreadable_rules_mid_run_alert_once_and_keep_the_last_figures`,
  `fichero-builder/tests/test_watcher.py::test_the_loop_publishes_the_owners_spend_and_models_for_the_jailed_run`. → #6851
- `local.perf.day-cap-counts-live-sessions` [OK] — the day's spend is the finished sessions' rows plus the running
  cost of every live session, so the cap holds with any number of workers. **Built** 2026-11-21: each run rewrites
  `<state>/live/<name>.json` with its running cost every tick, zeroes it at a handoff and removes it at its end; the spend a
  run checks, before its start and at every tick, is today's cost rows plus every other run's live file of today changed in
  the last 300 s (before, finished rows only: measured overshoot 30 to 115 USD, three times). Tests
  `fichero-builder/tests/test_watcher.py::test_live_spend_sums_other_sessions_fresh_files_of_today_only`,
  `fichero-builder/tests/test_dry_run.py::test_three_live_sessions_near_the_cap_keep_a_fourth_from_starting`,
  `fichero-builder/tests/test_dry_run.py::test_a_tick_parks_when_the_others_live_cost_and_its_own_reach_the_cap_and_the_own_file_goes_at_the_end`,
  `fichero-builder/tests/test_dry_run.py::test_a_stale_live_file_does_not_hold_back_a_start`. (#6589) → #6871
- `local.perf.expected-red-runs-once` [BROKEN] — a red is run again on another runner only where the rung expects
  green; the base run of red-on-base is never retried, and the first reachable runner counts as the first. Today
  `check_tool._run` retries any red whenever the first-listed runner did not run it. Test: an owed test in
  fichero-builder/tests/test_remote_list.py. (#6589) → #6872
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.red-on-base-one-base-run` [GAP] — the base tree runs every changed test file in one pytest command per
  runner and the result is read per file. Today `check_tool.red_on_base` runs one command per file. Test: an owed test
  in fichero-builder/tests/test_build_check.py (three files, one command, a per-file verdict). (#6589) → #6873
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.guards-alongside-red-on-base` [GAP] — the guards rung runs at the same time as red-on-base (they read
  different scratch trees); the first red still ends the ladder. Test: an owed test in
  fichero-builder/tests/test_build_check.py. (#6589) → #6873
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.cheap-rungs-at-done` [GAP] — at a worker's DONE the loop runs pinned-checks, ready and diff-bound before
  any chain starts; a red is told to the live session in the same tick, with no alert and no ladder slot. Test: an owed
  test in fichero-builder/tests/test_loop.py (a DONE with a bad trailer gets its finding in the same tick). (#6589)
  → #6874
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.verdict-remembered` [GAP] — a ladder verdict is kept for its base, head, pinned copy and approvals; the
  same four start no second ladder, and a DONE at an unchanged red head gets the old finding. Today
  `check_tool.ladder_over` refuses only an empty range. Test: an owed test in fichero-builder/tests/test_loop.py.
  (#6589) → #6875
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.rungs-keyed-by-tree` [GAP] — a rung that reads only the tree keeps its result by the tree's hash, so an
  amend that changes only commit messages re-runs `ready` alone. Test: an owed test in
  fichero-builder/tests/test_build_check.py (same tree, new sha, one rung runs). (#6589) → #6876
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.pinned-checks-own-commits` [BROKEN] — pinned-checks judges the lane's own commits (from its merge base
  with the land branch), and a commit pushed by hand moves the pinned copy like a landing does. Today a base commit
  that changed the rules file reds every lane behind it. Test: an owed test in fichero-builder/tests/test_presubmit.py.
  → #6853
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.approve-survives-rebase` [BROKEN] — an approve is bound to the test file and its change, and holds at the
  next head and after a rebase while that change is the same. Today it is bound to one head. Test: an owed test in
  fichero-builder/tests/test_approve_resume.py. (#6589) → #6877
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.ladder-slots-follow-runners` [GAP] — ladders run as many at once as there are reachable runners, and two
  batches that share a file take turns only on the build rung. Today the count is a fixed setting and sharing a file
  serialises the whole ladder. Test: an owed test in fichero-builder/tests/test_heavy_lock.py. (#6589) → #6878
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.every-wait-is-a-row` [GAP] — a queued step that does not start writes one row saying why (no worker slot
  and who holds them, paused, no chain slot), and a session whose step is blocked or checking holds no start slot.
  Today `queue.tick_lane` returns without a row in two of those cases. Test: an owed test in
  fichero-builder/tests/test_step_state.py. (#6589) → #6879
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.disk-floor-one-alert-sweeps-first` [BROKEN] — under the disk floor the loop sweeps first, then raises one
  alert naming the free space and the lanes held, and writes one row an hour. Today it writes a row per lane each time
  the figure changes and raises no alert (699 rows in one night). Test: an owed test in
  fichero-builder/tests/test_loop.py. → #6852
  **Built** 2026-11-23, the alert half only (the sweep before it and the row an hour stay owed): the floor is
  `[loop].disk_floor_gb`, re-read every tick; each held lane gets one `disk-hold` row when first held, one alert names the
  free space and every lane held, and one more is raised when the disk is back over the floor. A marker file in the state
  dir (`disk-floor.held`) says which of the two the loop is in, so a restart repeats neither and a tick reads no journal.
  Spec-change: manager 2026-11-21 one alert in and out. Tests
  `fichero-builder/tests/test_loop.py::test_a_falling_disk_holds_every_lane_with_one_alert_and_clearing_raises_one_more`,
  `fichero-builder/tests/test_loop.py::test_the_disk_floor_check_reads_no_journal_while_nothing_is_held`.
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.cap-park-is-one-alert` [OK] — when a cap or a provider refusal parks the workers of several lanes in one
  tick, the loop raises one alert listing the lanes, not one a lane; a park stops only the worker's own tmux window, never
  the tmux server. **Built** 2026-11-23, Spec-change: manager 2026-11-21 one alert for a cap park. Tests:
  `fichero-builder/tests/test_loop.py::test_a_cap_that_parks_two_workers_is_one_alert_listing_both_lanes`,
  `fichero-builder/tests/test_loop.py::test_a_park_stops_a_window_and_never_the_tmux_server`. → #6851
- `local.perf.remote-run-leaves-no-scratch` [BROKEN] — a test run sent to a runner makes no scratch dir on the builder's
  machine. Today `check_tool._remote_run` builds a local env, which makes a home dir and a base dir, drops both keys and
  removes neither. Test: an owed test in fichero-builder/tests/test_no_home_litter.py. (#6589) → #6880
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.landed-lane-litter-removed` [GAP] — when a lane's last step has landed and its patches are kept, its
  scratch dir, its derived data and any pytest base temp dir older than the retain time are listed, then removed. Test:
  an owed test in fichero-builder/tests/test_scratch_sweep.py. (#6589) → #6881
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.reviewer-spend-recorded` [GAP] — each review writes one cost row (model, tokens, cost, seconds, head).
  Today the reviewer runs with no session file and no row. Test: an owed test in
  fichero-builder/tests/test_status_page.py. (#6379) → #6882
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.successor-brief-names-its-place` [GAP] — a successor's brief carries the last commit, the files in flight
  with line numbers and the open findings, and a started session lists the code-index tool or the prompt does not name
  it. Today `run.successor_brief` points at the handoff file only. Test: an owed test in
  fichero-builder/tests/test_codemap.py. (#6589) → #6883
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.tick-rows-out-of-journal` [BROKEN] — the loop's heartbeat is one small file rewritten each tick, not a
  journal row listing every lane, and a reader that needs one kind of event does not parse the whole journal. Test: an
  owed test in fichero-builder/tests/test_journal.py. (#6589) → #6884
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.perf.start-sets-no-global-git-config` [OK] — a worker start sets its git identity for that worktree only
  (`git config --worktree`, its own `config.worktree` file, no lock) and its trust of the worktree through
  `GIT_CONFIG_*` in the worker's environment; the one write to the repo's shared config (`extensions.worktreeConfig`) is made
  once per repo, under a lock named for that repo, so two starts in one tick do not meet on one lock and `start_tool.prepare`
  never writes a global config. Test: `fichero-builder/tests/test_codemap.py::test_two_starts_at_once_set_each_worktrees_identity_and_leave_the_global_config_alone`. → #6854
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### Targets for a good week

| Measure | Measured | Target |
|---|---|---|
| Steps landed a day | 17.3 | 30 |
| First check green | 11% | 50% |
| Checks per landed step | 6.2 | 2.5 or fewer |
| Queued to landed, median | 330 min | 120 min |
| Ladder, median green run | 13.4 min | 8 min |
| Lane time blocked on the manager | 17% | 5% |
| Real spend per landing, Sonnet | 1.4 to 4.4 USD | 3 USD |
| Spend before a session's first commit | 36% | 20% |
| Handoffs on the spend cap | 55 a week | none: the context mark only |

## Scale-out: thirty cheap workers (review of 2026-11-21)

The owner asked how the builder could run thirty cheap workers with the checking and the landing keeping up, and whether
the test machines could be used more efficiently or less often. This section builds on "Performance and waste" above: it
uses that week's records (2026-11-14 to 2026-11-21) and adds what was measured for this question. The throughput figures
are a model made from the week's ratios, not a measurement of thirty workers.

### What was measured for this question

| Measure | Value |
|---|---|
| One worker session, idle, on the loop's Mac | about 330 MB: the session 211 to 245 MB (peak 300 to 320), its code-index server 66 to 77 MB, its watcher 26 to 40 MB |
| Nine idle sessions | 3.0 GB, 0.1% of one core |
| The loop's Mac with nine sessions (16 GB, 8 cores) | 15 GB in use, 4.6 of 6.1 GB of swap in use, load 28 to 32, 5 GB of disk free |
| A desktop runner (24 GB, 10 cores) | load 2.7, 84% of memory free, 39 GB and 191 GB free on two volumes |
| A laptop runner on an external disk (16 GB, 10 cores) | load 1.5, 80% of memory free, 4 GB free inside, 47 GB on the external disk |
| An older laptop runner (8 GB, 8 cores) | load 6 to 8, 17 GB of swap in use |
| A jail user on any runner | none: tests sent to a runner run as that Mac's own user |
| Ladder wall time | 148.8 h in 884 checks, 20.0 h a day, 70 min per landed step |
| Ladders running at once (178 h) | none 72.2 h, one 62.5 h, two 43.1 h |
| Checks per slot-hour | 5.9 (4.5 when green: a green ladder is 13.4 min, 17.7 min with a build, 12.2 without) |
| red-on-base | 79.3 h of wall for 23.0 h of running: every pytest goes to the first reachable runner, one at a time |
| The base moved under a checked head | 96 times for 125 landings; 9 checks were kept across the move; 26 rebases failed |
| Landings | 17 a day; the busiest hour landed 3 |
| Alerts and answers | 591 alerts, 4.6 per landing; the manager gave 633 answers, 85 a day |
| Reviews | 419 in 5.6 h, median 45 s; 0.4% of lane time |
| Mac build rung | 227 builds, 11.1 h, median 229 s in a green check (p90 698 s); 1.8 builds per landing |
| iOS simulator build, and the test target's build | 566 s and 572 s, median, once a day |
| verify-all after a milestone | 8 runs of 5 to 15 min, none green |
| Files most often changed by landings | one UI spec 83 commits, the rules file 34, the six generated contract files 23 each, the docs nav 19 |
| Worker sessions on the cheapest model | none in the week: 180 on the middle model, 76 on the largest |

### What limits landings, in order

1. **The manager.** 4.6 alerts per landing against 85 answers a day is 18 landings a day. The week landed 17.
2. **Checks per landing.** 6.2 checks and 70 min of ladder per landing; two slots give at most 29 landings a day at 70% use.
3. **One landing at a time.** Each landing moves the base under every other checked head. The model below puts the limit
   near 35 landings a day at today's ladder time and near 60 at half of it.
4. **Placement.** Every pytest goes to the first runner in the list under that machine's one heavy lock, while the
   largest runner idles.
5. **Where sessions run.** The loop's Mac is in swap with nine sessions and has 5 GB of disk.
6. Review and the Mac build are not limits yet.

More sessions raise none of the first four. Thirty workers on today's builder would land what ten do.

### The target shape

```
 work (milestones, steps) --> dispatcher: an area per lane, a model per step kind
                                   |
     +-----------------------------+------------------------------+
     | session host A              | session host B               | the loop's Mac
     | jail user, N sessions       | jail user, N sessions        | loop, manager, console
     +--------------+--------------+---------------+--------------+
                    | DONE: the cheap rungs, in the worker's turn |
                    v                                             v
            lane check on the lane's own base, once per tree (runner pool: slots per machine)
                    |            review beside it, by path and by worker model
                    v
            ready-to-land queue
                    |
            the train: up to 8 ready steps rebased in order, generated files made once,
            one ladder on the combined head (full guards, package suites, one Mac build)
                    |                         |
                  green: one push           red: halve, find the member, send it back
                    |
            daily: iOS and test-target builds     nightly: everything, uncached
            a later red is bisected by train, then by member
```

### Throughput model

Per landing the week used 2.05 h of session time, 70 min of ladder and 4.6 alerts. Landings a day are the least of four
limits: sessions (count x 24 h x the share of time a session works / session hours per landing), ladder (slots x 24 h x
0.7 / ladder hours per landing), the manager (answers a day / alerts per landing) and the landing itself. For one landing
at a time, ladders per landing grow as e^(rate x window), with the window fitted to the week's 96 moves in 125 landings.

| Changes in place | 10 workers | 20 workers | 30 workers | The limit that binds |
|---|---|---|---|---|
| Today | 17 to 20 | 20 | 20 | the manager |
| + the filed performance steps (Stage 10) | 30 | 30 | 30 | the manager, at 3.3 alerts per landing |
| + the builder answers what a rule can (Step 11.1) | 45 | 55 | 55 | one landing at a time; two ladder slots |
| + the runner pool (Step 11.2) | 50 | 60 | 60 | one landing at a time |
| + the train (Steps 11.3 to 11.5) | 65 | 110 | 150 | sessions, then spend and the manager |

The 20 and 30 columns need session hosts (Steps 11.7 and 11.8): the loop's Mac holds about eight sessions. At 3 USD a
landing a 250 USD day cap is 83 landings, so past that the cheapest model or a higher cap is needed.

### How often each check runs

| Check | Today | Proposed | What the proposed cadence risks | How a later red finds its landing |
|---|---|---|---|---|
| pinned-checks, ready, diff-bound | every check, on a ladder slot | at the worker's DONE, in its turn | nothing: the same rules, sooner | not needed |
| red-on-base, guards, security, contract | every check: 6.2 per landing | once per tree, on the lane's own base | a clash with what landed since; the train catches it | not needed |
| Mac build | every check that touches the app | a lane that touches the app: once per tree; then once per train | none for other lanes | the train's halving |
| package suites and every guard | after a milestone; 8 runs, none green | every train, on the combined head | a red train costs up to 2 x log2(members) more ladders | the train's halving |
| perf (report-only) | every check: 167 runs, 5.5 h | every train | a slowdown is known per train, not per step | by member, on request |
| iOS simulator and test-target builds | daily | daily, and before the nightly freeze if the app changed | up to a day of app landings on a broken target | by train, then by member: about 5 builds |
| nightly guards, the full suite, the DMG and smoke | nightly | nightly | a day of landings | by train, running only the red test or guard |

Runner hours a day, from the ladder records: today's cadence used 20.4 h (20.0 h of ladders, 0.4 h of verify and daily
builds) for 17 landings, and a further 5 h a day of dev builds until they were ruled off. The proposed cadence at the
same 17 landings is about 6.5 h (3.9 h of lane checks, 2.2 h of trains, 0.4 h of daily builds). At 100 landings a day
the proposed cadence is about 31 h spread over six slots; today's cadence would need 117 h.

### Behaviours

Sessions and the wall:

- `local.scale.sessions-run-on-hosts` [GAP] — a worker session starts on a declared session host over ssh, as that
  host's jail user, in a worktree under that host's workroot; the brief and each message are written there, the session's
  rows are read back each tick, and the lane's commits are fetched from the host. Today `queue.real_procs.start` runs
  `sudo -u` on the loop's own Mac and every path is local. Test: an owed test in
  fichero-builder/tests/test_jail_home.py (a fake ssh: a start on a second host, a message delivered, a DONE row
  read back, the head fetched). (#6589) → #6885
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.every-host-has-the-wall` [GAP] — a session host or a check runner with no jail user, a failed read
  probe or no worker login is refused with a row, and nothing falls back to that Mac's own user; a test run sent to a
  runner runs as the jail user there. Today `check_tool._remote_run` runs worker-written tests as the ssh user, on Macs
  that hold that user's own account. Test: an owed test in fichero-builder/tests/test_jail_home.py (a host with no
  jail user refuses; the remote command line starts as the jail user). (#6589) → #6886
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.host-capacity-is-declared` [GAP] — each machine declares how many sessions, how many check slots and
  whether it builds; a start past the count, or on a host whose free memory is under its floor, waits with a row naming
  the host. Today `[machines]` holds an ssh name, a dir and a disk floor, and the counts are `[queue] workers`,
  `[loop] lanes` and `[check] parallel` for the whole pool. Test: an owed test in
  fichero-builder/tests/test_heavy_lock.py (a third session on a host of two waits with a row; a host under its
  memory floor starts none). (#6356) → #6887
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.checks-go-to-the-least-busy-runner` [GAP] — a rung sent away goes to the runner with a free check slot
  and the fewest running, and a machine runs as many heavy jobs at once as it declares. Today `check_tool._run` takes
  the first reachable runner in the list and `_remote_heavy` holds one lock per machine, so red-on-base ran for 23 h
  of its 79 h of wall. A second machine may be a build runner, each with its own derived data. Test: an owed test in
  fichero-builder/tests/test_remote_list.py (two runs at once land on two runners; a runner of two slots runs two). This
  extends `local.perf.ladder-slots-follow-runners`. (#6356) → #6887
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

Landing:

- `local.scale.green-steps-land-as-a-train` [GAP] — a step that is green and READY waits in a ready-to-land queue; the
  train takes up to `[land] train_max` of them in order, rebases each onto the one before, runs one ladder on the
  combined head and pushes once; every member's landing steps (issues, pinned copy, jail root) then run for it. Today
  `work.after_run` lands each lane by itself and `landed.fast_forward` refuses any head the base moved under. Test: an
  owed test in fichero-builder/tests/test_landed_verb.py (three green lanes, one ladder, one push, three landed rows).
  (#6589) → #6888
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.train-ladder-judges-the-difference` [GAP] — the train's ladder runs every guard and every package suite
  on the combined head, and a test or guard that is red on the train's base too is inherited: one row and one issue,
  never a red train. Today the suites and the skipped guards run only after a milestone, and that run was red all eight
  times in the week. Test: an owed test in fichero-builder/tests/test_landed_verb.py (a test red on base and head does not
  red the train and is named once). (#6589) → #6888
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.red-train-halves` [GAP] — a red train is split in two and each half runs as its own train until the
  member that reds it is alone; that member goes back to its worker with the finding and the others land. Test: an owed
  test in fichero-builder/tests/test_landed_verb.py (four members, the third red: three land, one fix brief).
  (#6589) → #6889
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.lane-check-keeps-its-base` [GAP] — a lane's own check runs on the base the lane was built on and is not
  run again because the land branch moved; only the train rebases. A READY verdict carries onto the train when the
  member's commits have the same diff and message hashes and nothing landed since touches its files; otherwise the train
  reviews the rebased range. Today `land_tool.range_key` holds the base, so every move is a new check and a new review
  (96 in the week). Test: an owed test in fichero-builder/tests/test_landed_verb.py (a disjoint base move keeps the verdict;
  an overlapping one asks for a review). (#6589) → #6889
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.generated-files-are-made-at-compose` [PARTIAL] — a conflict that lies only in generated files is never
  a person's: the train takes the base's copy, and regenerates every generated file once on the combined head. Built:
  `work.do_rebase` re-bakes the two contract identity files named in `[check] generated`, and `work.regen` runs
  `[check] regen` after a clean rebase. Left: the other generated files (the three contract copies, the MCP tools, the
  engine embed list) still abort a rebase, and regeneration runs once per lane, not once per train. Test: an owed test
  in fichero-builder/tests/test_landed_verb.py (two members that each add a route compose without a conflict).
  (#4705) → #6891
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.exclusive-areas` [GAP] — the rules file names areas by path, and marks some exclusive (the rules file,
  the docs nav, a spec that many lanes edit); a lane names its areas when it is queued, and two lanes that share an
  exclusive area do not run at once: the second waits with a row. Test: an owed test in
  fichero-builder/tests/test_loop.py (two lanes on one exclusive area: one starts, one row says why the other waits).
  (#6589) → #6892
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

Cadence:

- `local.scale.rungs-have-a-cadence` [GAP] — the rules file gives each rung one cadence (done, step, train, daily,
  nightly) and the table above is the default. Today `check_tool._run_ladder` runs every rung at every check. Test: an
  owed test in fichero-builder/tests/test_build_check.py (a rung set to train does not run in a lane check and runs in
  the train's). (#6589) → #6890
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.later-red-finds-its-landing` [GAP] — each train writes one row naming its members and their commit
  ranges in order; a red at a daily or nightly cadence is bisected over the trains since the last green, then over that
  train's members, running only the red rung or test, and the member's lane gets one fix step. Nothing is reverted
  without the manager. Test: an owed test in fichero-builder/tests/test_landed_verb.py (a red planted in the fifth of eight
  trains is found in at most six runs). (#6589) → #6890
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

The manager:

- `local.scale.builder-answers-what-a-rule-can` [GAP] — the loop answers by itself, each with a named `auto` row: a
  runner that is down (a row; an alert only when none is left), a red from a runner's environment or the network (one
  retry at once), a second red at an unchanged head (the finding goes back to the worker), a rebase conflict (the worker
  resolves it in its own session), a tree outside the step that moved (a row), and a step out of fix rounds (the next
  model tier takes it with the findings before a person does). Today each is an alert: 53 runner-down, 40 rebase, 18
  outside-tree, and 236 answers of `retry`. Acceptance: alerts per landing is in the nightly report, with a target of
  0.5. Test: an owed test in fichero-builder/tests/test_loop.py (each class leaves a row and no alert).
  (#6589) → #6893
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)
- `local.scale.inherited-red-blocks-no-lane` [GAP] — a test the lane did not change that is red on its base and on its
  head is not the lane's: the check goes on, the test is put on a known-reds list with one issue, and the entry ends
  when the land branch is green for it. Today one red test on the land branch reds every lane's green run. Test: an
  owed test in fichero-builder/tests/test_build_check.py (a base-red test in an unchanged file leaves the lane green
  and one known-red row). (#6856) → #6894
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

Cheap models:

- `local.scale.model-by-step-kind` [GAP] — a step has a kind, and the rules file maps each kind to a model role and a
  file bound; the cheapest model takes only the kinds listed for it (a lint or warning batch, a format fix, a tag flip
  with its test, a test for behaviour that exists, a file move a guard checks), with a bound of 8 files, and a step that
  is red twice is queued again one tier up with the findings. A review is never done by the cheapest model. A kind
  joins the cheapest model's list after 20 measured steps cost less per landing than the tier above. Today one
  `[models] builder` serves every step. Test: an owed test in fichero-builder/tests/test_model_config.py (a kind maps
  to its role and bound; two reds move the step up a tier). This needs `agent-profiles.worker.small` and
  `local.perf.cheap-rungs-at-done`. (#6625) → #6895
  Superseded: owned by the builder specs in docs/contributor_manual/specs/harness/ (Spec-change: manager 2026-11-23)

### Judged not worth building

- Sharding the pytest of a lane check: it runs only the changed test files, and placement removes the wait.
- Starting the review earlier, or one review per train: reviews are 0.4% of lane time, and one per lane names its author.
- Landing first and reverting on a later red: the land branch was red under verify-all all week with nobody waiting on
  it, and thirty lanes would rebase onto each red.
- One shared red-on-base run per base commit: the red half runs each lane's own new tests, so there is nothing to share.

## Build order

Each step is one issue under the one milestone (`builder steps` files them from the headings below). Sonnet builds and Opus reviews
the harness's own code until the bake-off says otherwise. Sizes: S under a day, M one to two days, L a week of a lane. Stage 0 is
done by hand (this file, its review and report). The absorbed specs' own build orders follow as history, their Step headings demoted.

### Stage 0 — combine, answer, report (done by hand, nothing built)

- Behaviours: `local.spec-sceptical-read` (run by hand on this spec)
- Tests: none; the review and the report are the record

### Stage 1 — Pi on OpenRouter, and CI

#### Step 1.1 — the Pi adapter and the OpenRouter provider
- Behaviours: `agent-profiles.adapter.pi`, `local.bridge-openrouter`
- Tests: fichero-builder/tests/test_adapters.py, fichero-builder/tests/test_pi_rpc.py (a live start against a priced provider is owed)
- Size: M

#### Step 1.2 — the model budget, the per-model handoff mark and the interim machine
- Behaviours: `local.memory-budget`, `local.handoff-per-model`, `local.interim-16gb`
- Tests: fichero-builder/tests/test_model_config.py, fichero-builder/tests/test_watcher.py
- Depends on: 1.1
- Size: S

#### Step 1.3 — CI on hosted runners for engine tests, guards and scans
- Behaviours: `pipeline.github-actions`
- Tests: the workflow runs green on a lane push; fichero-builder/tests/test_verify_all.py
- Size: M

#### Step 1.4 — one harness.toml: the checkout and the live copy agree
- Behaviours: `agent-profiles.trailer.one-line`, `dev-workflows.run.rules-file`
- Tests: fichero-builder/tests/test_trailer.py, fichero-builder/tests/test_model_config.py
- Size: S

#### Step 1.5 — no metered provider without a weekly cap
- Behaviours: `local.spend.metered-provider-needs-a-cap`
- Tests: fichero-builder/tests/test_watcher.py (the week's rows reach the figure and the session parks), fichero-builder/tests/test_model_config.py (a metered provider with no figure refuses)
- Depends on: 1.1
- Size: S

### Stage 2 — the gates

#### Step 2.1 — the four [BROKEN] behaviours are fixed first
- Behaviours: `perf-sweep.rung.not-run-is-visible`, `builder-console.step.one-state`, `builder-console.numbers.labelled`, `dev-workflows.ux.controls-work`
- Tests: fichero-builder/tests/test_perf_rung.py, fichero-builder/tests/test_status_page.py
- Size: M

#### Step 2.2 — every batch measured: memory, disk, time, with budgets
- Behaviours: `local.resources-measured`, `perf-sweep.ratchet.budgets`, `perf-sweep.ratchet.baseline-from-n-runs`, `perf-sweep.ratchet.noise-band`
- Tests: fichero-builder/tests/test_perf_rung.py, fichero-builder/tests/test_measure.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — the security rung enforces after one clean week
- Behaviours: `dev-workflows.quality.security-scan-rung`, `dev-workflows.quality.scan-thresholds-and-waivers`
- Tests: fichero-builder/tests/test_security_rung.py
- Depends on: 2.1
- Size: S

#### Step 2.4 — the wall around a worker, proved by probes
- Behaviours: `agent-profiles.isolation.baseline`, `agent-profiles.isolation.implemented`, `dev-workflows.security.untrusted-text`
- Tests: fichero-builder/tests/test_jail_home.py, fichero-builder/tests/test_jail_git.py, fichero-builder/tests/test_pi_policy_extension.py
- Depends on: 1.1
- Size: L

#### Step 2.5 — a spec is linted and read sceptically before approval
- Behaviours: `local.spec-lint`, `local.spec-sceptical-read`, `pipeline.status`
- Tests: fichero-server/tests/unit/scripts/test_spec_pipeline.py
- Size: M

#### Step 2.6 — a DONE, a message and an approve are each counted once, for the right step
- Behaviours: `local.done-needs-delivery`, `local.undelivered-is-redelivered`, `local.no-commit-is-never-landed`, `local.approve-remembered-per-head-and-reason`, `local.dismiss-never-parks-in-flight`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_tell.py, fichero-builder/tests/test_alerts_clear.py
- Depends on: 2.1
- Size: M

#### Step 2.7 — the loop splits, waits and resumes by itself
- Behaviours: `local.already-built-is-declared`, `local.diff-bound-splits-the-step`, `local.removed-tree-is-not-a-moved-tree`, `local.restart-resumes-the-night`, `local.network-outage-is-infra`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_builder_restart.py, fichero-builder/tests/test_work_tree.py
- Depends on: 2.6
- Size: M

#### Step 2.8 — lanes follow the landing rate; checks run on other Macs
- Behaviours: `local.scale.lanes-follow-the-landing-rate`, `local.scale.checks-run-on-other-macs`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_measure.py
- Depends on: 2.2
- Size: S

#### Step 2.9 — a re-exec'd loop adopts every live session and stops none
- Behaviours: `local.run.reexec-adopts-by-window-or-pid`, `local.run.drain-expired-one-row`
- Tests: fichero-builder/tests/test_builder_restart.py (five live windows adopted, none stopped; a live pid adopted; neither queued once), fichero-builder/tests/test_loop_survives.py (one drain-expired row a lane and head; the re-exec after the running chain)
- Depends on: 2.1
- Size: S

#### Step 2.10 — a sent step has a live session, and a turn that ends without DONE is seen in one tick
- Behaviours: `local.run.sent-needs-a-live-session`, `local.run.turn-ended-without-done-alerts`
- Tests: fichero-builder/tests/test_loop.py (a sent step on a shell is queued again; a quiet sent step alerts once), fichero-builder/tests/test_dry_run.py (a question alerts in one tick; no question is nudged then alerted), fichero-builder/tests/test_watcher.py
- Depends on: 2.9
- Size: M

#### Step 2.11 — the loop thins local snapshots before it holds a lane for disk
- Behaviours: `local.disk.thin-snapshots-before-holding`
- Tests: fichero-builder/tests/test_loop.py (a thin that frees space starts the lane; one that frees nothing holds; once an hour)
- Depends on: 2.1
- Size: S

#### Step 2.12 — `queue add` refuses a repeated brief; `queue drop` takes a step that never started
- Behaviours: `local.queue.add-refuses-a-repeated-brief`, `local.queue.drop-takes-a-queued-step`
- Tests: fichero-builder/tests/test_queue_verb.py (a repeat refused by name; `--continues` appends landed and left; a queued step dropped, a sent one refused)
- Depends on: 2.1
- Size: S

#### Step 2.13 — a move the loop or the manager recorded is not a stray write
- Behaviours: `local.run.recorded-move-is-not-a-stray-write`
- Tests: fichero-builder/tests/test_loop.py (a fast-forward to origin's tip is silent; a `tree-moved` row excuses; a dirty root is one alert for three steps)
- Depends on: 2.7
- Size: S

#### Step 2.14 — mechanical fix rounds by script
- Behaviours: `local.autofix.loop-applies-the-printed-fix`, `local.autofix.classes`
- Tests: fichero-builder/tests/test_autofix.py (one fixture red a class; the refusals), fichero-builder/tests/test_loop.py (the fix, the row and the second check with no message to the worker)
- Depends on: 2.6
- Size: M

#### Step 2.15 — effort per role
- Behaviours: `local.models.effort-per-role`
- Tests: fichero-builder/tests/test_model_config.py, fichero-builder/tests/test_adapters.py
- Depends on: 2.1
- Size: S

### Stage 3 — state and reports

#### Step 3.1 — one SQLite database rebuilt from the journal, one row per unit
- Behaviours: `builder-console.store.one-database`, `dev-workflows.ledger.one-row-per-unit`, `dev-workflows.ledger.keyed-to-batch-and-lane`
- Tests: fichero-builder/tests/test_journal.py
- Size: L

#### Step 3.2 — the weekly report is queries
- Behaviours: `dev-workflows.ledger.comparison-view`, `dev-workflows.ledger.break-even-view`, `dev-workflows.bakeoff.decision-table`
- Tests: fichero-builder/tests/test_status_page.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — the run record and the Runs and Compare pages
- Behaviours: `agent-profiles.run.record`, `builder-console.runs.page`, `builder-console.compare.page`
- Tests: fichero-builder/tests/test_status_page.py
- Depends on: 3.2
- Size: M

#### Step 3.4 — the console on the phone, read-only over the tailnet
- Behaviours: `dev-workflows.console.tailnet-read-only`, `dev-workflows.console.phone-layout`
- Tests: fichero-builder/tests/test_status_page.py
- Depends on: 2.1
- Size: S

#### Step 3.5 — no tag without notes
- Behaviours: `local.notes-with-every-tag`
- Tests: fichero-server/tests/unit/scripts/test_release_guard.py
- Size: S

#### Step 3.6 — issues and milestones stay current on GitHub
- Behaviours: `issues.harness-closes-after-integration`, `local.push-or-nothing-closes`, `local.drift-is-reported`, `pipeline.issues-and-milestones-kept-current`, `dev-workflows.run.issues-close-when-done`
- Tests: fichero-builder/tests/test_landed_verb.py, fichero-builder/tests/test_issue_reconcile.py, fichero-builder/tests/test_triage_verb.py
- Depends on: 3.1
- Size: M

### Stage 4 — the bake-off

#### Step 4.1 — Qwen3-Coder-Next on Pi against Sonnet on Claude Code, measured
- Behaviours: `agent-profiles.bakeoff.measured`, `dev-workflows.bakeoff.held-until-the-cap`, `dev-workflows.bakeoff.public-data-only`, `dev-workflows.bakeoff.frozen-ground-truth`, `dev-workflows.bakeoff.replay-corpus`
- Tests: fichero-builder/tests/test_rung_stats.py; the decision table is the acceptance
- Depends on: 1.1, 2.2, 3.2
- Size: L

#### Step 4.2 — handoffs scored, the compressed build is the measure, every role names a local provider
- Behaviours: `local.handoff-measured`, `local.compressed-is-the-measure`, `local.target`
- Tests: fichero-builder/tests/test_rung_stats.py (new cases)
- Depends on: 4.1
- Size: M

#### Step 4.3 — a step has a kind, and a kind earns a cheaper role by measurement
- Behaviours: `local.small.step-kind-is-recorded`, `local.small.kind-has-its-lane-and-role`
- Tests: fichero-builder/tests/test_queue_verb.py (the kind by rule, on the cost row; one trial step in five), fichero-builder/tests/test_milestone_verb.py (a routed kind is placed on its lane)
- Depends on: 1.5
- Size: M

#### Step 4.4 — the worker checks before it says DONE, and every finding has one form
- Behaviours: `local.small.worker-prechecks-before-done`, `local.small.fix-brief-has-one-form`
- Tests: fichero-builder/tests/test_presubmit.py (a bad trailer prints a finding and no DONE line; no socket), fichero-builder/tests/test_loop.py (three kinds of red become blocks with every field)
- Depends on: 2.14
- Size: M

#### Step 4.5 — the brief carries the symbols and their lines
- Behaviours: `local.small.brief-carries-the-symbols`
- Tests: fichero-builder/tests/test_codemap.py (two cited functions with spans; the cap)
- Depends on: 4.3
- Size: S

### Stage 5 — the loop moves onto LangGraph

#### Step 5.1 — the package pinned; one harness lane runs as a graph beside the loop
- Behaviours: `local.pinned-dependency`, `local.orchestration-on-langgraph`
- Tests: fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_loop.py, fichero-builder/tests/test_loop_survives.py, fichero-builder/tests/test_builder_restart.py, fichero-builder/tests/test_approve_resume.py pass unchanged against the graph lane
- Depends on: 3.1
- Size: L

#### Step 5.2 — every lane moves; the old loop is deleted last
- Behaviours: `local.migration-one-lane-first`
- Tests: the same five, per lane; one new test: a session fed three briefs hands off at its mark and the successor lands
- Depends on: 5.1
- Size: L

### Stage 6 — manager, escalation, questions, reviewers (on the graph)

#### Step 6.1 — escalation is mechanical: tiers, triggers, one row each
- Behaviours: `local.escalation-tiers`, `local.escalation-triggers`, `local.escalation-row`
- Tests: fichero-builder/tests/test_watcher.py, fichero-builder/tests/test_queue_verb.py (new cases)
- Depends on: 5.1
- Size: M

#### Step 6.2 — what must escalate, pre-routing, and escalation through the handoff
- Behaviours: `local.must-escalate`, `local.pre-routing`, `local.escalation-by-handoff`
- Tests: fichero-builder/tests/test_watcher.py, fichero-builder/tests/test_queue_verb.py (new cases)
- Depends on: 6.1
- Size: M

#### Step 6.3 — the local manager and the question list
- Behaviours: `agent-profiles.role.manager`, `local.question-list`, `dev-workflows.node.human-question`
- Tests: fichero-builder/tests/test_alerts_clear.py, fichero-builder/tests/test_tell.py (new cases)
- Depends on: 6.2
- Size: L

#### Step 6.4 — the reviewers: binding, shadow, bug hunt; the judging files
- Behaviours: `local.reviewer-differs`, `pipeline.review`, `local.judging-files-reviewed`, `local.new-orchestration-on-the-graph`, `dev-workflows.quality.bug-review-stream`
- Tests: fichero-builder/tests/test_work_verb.py (new cases)
- Depends on: 5.1
- Size: L

### Stage 7 — nightly and release

#### Step 7.1 — the nightly dev pre-release when every stage is green
- Behaviours: `pipeline.nightly-gate`, `dev-workflows.run.nightly-build`
- Tests: fichero-builder/tests/test_nightly.py
- Depends on: 2.2, 3.5
- Size: M

#### Step 7.2 — four channels; a promotion is prepared by script and approved by the owner
- Behaviours: `local.release-channels`, `pipeline.weekly-release`
- Tests: fichero-server/tests/unit/scripts/test_release_guard.py, fichero-builder/tests/test_build_verb.py
- Depends on: 7.1
- Size: M

### Stage 8 — the Studio (128 GB)

#### Step 8.1 — move to the machine; the roles point at the local server
- Behaviours: `dev-workflows.run.local-parity`
- Tests: fichero-builder/tests/test_model_config.py; the bake-off repeated on the compressed build
- Depends on: 4.2
- Size: M

#### Step 8.2 — Swift tests per batch in the dedicated GUI user
- Behaviours: `agent-profiles.ladder.swift-tests`, `agent-profiles.ladder.ui-smoke`, `dev-workflows.run.swift-tests`
- Tests: fichero-server/tests/unit/workflows/test_check_tool.py (new rung cases)
- Depends on: 8.1
- Size: L

#### Step 8.3 — the Xcode worker
- Behaviours: `local.xcode-worker`
- Tests: a Swift step lands through it; previews and test results reach the reviewer
- Depends on: 8.2
- Size: L

#### Step 8.4 — the sandbox profile and the isolation trial
- Behaviours: `local.worker-sandboxed`, `agent-profiles.isolation.research-and-choice`
- Tests: fichero-builder/tests/test_jail_home.py (new probe cases)
- Depends on: 2.4, 8.1
- Size: L

#### Step 8.5 — the machine pool retires: placement
- Behaviours: `dev-workflows.pool.machines-declare-capabilities`, `dev-workflows.pool.placement-and-fallback`, `dev-workflows.pool.hold-holds-one-machine`
- Tests: fichero-builder/tests/test_remote_list.py (the retired paths refuse)
- Depends on: 8.1
- Size: S

#### Step 8.6 — the machine pool retires: the parallel gate and the litter rule
- Behaviours: `dev-workflows.pool.one-heavy-per-machine`, `dev-workflows.pool.parallel-gate`, `dev-workflows.pool.no-litter`
- Tests: fichero-builder/tests/test_remote_list.py (the retired paths refuse)
- Depends on: 8.5
- Size: S

### Stage 9 — handover and freeze

#### Step 9.1 — rulings become rules; the supervising manager leaves
- Behaviours: `local.rulings-become-rules`, `local.promotions-stay-with-owner`, `local.handover`, `local.freeze`
- Tests: the two quiet weeks are the acceptance; fichero-builder/tests/test_journal.py (the handover row)
- Depends on: 6.4, 7.2
- Size: S

### Stage 10 — spend the time, tokens and disk on real work (review of 2026-11-21)

The steps of "Performance and waste", cheapest and largest saving first. Each is one step of 25 files or fewer.

#### Step 10.1 — the spend meter is right, live and whole
- Behaviours: `local.perf.spend-counts-a-message-once`, `local.perf.caps-reread-each-tick`, `local.perf.day-cap-counts-live-sessions`
- Tests: fichero-builder/tests/test_session.py, fichero-builder/tests/test_watcher.py, fichero-builder/tests/test_dry_run.py
- Size: S

#### Step 10.2 — red-on-base at half the time
- Behaviours: `local.perf.expected-red-runs-once`, `local.perf.red-on-base-one-base-run`, `local.perf.guards-alongside-red-on-base`
- Tests: fichero-builder/tests/test_remote_list.py, fichero-builder/tests/test_build_check.py
- Size: M

#### Step 10.3 — a cheap red costs seconds, and nothing is checked twice
- Behaviours: `local.perf.cheap-rungs-at-done`, `local.perf.verdict-remembered`, `local.perf.rungs-keyed-by-tree`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_build_check.py
- Depends on: 10.2
- Size: M

#### Step 10.4 — reds a rule can answer never reach the manager
- Behaviours: `local.perf.pinned-checks-own-commits`, `local.perf.approve-survives-rebase`
- Tests: fichero-builder/tests/test_presubmit.py, fichero-builder/tests/test_approve_resume.py
- Size: M

#### Step 10.5 — slots follow the runners, and every wait is a row
- Behaviours: `local.perf.ladder-slots-follow-runners`, `local.perf.every-wait-is-a-row`
- Tests: fichero-builder/tests/test_heavy_lock.py, fichero-builder/tests/test_step_state.py
- Depends on: 10.3
- Size: M

#### Step 10.6 — the disk: sweep first, one alert, no litter
- Behaviours: `local.perf.disk-floor-one-alert-sweeps-first`, `local.perf.remote-run-leaves-no-scratch`, `local.perf.landed-lane-litter-removed`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_no_home_litter.py, fichero-builder/tests/test_scratch_sweep.py
- Size: M

#### Step 10.7 — the records: reviewer cost, a small heartbeat, no shared git config
- Behaviours: `local.perf.reviewer-spend-recorded`, `local.perf.tick-rows-out-of-journal`, `local.perf.start-sets-no-global-git-config`
- Tests: fichero-builder/tests/test_status_page.py, fichero-builder/tests/test_journal.py, fichero-builder/tests/test_jail_git.py
- Size: S

#### Step 10.8 — a successor starts where the last session stopped
- Behaviours: `local.perf.successor-brief-names-its-place`
- Tests: fichero-builder/tests/test_codemap.py
- Depends on: 10.1
- Size: S

### Stage 11 — scale-out: more workers only once landing keeps up (review of 2026-11-21)

The steps of "Scale-out", the largest gain per file first. Stage 10 comes first: its steps are the cheapest landings
there are. Session hosts come last because nothing before them needs more than eight sessions.

#### Step 11.1 — the builder answers what a rule can
- Behaviours: `local.scale.builder-answers-what-a-rule-can`, `local.scale.inherited-red-blocks-no-lane`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_build_check.py
- Depends on: 10.4
- Size: M

#### Step 11.2 — the runner pool: counts per machine, the least-busy runner
- Behaviours: `local.scale.host-capacity-is-declared`, `local.scale.checks-go-to-the-least-busy-runner`
- Tests: fichero-builder/tests/test_heavy_lock.py, fichero-builder/tests/test_remote_list.py
- Depends on: 10.5
- Size: M

#### Step 11.3 — generated files and exclusive areas
- Behaviours: `local.scale.generated-files-are-made-at-compose`, `local.scale.exclusive-areas`
- Tests: fichero-builder/tests/test_landed_verb.py, fichero-builder/tests/test_loop.py
- Size: S

#### Step 11.4 — the train
- Behaviours: `local.scale.green-steps-land-as-a-train`, `local.scale.train-ladder-judges-the-difference`
- Tests: fichero-builder/tests/test_landed_verb.py
- Depends on: 10.3, 11.3
- Size: L

#### Step 11.5 — a red train halves; a lane's check keeps its base
- Behaviours: `local.scale.red-train-halves`, `local.scale.lane-check-keeps-its-base`
- Tests: fichero-builder/tests/test_landed_verb.py
- Depends on: 11.4
- Size: M

#### Step 11.6 — a cadence per rung; a later red finds its landing
- Behaviours: `local.scale.rungs-have-a-cadence`, `local.scale.later-red-finds-its-landing`
- Tests: fichero-builder/tests/test_build_check.py, fichero-builder/tests/test_landed_verb.py
- Depends on: 11.4
- Size: M

#### Step 11.7 — the wall on every host and runner
- Behaviours: `local.scale.every-host-has-the-wall`
- Tests: fichero-builder/tests/test_jail_home.py
- Depends on: 11.2
- Size: M

#### Step 11.8 — sessions run on hosts
- Behaviours: `local.scale.sessions-run-on-hosts`
- Tests: fichero-builder/tests/test_jail_home.py
- Depends on: 10.7, 11.7
- Size: L

#### Step 11.9 — a model per step kind
- Behaviours: `local.scale.model-by-step-kind`
- Tests: fichero-builder/tests/test_model_config.py
- Depends on: 10.3, 11.1
- Size: M

### From `dev-workflows.md` — Build order (history; Step headings demoted so `builder steps` files only this spec's steps)


Steps a long-running builder can take from the heading. `Depends on` defaults to the step before. No dates (owner
2026-11-01: no deadline, do it right); each step ends on a real issue where it can, and the TSV of step 1.1 measures it.

#### Stage 0 — Slice 0: done by hand (§ 0)

##### Step 0.1 — the rules file, the hooks, check and land as scripts, the verdict store, the second user, the B1 fix
- Behaviours: `dev-workflows.rollout.slice-zero`, `dev-workflows.run.policy-hook`, `dev-workflows.run.land-gate`, `dev-workflows.run.review-and-land`
- Tests: fichero-server/tests/unit/workflows/test_rules_problems.py, fichero-server/tests/unit/workflows/test_policy_hook.py, fichero-server/tests/unit/workflows/test_land_tool.py, fichero-server/tests/unit/workflows/test_check_tool.py, fichero-server/tests/unit/workflows/test_start_tool.py
- Size: M

##### Step 0.2 — the cluster brief; pipeline frozen
- Behaviours: `dev-workflows.builder.cluster`, `dev-workflows.rollout.pipeline-frozen`
- Tests: fichero-server/tests/unit/workflows/test_brief_tool.py, fichero-server/tests/unit/workflows/test_pipeline_frozen.py
- Size: S

#### Stage 1 — the Builder package and the watcher

##### Step 1.1 — `fichero-builder/` on the standard library: check, land, jail, policy, start, brief, journal, budget; the ratchet's TSV
- Behaviours: `dev-workflows.core.shared`, `dev-workflows.project.neutral`, `dev-workflows.run.ratchet`
- Tests: fichero-builder/tests/test_no_engine_import.py, fichero-builder/tests/test_second_project.py, fichero-builder/tests/test_ratchet.py
- Size: M

##### Step 1.2 — `builder run`: one process starts a worker and watches its session file; caps; the fake kind
- Behaviours: `dev-workflows.run.worker-start-stop`, `dev-workflows.run.watch-tick`, `dev-workflows.rollout.dry-run`, `dev-workflows.run.records-are-truth`
- Tests: fichero-builder/tests/test_watcher.py, fichero-builder/tests/test_journal.py, fichero-builder/tests/test_session.py, fichero-builder/tests/test_dry_run.py
- Size: M

##### Step 1.3 — handoff and successor from the session file; supervision; the worker steers within its brief
- Behaviours: `dev-workflows.worker.handoff`, `dev-workflows.run.supervision`, `dev-workflows.worker.steers`
- Tests: fichero-builder/tests/test_handoff.py, fichero-builder/tests/test_supervision.py, fichero-builder/tests/test_cluster_run.py
- Size: M

##### Step 1.4 — `builder ask`: the question record as a file and a journal row
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_ask.py
- Size: S

#### Stage 2 — check, review, land, in that order

##### Step 2.1 — `builder check` then `builder review` with a shell and a throwaway checkout, then `builder land`; the size rule ignores generated files
- Behaviours: `dev-workflows.tool.check`, `dev-workflows.security.grants`, `dev-workflows.worker.two-capability-sets`, `dev-workflows.run.jail-home`, `dev-workflows.run.remote-list`
- Tests: fichero-builder/tests/test_check.py, fichero-builder/tests/test_review_with_a_shell.py, fichero-builder/tests/test_land_order.py, fichero-builder/tests/test_jail_home.py, fichero-builder/tests/test_jail_git.py, fichero-builder/tests/test_remote_list.py
- Size: M

##### Step 2.2 — a week on real issues under Claude Code; the TSV compared with Slice 0
- Behaviours: `dev-workflows.run.worker-address`, `dev-workflows.run.tell`
- Tests: fichero-builder/tests/test_real_cluster_record.py
- Size: S

##### Step 2.3 — the chain as verbs: `builder milestone`, `builder spec`, `builder steps` (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.milestone`, `dev-workflows.tool.work`, `dev-workflows.tool.spec`, `dev-workflows.tool.steps`, `dev-workflows.tool.file`
- Tests: fichero-builder/tests/test_milestone_verb.py, fichero-builder/tests/test_work_verb.py, fichero-builder/tests/test_spec_verb.py, fichero-builder/tests/test_steps_verb.py, fichero-builder/tests/test_file_verb.py
- Depends on: 2.1
- Size: M

##### Step 2.4 — one command after a verdict, no hand edits, two lanes in turn (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.landed` (the pinned copy, the rebase step, the no-second-ladder land and the rules in the brief are Built sentences under `tool.work`, `tool.milestone` and `tool.check`, whose steps they stay in)
- Tests: fichero-builder/tests/test_landed_verb.py, fichero-builder/tests/test_work_verb.py, fichero-builder/tests/test_main.py, fichero-server/tests/unit/workflows/test_brief_tool.py
- Depends on: 2.3
- Size: M

##### Step 2.5 — `builder triage`: the closed label set, the milestone is the spec, needs-spec, assignees, the build-order file read (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.triage`
- Tests: fichero-builder/tests/test_triage_verb.py, fichero-builder/tests/test_milestone_verb.py
- Depends on: 2.4
- Size: M

##### Step 2.6 — `builder queue`: one long-running worker per lane, fed step by step, checked and landed in between (owner 2026-11-01)
- Behaviours: `dev-workflows.tool.queue`, `dev-workflows.run.loop-external-intake`
- Tests: fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_dry_run.py, fichero-builder/tests/test_milestone_verb.py
- Depends on: 2.5
- Size: M

##### Step 2.7 — the code map for jail workers, briefs that carry it, the reading metric (owner 2026-11-01)
- Behaviours: `dev-workflows.run.code-map`, `dev-workflows.run.heavy-lock`
- Tests: fichero-builder/tests/test_codemap.py, fichero-builder/tests/test_milestone_verb.py, fichero-builder/tests/test_dry_run.py, fichero-builder/tests/test_heavy_lock.py
- Depends on: 2.6
- Size: M

##### Step 2.8 — `builder build --dev`: the dev DMG as a verb (owner 2026-11-02)
- Behaviours: `dev-workflows.tool.build`, `dev-workflows.run.measure`, `dev-workflows.run.verify-all`
- Tests: fichero-builder/tests/test_build_verb.py, fichero-builder/tests/test_verify_all.py, fichero-builder/tests/test_supersede_followups.py
- Depends on: 2.1
- Size: S

##### Step 2.9 — the continuous loop: a lane's DONE lands with no person (chain, fetch, fix rounds, tell) (owner 2026-11-02)
- Behaviours: `dev-workflows.run.loop`, `dev-workflows.run.loop-chain`, `dev-workflows.run.loop-fetches-the-lane`, `dev-workflows.run.loop-fix-rounds`, `dev-workflows.run.loop-tell`
- Tests: fichero-builder/tests/test_loop.py
- Depends on: 2.6
- Size: M

##### Step 2.10 — the loop's stops: alerts with evidence and actions, needs-maintainer, the session cap hands off, the token handoff, roles (owner 2026-11-02)
- Behaviours: `dev-workflows.run.loop-alerts`, `dev-workflows.run.loop-needs-maintainer`, `dev-workflows.run.loop-session-cap-hands-off`, `dev-workflows.run.loop-handoff-tokens`, `dev-workflows.run.loop-roles`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_watcher.py, fichero-builder/tests/test_approve_resume.py
- Depends on: 2.9
- Size: M

##### Step 2.11 — the loop at large: rolls on, external lanes, machine-checked trees, `builder status`, the six-hour soak (owner 2026-11-02)
- Behaviours: `dev-workflows.run.loop-rolls-on`, `dev-workflows.run.loop-external-lane`, `dev-workflows.run.loop-machine-checked`, `dev-workflows.run.loop-status`, `dev-workflows.run.loop-soak`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_status_page.py
- Depends on: 2.10
- Size: M

#### Stage 3 — the Pi kind by RPC, the sandbox, local parity


##### Step 2.12 — the loop survives a lane's exception and its own tree follows origin (manager 2026-11-03)
- Behaviours: `dev-workflows.run.loop-survives`, `dev-workflows.run.restart-resets-nothing`, `dev-workflows.run.restart-adopts-live-window`, `dev-workflows.run.restart-rules-per-tick`, `dev-workflows.run.restart-on-builder-landing`
- Tests: fichero-builder/tests/test_loop_survives.py
- Depends on: 2.11
- Size: S

##### Step 2.13 — the loop and the console start at login and find the lanes' panes again (owner 2026-11-03)
- Behaviours: `dev-workflows.run.loop-launchd`
- Tests: fichero-builder/tests/test_launchd.py
- Depends on: 2.12
- Size: S


##### Step 2.14 — named rule classes the ladder decides by itself, each journalled; the presubmit before a done (manager 2026-11-03)
- Behaviours: `dev-workflows.run.auto-rules`, `dev-workflows.run.presubmit`, `dev-workflows.run.build-incremental`, `dev-workflows.run.scratch-sweep`, `dev-workflows.run.rebase-rebakes-generated`
- Tests: fichero-server/tests/unit/workflows/test_check_tool.py, fichero-builder/tests/test_presubmit.py, fichero-builder/tests/test_scratch_sweep.py, fichero-builder/tests/test_autofix.py
- Depends on: 2.13
- Size: S

##### Step 2.15 — a presubmit lint for each recurring review finding (manager 2026-11-04)
- Behaviours: `dev-workflows.run.presubmit-lints`
- Tests: fichero-server/tests/unit/scripts/test_check_spec_no_duplicates.py, pipeline/tests/test_checks.py
- Depends on: 2.14
- Size: S

##### Step 2.16 — a compile answer for a lane before its done (manager 2026-11-04)
- Behaviours: `dev-workflows.run.build-check`
- Tests: fichero-builder/tests/test_build_check.py
- Depends on: 2.14
- Size: S
##### Step 2.17 — the per-unit ledger: tokens, cost, wall time and outcome for every build, check, review and fix round, from transcripts and provider usage; a dated price table; the comparison per role (#6379)
- Behaviours: `dev-workflows.ledger.numbers-from-the-cheap-sources`, `dev-workflows.ledger.prices-in-one-dated-table`
- Tests: fichero-builder/tests/test_status_page.py, test_ledger.py (not yet written)
- Depends on: 2.16
- Size: M

Order: the row and the file with the transcript reader first (it reuses `console._usage_rows` and `session.py`'s provider-neutral usage fields; nothing new is asked of a model), then the price table's new shape with the old one still read, then the `landed` row's sums and the digest block, then `builder ledger` and the console view. The owner's purpose (#6274, the Studio goal) is served by the view: the harness records, the owner decides. Ruled 2026-11-07 (manager default, owner may veto): models are ranked by cost per landed batch; the view prints cost per landed batch divided by rework rounds beside it.

- test (to write): `test_ledger.py` in fichero-builder/tests/ (the row per unit from a fixture journal and transcript; the time-window split; the three sources; the price table old and new shape, null cost and one alert; the sums on the landed row; the compare table with a "few" mark)
##### Step 2.18 — the machine pool: `[machines]` declares capabilities, the ladder places each rung, a hold holds one machine, one heavy job per machine (#6356)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_remote_list.py, fichero-builder/tests/test_heavy_lock.py, test_machine_pool.py (not yet written)
- Depends on: 2.16
- Size: M

Not for the 2026-11-05 dev build (owner). Order: the table and `builder machines` first (nothing moves); then placement behind a flag that defaults to today's `run.remote-list` order until the fake-ssh tests pass; then the hold verb and the per-machine lock. The M4 Air has no gate yet: it joins the table with `hours = "overnight"` and no tags until `builder machines sync m4air` runs (the manager's rule stands). Ruled 2026-11-07 (manager default, owner may veto): the `public` tag exists, and nothing is sent to a hosted runner until the owner declares a machine with that tag in `harness.toml`.

- test (to write): `test_machine_pool.py` in fichero-builder/tests/ (the table loads and refuses an unknown tag; placement from tags and a fake state; the busy skip is a row not an alert; the Pro fallback; the hold on one machine; two heavy rungs on two machines)

##### Step 2.19 — the parallel gate across machines, and nothing written outside a machine's root (#6356, #6357)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_remote_list.py, test_parallel_gate.py (not yet written), test_pool_writes_under_the_root.py (not yet written)
- Depends on: 2.18
- Size: M

Order: the manifest line per created path (with #6357's sweep, which lands first or beside); then the rung graph (which rungs may run together, which wait) with the join; then the shard split of the pytest rung. The DMG stays whole on one machine.

- test (to write): `test_parallel_gate.py` in fichero-builder/tests/ (three rungs on three fake machines finish in the longest rung's time; a dependent rung waits; one machine runs them in sequence; a red in one reds the check)
- test (to write): `test_pool_writes_under_the_root.py` in fichero-builder/tests/ (every sent path under the root and `runs/<run-id>/`; a manifest line per path; a write outside the root fails naming it)

##### Step 2.20 — the quality stream's ratchets: SwiftLint on its baseline, ruff, compiler warnings from the build log, the hang ratchet armed, error signatures; nothing weakens a gate (#6391)
- Behaviours: `dev-workflows.quality.ratchets-held-exactly`, `dev-workflows.quality.never-weakens-a-gate`, `dev-workflows.quality.baseline-falls-every-batch`, `dev-workflows.quality.slow-path-ratchet`
- Tests: fichero-builder/tests/test_verify_all.py, test_quality_ratchets.py (not yet written), test_guard_skip_has_no_ratchet.py (not yet written)
- Depends on: 2.15
- Size: M

Order (the lint review of 22:51 supersedes the planned harness side where they differ): the compiler-warning count first (one `xcresulttool` read, the baseline written); the SwiftLint config changes and the noisy rules off, the one reformat commit, then the baseline and its guard (the one error is lane-onboard's Monday split, kept apart); the build phase neutered in Debug in its own small batch after Monday, never a pbxproj edit; then ruff's baseline; then the compiler-warning count from the build log; then the hang ratchet armed from the Monday session's trace and, beside it, the slow-path ratchet: the one engine line shape, the trace export, the parser and the guard over a fake log first, the standard scripted run on the fixture library after; then the signature ratchet once the watcher (#6369, #6370, on the harness-digest branch, not landed) lands, which this step depends on for (5) only. The harness builder's planned side (the SwiftLint and ruff baselines, the build phase dropped, the ratchet in the guards rung) is this step; nothing here is a new API where SwiftLint's `--baseline` and the existing `check_*_ratchet.py` shape fit.

- test (to write): `test_quality_ratchets.py` in fichero-builder/tests/ (a new SwiftLint violation red and a fix green with a smaller baseline; ruff per (file, rule); one more `warning:` line red naming the category; a raised baseline refused; the disable and noqa lints)
- test (to write): `test_check_slow_path_ratchet.py` in fichero-server/tests/unit/scripts/ (the fake engine log and trace export parsed per operation with count and p95; red naming the operation and both figures; green prints the lower p95; a new operation red; a raised baseline refused; scenarios never compared)
- test (to write): `test_guard_skip_has_no_ratchet.py` in fichero-server/tests/unit/scripts/ (a `guard_skip` naming a ratchet fails)

##### Step 2.21 — the standing workers, one category or signature per batch, on a reserved lane slot (#6391)
- Behaviours: `dev-workflows.quality.workers-one-category-per-batch`, `dev-workflows.quality.reserved-slot`
- Tests: fichero-builder/tests/test_status_page.py, test_quality_workers.py (not yet written), test_reserved_lane_slot.py (not yet written)
- Depends on: 2.20
- Size: M

Order: the `quality` lane and its brief template (the kind, the category or signature, the batch size, the cap, the before-and-after rule for slowdowns), then the reserved slot in `[loop]`, then the presubmit lint that a quality batch touches one category and its baseline. The workers are cheap models; the reviewer is unchanged.

- test (to write): `test_quality_workers.py` in fichero-builder/tests/ (the brief names one category, the size and the cap; a two-category batch is sent back; the slowdown batch's before and after)
- test (to write): `test_reserved_lane_slot.py` in fichero-builder/tests/ (the next pick with two features waiting; both slots to features when idle; more reservations than slots refused)

##### Step 2.22 — the first batches, from the sources read on 2026-11-07 (#6391)
- Behaviours: `dev-workflows.quality.first-batches-from-the-reviewed-sources`
- Tests: fichero-builder/tests/test_build_check.py, test_quality_first_batches.py (not yet written)
- Depends on: 2.21
- Size: S

The step is the ordered list the first worker briefs are cut from (the SwiftLint error, then `line_length` by package starting with the six grown files; the F811 test ruling then F401 and F841; the compiler-warning baseline from the newest build log; section H's launch offenders; the three console signatures of #6375), each batch one of them. The figures are the ones in the behaviour and are re-read at the first batch (the baseline the guard writes is the truth from then on).

- test (to write): `test_quality_first_batches.py` in fichero-builder/tests/ (the brief list is cut in the stated order; each brief names one item and the issue it closes)

##### Step 2.23 — the fourth stream, bug review: one module per pass through the restricted reviewer, filed by the watcher's filer, placed by triage, fixed in grouped batches; the trial on one module after Monday (#6391, #6389)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_status_page.py, test_bug_review_pass.py (not yet written)
- Depends on: 2.21
- Size: M

Nothing new where a thing fits: the reviewer wrapper gains a `--module <dir>` mode beside its range mode; the watcher's filer gains a source; triage's `--move` and `steps` are used as they are. The first pass is the trial, one module, and the rotation above starts only when the trial's three figures are in the digest.

- test (to write): `test_bug_review_pass.py` in fichero-builder/tests/ (a fake reviewer's findings filed through the filer with dedupe and caps; each finding's three parts; a repeat pass files nothing new; the moves and the step placement; the three figures)

##### Step 2.24 — usage and cost per role and model priced every way the owner may buy it, plan-limit hits, the break-even view, and a cheapest-provider router behind the quality bar (#6387)
- Behaviours: `dev-workflows.ledger.plan-prices-in-one-dated-table`, `dev-workflows.ledger.plan-limit-hits`, `dev-workflows.ledger.daily-digest-per-role-and-model`, `dev-workflows.ledger.cheapest-provider-router`
- Tests: fichero-builder/tests/test_status_page.py, test_ledger_plans.py (not yet written), test_cheapest_provider_router.py (not yet written)
- Depends on: 2.17
- Size: M

Extends Step 2.17's ledger and the status digest; rebuilds nothing: the rows, the price table and the comparison view are 2.17's, `session.py`'s `QUOTA` match is the hit detector, `console.lane_usage`'s card is the pattern for the plan card, and Pi's `models.json` is read for its prices. Order: the plan table and its loader; the hit rows; the digest block; the break-even command and card; the router last, behind the bar, and only for a role whose `[models]` row asks for it. The owner's decision (Max, Ultra, API, OpenAI, Google, OpenRouter) is read off the break-even view and the bake-off; nothing here makes it. The rule the owner set stands: every price has a source and a date, never a guess.

- test (to write): `test_ledger_plans.py` in fichero-builder/tests/ (the plan table loader's refusal; the four per-token prices and the daily shares; the hit rows from a Claude Code and a Pi fixture; the digest block with its flags and no key or path; the median, the 90th percentile and the break-evens)
- test (to write): `test_cheapest_provider_router.py` in fichero-builder/tests/ (routes only past the bar and five units; the reason on the row; the fallback on a hit; `[models]` unchanged)

##### Step 2.25 — no new APIs: the checklist rule, the ponytail lens in the review prompt, the brief line and the presubmit note (#6389)
- Behaviours: `dev-workflows.review.no-new-apis-rule`, `dev-workflows.review.ponytail-lens`, `dev-workflows.brief.search-before-adding`, `dev-workflows.presubmit.new-api-note`
- Tests: fichero-builder/tests/test_presubmit.py, test_new_api_note.py (not yet written)
- Depends on: 2.15
- Size: S

One small harness batch, after harness-gen3 batch 33 and the digest (manager 2026-11-08: no fixed build date). Nothing new is computed: the route list is the operation-set diff the route-set guard already builds, the action and schema lists are a grep of the diff for the registry's decorator and the schema base class, the prompt gains one block above CHECKLIST and the ponytail lens as a named check under it, the checklist one numbered rule, the brief one line. The rule is a reviewer's rule, not a lint: whether an existing route "fits" is a judgement, so the presubmit reports and the review decides.

- test (to write): `test_new_api_note.py` in fichero-builder/tests/ (a fixture batch adding a route and an action: two lines in the note and at the top of the prompt; a batch with none: "none" in both; no home path in a line)

##### Step 2.26 — the console: why a lane waits, recent events and log links; a phone layout; a read-only tailnet view behind the owner's identity; nothing private in the page (#6388)
- Behaviours: `dev-workflows.console.why-waiting-and-last-landing`, `dev-workflows.console.nothing-private-in-the-page`
- Tests: fichero-builder/tests/test_status_page.py, test_console_tailnet.py (not yet written)
- Depends on: 2.24
- Size: M

The order inside the step (manager 2026-11-08: no fixed build date): the privacy strip first (it changes what every later card may show), then the desktop cards, then the media query, then the tailnet setting last, since the first three are useful on the Mac alone. The exposure is `tailscale serve`, never a bind of our own: the proxy terminates HTTPS, keeps the tailnet boundary and adds the identity header, so the console's only new logic is "non-loopback or identity header present = read-only, and only for the owner's login". Answering an alert from the phone is deliberately out (the manager's order); the owner opens the Mac for that, and the phone view says so on each alert.

- test (to write): `test_console_tailnet.py` in fichero-builder/tests/ (the setting unset: today's refusals; set: the owner's GET without buttons and with an empty token, the POST 403 with its row, a stranger's GET 403, `funnel` refused at startup; the strip pass on a fixture journal with a home path, a key and a pair link; the phone card order at 390 px, the desktop unchanged)

##### Step 2.27 — the model bake-off as a measured plan, held until the owner confirms the OpenRouter cap (#6380)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_status_page.py, test_bakeoff_plan.py (not yet written)
- Depends on: 2.24
- Size: M

HELD. The plan file is the readable order; this step is what the harness enforces: the start row, the public-data check, the frozen list, the replay reuse rule and the table. The two facts it is built on are already measured (the Qwen trial's nine items): the 27B as a builder costs about what Sonnet costs per READY item once rework is counted, and no open model reviewed to Opus's standard, so the reviewer field is the Claude tiers and the open models are shadows. The parts run in cost order, the free ones first, so the owner's cap buys only the runs that still have a question.

- test (to write): `test_bakeoff_plan.py` in fichero-builder/tests/ (no ledger row before the start row; the public-data drop with its reason; the all-READY reviewer's scores; the replay reuse on a matching spec version and base, anew on a changed spec; the table's rows match the runs and `[models]` is byte-identical)

##### Step 2.28 — work landed elsewhere is adopted, not reworked; the approve is fingerprinted; four more auto-pass classes (#6202)
- Behaviours: `dev-workflows.ladder.landed-elsewhere-detected`, `dev-workflows.ladder.adopt-landed-elsewhere`, `dev-workflows.ladder.approve-is-fingerprinted`, `dev-workflows.ladder.auto-pass-classes`
- Tests: fichero-builder/tests/test_presubmit.py, test_adopt_landed_elsewhere.py (not yet written)
- Depends on: 2.14
- Size: M

The issue was written against the old `pipeline/` (`approve-checks`, `core._since`, the recorded `since`); that code is deleted (Step 4.1) and its items 3 and 4 (the last `since` written by `repair`; diffing from the merge-base when the recorded start is an ancestor of the base) are moot in the builder, whose presubmit already diffs the lane's range against `origin/<[land].branch>` at each boundary. What survives: the adopt (items 2; the brief's ask), the fingerprint (item 1) and the four auto-pass classes (item 5) not yet among `[check].auto`. Order: detection first (it is read-only and tells the maintainer where today's foreign-commit trips come from), then the adopt action and verb, then the fingerprint, then the classes one at a time, each landing with its fixture.

- test (to write): `test_adopt_landed_elsewhere.py` in fichero-builder/tests/ (the cherry-picked commit detected by patch-id and the alert's `adopt` action; a mixed range presubmits the new commit alone; the verb lands the step with `adopted: true`, the row and the closed issue; a `--sha` not on the base refused; the approve carrying while the blob is unchanged and tripping when it changes; the four classes passing and tripping on their fixtures)

##### Step 2.29 — the performance and security lenses in every review, and the security surface listed at the top of the prompt (#6600)
- Behaviours: `dev-workflows.review.performance-lens`, `dev-workflows.review.security-lens`
- Tests: fichero-server/tests/unit/scripts/test_harness_review_lenses.py
- Depends on: 2.25
- Size: S

The cheap part, first and alone: two named checks in the prompt text, beside the ponytail lens, and one more line in the top block the new-API note already puts there, fed by the `since-guards` file list. Nothing runs; nothing is installed. Order: the two checks; the "SECURITY SURFACE CHANGED" line; the review checklist's one paragraph pointing at both (`docs/contributor_manual/review-checklist.md`). This step lands before any scanner so the reviewer reads for these from the next batch on.

- test (to write): `test_harness_review_lenses.py` in fichero-server/tests/unit/scripts/ (both checks in the rendered prompt; the store-wide observation, the N+1 and the shell call each draw a finding; an entitlement change listed at the top, "none" otherwise; the one verdict line last)

##### Step 2.30 — the method, the engine `perf` rung and the `security` rung: pytest-benchmark, pyinstrument, peak RSS and the disk delta under perf_trial's rules; bandit, semgrep, osv-scanner and gitleaks reporting only what is new (#6600)
- Behaviours: `dev-workflows.quality.perf-method`, `dev-workflows.quality.perf-rung-engine`
- Tests: fichero-server/tests/unit/scripts/test_perf_trial.py, fichero-builder/tests/test_perf_rung.py, fichero-builder/tests/test_security_rung.py, fichero-server/tests/unit/scripts/test_harness_review_lenses.py
- Depends on: 2.20
- Size: M

Order: `perf_trial.py` learns the new measurement kinds and the machine key (its tests first, red on base); the scanners installed and version-pinned on the runners in one batch with the two baselines written from the whole tree and their findings filed as `Security - *` issues; the `security` rung reading the five JSON outputs, with its REFUSED for a missing or unpinned tool; the thresholds and the waiver lints in the presubmit; then the `perf` rung's engine half, the seven perf tests moved under pytest-benchmark with their method unchanged, the baseline written from three nights of runs on the M4 (never a single run), and the skip rows for a batch that touches no engine path. Each rung is one entry in `RUNGS` and one function in `check_tool.py` like the others; the remote form is `remote_guards`'s. The budget in `perf-method` is measured on the first real batches and the figures written into this step before the rung may red a lane (until then it reports).

- test (to write): `test_perf_rung.py` in fichero-builder/tests/ (a benchmark 8% over is red and 4% green, with the test, both medians and the machine named; RSS over is red; a disk delta with no declared output is red naming the directory; a new own frame in the top ten prints a finding; a raised baseline refused; "not required" for a no-engine batch)
- test (to write): `test_security_rung.py` in fichero-builder/tests/ (each scanner's fixture JSON: new red, baselined green; a missing scanner REFUSED by name; the table in the prompt; the thresholds; a bare `# nosec` refused; a waiver with reason and issue passes; the waiver count and the baselines held exactly; `ignoreUntil` too far out refused)

##### Step 2.31 — the app half of the `perf` rung: XCTest metrics on committed Xcode baselines, body counts from `BodyCount`, and the nightly Instruments templates (#6600)
- Behaviours: `dev-workflows.quality.perf-rung-app`
- Tests: fichero/Tests/UI/general/Launch/LaunchPerformanceUITests.swift, test_perf_rung.py (not yet written)
- Depends on: 2.30, 2.8
- Size: M

Waits on Step 2.8's Swift tests for the scheme and the GUI session on the build machine; until then everything here runs nightly from the quality lane. Order: the `FicheroPerfTests` plan with its five scripted actions around the signposts that exist and `.xcbaseline` plists recorded on the M4 over three nights; `BodyCount.tick` at the top of the five named views' bodies where it is not already; the body-count baseline from the same nights; the rung's xcresult and log reads; then the nightly `xctrace` recordings and exports, the hang ratchet reading `potential-hangs` as it does today, leaks at zero, allocations at 3%. No new judge is written: Xcode fails the metric, the hang ratchet judges the hangs, `perf_trial.py` decides the rest.

- test (to write): the app-half cases of `test_perf_rung.py` (a failed perf metric in an xcresult summary red naming test and metric; `SidebarView` 31 against 4 red naming view, action and both counts; a `leaks` row red; a `potential-hangs` export through the hang ratchet unchanged; "not required" for a no-app batch)

##### Step 2.32 — the fifth stream: one module a night profiled and scanned without a baseline, reviewed through the two lenses, filed into `Performance - *` and `Security - *`, fixed in grouped batches that lower a baseline (#6600)
- Behaviours: `dev-workflows.quality.perf-security-sweep`
- Tests: fichero-builder/tests/test_status_page.py, test_perf_security_sweep.py (not yet written)
- Depends on: 2.23, 2.31
- Size: M

Nothing new where the bug stream's part fits: the reviewer's `--module` mode, the filer's source, triage's `--move` and `steps`, the quality lane's one-group batches. What is new is the profile and scan inputs handed to the reviewer as files, the two buckets, and the lowered-sum figure in the digest. The first pass is one engine module (`recipes/`, as the bug stream's trial) and one app module (`Views/Sidebar/`, #6547's), and the rotation starts when their figures are in the digest.

- test (to write): `test_perf_security_sweep.py` in fichero-builder/tests/ (a fake profile, scan and reviewer: at most 3 issues and one rolling issue, each with `file:line`, a figure and a test or benchmark, in the right bucket under a step; a repeat pass files nothing new; the four digest figures)

##### Step 2.33 — the perf and security rungs actually run: the gate venv's python, the pinned tools, a crash told from an outage, and "not run" told truthfully (#6589, #6600)
- Behaviours: `dev-workflows.quality.perf-rung-runs`, `dev-workflows.quality.perf-remote-crash`, `dev-workflows.quality.rung-not-run-is-truthful`, `dev-workflows.quality.security-pins-installed`
- Tests: fichero-builder/tests/test_perf_rung.py
- Depends on: 2.30
- Size: S

Order: the gate-venv default and the pinned tools; the first-figures recording; the crash row; the not-run flag; the scanner pins written on the M4.

##### Step 2.34 — one home for the builder's and the manager's files: the review dirs in the state dir, the manager folders, the brief copied by `queue add` (#6589)
- Behaviours: `dev-workflows.run.review-files-in-state-dir`, `dev-workflows.run.manager-files-one-home`
- Tests: fichero-server/tests/unit/workflows/test_review_wrapper.py, fichero-builder/tests/test_scratch_sweep.py, fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_no_home_litter.py
- Depends on: 2.33
- Size: S

Order: the review dirs under the workroot and their sweep; the placement rule in AGENTS.md; the brief copy; the no-`$HOME` test.

##### Step 3.1 — `--kind pi` over RPC with a fail-closed `tool_call` extension; a metered provider; one model per role in the rules file
- Behaviours: `dev-workflows.node.worker`, `dev-workflows.models.by-config`, `dev-workflows.models.review-by-path`
- Tests: fichero-builder/tests/test_pi_rpc.py, fichero-builder/tests/test_pi_policy_extension.py, fichero-builder/tests/test_model_config.py
- Size: M

##### Step 3.2 — the sandbox chosen by test (launcher with entitlements, Seatbelt profile, Apple container) behind one wrapper
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_sandbox_wrapper.py
- Depends on: 3.1
- Size: M

##### Step 3.3 — local on the Studio: coder only, one issue per session, review on a cloud model until the TSV agrees
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_local_parity.py
- Depends on: 3.1
- Size: M

#### Stage 4 — cleanup, the records, the Researcher, the app

##### Step 4.1 — an issue lint matched to how issues are written; `builder clean`; `pipeline/` deleted; AGENTS.md rewritten
- Behaviours: `dev-workflows.surface.one-action-layer`
- Tests: fichero-builder/tests/test_issue_lint.py, fichero-builder/tests/test_clean.py
- Depends on: 2.2
- Size: M

##### Step 4.2 — the records and the guarded GitHub sync (pull)
- Behaviours: `dev-workflows.combined.entities`, `dev-workflows.combined.github-sync`
- Tests: fichero-server/tests/unit/research/test_combined_model_records.py, fichero-server/tests/unit/research/test_github_sync.py
- Depends on: 2.2
- Size: M

##### Step 4.3 — the Researcher's first tasks
- Behaviours: `dev-workflows.researcher.tasks`
- Tests: fichero-server/tests/unit/research/test_researcher_tasks.py
- Depends on: 4.2
- Size: M

##### Step 4.4 — the app reads the journal: the Activity table with a hierarchy, and controls that work
- Behaviours: `dev-workflows.ux.activity-table`, `dev-workflows.ux.lane-usage`
- Tests: fichero/Tests/Unit/general/Models/ActivityTableTests.swift, fichero-server/tests/unit/workflows/test_controls_reach_the_call.py
- Depends on: 4.1
- Size: M

##### Step 4.5 — the loop runs managed workers by itself: dispatch, landing, the watchdog (landed in part: watch the first batch land)
- Behaviours: `dev-workflows.run.loop-dispatch`, `dev-workflows.run.loop-already-landed`, `dev-workflows.run.loop-blocked-watchdog`, `dev-workflows.run.loop-dismiss-parks`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_work_verb.py, fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_alerts_clear.py
- Depends on: 4.4
- Size: S

Built by the harness-fix branch (2026-11-10); what remains is one managed batch landing with no person present, then `[loop].dispatch` widened lane by lane.

##### Step 4.6 — pinned auto-approval and the console plan
- Behaviours: `dev-workflows.run.loop-auto-approve-pinned`, `dev-workflows.run.loop-plan`, `dev-workflows.run.loop-current`, `dev-workflows.run.loop-cleanup`
- Tests: fichero-builder/tests/test_status_page.py, fichero-builder/tests/test_launchd.py, fichero-builder/tests/test_loop_survives.py, fichero-builder/tests/test_loop.py
- Depends on: 4.5
- Size: S

Built by the same branch; open work is the console Plan page (#6467).

##### Step 4.7 — the review of 2026-11-10: managed sessions that are refused or ended
- Behaviours: `dev-workflows.run.loop-brief-preflight`, `dev-workflows.run.loop-session-ends`, `dev-workflows.run.loop-no-session`, `dev-workflows.run.loop-owner-branch-lands`, `dev-workflows.run.daily-builds-alert`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_queue_verb.py
- Depends on: 4.6
- Size: S

Issues #6495, #6496, #6500-#6502 (the review at 15:17 ADT); built on the harness-console-fix branch.

##### Step 4.8 — the review of 2026-11-10: a console that is fast and true
- Behaviours: `dev-workflows.run.console-status-cache`, `dev-workflows.run.console-tabs-refetch`, `dev-workflows.run.console-gh-in-the-repo`, `dev-workflows.run.console-worktrees-own`, `dev-workflows.run.console-one-spend`
- Tests: fichero-builder/tests/test_status_page.py, fichero-builder/tests/test_milestone_verb.py
- Depends on: 4.7
- Size: S

Issues #6497-#6499, #6503, #6505; built on the same branch.

##### Step 4.9 — the review of 2026-11-10: the page's event tables, and green-first chain slots
- Behaviours: `dev-workflows.run.console-events-true`, `dev-workflows.run.loop-green-first`, `dev-workflows.run.console-since-build`, `dev-workflows.run.loop-retried-batch-lands`, `dev-workflows.console.abandoned-after-six-hours`
- Tests: fichero-builder/tests/test_status_page.py, fichero-builder/tests/test_loop.py, fichero-builder/tests/test_presubmit.py
- Depends on: 4.8
- Size: S

Issues #6467, #6504, #6506, #6507, #6524; built on the same branch.

##### Step 4.10 — alerts a person answered the same way every time
- Behaviours: `dev-workflows.run.loop-approval-by-diff`, `dev-workflows.run.loop-guard-data-by-content`, `dev-workflows.run.loop-retry-keeps-head`, `dev-workflows.run.presubmit-scratch-owned`, `dev-workflows.run.brief-for-worker`
- Tests: fichero-builder/tests/test_loop.py, fichero-builder/tests/test_presubmit.py, fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_milestone_verb.py
- Depends on: 4.9
- Size: S

Lead 2026-11-11, after the harness-console-fix batch landed; built on the same branch.

##### Step 4.11 — issues close when they are done: the reconcile after every landing and nightly
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_issue_reconcile.py, fichero-builder/tests/test_queue_verb.py
- Depends on: 4.10
- Size: S

Owner 2026-11-14 (#6589); built on the issue-close lane. Not yet: a run on the real jail user.

##### Step 4.12 — the nightly dev build of one frozen sha (owner 2026-11-17)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_nightly.py, fichero-builder/tests/test_queue_verb.py, fichero-builder/tests/test_verify_all.py
- Depends on: 4.11
- Size: M

Issue #6665; replaces the per-landing dev build. Not yet: a real night on the machines.


### From `agent-profiles.md` — Build order (history; Step headings demoted so `builder steps` files only this spec's steps)


Smallest first; each step is one lane batch unless marked; `Depends on` defaults to the step before.

#### Stage 1 — the rule, the folder, the servers, the small worker, the Swift rungs

##### Step 1.1 — the trailer: one line, one rule, every file
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_trailer (new)
- Size: S
- Order: (a) the test with the four refused shapes and the one accepted; (b) `policy_hook.py` compares one exact shape
  built from MODEL and HARNESS; (c) `harness.toml`; (d) `review-checklist.md` 10, `AGENTS.md`, `harness_review.py`,
  `check_agent_commits_authored_as_claude.py`; (e) a commit with the new line lands.

##### Step 1.2 — the folder, the common prompt, assembly, the adapter interface, the Claude Code adapter
- Behaviours: `agent-profiles.folder.one-place`, `agent-profiles.prompt.common`, `agent-profiles.prompt.assembly`, `agent-profiles.adapter.interface`, `agent-profiles.adapter.claude-code`
- Tests: fichero-builder/tests/test_profiles (new), fichero-builder/tests/test_adapters (new)
- Size: M

##### Step 1.3 — jcodemunch and jdocmunch required for every worker; tool sets per role and per project
- Behaviours: `agent-profiles.mcp.required`
- Tests: fichero-builder/tests/test_mcp_servers (new)
- Size: S

##### Step 1.4 — the small-worker rule: one step, a short brief, named files and tests, a diff bound
- Behaviours: `agent-profiles.worker.small`
- Tests: fichero-builder/tests/test_small_worker (new)
- Depends on: 1.2
- Size: S

##### Step 1.5 — Swift unit and UI test rungs in the dedicated GUI user; the UI smoke on request
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_swift_rungs (new)
- Depends on: 1.2
- Size: M

#### Stage 2 — generic: project profile, workflow, run record, console, cleanup

##### Step 2.1 — the project profile, the declared workflow, the thin project prompt layer
- Behaviours: `agent-profiles.project.profile`, `agent-profiles.workflow.declared`, `agent-profiles.prompt.project-layer`
- Tests: fichero-builder/tests/test_project_profile (new), fichero-builder/tests/test_workflow (new), fichero-builder/tests/test_profiles (new)
- Depends on: 1.4
- Size: M

##### Step 2.2 — the run record
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_run_record (new)
- Depends on: 2.1
- Size: S

##### Step 2.3 — the console's Runs, Compare and Bake-offs views (reconciled with `builder-console.md`)
- Behaviours: `agent-profiles.console.runs`
- Tests: fichero-builder/tests/test_console_runs (new)
- Depends on: 2.2
- Size: M

##### Step 2.4 — cleanup as the workflow's last step (#6589 item 16)
- Behaviours: `agent-profiles.cleanup.after-land`
- Tests: fichero-builder/tests/test_workflow (new)
- Depends on: 2.1
- Size: S

#### Stage 3 — adapters, one per step, in the owner's order

##### Step 3.1 — the Pi adapter in the folder; Ollama and OpenAI-compatible providers through it
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_pi_rpc.py
- Depends on: 1.3
- Size: S

##### Step 3.2 — the opencode adapter
- Behaviours: `agent-profiles.adapter.opencode`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: M

##### Step 3.3 — the Qwen Code adapter
- Behaviours: `agent-profiles.adapter.qwen-code`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

##### Step 3.4 — the Codex CLI adapter
- Behaviours: `agent-profiles.adapter.codex-cli`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

##### Step 3.5 — the Gemini CLI / Antigravity adapter
- Behaviours: `agent-profiles.adapter.gemini-cli`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

##### Step 3.6 — the goose adapter
- Behaviours: `agent-profiles.adapter.goose`
- Tests: fichero-builder/tests/test_adapters (new)
- Depends on: 3.1
- Size: S

#### Stage 4 — roles, the manager, the bake-off, the text project

##### Step 4.1 — the role profiles and the stack profiles: a worker is role × stack
- Behaviours: `agent-profiles.prompt.roles`, `agent-profiles.prompt.stacks`
- Tests: fichero-builder/tests/test_profiles (new)
- Depends on: 2.1
- Size: M
- Order: the `swift` and `python` stacks with the feature role first (one real step each), then code-review (the
  reviewer script reads its file), testing and bug-fixing on both stacks, perf and the measuring roles against
  `performance-sweep.md`'s rungs on both stacks, landing, then the text roles.

##### Step 4.2 — the built-in manager role
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_manager_role (new)
- Depends on: 4.1
- Size: M

##### Step 4.3 — the bake-off
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_bakeoff (new)
- Depends on: 2.3, 3.2, 4.1
- Size: M

##### Step 4.4 — a text project runs the generic workflow
- Behaviours: `agent-profiles.workflow.text-project`
- Tests: fichero-builder/tests/test_text_project (new)
- Depends on: 4.1
- Size: M

#### Stage 5 — worker isolation (the longest steps: several trials each; after the adapters)

##### Step 5.1 — isolation research: one page and one measured trial per option, a written choice per lane kind
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_isolation_trial (new), fichero-builder/tests/test_jail (new)
- Depends on: 3.6
- Size: M
- Order: (a) the trial runner and its row shape with fixtures; (b) `sandbox-exec`; (c) a macOS VM (`tart`, then `lume`
  if `tart` fails the Xcode build); (d) `container` and Docker for an engine lane; (e) egress and per-worker
  credentials on each; (f) the pages and the choice table go to the owner as a question.

##### Step 5.2 — the chosen isolation behind the wrapper, with the four probes at every start
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_isolation (new)
- Depends on: 5.1
- Size: M


### From `builder-console.md` — Build order (history; Step headings demoted so `builder steps` files only this spec's steps)


Smallest first; each step is one lane batch; `Depends on` defaults to the step before. Steps 1.x make the loop forget
nothing; 2.x make the page say it; 3.x compare; 4.3 is held.

#### Stage 1 — one state, one source, the loop acts

##### Step 1.1 — one state per step with an age; `why` is about the current state; paused and held are flags
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_step_state (new)
- Size: S

##### Step 1.2 — the store: DuckDB + Pydantic records with the journal as its log, and the WorkStore interface with its GitHub implementation
- Behaviours: `builder-console.work-store.host-agnostic`
- Tests: fichero-builder/tests/test_store (new), fichero-builder/tests/test_work_store (new)
- Size: M

##### Step 1.3 — the work tree in the store: milestones › steps › lanes; the order is a record; `build-order.md` is generated
- Behaviours: `builder-console.ordered-work.one-source`, `builder-console.work.counts-are-live`
- Tests: fichero-builder/tests/test_work_tree (new)
- Size: M

##### Step 1.4 — stale work is listed and acted on every tick; a finished step moves the lane on
- Behaviours: `builder-console.stale.acted-on`, `builder-console.step.moves-on`
- Tests: fichero-builder/tests/test_stale (new), fichero-builder/tests/test_moves_on (new)
- Size: M

##### Step 1.5 — cleanup as the last step of every lane
- Behaviours: `builder-console.cleanup.is-a-step`
- Tests: fichero-builder/tests/test_cleanup_step (new)
- Depends on: 1.2
- Size: S

#### Stage 2 — the page

##### Step 2.1 — labelled numbers everywhere; a header row that stays; billed and API-equivalent apart
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_console_numbers (new)
- Depends on: 1.1
- Size: S

##### Step 2.2 — the lane page and `GET /api/lane/<id>`
- Behaviours: `builder-console.lane.page`, `builder-console.read-only-by-get`
- Tests: fichero-builder/tests/test_lane_page (new), fichero-builder/tests/test_status_page.py
- Depends on: 2.1
- Size: M

##### Step 2.3 — the Work tab first: running, needs you, failed lately, landed lately, history folded
- Behaviours: `builder-console.page.work-first`
- Tests: fichero-builder/tests/test_console_page (new)
- Depends on: 1.2, 2.2
- Size: M

#### Stage 3 — runs and comparison (needs the sibling's run record, `agent-profiles` Step 2.2, #6628)

##### Step 3.1 — the Runs tab on `/api/runs`, old cost rows shown as runs, after the sibling's #6628
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_console_runs (new)
- Depends on: 2.3
- Size: S

##### Step 3.2 — Compare and Bake-offs
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_console_compare (new)
- Size: M

##### Step 3.3 — the pages on a second project of kind `text`, after the sibling's #6627
- Behaviours: `builder-console.project.neutral`
- Tests: fichero-builder/tests/test_console_second_project (new)
- Depends on: 3.2
- Size: S

#### Stage 4 — one API, edits both ways, the separate repository

##### Step 4.1 — the verb table generates the page's forms and the MCP tools; reads are one API
- Behaviours: `builder-console.api.one-engine`
- Tests: fichero-builder/tests/test_api_one_engine (new)
- Depends on: 2.2
- Size: M

##### Step 4.2 — roles, prompts, workflows, models and controls editable from the page and MCP, audited
- Behaviours: `builder-console.edit.both-ways`
- Tests: fichero-builder/tests/test_edit_both_ways (new)
- Depends on: 4.1
- Size: M

##### Step 4.3 — HELD (owner 2026-11-16): the repository split into a Fichero Harness repository, the data kind and the in-Fichero work store
- Behaviours: `builder-console.repo.split-held`
- Tests: fichero-builder/tests/test_console_second_project (new)
- Depends on: 4.2
- Size: M


### From `performance-sweep.md` — Build order (history; Step headings demoted so `builder steps` files only this spec's steps)


Smallest first; each step is one lane batch unless marked. Steps 1–2 produce value with no new tool on any machine. Owner 2026-11-15: all eight steps are v1 and none is deferred, so the review's v1 cut does not apply.

##### Step 1 — the #6589 blockers: the rungs run, or say they did not (#6589)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_perf_rung.py, fichero-builder/tests/test_security_rung.py
- Size: S
- Order: (a) `_remote_build` keeps the env-red row and `perf()` / the security rung map the three causes to `not-run` with
  the remote stderr (tests first, red on base); (b) the manager runs `scripts/install_security_tools.sh --write-pins` on
  the M4 and the iMac and commits the pins (`[check.security].pins`), and `--check` runs in the rung before the scan;
  (c) confirm `scripts/perf_baseline.json` and `fichero-server/tests/perf/` reach the rsynced stable tree
  (`_stable_build_tree`'s filter) and that `[check].remote_python` points at the gate venv with `pytest-benchmark` and
  `pyinstrument`; the first real `not-run` reason seen on the M4 is written into #6589 as the finding; (d) alert ids.
  Done when one ladder shows `perf` and `security` with a figure or a named `not-run`, never a bare green.

##### Step 2 — read what is already logged: app phases and engine spans into the first hotspot table (#6600)
- Behaviours: `perf-sweep.source.app-log-phases`, `perf-sweep.source.engine-perf-lines`, `perf-sweep.output.row`,
  `perf-sweep.output.table`
- Tests: fichero-server/tests/unit/scripts/test_perf_log_readers (new), fichero-builder/tests/test_perf_sweep (new)
- Depends on: 1
- Size: S
- Order: the two readers over fixture logs; the row shape and the area map; `hotspots.json` + `latest.json` from the
  logs of the existing smoke and perf-test runs (the daily `tests` build's run and the engine perf rung's log); `builder
  perf show`; the console panel last. No new tool, no new workload: the table exists after this step.

##### Step 3 — the workloads and the corpus manifest (#6600)
- Behaviours: `perf-sweep.workload.set`, `perf-sweep.workload.corpus`, `perf-sweep.source.machines`
- Tests: fichero-builder/tests/test_perf_sweep (new), fichero-server/tests/unit/scripts/test_perf_corpus (new)
- Depends on: 2
- Size: M
- Order: the manifest and `builder install --corpus` (hash-verified); the `[perf.workloads]` table with W1–W5 as pytest
  drivers (the seven perf tests regrouped, methods unchanged) and W6–W10 as `FICHERO_PERF_WORKLOAD` scenarios in the Dev
  Local build's test hooks; the machine tags. The boundary grep covers the two new files.

##### Step 4 — engine profiles nightly: pyinstrument or py-spy, memray, du, CPU/wall (#6600)
- Behaviours: `perf-sweep.source.engine-profiles`
- Tests: fichero-builder/tests/test_perf_sweep (new)
- Depends on: 3
- Size: M
- Order: readers over fixture outputs first; the nightly driver on the M4 behind the heavy lock, one workload at a time,
  W2 last and with its own budget; rows into the table. py-spy runs with sudo on the M4 only, through the one sudoers line the owner approved on 2026-11-15 (Open questions, 2).

##### Step 5 — the filing rule through the watcher's filer (#6600)
- Behaviours: `perf-sweep.output.filing-rule`
- Tests: fichero-builder/tests/test_perf_sweep (new)
- Depends on: 2 (useful from the log rows alone), 4
- Size: S
- Order: floors, the two-run rule, the key, reopen-on-regression, the caps and placement, the issue body with the inline
  frames and the owner's ask. Owner 2026-11-15: no daily cap; every spot over its floor is filed, deduped by key.

##### Step 6 — the warnings ratchet and list (#6610)
- Behaviours: `perf-sweep.warnings.from-the-result-bundle`, `perf-sweep.warnings.ratchet`,
  `perf-sweep.warnings.ranked-list-and-issues`
- Tests: fichero-server/tests/unit/scripts/test_check_xcode_warning_ratchet (new), fichero-builder/tests/test_perf_sweep (new)
- Depends on: 1 (the kept build logs and result bundles)
- Size: M
- Order: `-resultBundlePath` on the build rung and the daily builds (the `ipad-sim` daily build waits for an iPad scheme); the reader and the
  normaliser over fixtures; the baseline written from the next green mac, iOS and iPad builds (its own commit); the
  ratchet in the build rung for `fichero/` batches; the SwiftLint `--json`; the ranked list, the console panel and one
  issue per kind, the script-phase issue filed first and fixed in its own small batch (a pbxproj edit: owner or manager,
  `builder-ladder-traps`). Step 2.20's "compiler warnings from the build log" line in dev-workflows points here.

##### Step 7 — the ratchet: budgets, five-run baselines, the noise band, enforce per measure (#6600)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-server/tests/unit/scripts/test_perf_trial.py, fichero-builder/tests/test_perf_sweep (new)
- Depends on: 4, and five nightly runs having happened
- Size: M
- Order: the figure shape in `perf_trial.py`; `builder perf baseline --write/--lower`; the band; `[check.perf].enforce`
  as a list; the first measures enforced are the exact ones (disk, leaks, hangs, bodies), time and RSS only after their
  band is known.

##### Step 8 — app profiles, runtime checkers, XCTest metrics and MetricKit (#6600; with dev-workflows Step 2.31)
- Behaviours: `perf-sweep.source.app-profiles`, `perf-sweep.source.runtime-checkers`, `perf-sweep.source.xctest-metrics`,
  `perf-sweep.source.metrickit-and-field`
- Tests: fichero-builder/tests/test_perf_sweep (new), fichero/Tests/UI/general/Launch/LaunchPerformanceUITests.swift
- Depends on: 3, dev-workflows 2.8 (the Swift tests on the M4's GUI session) and 2.31
- Size: L (two batches: recordings and exports; then the diagnostics plan and MetricKit)
- Order: xctrace recordings of W6–W10 with the toc pinned and the exports read (the hang ratchet unchanged as the hang
  judge); the diagnostics test plan with its two configurations, nightly; the perf plan's metrics as rows; the MetricKit
  subscriber in the app (its own small app batch) and the Organizer read from the nightly.


### From `issues-and-labels.md` — Build order (history; Step headings demoted so `builder steps` files only this spec's steps)


#### Stage 1 — the record

##### Step 1.1 — the build-order file and the pick order (#6116)
- Behaviours: `issues.build-order-file-orders-milestones`, `issues.pick-order-step-bug-priority`
- Tests: fichero-builder/tests/test_milestone_verb.py
- Size: S

##### Step 1.2 — landed closes and comments (#6116)
- Behaviours: (re-placed in the Builder build order above)
- Tests: fichero-builder/tests/test_landed_verb.py
- Depends on: 1.1
- Size: S

##### Step 1.3 — triage (#6116)
- Behaviours: `issues.milestone-is-the-spec`, `issues.label-set-is-closed`, `issues.spec-less-milestone-gets-a-spec-issue`
- Tests: fichero-server/tests/unit/workflows/test_triage_tool.py
- Depends on: 1.2
- Size: M


## Stop rules

Stop and report if: more than a third of steps end blocked or parked; the supervising manager's tokens exceed what
Sonnet used for the same work, or its use crowds the owner's own on the Max plan; OpenRouter passes 50 dollars in a week; relaxed checks rise week over week; or the harness's share of landed steps stays above
half for two weeks after the freeze.

## Behaviour tests

The test tables of the absorbed specs, moved in Phase 0. A behaviour's own bullet names its test; these tables are the
index each spec kept.

### From `dev-workflows.md` — Behaviour tests


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
| `dev-workflows.run.jail-home` | 2.1 |
| `dev-workflows.run.remote-list` | 2.1 |
| `dev-workflows.ledger.one-row-per-unit` | 2.17 |
| `dev-workflows.ledger.numbers-from-the-cheap-sources` | 2.17 |
| `dev-workflows.ledger.prices-in-one-dated-table` | 2.17 |
| `dev-workflows.ledger.keyed-to-batch-and-lane` | 2.17 |
| `dev-workflows.ledger.comparison-view` | 2.17 |
| `dev-workflows.pool.machines-declare-capabilities` | 2.18 |
| `dev-workflows.pool.placement-and-fallback` | 2.18 |
| `dev-workflows.pool.hold-holds-one-machine` | 2.18 |
| `dev-workflows.pool.one-heavy-per-machine` | 2.18 |
| `dev-workflows.pool.parallel-gate` | 2.19 |
| `dev-workflows.pool.no-litter` | 2.19 |
| `dev-workflows.quality.ratchets-held-exactly` | 2.20 |
| `dev-workflows.quality.never-weakens-a-gate` | 2.20 |
| `dev-workflows.quality.workers-one-category-per-batch` | 2.21 |
| `dev-workflows.quality.reserved-slot` | 2.21 |
| `dev-workflows.quality.first-batches-from-the-reviewed-sources` | 2.22 |
| `dev-workflows.quality.baseline-falls-every-batch` | 2.20 |
| `dev-workflows.quality.slow-path-ratchet` | 2.20 |
| `dev-workflows.quality.bug-review-stream` | 2.23 |
| `dev-workflows.ledger.plan-prices-in-one-dated-table` | 2.24 |
| `dev-workflows.ledger.plan-limit-hits` | 2.24 |
| `dev-workflows.ledger.daily-digest-per-role-and-model` | 2.24 |
| `dev-workflows.ledger.break-even-view` | 2.24 |
| `dev-workflows.ledger.cheapest-provider-router` | 2.24 |
| `dev-workflows.review.no-new-apis-rule` | 2.25 |
| `dev-workflows.review.ponytail-lens` | 2.25 |
| `dev-workflows.brief.search-before-adding` | 2.25 |
| `dev-workflows.presubmit.new-api-note` | 2.25 |
| `dev-workflows.console.why-waiting-and-last-landing` | 2.26 |
| `dev-workflows.console.phone-layout` | 2.26 |
| `dev-workflows.console.tailnet-read-only` | 2.26 |
| `dev-workflows.console.nothing-private-in-the-page` | 2.26 |
| `dev-workflows.bakeoff.held-until-the-cap` | 2.27 |
| `dev-workflows.bakeoff.public-data-only` | 2.27 |
| `dev-workflows.bakeoff.frozen-ground-truth` | 2.27 |
| `dev-workflows.bakeoff.replay-corpus` | 2.27 |
| `dev-workflows.bakeoff.decision-table` | 2.27 |
| `dev-workflows.ladder.landed-elsewhere-detected` | 2.28 |
| `dev-workflows.ladder.adopt-landed-elsewhere` | 2.28 |
| `dev-workflows.ladder.approve-is-fingerprinted` | 2.28 |
| `dev-workflows.ladder.auto-pass-classes` | 2.28 |
| `dev-workflows.review.performance-lens` | 2.29 |
| `dev-workflows.review.security-lens` | 2.29 |
| `dev-workflows.quality.perf-method` | 2.30 |
| `dev-workflows.quality.perf-rung-engine` | 2.30 |
| `dev-workflows.quality.perf-rung-runs` | 2.33 |
| `dev-workflows.quality.perf-remote-crash` | 2.33 |
| `dev-workflows.quality.rung-not-run-is-truthful` | 2.33 |
| `dev-workflows.quality.security-pins-installed` | 2.33 |
| `dev-workflows.run.review-files-in-state-dir` | 2.34 |
| `dev-workflows.run.manager-files-one-home` | 2.34 |
| `dev-workflows.quality.security-scan-rung` | 2.30 |
| `dev-workflows.quality.scan-thresholds-and-waivers` | 2.30 |
| `dev-workflows.quality.perf-rung-app` | 2.31 |
| `dev-workflows.quality.perf-security-sweep` | 2.32 |
| `dev-workflows.tool.milestone` | 2.3 |
| `dev-workflows.tool.work` | 2.3 |
| `dev-workflows.tool.spec` | 2.3 |
| `dev-workflows.tool.steps` | 2.3 |
| `dev-workflows.tool.file` | 2.3 |
| `dev-workflows.tool.landed` | 2.4 |
| `dev-workflows.tool.triage` | 2.5 |
| `dev-workflows.tool.queue` | 2.6 |
| `dev-workflows.run.code-map` | 2.7 |
| `dev-workflows.tool.build` | 2.8 |
| `dev-workflows.run.swift-tests` | 2.8 |
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
| `dev-workflows.run.nightly-build` | 4.12 |
| `dev-workflows.run.release-stages` | 4.12 |
| `dev-workflows.run.loop-dispatch` | 4.5 |
| `dev-workflows.run.loop-already-landed` | 4.5 |
| `dev-workflows.run.loop-blocked-watchdog` | 4.5 |
| `dev-workflows.run.loop-dismiss-parks` | 4.5 |
| `dev-workflows.run.loop-auto-approve-pinned` | 4.6 |
| `dev-workflows.run.loop-plan` | 4.6 |
| `dev-workflows.run.loop-current` | 4.6 |
| `dev-workflows.run.loop-cleanup` | 4.6 |
| `dev-workflows.run.loop-brief-preflight` | 4.7 |
| `dev-workflows.run.loop-session-ends` | 4.7 |
| `dev-workflows.run.loop-no-session` | 4.7 |
| `dev-workflows.run.loop-owner-branch-lands` | 4.7 |
| `dev-workflows.run.daily-builds-alert` | 4.7 |
| `dev-workflows.run.console-status-cache` | 4.8 |
| `dev-workflows.run.console-tabs-refetch` | 4.8 |
| `dev-workflows.run.console-gh-in-the-repo` | 4.8 |
| `dev-workflows.run.console-worktrees-own` | 4.8 |
| `dev-workflows.run.console-one-spend` | 4.8 |
| `dev-workflows.run.console-events-true` | 4.9 |
| `dev-workflows.run.loop-green-first` | 4.9 |
| `dev-workflows.run.console-since-build` | 4.9 |
| `dev-workflows.run.loop-retried-batch-lands` | 4.9 |
| `dev-workflows.run.loop-approval-by-diff` | 4.10 |
| `dev-workflows.run.loop-guard-data-by-content` | 4.10 |
| `dev-workflows.run.loop-retry-keeps-head` | 4.10 |
| `dev-workflows.run.presubmit-scratch-owned` | 4.10 |
| `dev-workflows.run.brief-for-worker` | 4.10 |
| `dev-workflows.run.issues-close-when-done` | 4.11 |
| `dev-workflows.console.abandoned-after-six-hours` | 4.9 |
| `dev-workflows.models.review-by-path` | 3.1 |
| `dev-workflows.run.auto-rules` | 2.14 |
| `dev-workflows.run.build-check` | 2.16 |
| `dev-workflows.run.build-incremental` | 2.14 |
| `dev-workflows.run.heavy-lock` | 2.7 |
| `dev-workflows.run.loop` | 2.9 |
| `dev-workflows.run.loop-alerts` | 2.10 |
| `dev-workflows.run.loop-chain` | 2.9 |
| `dev-workflows.run.loop-external-intake` | 2.6 |
| `dev-workflows.run.loop-external-lane` | 2.11 |
| `dev-workflows.run.loop-fetches-the-lane` | 2.9 |
| `dev-workflows.run.loop-fix-rounds` | 2.9 |
| `dev-workflows.run.loop-handoff-tokens` | 2.10 |
| `dev-workflows.run.loop-launchd` | 2.13 |
| `dev-workflows.run.loop-machine-checked` | 2.11 |
| `dev-workflows.run.loop-needs-maintainer` | 2.10 |
| `dev-workflows.run.loop-roles` | 2.10 |
| `dev-workflows.run.loop-rolls-on` | 2.11 |
| `dev-workflows.run.loop-session-cap-hands-off` | 2.10 |
| `dev-workflows.run.loop-soak` | 2.11 |
| `dev-workflows.run.loop-status` | 2.11 |
| `dev-workflows.run.loop-survives` | 2.12 |
| `dev-workflows.run.loop-tell` | 2.9 |
| `dev-workflows.run.measure` | 2.8 |
| `dev-workflows.run.presubmit` | 2.14 |
| `dev-workflows.run.presubmit-lints` | 2.15 |
| `dev-workflows.run.rebase-rebakes-generated` | 2.14 |
| `dev-workflows.run.restart-adopts-live-window` | 2.12 |
| `dev-workflows.run.restart-on-builder-landing` | 2.12 |
| `dev-workflows.run.restart-resets-nothing` | 2.12 |
| `dev-workflows.run.restart-rules-per-tick` | 2.12 |
| `dev-workflows.run.scratch-sweep` | 2.14 |
| `dev-workflows.run.tell` | 2.2 |
| `dev-workflows.run.verify-all` | 2.8 |
| `dev-workflows.ux.lane-usage` | 4.4 |


### From `dev-workflows.md` — Test matrix


| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | workers, tools, gates, watches, records, sync, researcher tasks, models | `fichero-server/tests/unit/workflows/`, `tests/unit/research/`, `tests/unit/security/` |
| CLI (pytest) | y | dev verbs are audited actions | `fichero-cli/tests/test_chat_dev_verbs.py` |
| Swift unit | y | the table's rows, columns, in-place update, lazy children | `fichero/Tests/Unit/general/Models/ActivityTableTests.swift` |

### From `agent-profiles.md` — Behaviour tests


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

### From `builder-console.md` — Behaviour tests


| Behaviour | Step |
|---|---|
| `builder-console.step.one-state` | 1.1 |
| `builder-console.store.one-database` · `work-store.host-agnostic` | 1.2 |
| `builder-console.ordered-work.one-source` · `work.counts-are-live` | 1.3 |
| `builder-console.stale.acted-on` · `step.moves-on` | 1.4 |
| `builder-console.cleanup.is-a-step` | 1.5 |
| `builder-console.numbers.labelled` | 2.1 |
| `builder-console.lane.page` · `read-only-by-get` | 2.2 |
| `builder-console.page.work-first` | 2.3 |
| `builder-console.runs.page` | 3.1 |
| `builder-console.compare.page` | 3.2 |
| `builder-console.project.neutral` | 3.3 |
| `builder-console.api.one-engine` | 4.1 |
| `builder-console.edit.both-ways` | 4.2 |
| `builder-console.repo.split-held` | 4.3 (held) |

### From `issues-and-labels.md` — Test matrix


| Behaviour | Test | Status |
|---|---|---|
| milestone-is-the-spec | test_triage_tool.py | to write |
| label-set-is-closed | test_triage_tool.py | to write |
| build-order-file-orders-milestones | test_milestone_verb.py | to write |
| pick-order-step-bug-priority | test_milestone_verb.py | to write |
| harness-closes-after-integration | test_landed_verb.py | to write |
| spec-less-milestone-gets-a-spec-issue | test_triage_tool.py | to write |









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
