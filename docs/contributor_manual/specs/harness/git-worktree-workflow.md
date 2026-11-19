# Git / Worktree / GitHub Workflow — Design Spec (#TBD)

> **Status: SUPERSEDED 2026-11-18 (Phase 0 of `building-fichero-locally.md`).** The behaviours this spec still governs (9) were moved into that spec under their existing ids and tags (B (the worktree rules the loop relies on; `git.shared-venv` [OK] stays here because the test it names does not exist)); nothing was deleted and no id was renamed. This file stays so that old links resolve; read `building-fichero-locally.md`. The rest stays here as history: superseded by `dev-workflows` (now in the same spec) or replaced by `builder triage`, `builder steps` and `builder milestone`.

> Milestone: Builder
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

1. **Branch off the right commit, never stale local `main`.** A lane that must see unpushed integration
   commits is made from that branch's HEAD sha (`git worktree add <path> <sha>`); a fresh lane fetches `origin`
   first. `git worktree add … main` branches off whatever local `main` happens to be (stale-code hazard).
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

- (moved) git.one-repo → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.branch-off-origin-main → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.integration-gate → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.commit-never-stash → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.agent-commits-authored-as-claude → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.cleanup-merged-worktrees → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.abandoned-worktree-flagged → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.canonical-checkout-clean → `building-fichero-locally.md` (Phase 0, 2026-11-18)
- (moved) git.updated-via-github → `building-fichero-locally.md` (Phase 0, 2026-11-18)
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

**Ruled 2026-10-04 (design lead, applying the spec's own lean):** the canonical checkout stays a
clean `main` mirror and venv host; all work happens in worktrees (`git.canonical-checkout-clean`).
Yes to a guardrail that flags an `ahead:0`, abandoned lane worktree (`git.abandoned-worktree-flagged`).

Still open: none.
1. ~~Should the canonical checkout (`~/code/fichero`) ever hold uncommitted work, or stay a clean
   `main` mirror + venv host only?~~ **Answered 2026-10-04:** clean mirror.
2. ~~Worth a guardrail asserting no lane worktree is `ahead:0` and abandoned?~~ **Answered
   2026-10-04:** yes, owed as a [GAP].
