# Spec Pipeline — Design Spec (#TBD)

> **Status: SUPERSEDED 2026-11-18 (Phase 0 of `building-fichero-locally.md`).** The behaviours this spec still governs (18) were moved into that spec under their existing ids and tags (B2 (the spec ↔ issues ↔ tests check) and the two triaged issues); nothing was deleted and no id was renamed. This file stays so that old links resolve; read `building-fichero-locally.md`. The rest stays here as history: superseded by `dev-workflows` (now in the same spec) or replaced by `builder triage`, `builder steps` and `builder milestone`.

> Milestone: Builder
> Manual: TBD — contributor-facing only; the user manual needs nothing (this is how the
> agent team works, not a user-visible surface).

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval before code is treated as final.**
> The state machine itself already exists (`scripts/spec_pipeline.py` +
> `fichero-server/tests/unit/scripts/test_spec_pipeline.py` +
> `scripts/spec_pipeline_baseline.json`); this spec stays DRAFT until the creative director
> rules on the milestone-priority seed and the orphan-issue strictness default, both called
> out in Open questions below.
>
> Tags: **[OK]** built and tested by name below · **[MISSING]** not built.

## Intent (the design)

The development pipeline — agent-work note → spec → milestone + issues → issue hygiene →
issue to worker → review → test pinned to spec → retag — happens today because someone
remembers each hand-off. `scripts/spec_pipeline.py` turns it into a state machine: it reads
every spec behavior, cross-checks it against GitHub issues and the test tree in one batched
fetch, and prints the illegal states instead of leaving them to be noticed. `queue` and
`brief` turn a clean state into a mechanical dispatch step, so the manager agent can drive
the loop without re-deriving "what's next" by hand each time.

This is deliberately a companion to, not a replacement for, the three existing guardrails
(`check_spec_milestones.py`, `check_specs_have_tests.py`, `check_spec_manual_refs.py`,
`check_spec_broken_has_issue.py`). Those stay in the gate — offline, deterministic, run on
every commit. `spec_pipeline.py check` is broader (it needs two live GitHub calls — issues
and milestones) and is run by hand as a dispatch step, not wired into `verify_all.sh`.

`check` is a **baseline ratchet**, not a green/red gate on the whole backlog: today's tree
has hundreds of pre-existing illegal states (mostly legacy `[OK]` behaviors written before
this script's "cite the test name in backticks" convention existed, and dozens of GitHub
milestones that predate spec-per-milestone discipline). `check --update-baseline` accepts
that debt into `scripts/spec_pipeline_baseline.json` once; from then on, plain `check` fails
only on a NEW illegal state, or on a baselined one that quietly stopped occurring (fixed but
not removed — the list can only shrink, so a shrink has to be deliberate). This is the same
contract `check_spec_broken_has_issue.py`'s `GRANDFATHERED_FILES` and the coverage ratchet
already use for exactly this kind of "we know about this, don't let it grow" debt.

## Prior art / best practices

This is closest to a lightweight **workflow/state-machine engine** (think a lint rule +
Jira-hygiene bot combined) rather than anything DH/NLP-specific — the surface being modelled
is the team's own process, not archival content. The design borrows directly from the
existing guardrail scripts' shape (stdlib-only, `gh` via subprocess, one-line OK/FAIL
summaries, offline-safe by default) rather than inventing a new convention. It reuses
`check_spec_broken_has_issue.py`'s behavior-block parser by import rather than duplicating a
second markdown-bullet parser — one parser, one bug surface.

## Behaviors

- (moved) pipeline.status → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-a-broken-needs-issue → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-b-stale-tag-closed-issue → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-c-milestone-mismatch → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-d-ok-needs-real-test → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-e-ok-needs-closed-issue → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-f-orphan-open-issue → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-g-milestone-spec-mirror → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-g-scope → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-g-non-spec-allowlist → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.rule-h-convention-governance → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.offline-blind-not-green → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.gh-failure-exits-2 → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.missing-specs-dir-exits-2 → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.baseline-ratchet → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.check.update-baseline → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- `pipeline.queue.deterministic-order` — **[OK]** the queue orders by
  (milestone priority from the `MILESTONE_PRIORITY` seed list, then alphabetical), then tag
  severity (BROKEN before PARTIAL before GAP/MISSING), then spec path/line — same inputs,
  same output, every run. Pinned by `test_spec_pipeline.py::test_queue_orders_by_milestone_priority_then_tag_severity`.
- `pipeline.queue.only-open-unclaimed` — **[OK]** the queue excludes behaviors whose cited
  issue is CLOSED or already claimed (has an assignee or the `status:in-progress` label).
  Pinned by `test_spec_pipeline.py::test_queue_excludes_claimed_and_closed_issues`.
- `pipeline.queue.json-and-limit` — **[OK]** `--json` emits the same items as structured
  data; `--limit N` truncates after sorting. Pinned by
  `test_spec_pipeline.py::test_queue_orders_by_milestone_priority_then_tag_severity` (uses `--json`),
  `test_spec_pipeline.py::test_queue_limit_truncates_after_sorting`.
- `pipeline.queue.kind-retag` — **[OK]** `queue --kind retag` lists rule (b)/(d)/(e) findings
  — DOC-fixable debt (find/cite a pinning test, or reopen/close a mistagged issue) — grouped
  by spec, distinct from the default `--kind code` dispatch queue. A docs lane clears these
  in bulk without touching the code-work queue's ordering. Pinned by
  `test_spec_pipeline.py::test_queue_retag_lists_rule_b_and_d_grouped_by_spec`, `test_spec_pipeline.py::test_queue_default_kind_is_code`.
- `pipeline.brief.renders-full-context` — **[OK]** `brief <id>` prints the behavior text, its
  spec path:line, its cited issue + title, the standing worker rules (no xcodebuild/gate/
  commit, never bare git stash, `swiftc -parse` + `-typecheck`, one-literal test messages,
  `Self.`-qualified statics, PYTHONPATH for pytest), the test it must ship, the retag
  instruction, and the claim command. Pinned by `test_spec_pipeline.py::test_brief_renders_behavior_issue_and_rules`.
- `pipeline.brief.unknown-id-fails` — **[OK]** briefing an id that matches no behavior prints
  a clear failure and exits 1. Pinned by `test_spec_pipeline.py::test_brief_unknown_behavior_fails`.
- `pipeline.agent-work.triage` — **[OK]** every `agent-work/**/*.md` file is classified
  FOLDED (a spec's body references its path or filename), HISTORICAL (a
  `Status: HISTORICAL` / leading `HISTORICAL` marker), or UNTRIAGED; counts + the UNTRIAGED
  list print, INFO only, never fails. Pinned by
  `test_spec_pipeline.py::test_agent_work_triages_folded_historical_untriaged`,
  `test_spec_pipeline.py::test_agent_work_missing_dir_is_info_only`.
- `pipeline.not-in-gate` — **[OK]** the script is named `spec_pipeline.py`, not
  `check_*.py`, so `verify_all.sh`'s auto-discovery of `check_*.py` scripts never picks it up
  — a network-dependent check cannot silently enter the offline gate. Pinned by
  `test_spec_pipeline.py::test_script_name_does_not_match_verify_all_check_glob`
  (`fnmatch` against the exact `scripts/check_*.py` pattern `verify_all.sh` uses);
  `verify_all.sh`'s own discovery logic is covered by its existing tests.

## The state table

| State | What must be true | Which check enforces it |
|-------|--------------------|--------------------------|
| Behavior filed | broken/gap/partial/missing behavior cites `#N` | `check` rule (a) |
| Tag matches issue | broken-family tag ⇒ issue still OPEN | `check` rule (b) |
| Issue on right milestone | a PLAIN `#N` citation's milestone == spec's `Milestone:` (arrow citations exempt) | `check` rule (c) |
| OK is proven | `[OK]` cites a test that exists | `check` rule (d) |
| OK is landed | `[OK]`'s cited issue is CLOSED | `check` rule (e) |
| Milestone fully cited | every OPEN issue on a spec's milestone is cited by some behavior | `check` rule (f), INFO / `--strict` |
| Milestone ↔ spec mirrored | a live (not dead-closed), non-allowlisted GH milestone has a spec; spec's milestone exists on GH | `check` rule (g) |
| Non-spec milestone allowlist is honest | an allowlisted milestone still exists, has no spec, and carries a reason | `check` rule (g), `scripts/spec_pipeline_non_spec_milestones.json` |
| Convention tag is guarded | `[CONVENTION]` lives under `specs/harness/`, carries a reason clause, and its count only grows via a deliberate re-baseline | `check` rule (h) |
| No new debt | today's illegal-state set == baseline, modulo a shrink | `check` baseline ratchet |
| Ready to dispatch | broken-family, OPEN, unclaimed issue | `queue` (default `--kind code`) |
| Worker briefed | queue item rendered with rules + retag instruction | `brief` |
| Doc debt clearable in bulk | rule (b)/(d)/(e) findings, grouped by spec | `queue --kind retag` |
| Retagged | worker flips `[OK]`, cites the test; manager adds the sha | manual step, not automated (see below) |
| Baseline is current | `check` is green against `scripts/spec_pipeline_baseline.json` | `check must be green against the baseline before dispatch` (loop step 1) |

## The manager loop (numbered steps)

1. **check must be green against the baseline before dispatch** —
   `python scripts/spec_pipeline.py check` (add `--strict` to also fail on orphan issues).
   Green here means "no NEW debt, nothing baselined silently fixed" — it does NOT mean the
   backlog in `scripts/spec_pipeline_baseline.json` is empty. Fix every NEW illegal state it
   prints, or remove a stale baseline entry it flags, before dispatching from a dirty state.
2. **queue** — `python scripts/spec_pipeline.py queue --limit N` for the next batch of CODE
   work, or `--milestone <name>` to stay inside one surface; `queue --kind retag` for the
   DOC-fixable (b/d/e) batch a docs lane can clear separately.
3. **brief** — `python scripts/spec_pipeline.py brief <behavior-id>` for each item; send the
   printed brief to a worker.
4. **dispatch** — the worker claims the issue (`gh issue edit N --add-label
   status:in-progress`, printed by `brief`) and implements the pinning test.
5. **verify at tree** — the worker runs the test/build steps its brief specifies; no gate,
   no commit from inside the worker unless told otherwise.
6. **gate** — the manager runs the full verify gate on the integrated change.
7. **commit** — the manager commits (worker output is reviewed, not committed blind — see
   MEMORY `commit-only-workers-produce-noncompiling-code`).
8. **retag** — the spec line flips to `[OK]`, cites the test name; the manager adds the
   landing commit sha.
9. **check again** — confirms the retag didn't introduce a new illegal state (e.g. rule e:
   an `[OK]` citing a still-OPEN issue because the issue wasn't closed yet), and run
   `check --update-baseline` to shrink the baseline by the entries just fixed (never to
   absorb new debt — only right after fixing something).

## What is deliberately NOT automated

- **Creative-director rulings** — what a behavior should say, which milestone it belongs to,
  whether a gap is worth fixing at all. The pipeline only checks that decisions already made
  are consistently recorded; it does not make design decisions.
- **Review of diffs** — `check` proves a test exists and its issue is closed; it does not
  read the diff or judge whether the fix is correct. That's the manager's/reviewer's job.
- **Choosing between competing designs** — when two specs could both claim a behavior, or a
  milestone's scope is ambiguous, this script has no opinion; it only enforces the anchors
  once they're declared.
- **Milestone/issue creation** — `check` rule (g) reports a missing milestone or an
  uncited issue; it never creates or closes anything. All mutation (`gh issue edit
  --add-label`) happens explicitly, printed for a human/worker to run, never auto-executed.
- **Baseline shrinking** — `--update-baseline` is a deliberate command a human/manager runs
  right after fixing something; the script never shrinks the baseline on its own, and never
  runs `--update-baseline` implicitly from plain `check`.

## Open questions for the creative director

1. `MILESTONE_PRIORITY`'s seed order (modes-to-panes, panes-workspaces, workflows, research,
   automation, kg-tables, kg-entity-inspector, kg-readable-representation, ui-test-harness,
   ui-testing-strategy) was given verbatim in the dispatch brief — ratify as-is, or reorder?
2. **Answered** (design lead 2026-10-04, applying the spec's lean): Yes, the daily check runs strict once the backlog is worked down. Rule (f) (orphan open issues) defaults to INFO, `--strict` promotes to failure. Should the
   manager's daily `check` run with `--strict` by default once the real-tree backlog (see the
   first real run below) is worked down, or stay INFO indefinitely?
3. Every rule-c/d/f/g fixture test now exists; no `[MISSING]` behaviors remain in this spec.
4. **Answered** (design lead 2026-10-04, by the existing design): Rule (g) keeps its shrink-only baseline plus the allowlist whose entries need reasons (`scripts/spec_pipeline_non_spec_milestones.json`), so it is not strict-only. The baseline seeded from the real tree (2026-09-18) carries 354 illegal states, 138 of
   them rule (g) — GitHub milestones (of 156 total) that predate spec-per-milestone
   discipline and legitimately have no spec (`audit_spec_milestone_manual.py` already
   surfaces this same backlog as an audit). Is baselining all 138 at once acceptable, or
   should rule (g) start `--strict`-only (INFO by default, like rule f) until that backlog is
   triaged down?

## First real run against the tree (2026-09-18, not fixed — reported as found)

`check --update-baseline` seeded `scripts/spec_pipeline_baseline.json` with 354 illegal
states (b=4, c=33, d=175, e=4, g=138) across 372 tagged behaviors in 26 specs; plain `check`
is green against that baseline. `queue --limit 15` and `queue --kind retag` were also run
against the real tree; illegal states and debt found are pipeline backlog to work down via
`queue`/`brief`, not bugs in this script. See the worker's report for the full pasted output.

## Triaged from the backlog (2026-10-04)
- (moved) spec.absent-tags-agree-with-tests → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) pipeline.github-hygiene-milestones-labels-needs-your-test → `building-fichero-locally.md` (Phase 0, 2026-11-18)
