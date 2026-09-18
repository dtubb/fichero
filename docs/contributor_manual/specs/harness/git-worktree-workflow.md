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

Retagged 2026-09-18: a spec behavior needs a tag the pipeline can hold it to. Two of these
seven are genuinely source-inspectable (a script's own content proves or disproves the
claim) and now cite a real test. The other five are **CONVENTION** — a human/agent
discipline about how git is used, not a code path — nothing in the repo tree can prove or
disprove them, so tagging them `[OK]` and citing a fake test would be dishonest. See "Marking
a convention" below for the proposed spec-format fix.

- `git.one-repo` — **[CONVENTION]** all worktrees share `~/code/fichero/.git`; only `main`
  pushes to origin. True by definition of `git worktree` (there is only one `.git`, ever) —
  not a code path that could regress independently of git itself.
- `git.branch-off-origin-main` [OK] — lanes branch off fetched `origin/main` via
  `spawn-worker.sh`. Pinned:
  `test_git_worktree_workflow.py::test_spawn_worker_fetches_origin_before_creating_the_worktree`.
- `git.integration-gate` — **[CONVENTION]** multi-lane work gates on `integration` before
  `main`. A manager decision about WHEN to gate, not a code path — `verify_all.sh` runs the
  same way regardless of which branch invokes it.
- `git.commit-never-stash` — **[CONVENTION]** interrupted work is a WIP commit, not a stash.
  A per-agent discipline (this very worker's standing instructions say the same thing) —
  no test can observe whether a human/agent chose to stash.
- `git.cleanup-merged-worktrees` — **[CONVENTION]** merged lanes removed + branch deleted; no
  rot. Describes a manual cleanup step taken after a merge — there is no code path to pin,
  only a habit (the spec's own "open question 2" already proposes a rot-detection guardrail
  as FUTURE work, distinct from testing this convention itself).
- `git.updated-via-github` — **[CONVENTION]** "what's next" comes from milestones/ROADMAP,
  not a shared branch. Describes where a human/agent looks for work — not a code path.
- `git.shared-venv` [OK] — ONE `.venv` at the canonical checkout (`~/code/fichero/.venv`), shared
  by all worktrees; worktrees have none of their own. Correctness comes from
  **`PYTHONPATH=fichero-server/src` relative to the worktree you're in**, which forces that tree's
  source ahead of the venv's editable install (which points at the canonical checkout / `main`).
  Never rely on the bare editable install in a worktree, and never hard-code an absolute
  `~/code/fichero/.venv` path in a doc or script. Per-worktree venvs are the fallback ONLY if the
  PYTHONPATH discipline stops holding (costs a `uv venv + pip install -e` per ephemeral worktree).
  Pinned: `test_git_worktree_workflow.py::test_no_shell_script_hardcodes_the_canonical_venv_path`.

### Marking a convention (proposal, not yet in the spec format)

`spec_pipeline.py`'s tag vocabulary is `OK`/`BROKEN`/`GAP`/`PARTIAL`/`MISSING`/`PROPOSED` —
none of them mean "true by construction / a human discipline, not a code path." Tagging one
of the five above `[OK]` demands a test that cannot exist; leaving them untagged makes them
invisible to the pipeline's own bookkeeping (queue/status never see them at all). Proposal:
add a **`CONVENTION`** tag, exempt from rule (d)'s test-citation requirement the same way an
`[OK]`-tagged behavior with a test is exempt from rule (a)'s issue requirement — a behavior
so tagged states a norm, not a claim about code, and the pipeline should say so rather than
silently drop it or force a fake citation. Used above ahead of that change landing; `check`
currently treats an unrecognized tag word as untagged (skipped, not tracked) — the CD/tool
owner decides whether to add real `CONVENTION` support or use a different existing tag for
this class.

## Rulings + open questions

**Ruling (2026-09-12):** `integration` is a **permanent** long-lived staging branch — lanes merge
into it, it gates, then it merges to `main`, and it persists (its worktree
`~/code/fichero-worktrees/integration` is not torn down per batch).

Still open:
1. Should the canonical checkout (`~/code/fichero`) ever hold uncommitted work, or stay a clean
   `main` mirror + venv host only? (Lean: clean mirror — all work happens in worktrees.)
2. Worth a guardrail asserting no lane worktree is `ahead:0` and abandoned (auto-flag rot)?
