# Fabel Review: Git Practices for the Manager + Agent Workflow

**Status:** proposal — review-only, no live docs edited. Daniel approves before
`AGENTS.md` / `agents/skills/session-start-manager/SKILL.md` / `agents/prompts/manager-loop.md`
/ `agents/prompts/worker-loop.md` are touched.

**Scope:** this reviews branch/worktree/commit/stash practice only — not
release process, not the OpenAPI/Pydantic discipline, not build gating content
(those already have their own sections in `AGENTS.md`).

## What already exists (read before drafting this)

- `AGENTS.md` rule 7: never per-task branches — commit to the milestone branch
  directly. Rule 11: worktrees ONLY under `~/code/fichero-worktrees/<name>`,
  create with `git worktree add … -b <branch> main`, remove with
  `git worktree remove --force`, never `rm -rf` a `~/code/` sibling.
- `AGENTS.md` "Commit Attribution": each agent commits as itself; committer
  stays the human; `Directed-By: Daniel Tubb`.
- `AGENTS.md` "Verification (`verify_all`)": `--fast` / `--standard` / `--full`
  tiers; "Parse the summary — merge only on **0 failed**."
- `agents/skills/dispatch-worker/SKILL.md`: worker worktrees come from
  `scripts/spawn-worker.sh`, branch off **`origin/main`** (never stale local
  `main`), workers are **commit-only** (never pytest/xcodebuild), manager
  build-verifies + gates + merges via PR, then `git worktree remove --force` +
  `git branch -D <branch>`.
- `agents/prompts/manager-loop.md`: manager merges a worker's lane into
  `~/code/fichero-worktrees/integrate` (never Daniel's own checkout), gates
  from the repo root, fast-forwards to main on green, resets the worker's
  worktree to new main only after confirming 0 uncommitted + 0 unmerged.
- `agents/prompts/worker-loop.md`: worker drains a milestone in a commit-loop,
  step 4 says explicitly "**Commit only** — NEVER build, NEVER run the full
  suite."

The workflow below is already implicit in these four files. It has never been
written down end-to-end in one place, and none of the five failure-modes below
have a named rule anywhere — they were each hit as an incident this session
and fixed ad hoc. This review's job is to make the implicit workflow explicit
and turn each incident into a standing rule.

---

## (a) The recommended workflow, end to end

```
origin/main
   │
   ├── lane branch (short-lived, one worker, one milestone or issue-slice)
   │     └── isolated worktree: ~/code/fichero-worktrees/<name>
   │           worker drains issues in a commit-loop, never builds/tests
   │
   ├── lane branch  ─┐
   ├── lane branch  ─┤──▶ merge into an INTEGRATION branch
   ├── lane branch  ─┘     (e.g. feature/research-and-hygiene, "batch")
   │                       manager gates the WHOLE batch here:
   │                       verify_all.sh --standard|--full, 0 failed
   │
   └────────────────────────  fast-forward integration → main  (only on green)
                                delete merged lane branches (commits already live
                                in main; the branch pointer was scaffolding)
```

**Lane branch + worktree.** One worker = one branch = one worktree, always
under `~/code/fichero-worktrees/<name>`, always branched off **`origin/main`**
(fetch first — never stale local `main`). This is already rule 11 and the
dispatch-worker HARD rules; this review adds nothing here except naming it
"lane branch" consistently so it's not confused with a long-lived feature
branch.

**Integration branch.** When 2+ lanes need to land together before hitting
`main` (a batch, e.g. `integrate/launch` seen in this repo's current history),
the manager merges each lane into that integration branch and gates the
*combined* diff — not each lane in isolation. A lane can pass its own
`--fast` check and still break another lane's guardrail once merged (path-keyed
guardrails, see rule 4 below); the integration branch is where that surfaces.
Fast-forward `main` only when the full suite reports 0 failed on the
integration branch's HEAD.

**Delete merged lane branches.** Once a lane's commits are in `main` (or the
integration branch that itself reached `main`), delete the lane branch.
Nothing is lost — the commits live on in `main`'s history, reachable by SHA,
`git log --grep`, and the GitHub issue's "closed by" link. A long-lived lane
branch left around only invites someone to keep committing to stale state or
to accidentally branch a new worker off it instead of `origin/main`.

**Bringing an agent up to speed without long-lived branches.** The repo
already has the tools for this and should keep using them instead of a
drifting long-lived branch as tribal memory:
- Per-area `*_STATUS.md` / fabel-review docs (like this one) — durable,
  point-in-time state a fresh agent can read in one pass.
- GitHub issue milestones — `agents/ROADMAP.md` + `scripts/choose_next.py`
  already encode "what's next" as data, not branch state.
- Conventional-commit scopes — `git log --grep '(#1234)'` or
  `git log --oneline --grep 'feat:'` recovers "what happened and why" without
  needing to have been on the branch when it happened.

A long-lived branch that several agents keep rebasing onto is the opposite of
this: it drifts, nobody remembers which commits are "really" merged, and a
fresh agent can't tell branch state from `main` state without asking.

---

## (b) Commit vs. stash

**Commit early, commit often, on the lane branch.** A worker mid-slice that
needs to context-switch (blocked, needs a different file, session ending)
should make a **WIP commit** on its own lane branch, not `git stash`. The
commit is:
- visible to the manager (`git log`, `notify_manager.sh` can reference the sha)
- safe across a worktree being reset, torn down, or re-entered by a different
  session
- reviewable and revertible with normal git tools

**Never park real work in `git stash`.** A stash is invisible to anyone but
the shell that made it, doesn't survive a `git worktree remove`, and is
already a named hazard in this repo's memory: a bare `git stash pop` mid
"checkout-dance" (switching branches/worktrees to compare state) silently
clobbered work because the pop landed on the wrong branch/tree state ("Baseline-diff
stash-pop hazard" — baseline-diffing must happen in a **separate worktree**,
never via stash-and-switch in the same one). If a diff must be temporarily set
aside to look at a clean tree, use a second worktree (already the pattern for
baseline-diffing) or a WIP commit + `git reset --soft` later — not stash.

---

## (c) Failure-modes hit this session, each as a named rule

### Rule G1 — Verification must run in the foreground before a worker's turn ends

**What happened:** a commit-only worker (hit 3× this session — envelope
rework, routes-reorg, routes-finish) launched its own verification as a
**background** process plus a `Monitor`, then ended its turn waiting for the
result. The turn boundary landed before the background job finished, so the
worker never saw pass/fail and never committed — it just looped, re-launching
the same check next turn.

**Rule:** a worker (or any agent whose job is "verify then commit") runs its
own verification **in the foreground, blocking**, and commits in the **same
turn** it saw the result. Never background the gate-check and then pause —
if the result isn't known before the turn ends, there is nothing to commit on,
and the agent burns a full turn doing nothing. (This is distinct from the
manager's own use of `Monitor` on `~/.fichero-manager-inbox` to react to
*other* agents' signals — that pattern is fine because the manager isn't
blocked on the file it's watching.)

### Rule G2 — Lanes own disjoint files; verify provenance before trusting a commit

**What happened:** two workers editing overlapping files/import-sites
collided (already partially covered by dispatch-worker's "PARTITION BY
FILE-SET" rule). Separately, a concurrent process landed an unrelated file
*move* bundled inside a doc commit — i.e. a commit's message didn't match its
actual diff, and that was only caught by inspection.

**Rule:** lanes own disjoint files, predicted with `get_blast_radius` /
`find_importers` *before* fan-out (already documented in dispatch-worker —
this review just names it as a git-practices rule too, since the enforcement
mechanism is git: non-overlapping paths per branch). Additionally: before
trusting a commit's provenance (whose lane it came from, what it's supposed to
contain), run `git show --stat <sha>` and confirm the file list matches the
commit message's claim — don't assume a docs-scoped commit only touched docs.
When a collision does slip through, the worker that *wrote* the code
reconciles it (already stated in `session-start-manager/SKILL.md` §Dispatch
Rules) — the manager does not blind `git checkout --theirs` a test file whose
semantics it can't verify.

### Rule G3 — A worktree-isolated subagent needs to branch from the integration HEAD, not `origin/main`, when it must build on un-pushed state

**What happened:** a subagent launched with `isolation: "worktree"` couldn't
reproduce a failure because that isolation mode branches from
`origin/<default-branch>` — i.e. `origin/main` — by default. When the fix
needed to build on commits that exist only on an un-pushed integration branch
(the batch HEAD), the subagent's worktree simply didn't have those commits.

**Rule:** when a task requires building on integration-branch state that
hasn't reached `origin/main`, don't rely on the Agent tool's default
worktree isolation. Instead: create a worktree from the batch's HEAD sha
explicitly (`git worktree add <path> <integration-branch-or-sha>`, following
the same `~/code/fichero-worktrees/<name>` placement + `git worktree remove
--force` cleanup as every other worktree) and point the agent there via
`EnterWorktree { path: ... }` or an explicit `cwd`. State this explicitly in
the dispatch brief whenever the task depends on integration-only commits —
don't assume the default isolation mode covers it.

### Rule G4 — Path-keyed guardrails move in the same commit as the file they guard, and their test files are part of the gate

**What happened:** several of this repo's guardrail scripts
(`PERSISTENCE_PATH`, `WILDCARD_BIND`, the XML chokepoint check, `db_access`,
`single_connection`, and the `TARGET_FILES` lists inside `scripts/check_*.py`)
hardcode file paths. Any move or rename that doesn't update those allowlists
in the same commit leaves the guardrail either silently blind (checking a path
that no longer exists) or falsely red (checking the old path against new
content). This is a known-recurring class — "renames/moves/comment-edits
break path-keyed guardrails" cost 7 regressions from #3751/#3754 in this
repo's history.

**Rule:** any commit that moves, renames, or splits a file must, in the SAME
commit, grep for that path across `scripts/check_*.py` (all `TARGET_FILES`-
style constants) and update it. This is not optional cleanup — a green
`--fast` gate on a commit that broke a guardrail's path lookup is a false
green. And the guardrail **test files** (not just the `check_*.py` scripts
themselves) are part of the gate: `pytest -k` subsets that exclude
guardrail tests are not sufficient to certify a reorg-shaped change; see G5.

### Rule G5 — Gate the FULL suite before push; serialize heavy jobs; read the summary, never `&&`-chain

**What happened:** already a named repo rule ("Targeted gate misses guardrail
tests" — `pytest -k` subsets skip guardrails; DB-adding backend work needs the
full suite) and ("Serialize builds" — the machine is slow, one `xcodebuild` /
one full `pytest` at a time) and ("Verify suite result before push" — never
`&&`-chain a push onto a test run; parse the summary and push only on 0
failed). This review folds all three into one git-practices rule because
they're the same failure shape applied to three different resources
(test selection, machine load, and the push trigger):

**Rule:** before any push to `origin/main` (or fast-forward of the
integration branch): (1) run the FULL relevant suite, not a `-k` subset —
targeted subsets are for the worker's own inner loop only; (2) run it alone —
never a second `xcodebuild`/full-pytest concurrently on the same machine;
(3) read the summary line and confirm **0 failed** as a distinct step before
the push command — never write `pytest ... && git push`, because a hook
failure, a crash, or a non-zero-but-swallowed exit still lets the `&&` chain
fire on stale confidence rather than a parsed result.

---

## (d) PROPOSED EDITS (not yet applied — for Daniel's review)

### `AGENTS.md`

**1. New subsection after "Worker Orchestration" (after line 130, before the
`---` at line 132), titled "Git Practices — Lanes, Integration, Commits":**

```markdown
## Git Practices — Lanes, Integration, Commits

Short-lived **lane branches** (one worker, one worktree under
`~/code/fichero-worktrees/<name>`, branched off `origin/main`) merge into an
**integration branch** when 2+ lanes must land together; the manager gates
the combined diff there (full suite, 0 failed) before fast-forwarding to
`main`. Delete a lane branch once its commits reach `main` — nothing is
lost, the commits stay reachable by SHA / `git log --grep` / the closed
issue.

**Commit, never stash.** Park interrupted work as a WIP commit on the lane
branch, not `git stash` — a stash doesn't survive a worktree teardown and is
invisible outside the shell that made it. Baseline-diffing (comparing two
tree states) happens in a **separate worktree**, never via
stash-and-checkout in the same one (see `docs/design/git-practices-fabel-review.md`
Rule "stash-pop hazard").

**Bring an agent up to speed with data, not a long-lived branch:**
`agents/ROADMAP.md` + GitHub milestones for "what's next", per-area
`*_STATUS.md` / fabel-review docs for "what's the current state",
conventional-commit scopes (`git log --grep '(#1234)'`) for "what happened
and why". A branch several agents keep rebasing onto is the failure mode
this replaces.

**Verification runs in the foreground.** Any agent whose job is "verify then
commit" (worker or otherwise) blocks on its own check and commits in the
SAME turn it sees the result. Never launch a background test + a `Monitor`
and pause — the turn ends before the result lands, and the agent loops
without ever committing.

**Path-keyed guardrails move with the file.** Any commit that moves, renames,
or splits a file must update every `scripts/check_*.py` `TARGET_FILES`-style
constant and guardrail allowlist in the SAME commit — see "A `pytest -k`
subset skips the architecture guardrails" in Common Pitfalls below; the
guardrail's own test files are part of the gate, not optional.

Full rationale and the incidents behind each rule:
`docs/design/git-practices-fabel-review.md`.
```

**2. Amend rule 11 (Worktrees) to cross-reference the new integration-branch
worktree case** — append a sentence:

> Before: `...NEVER rm -rf a ~/code/ path and NEVER glob-delete ~/code/fichero-*`
> After (append): `A worktree that must build on un-pushed integration-branch
> state (not yet on origin/main) is created from that branch's HEAD sha
> explicitly — git worktree add <path> <integration-branch-or-sha> — not the
> Agent tool's default isolation: "worktree", which branches from
> origin/main and won't see integration-only commits.`

**3. Common Pitfalls bullet (after the existing "A `pytest -k` subset skips
the architecture guardrails" bullet at line 264) — add:**

> - **Renames/moves break path-keyed guardrails.** `PERSISTENCE_PATH`,
>   `WILDCARD_BIND`, the XML chokepoint check, `db_access`,
>   `single_connection`, and every `check_*.py` `TARGET_FILES` list hardcode
>   paths. A move that doesn't update them in the same commit gives a false
>   green (7 regressions from #3751/#3754). Grep for the old path across
>   `scripts/check_*.py` before committing a rename.

### `agents/skills/session-start-manager/SKILL.md`

**Add to "Owns" (after the existing bullet list, before "## Does Not Own"):**

> - Gate the **integration branch**, not individual lane branches in
>   isolation — a lane can pass `--fast` alone and still break a guardrail
>   once merged with another lane's changes (path-keyed guardrails move
>   together; a combined diff can collide even when neither lane's own diff
>   does).
> - Verify commit provenance before trusting it: `git show --stat <sha>` and
>   confirm the file list matches what the commit message claims, especially
>   for docs/tooling-only commits landed by a concurrent process.

### `agents/prompts/manager-loop.md`

**Add under "## Gate + merge" (after the existing bullet about resetting the
worker's worktree, before "## File new issues..."):**

> - Gate the FULL suite, not a `-k` subset, before any fast-forward to
>   `main` — targeted subsets skip guardrail tests. Read the summary and
>   confirm 0 failed as its own step; never `&&`-chain the push onto the
>   test command.
> - Delete a lane branch once its commits are confirmed in `main` (or in an
>   integration branch that itself reached `main`) — the commits stay
>   reachable by SHA and by the closed issue; don't keep dead lane branches
>   around as memory.

### `agents/prompts/worker-loop.md`

**Amend step 4 ("Commit only") to make the foreground-verification rule
explicit — insert after the existing sentence:**

> Before: `4. Commit only — NEVER build, NEVER run the full suite or
> xcodebuild (the machine is slow; the manager gates serially). Backend: you
> may ruff your own diff, but do NOT run pytest. Closes #n in the message.`
> After (append a sentence): `Any check you DO run (ruff, swiftlint,
> check_*.py) runs in the FOREGROUND and blocks until it returns — never
> background it with a Monitor and pause; if your turn ends before you see
> the result, you commit nothing and the manager sees a stalled lane.`

---

## Summary of what to decide

These are proposals only. Nothing outside this new file has been edited.
Daniel reviews G1–G5 and the AGENTS.md / manager-loop.md / worker-loop.md /
session-start-manager/SKILL.md insertions above and either approves them
verbatim, edits wording, or rejects a subset before they're applied to the
live docs.
