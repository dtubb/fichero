---
name: session-start-milestone-worker
description: Autonomous milestone worker — claim and work through 5–15 issues in a single milestone, with leeway to make implementation decisions. Claims each issue to avoid overlap with sibling workers, verifies every issue, commits to the milestone branch, and shuts down gracefully when the milestone is drained or the worker is far ahead.
---

# /session-start-milestone-worker

A higher-autonomy worker lane. Instead of a single hand-assigned issue, you own a **milestone** and work through its issues yourself — claiming each one so parallel workers don't collide, making reasonable implementation decisions without asking, and stopping cleanly when you've gotten far enough ahead.

The manager dispatches you with a milestone name (and optionally a tier hint like "backend only" or "SwiftUI only"). If none was given, ask once, then proceed.

## Startup Checklist

1. Confirm branch and cleanliness.
   ```bash
   git branch --show-current
   git status --short --branch
   ```
   You should be on the milestone branch (e.g. `0.0.3`) in your own worktree. If you're on `main`, STOP and ask the manager — never commit milestone work to `main`.

2. Read project context:
   ```bash
   [ -f CLAUDE.md ] && sed -n '1,80p' CLAUDE.md
   [ -f STATE.md ] && sed -n '1,60p' STATE.md
   ```

3. List your milestone's open, unclaimed work:
   ```bash
   gh issue list --milestone "<MILESTONE>" --state open \
     --search "no:assignee -label:status:in-progress -label:status:blocked -label:needs-human-test" \
     --limit 30
   ```

## Owns

- Work through **5–15 issues** in the assigned milestone this session
- Claim each issue before starting (see Claim Protocol) so siblings don't double-work it
- Make reasonable implementation decisions independently — you don't need to ask for routine choices
- Verify every issue (build/test/lint per CLAUDE.md) before moving to the next
- Commit each issue's work to the milestone branch with a message referencing the issue
- Release any issue you can't finish, with a note
- Shut down gracefully when the milestone is drained or you're far ahead of integration

## Does Not Own

- No work outside the assigned milestone (claim from other milestones only if yours is empty AND the manager OK'd it)
- No merge to `main` — push the milestone branch; the integrator/manager merges
- No starting a milestone more than one ahead of what's being tested (see CLAUDE.md two-ahead rule)

## Claim Protocol (prevents sibling overlap)

The `status:in-progress` label is the cross-worker lock. Before touching any issue:

```bash
# 1. Re-confirm it's still free (another worker may have grabbed it since you listed)
gh issue view <N> --json assignees,labels \
  -q '{assignees: [.assignees[].login], labels: [.labels[].name]}'
# If it has an assignee OR status:in-progress → skip it, pick the next one.

# 2. Claim: assign self + add lock label
gh issue edit <N> --add-assignee @me --add-label "status:in-progress"

# 3. Race re-check: re-read assignees. If two workers both grabbed it, the one
#    whose login sorts alphabetically first keeps it; the other runs
#    /release-task <N> "lost claim race" and picks a different issue.
gh issue view <N> --json assignees -q '.assignees[].login'
```

When done: `/complete-task <N>` removes the label and closes.
When blocked: `/block-task <N> <reason>` (label stays off; issue gets `status:blocked`).
When pausing unfinished: `/release-task <N> <reason>` removes the label so a sibling can resume.

## Execution Loop

Repeat until the stop condition (below) is hit:

1. **Pick** the lowest-numbered unclaimed issue in the milestone.
2. **Claim** it (Claim Protocol).
3. **Check** it isn't already fixed (`check_references` + recent commits on main and your branch).
4. **Plan** in 2–3 sentences. For anything non-trivial or cross-layer, write the plan in the issue as a comment before coding.
5. **Implement** the change. Use jCodemunch tools to navigate; `Read` only immediately before `Edit`/`Write`.
6. **Verify** — run the gates from CLAUDE.md for the files you touched (backend: targeted ruff + the issue's regression test; SwiftUI: the Xcode build). Keep commits small and issue-scoped.
7. **Commit** to the milestone branch: `git commit -m "<imperative description> (#N)"`.
8. **Close** with `/complete-task <N>`.
9. **Push** the branch every 2–3 issues so the integrator sees progress.
10. Loop back to step 1.

### Using your leeway

You are trusted to decide routine things without asking: which of two reasonable implementations to use, whether a small refactor is justified to land the fix cleanly, how to name things, what tests to add. Reserve questions for genuine product decisions (changes to user-facing behavior the issue doesn't specify) — leave those as an issue comment and skip to the next issue rather than blocking.

## Stop Condition — Shut Down Gracefully

Stop the loop and wrap up when ANY of these is true:

- You've completed **10–15 issues** this session (don't run forever).
- The milestone has **no unclaimed issues left**.
- You are **far ahead of integration** — your branch is 15+ commits ahead of `main` and unmerged. Piling up more just makes the integrator's job harder; let them catch up.
- A gate is **persistently red** and you can't get the branch green — stop, don't keep stacking work on a broken base.

On stop:
1. Release any issue still claimed but unfinished (`/release-task`).
2. Push the milestone branch.
3. Run `/session-end-worker` to record the handoff.
4. Report (below).

## Output — Handoff Report

```
MILESTONE WORKER — <milestone> — <date>

Completed (N): #.. #.. #..   (each: 1-line what + commit)
Released (M):  #.. — reason
Blocked (K):   #.. — reason
Branch:        <name>, <X> commits ahead of main, pushed
Stop reason:   <drained / 15-done / far-ahead / red-gate>
For integrator: <anything overlapping or risky they should know>
```

## Constraints

- Always claim before working; always release/close to drop the lock label
- Never commit to `main`; never exceed the two-ahead milestone rule
- Keep commits small and issue-scoped so the integrator can cherry-pick if a merge goes sideways
- If two workers land overlapping changes, that's expected — flag it in the handoff so the integrator/reviewer can reconcile
