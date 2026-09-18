# Git / Worktree / GitHub Workflow — Design Spec (#TBD)

> Milestone: git-worktree-workflow
> Manual: docs/contributor_manual/guide/10-setup-and-day-to-day-development.md
>
> Design-led. **Status: DRAFT — for the design lead's review.** How the repo, the worktrees, and GitHub fit
> together — so it's ONE tracked repo, clear, and nothing lives outside git. Grounded in the actual
> layout (`git worktree list`, 2026-09-12).

## Intent

There is **one git repository** and one GitHub remote. Everything is tracked and reaches GitHub
through `main`. The several on-disk directories are not separate repos — they are **worktrees**:
cheap, ephemeral working copies of the same repository, each checked out on a different branch,
all sharing one history and one object store. A reader should never wonder "is this in git?" — it
always is; only *which branch/worktree* differs.

## The layout (verified 2026-09-12)

| Path | Branch | Role |
|------|--------|------|
| `~/code/fichero` | `main` | **Canonical checkout.** Holds the real `.git` (the shared common dir). On `main`; this is what pushes to `origin`. Holds the `.venv`. |
| `~/code/fichero-worktrees/integration` | `integration` | Where combined multi-lane work is assembled + gated before `main`. |
| `~/code/fichero-worktrees/<lane>` | `<lane>` | A worker's isolated worktree, branched off `origin/main`, one milestone's work. Ephemeral. |
| `~/code/fichero-worktrees/release-merge`, `.gate-snapshots/*` | detached | Release/gate infrastructure worktrees. |

- **One repo:** `git rev-parse --git-common-dir` → `~/code/fichero/.git` from every worktree. One
  history, one `origin` (`github.com/dtubb/fichero`).
- **"Can it all be in `~/code/fichero` and pushed to GitHub?"** — it already is. The worktree
  *directories* aren't tracked files (they're checkouts), but every *commit* made in any worktree
  lives in the shared object store and lands on GitHub the moment it reaches `main`.

## The process (add work → keep updated → land)

1. **Branch off `origin/main`, never stale local `main`.** `scripts/spawn-worker.sh` fetches first
   and creates the worktree off `origin/main` — hand-rolling `git worktree add … main` branches off
   whatever local `main` happens to be (stale-code hazard).
2. **Work in the lane worktree.** Commit, never `git stash` (a stash doesn't survive a worktree
   teardown and is invisible outside its shell — park interrupted work as a WIP commit).
3. **Integrate.** When 2+ lanes must land together, merge them into the `integration` branch and
   gate the combined diff there (`verify_all`, 0 failed). A single lane can gate on its own branch.
4. **Land on `main` + push.** Fast-forward `main` to the gated commit and `git push origin main`.
   `main` is the only branch that reaches GitHub as the source of truth.
5. **Keep updated:** workers pull "what's next" from **GitHub milestones + `agents/ROADMAP.md`**,
   not a long-lived shared branch; they re-branch off fresh `origin/main`. Never keep several agents
   rebasing one branch (the failure mode this replaces).
6. **Clean up.** Merged lane → `git worktree remove` (never `rm -rf` a sibling) + `git worktree
   prune` + delete the lane branch. Its commits stay reachable by SHA / `git log --grep '(#N)'` /
   the closed issue. Keep only worktrees with an active worker or genuinely unintegrated commits.

## Behaviors

Retagged 2026-09-18: a spec behavior needs a tag the pipeline can hold it to. `spec_pipeline.py`
now recognizes `CONVENTION` as a real tag (rule h): each one is a tracked ledger entry under
a shrink-only baseline ceiling, allowed only in `specs/harness/`, and must carry a reason
clause (enforced — see "Marking a convention" below). Every behavior was challenged (per
creative-director instruction): is it REALLY untestable, or just currently untested? Four of
these seven turned out to be source-inspectable or cheaply script-checkable and now cite a
real test (two were already that way; a second pass moved `git.commit-never-stash` and
`git.cleanup-merged-worktrees` OFF `CONVENTION` once their proposed guardrails were built —
running the second one for real even found a genuine violation, not just a theoretical one).
The other three stay **CONVENTION** — a human/agent discipline about how git is used, not a
code path — nothing in the repo tree can prove or disprove them.

- `git.one-repo` — **[CONVENTION]** all worktrees share `~/code/fichero/.git`; only `main`
  pushes to origin. True by definition of `git worktree` (there is only one `.git`, ever) —
  not a code path that could regress independently of git itself. Challenged: a script
  COULD run `git rev-parse --git-common-dir` from every worktree and assert they agree, but
  that's checking git's own invariant, not this repo's discipline — stays CONVENTION.
- `git.branch-off-origin-main` [OK] — lanes branch off fetched `origin/main` via
  `spawn-worker.sh`. Pinned:
  `test_git_worktree_workflow.py::test_spawn_worker_fetches_origin_before_creating_the_worktree`.
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
- `git.updated-via-github` — **[CONVENTION]** "what's next" comes from milestones/ROADMAP,
  not a shared branch. Describes where a human/agent looks for work — not a code path.
  Challenged: no artifact in the repo records WHERE an agent looked for its next task, so
  there is nothing to assert against — stays CONVENTION.
- `git.shared-venv` [OK] — ONE `.venv` at the canonical checkout (`~/code/fichero/.venv`), shared
  by all worktrees; worktrees have none of their own. Correctness comes from
  **`PYTHONPATH=fichero-server/src` relative to the worktree you're in**, which forces that tree's
  source ahead of the venv's editable install (which points at the canonical checkout / `main`).
  Never rely on the bare editable install in a worktree, and never hard-code an absolute
  `~/code/fichero/.venv` path in a doc or script. Per-worktree venvs are the fallback ONLY if the
  PYTHONPATH discipline stops holding (costs a `uv venv + pip install -e` per ephemeral worktree).
  Pinned: `test_git_worktree_workflow.py::test_no_shell_script_hardcodes_the_canonical_venv_path`.

### Marking a convention (built, 2026-09-18 — `spec_pipeline.py` rule h)

`spec_pipeline.py`'s tag vocabulary was `OK`/`BROKEN`/`GAP`/`PARTIAL`/`MISSING`/`PROPOSED` —
none of them meant "true by construction / a human discipline, not a code path." Tagging one
of the five above `[OK]` demands a test that cannot exist; leaving them untagged made them
invisible to the pipeline's own bookkeeping (queue/status never saw them at all). Built:
`CONVENTION` is now a real tag, exempt from rule (d)'s test-citation requirement the same
way an `[OK]`-tagged behavior with a test is exempt from rule (a)'s issue requirement — a
behavior so tagged states a norm, not a claim about code. Guarded (rule h), so it can't
become a silent escape hatch from "cite a test":
- **counted separately** — `status`'s per-spec table has its own `CONVENTION` column;
  `check`'s summary breaks illegal-state counts down `by rule`, so `h` is visible on its own.
- **location-gated** — allowed only in a spec under `docs/contributor_manual/specs/harness/`
  (a process/harness spec); used anywhere else, it's its own rule-h finding — CONVENTION is
  for how the team/agents work, not a way to skip testing a product behavior.
- **reason-gated** — a `[CONVENTION]` bullet with no explanation of why no test can pin it is
  its own rule-h finding (a cheap keyword check — see `CONVENTION_REASON_RE` in
  `spec_pipeline.py` — this checks a reason is PRESENT, not that it's good; a human still
  reads it).
- **shrink-only ceiling** — every `[CONVENTION]` behavior, even a fully compliant one, is
  itself a tracked rule-h "ledger" finding, so the CURRENT count of conventions becomes the
  baseline ceiling exactly like every other rule here; a NEW convention tag anywhere fails
  `check` until someone runs `check --update-baseline` to deliberately accept the raised
  count — CONVENTION can't quietly proliferate.
Pinned: `docs/contributor_manual/specs/harness/spec-pipeline.md`'s own behaviors cite the
fixture tests for all three checks (registration, location, reason) plus the shrink-only
ceiling behavior.

## Rulings + open questions

**Ruling (2026-09-12):** `integration` is a **permanent** long-lived staging branch — lanes merge
into it, it gates, then it merges to `main`, and it persists (its worktree
`~/code/fichero-worktrees/integration` is not torn down per batch).

Still open:
1. Should the canonical checkout (`~/code/fichero`) ever hold uncommitted work, or stay a clean
   `main` mirror + venv host only? (Lean: clean mirror — all work happens in worktrees.)
2. Worth a guardrail asserting no lane worktree is `ahead:0` and abandoned (auto-flag rot)?
