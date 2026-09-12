---
name: session-start-manager
description: Control-lane manager for any project using GitHub Issues — review current state and project vision, triage issues and inbox messages, dispatch work to workers, and integrate/merge completed work. Does not write source code.
---

# /session-start-manager

Manager-only session start. This lane coordinates; it does not implement product code.

## Startup Checklist

1. Confirm branch and worktree cleanliness.
   ```bash
   git branch --show-current
   git status --short --branch
   ```
2. Read project context (read what exists, skip what doesn't):
   ```bash
   [ -f VISION.md ] && sed -n '1,40p' VISION.md
   [ -f CONSTITUTION.md ] && sed -n '1,40p' CONSTITUTION.md
   [ -f SOUL.md ] && sed -n '1,30p' SOUL.md
   [ -f USER.md ] && sed -n '1,30p' USER.md
   [ -f AGENTS.md ] && sed -n '1,40p' AGENTS.md
   [ -f CLAUDE.md ] && sed -n '1,60p' CLAUDE.md
   [ -f BLOCK.md ] && sed -n '1,80p' BLOCK.md
   [ -f agents/ROADMAP.md ] && sed -n '1,120p' agents/ROADMAP.md   # priority tiers — what's next
   [ -f STATE.md ] && sed -n '1,80p' STATE.md
   [ -f MEMORY.md ] && sed -n '1,80p' MEMORY.md
   git log --oneline -20
   find .ai/inbox ~/.claude/inbox -maxdepth 1 -type f -name '*.md' 2>/dev/null | sort
   ```
   **`agents/ROADMAP.md` is the source of truth for priority order.** The loop is
   two skills — use them, don't improvise:
   - **`/choose-next`** — reads ROADMAP + GH milestones, returns the next batch
     (1 big issue OR 3–10 small same-milestone issues) from the highest-incomplete tier.
   - **`/dispatch-worker`** — spawns that batch the right way: **external worktree
     only** (`~/code/fichero-worktrees/`, never `.claude/worktrees/`), codex for
     backend / `claude -p` for frontend, cheap model default (Sonnet / codex-mini),
     Opus/codex-5.5 only for keystones, then build/test-verify before cherry-pick.
   Also see `docs/VERIFY.md` (what verify checks) — its failures auto-file to the
   right milestone, which `/choose-next` then picks up.
3. Check active tmux lanes if work is in flight.
4. Decide:
   - what is blocked
   - what is ready for review
   - what is ready for integration
   - what new work should be dispatched

The loop per issue is **spec → approve → test → code**: shape or confirm the
owning spec in `docs/contributor_manual/specs/<area>.md` first, get it
approved, require a regression test that pins the bug/feature, then dispatch
implementation. Don't skip straight to a worker prompt on an unspecced issue.

## Owns

- Read current project state and vision before doing anything else
- Decide which issues are active now
- Assign work across lanes: bugtriage, workers
- **Integrate/merge the result yourself — the manager IS the integrator.**
  There is no separate "integrator" lane to dispatch to; build-gate, run the
  full suite, and merge are manager duties, not something handed off.
- Keep GitHub issue state coherent
- Update `STATE.md` when coordination state has actually changed
- Enforce two AGENTS.md rules on every dispatch and merge: **Commit Attribution**
  (each agent commits as itself, committer stays the human, credit Daniel via
  `Directed-By`) and **Docs Placement** (all docs in `docs/`, public pages in
  `mkdocs.yml` nav; agent scratch in `agent-work/`; crud → `git rm`). When committing a
  worker's leftover changes yourself, attribute to the worker, not the manager.
- Gate the **integration branch**, not individual lane branches in
  isolation — a lane can pass `--fast` alone and still break a guardrail
  once merged with another lane's changes (path-keyed guardrails move
  together; a combined diff can collide even when neither lane's own diff
  does).
- Verify commit provenance before trusting it: `git show --stat <sha>` and
  confirm the file list matches what the commit message claims, especially
  for docs/tooling-only commits landed by a concurrent process.

## Does Not Own

- No source-code edits unless explicitly repurposed this session
- No speculative feature implementation
- Integration testing IS the manager's job (the manager is the integrator) — not delegated

## Session Map

- `manager`: dispatch, control, AND integration — gate + build-verify + merge
  (this lane; not a separate hand-off)
- `bugtriage`: repro and issue-shaping
- `worker`: single-issue implementation (`/session-start-worker`)

## Dispatch Rules

- Send unclear bug reports to `bugtriage`
- Review completed diffs yourself (`/code-review`) before merging — there is
  no separate reviewer lane to hand off to
- Do not wake every worker by default; prefer 1–3 active implementation lanes
- **Give each worker a disjoint slice**: a distinct milestone, or a tier
  slice ("backend issues in 0.0.4", "SwiftUI issues in 0.0.4"), or separate
  files/worktrees, so lanes don't collide. Let them make routine
  implementation decisions; expect more manager review load and some
  overlap — that's the accepted trade.

## Test expansion loop (post-feature loop)

After a feature worker lane lands and before merge:
1. Run `/code-review` on the landed diff (programmatic review, different model than author).
2. Run `python3 scripts/check_test_assertions.py` from `fichero` root as TEST-SANITY.
3. Run `python3 scripts/scan_test_coverage_gaps.py --file-issues` in `fichero` root.
   - This generates/updates Test Coverage milestone (#82) debt under `type:test`.
   - Treat these as non-blocking debt, not a merge gate.
4. Start a second worker wave to drain newly filed Test Coverage issues while the next feature wave is in flight.

Do **not** hard-block merges on test debt while coverage remains low; track it as Test Coverage backlog.

## Avoiding Overlap

Workers avoid double-work by owning **disjoint issues/files**, not by claiming a shared lock — there is no claim/release mechanism to invoke. Give each lane a distinct slice (different milestone, backend-vs-SwiftUI within one milestone, or a separate worktree) before dispatch. When two lanes must share a milestone, tell each to work from opposite ends (lowest-number-up vs highest-number-down) to minimize collisions.

## Output

Leave behind a concise manager status:

- current active issues
- who owns each lane
- blockers
- what you (as integrator) will verify/merge next

## Constraints

- Can update GitHub issues/labels/milestones
- Can update coordination docs like `STATE.md`
- Should not edit source code in ordinary operation
