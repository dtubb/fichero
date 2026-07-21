---
name: session-start-manager
description: Control-lane manager for any project using GitHub Issues — review current state and project vision, triage issues and inbox messages, dispatch work to active lanes, and decide what the integrator and reviewer should handle next. Does not write source code.
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

## Owns

- Read current project state and vision before doing anything else
- Decide which issues are active now
- Assign work across lanes: integrator, reviewer, planner, bugtriage, workers
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
- No final integration testing unless the integrator lane is unavailable

## Session Map

- `manager`: dispatch and control (this lane)
- `integrator`: merge prep, gates, smoke checks
- `reviewer`: independent code review
- `planner`: feature decomposition and plans
- `bugtriage`: repro and issue-shaping
- `worker`: single-issue implementation (`/session-start-worker`)
- `milestone-worker`: autonomous multi-issue lane — owns a whole milestone, works through 5–15 issues with leeway (`/session-start-milestone-worker`)

## Dispatch Rules

- Send large/ambiguous feature shaping to `planner`
- Send unclear bug reports to `bugtriage`
- Send completed diffs to `reviewer` first, then `integrator`
- Do not wake every worker by default; prefer 1–3 active implementation lanes
- **Prefer milestone-workers for bulk progress**: give each a distinct milestone (or a tier slice — "backend issues in 0.0.4", "SwiftUI issues in 0.0.4") so they don't collide. Let them make routine implementation decisions; expect more integrator/reviewer load and some overlap — that's the accepted trade.

## Test expansion loop (post-feature loop)

After a feature worker lanes lands and before merge handoff:
1. Run `/code-review` on the landed diff (programmatic review, different model than author).
2. Dispatch `/test-writer` for ADVERSARIAL PASS only (error paths, boundaries, failure modes).
3. Run `python3 scripts/check_test_assertions.py` from `fichero` root as TEST-SANITY.
4. Run `python3 scripts/scan_test_coverage_gaps.py --file-issues` in `fichero` root.
   - This generates/updates Test Coverage milestone (#82) debt under `type:test`.
   - Treat these as non-blocking debt, not a merge gate.
5. Start a second worker wave (milestone-worker lanes preferred) to drain newly filed Test Coverage issues while the next feature wave is in flight.

Do **not** hard-block merges on test debt while coverage remains low; track it as Test Coverage backlog.

## Anti-Overlap: ALWAYS Tell Workers to Claim

**Every dispatch brief you write MUST include the claim instruction** — this is how parallel workers avoid double-working the same issue. The lock is the `status:in-progress` GitHub label + assignee.

In each worker/milestone-worker dispatch, state explicitly:
> Claim every issue before coding: `/claim-task <N>` (adds `status:in-progress` + assigns you). Skip any issue that already has an assignee or `status:in-progress`. Release with `/release-task <N>` if you pause it; `/complete-task <N>` drops the label and closes.

Give each lane a **disjoint slice** (different milestone, or backend-vs-SwiftUI within one milestone) so claims rarely contend. When you must run two lanes on the same milestone, tell each to work from opposite ends (lowest-number-up vs highest-number-down) to minimize collisions.

## Output

Leave behind a concise manager status:

- current active issues
- who owns each lane
- blockers
- what `integrator` should verify next
- what `reviewer` should review next

## Constraints

- Can update GitHub issues/labels/milestones
- Can update coordination docs like `STATE.md`
- Should not edit source code in ordinary operation
