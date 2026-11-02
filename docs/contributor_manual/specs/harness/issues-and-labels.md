# Issues, milestones, labels and the order of work — Design Spec (#6116)

> Milestone: dev-workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — the contributor section says where work is recorded (GitHub)
> and how the harness picks the next thing.

> **Status: DRAFT — awaiting the owner's approval (written 2026-11-01 from the owner's rulings of that evening).**
> Tags: [OK] built · [PARTIAL] exists, not wired · [GAP] not built · [PROPOSED] decided here, not yet ruled.
> Scope with other specs: `harness/dev-workflows.md` owns the verbs (`builder milestone`, `steps`, `landed`, `triage`,
> `queue`); this spec owns what those verbs read and write on GitHub. `specs/_TEMPLATE.md` and
> `specs/_MILESTONE_TEMPLATE.md` point here instead of repeating it; AGENTS.md "Where state lives" points here.

## Intent

GitHub is the record of work: an issue is a thing to do, a milestone is a spec's worth of things, a label says how an
issue is ordered and what kind it is. The harness keeps all three current on its own, after its own test and
integration; a person never closes, labels or files by hand except to overrule. Anyone, human or model, can answer
"what is next" from GitHub alone, in one listing, with no vibes.

## The three records

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

## How the harness picks the next thing

In the first unfinished milestone of the build-order file: the lowest open `step:N.M` whose `Depends on` steps have
landed; then open `type:bug` issues in the milestone by priority; then the rest by priority. Across milestones,
never: it finishes one before the next, which is also the Studio's constraint (one worker).

## What the harness writes, and when

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

## Behaviors

- `issues.milestone-is-the-spec` [PARTIAL] (#6336) — every open issue sits in the milestone its spec names; `check_spec_milestones.py` binds spec↔milestone today, nothing yet moves issues. Test: fichero-server/tests/unit/workflows/test_triage_tool.py → #6116
- `issues.label-set-is-closed` [PARTIAL] (#6336) — only the labels in the table exist; the one-off consolidation was done by hand 2026-11-01 (70 → 48); triage refuses an unknown label. Test: fichero-server/tests/unit/workflows/test_triage_tool.py → #6116
- `issues.build-order-file-orders-milestones` [PARTIAL] (#6336) — the harness briefs only the first unfinished milestone of `specs/build-order.md`. Test: fichero-builder/tests/test_milestone_verb.py → #6116
  Built 2026-11-02: the owner's reorder from the console is `builder order` (tests `fichero-builder/tests/test_order_verb.py::test_rewrite_renumbers_parks_and_unparks_keeping_each_lines_text`, `::test_save_commits_on_the_build_order_branch_queues_a_tiny_batch_and_refuses_while_one_is_saving`).
- `issues.pick-order-step-bug-priority` [GAP] — within a milestone: steps in build order, then bugs, then priority. Test: fichero-builder/tests/test_milestone_verb.py → #6116
- `issues.harness-closes-after-integration` [OK] (#6337) — an issue closes only by `builder landed` once its commit is on origin/integration. Test: fichero-builder/tests/test_landed_verb.py → #6116
- `issues.spec-less-milestone-gets-a-spec-issue` [PARTIAL] (#6336) — Test: fichero-server/tests/unit/workflows/test_triage_tool.py → #6116

## Test matrix

| Behaviour | Test | Status |
|---|---|---|
| milestone-is-the-spec | test_triage_tool.py | to write |
| label-set-is-closed | test_triage_tool.py | to write |
| build-order-file-orders-milestones | test_milestone_verb.py | to write |
| pick-order-step-bug-priority | test_milestone_verb.py | to write |
| harness-closes-after-integration | test_landed_verb.py | to write |
| spec-less-milestone-gets-a-spec-issue | test_triage_tool.py | to write |

## Build order

### Stage 1 — the record

#### Step 1.1 — the build-order file and the pick order (#6116)
- Behaviours: `issues.build-order-file-orders-milestones`, `issues.pick-order-step-bug-priority`
- Tests: fichero-builder/tests/test_milestone_verb.py
- Size: S

#### Step 1.2 — landed closes and comments (#6116)
- Behaviours: `issues.harness-closes-after-integration`
- Tests: fichero-builder/tests/test_landed_verb.py
- Depends on: 1.1
- Size: S

#### Step 1.3 — triage (#6116)
- Behaviours: `issues.milestone-is-the-spec`, `issues.label-set-is-closed`, `issues.spec-less-milestone-gets-a-spec-issue`
- Tests: fichero-server/tests/unit/workflows/test_triage_tool.py
- Depends on: 1.2
- Size: M

## Rulings

- Owner 2026-11-01: one lane at a time; the harness closes issues, never a person; milestone = spec; labels are
  step, kind and priority; pick order steps → bugs → priority; the order of milestones is written down, not vibes.

## Open questions

1. Does `priority:` survive once every spec has a build order, or is it only for the ops buckets? [PROPOSED: keep]
2. The `phase:R*` labels: removed when the wide-onboarding build order carries the recipe phases, or kept as a second key? [PROPOSED: removed]
