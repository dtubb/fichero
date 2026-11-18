# Review of `building-fichero-locally.md` (sceptical pass, Phase 0, 2026-11-18)

Read against `origin/integration` at `b56999b271` and the branch `harness-phase0-2026-11-18` after the eleven absorbing commits.
The pattern is `performance-sweep-REVIEW.md`: what is claimed and is not so, what cannot be tested as written, what is missing.
Nothing here is built; every finding is a sentence in the spec or a step in its build order.

## 1. The behaviour check (`local.spec-lint` run by hand)

| Rule | Result |
|---|---|
| Unique id | 307 behaviours in the one spec after the cuts (33 `local.*`); no id is defined in two files across `specs/harness/` (the three `openapi.mcp.*` duplicates inside `surfaces-from-openapi.md` predate Phase 0 and are in `check_spec_no_duplicates` KNOWN) |
| A tag | every bullet carries one (`check_spec_behaviors_are_tagged` green) |
| An issue on every [GAP]/[BROKEN]/[PARTIAL]/[MISSING] | green; the `local.*` behaviours cite #6116 (the parent) until `builder steps` files their own |
| A test or an owed-test note | every moved bullet that named a test file which does not exist now says "an owed test `<file>`"; 35 `dev-workflows.*` rows were missing from the Behaviour tests table and are added; `git.shared-venv` [OK] names a test that exists nowhere and stays in `git-worktree-workflow.md` until one does |
| A "serves" line | the 33 `local.*` behaviours carry one; the 274 absorbed behaviours do NOT: they predate the rule. The report proposes that `local.spec-lint` demands it of new bullets only and that absorbed ones gain it as they are touched |
| A size | sizes are on the steps (S/M/L), not on behaviours; twelve steps are L, which the shape guard flags and `agent-profiles.worker.small` says `builder steps` must split before any brief |
| The build order | nine stages, 28 steps, every `local.*` behaviour in exactly one step; the absorbed build orders are history with demoted headings, so their 165 `dev-workflows.*` ids read as "in no step" to the shape guard (a warning on a DRAFT) |

## 2. Claimed built, and what the code says

- **"Every lane today runs Claude Code; the Pi driver and policy extension exist without a finished adapter."** True. `adapters.py` knows one
  harness (`ClaudeCode`); `pi_rpc.py`, `pi/policy.ts` and the Pi session reader exist and are tested against fixtures; nothing routes a lane
  to them, `harness.toml` has no OpenRouter provider and no price row a Pi model would need. The spec's [PARTIAL] on `adapter.pi` is right.
- **"Stage 7 — land and close: built; closes the issue, marks [OK], re-pins."** Built, but the journal shows the loop runs with the push on
  (`landed` rows carry `pushed`), which contradicts the still-written "nothing pushes except `builder landed --push`, typed by a person" in the
  Builder README's reviewer list. The overturned-rulings table resolves it; the README sentence is now stale and is listed as a residue.
- **"In `harness.toml` both the security rung and the perf rung are report-only."** True in the checkout; the alert rows show why: the perf rung
  refused 12 times ("no pytest-benchmark JSON was written") and the security rung 16 times ("bandit/semgrep/gitleaks not installed on the
  runner", then "the scan printed no SECURITY-RESULT line"). Enforcing either today would block every lane. Step 2.1 and 2.3 are in the right order.
- **"The JSONL journal stays the append-only record; reports are queries."** The journal has no cost row at all (no `usd`, `tokens` or price
  key on any of 93,147 rows); the README's `worker` and `cost` events are not written by the queue path. `ledger.one-row-per-unit` is the first gap
  in § F, and the weekly report's "cost per landed step" cannot be answered until it lands.
- **"`dev-workflows.md` ... 9 [OK], 93 [PARTIAL], 46 [GAP], 16 [PROPOSED], 1 [BROKEN]."** Counted: 165 bullets; the tag counts match.
  `deterministic-conductor.md` has 46 tagged bullets, not 45 (three sit under Open questions). `agent-profiles.md` has 26, not 30.
- **"Rename the `dev-workflows` milestone."** There is no such milestone; the issues sit in `dev-orchestration-harness` (#282). The report says what to do.
- **The handoff.** The spec treats the handoff as "built and in use". It is built (`watcher.py`, `run.py`) and rarely used: seven journal rows
  name one in seventeen days. Steps mostly end by DONE inside one session. `local.handoff-measured` is therefore the first real test of it.

## 3. What cannot be tested as written

- On `local.handoff-per-model`: "each model declares its usable window on this machine" has no measurement procedure; Step 1.2 must say how
  (prompt re-read time at a fixed token count, on the compressed build).
- On `local.worker-sandboxed`: "may write only its worktree and scratch ... reach only the model endpoint" names no probe. The four probes of
  `agent-profiles.isolation.implemented` are the test; the amendment from the cut `local.wall` lists what they must also prove.
- On `local.escalation-triggers`: "repeated tool-call failures" has no number. The journal has the data (`queue` `tell-refused` 191 rows, `gone` three times
  parks today); Step 6.1 sets the number from it.
- On `local.pre-routing`: "recorded local failure rate over half" needs the ledger (Step 3.1) first; the step order says so.
- On `local.question-list`: "risk" is undefined except by `local.must-escalate`; that is enough for a first version and the review says so.
- On `local.release-channels`: "the smoke test passed on a clean machine" — the only smoke machine in `harness.toml` is overnight-only; the step must
  name where a daytime promotion's smoke runs or wait for the night.
- On `local.xcode-worker`: untestable before the Studio; it is in Stage 8 and says "Phase 0 says how that sits with the jail" — answered in the report.
- On `local.interim-16gb`: "nothing built now is machine-specific" is a review rule, not a test; the review lens must carry it.

## 4. What is missing

- A behaviour for the **loop pushing** (the overturned ruling): `local.push-or-nothing-closes` covers the refusal, nothing says the loop pushes
  after READY + green. The Phase 0 amendment on `dev-workflows.tool.landed` should carry it; proposed as the first Stage 3 residue.
- **`harness.toml` drift**: the checkout and the live copy disagree in both directions (the live one still accepts `Directed-By: the maintainer`,
  runs 3 lanes and 3 workers and lists 70 lanes; the checkout has `[nightly]` and the one trailer). Step 1.4 reconciles; no behaviour says the
  live rules file must equal the landed one — proposed as a `local.*` behaviour for the owner.
- **The 981 `check-base-*` scratch trees** (12 GB, none referenced by a running process): `dev-workflows.run.scratch-sweep` [PARTIAL] exists and
  did not sweep them. A residue on that id.
- **Two jcodemunch index processes** have been running as the worker user since 12:41 and 14:12 today; `dev-workflows.run.code-map` [OK] has no
  time bound. A residue.
- **`how-fichero-is-built.md`**, the Manual this spec and four others declare, does not exist (`check_spec_manual_refs` warns). The manual is owed
  before approval.

## 5. The sixteen cuts (question 4)

Each cut `local.*` behaviour repeated an existing id; the existing bullet carries the new sentence as a "Phase 0 amendment" line.

| Cut | Survivor |
|---|---|
| `local.long-running-kept` | `dev-workflows.tool.queue` (and `run.loop*`, `worker.handoff`) |
| `local.handoff-before-compaction` | `dev-workflows.worker.handoff` |
| `local.gates-enforce` | `dev-workflows.quality.security-scan-rung` (perf: `perf-sweep.ratchet.*`) |
| `local.swift-tests-per-batch` | `dev-workflows.run.swift-tests` (with `agent-profiles.ladder.swift-tests`, `ladder.ui-smoke`) |
| `local.wall` | `agent-profiles.isolation.implemented` (with `isolation.baseline`, `run.jail-home`, `security.untrusted-text`) |
| `local.manager` | `agent-profiles.role.manager` |
| `local.shadow-reviewer` | `pipeline.review` |
| `local.bug-hunt-per-milestone` | `dev-workflows.quality.bug-review-stream` |
| `local.issues-close-on-landing` | `issues.harness-closes-after-integration` |
| `local.milestone-closes-when-empty` | `dev-workflows.tool.triage` |
| `local.ci` | `pipeline.github-actions` |
| `local.nightly` | `dev-workflows.run.nightly-build` (with `pipeline.nightly-gate`) |
| `local.one-trailer` | `agent-profiles.trailer.one-line` |
| `local.journal-is-the-record` | `builder-console.store.one-database` |
| `local.report-by-query` | `dev-workflows.ledger.comparison-view` |
| `local.console-reachable` | `dev-workflows.console.tailnet-read-only` (with `console.phone-layout`) |

## 6. Disagreements between the absorbed specs, and how each was resolved

- On `agent-profiles.worker.small` vs `dev-workflows.tool.queue`: read as one step per brief, one session per lane; the diff bound counts per step. The long-running worker wins (owner 2026-11-01).
- On `builder-console.store.one-database` (DuckDB) vs the owner's 2026-11-17 ruling: SQLite; amended on the id.
- On `dev-workflows` push rule vs the loop as run: the loop pushes after READY and a green gate (owner 2026-11-18); the journal row is the record.
- On `pipeline.closes-issues` / `pipeline.issues-and-milestones-kept-current` (conductor) vs `issues.*`: both kept; the `issues.*` text governs.
- On `pipeline.weekly-release` "waits for the maintainer's yes" vs automatic dev builds: kept for alpha, beta and release; dev is automatic.
- On `agent-profiles.role.manager` "supervised by the human manager" vs the supervising manager: amended.
- On `pipeline.github-actions` (conductor, three workflows) vs the live five workflows: the live ones are `claude.yml`, `claude-code-review.yml`,
  `close-fixed-issues.yml` (on push to integration), `issue-milestone.yml`, `worker-image.yml` (on push to main); none runs tests. Step 1.3 adds the test run.
- The Builder README still says "Nothing pushes except `builder landed --push`, typed by a person" and "stdlib only"; both are overturned. Residues.

## 7. Pre-existing reds, unchanged by Phase 0

`check_docs_paths` (29 unaccounted paths, the same set as on `origin/integration`); `check_spec_manual_refs` warns on the missing manual;
`check_spec_build_order_shape` warns on the DRAFT (twelve L steps; the demoted history ids). `test_dev_workflows_spec.py` was red on
`origin/integration` (165 behaviours, 130 table rows) and is green on the branch.
