---
name: session-end
description: End a working session — summarize what happened, update MEMORY.md and STATE.md with durable knowledge and next session entry point. Run at the end of every session.
---

# /session-end

Wrap up so the next session starts informed. Don't ask permission — just do it.

Use this global skill by default. Only use a project-level `/session-end` override when `CLAUDE.md` explicitly requires it.

## Step 1 — Summarize the Session

Review what was accomplished this session:
- What was built, fixed, or refactored?
- What decisions were made (and why)?
- What was left incomplete?
- What problems or surprises were encountered?
- What did you learn that should persist?

## Step 2 — Update MEMORY.md

Add **durable knowledge only** — things that will matter in future sessions:
- New conventions discovered or confirmed
- Decisions made and the rationale
- Problems solved and how
- Environment or architecture facts that changed
- Patterns to avoid (and why they failed)

**Do NOT add:**
- Session-specific details (what we did today)
- Things already documented elsewhere
- Observations that won't affect future work

Use targeted edits. Never rewrite MEMORY.md from scratch. Add to the relevant section.

## Step 3 — Archive to HISTORY.md, then Update STATE.md

**First, archive completed work** — move anything finished this session from STATE.md to HISTORY.md programmatically:

```bash
# Append completed work to HISTORY.md with timestamp
echo "" >> HISTORY.md
echo "## $(date +%Y-%m-%d) — Session Summary" >> HISTORY.md
echo "" >> HISTORY.md
echo "- <what was completed this session, one bullet per task>" >> HISTORY.md
```

**Then update STATE.md** — it should only contain current state, not history:
- **Current Branch** — if it changed
- **This Week's Focus** — if priorities shifted
- **In Progress** — what's active right now (carry forward unfinished work)
- **Blocked** — any new blockers discovered
- **Next Session — Start Here** — clear, specific entry point (3-5 bullets max):
  - What to check first
  - What to do first
  - Any gotchas the next session needs to know about

Keep STATE.md lean. It's a snapshot of *right now*, not a log. Completed work lives in HISTORY.md.

## Step 4 — Update Tasks

Check `TASK_TRACKING:` in CLAUDE.md (`local`, `github`, or `both`), then update accordingly:

- **`local` (TASKS.md):** move completed tasks to done, add new ones, update in-progress, flag blocked
- **`github` (GitHub Issues/Milestones):** close completed issues, open new ones, update labels/milestone, add blocker comments
- **`both`:** sync changes to both

Use `gh issue` CLI or GraphQL as specified in `CLAUDE.md` for GitHub projects.

## Step 5 — Checkpoint Git State

```bash
git status
```

If \`CLAUDE.md\` defines \`UPCOMING_BRANCH: <name>\`, switch to that branch (create it from \`origin/main\` if missing), then checkpoint automatically:

\`\`\`bash
git fetch --all --prune
git checkout <UPCOMING_BRANCH> 2>/dev/null || git checkout -b <UPCOMING_BRANCH> origin/main
git add -A
git commit -m "chore(session-end): checkpoint state" || true
git push -u origin <UPCOMING_BRANCH> || true
\`\`\`

If \`UPCOMING_BRANCH\` is not defined, keep current behavior: report uncommitted changes and request direction.

## Step 6 — Confirm

Print a brief end-of-session summary:

```
SESSION END — [Project] — [date]

COMPLETED: [list — or "Nothing fully complete"]
MEMORY UPDATED: [yes/no — what was added]
STATE UPDATED: [yes/no — next session entry point set]
TASKS UPDATED: [yes/no — and which system: TASKS.md / GitHub / both]
UNCOMMITTED: [yes + description / no]

Next session: [one-line preview of the STATE.md entry]
```

## Step 7 — Write Completion Sentinel

Write `.session-end-complete` in the project root so an outer autonomous loop (e.g. `agent-autonomous-loop.py`) knows `/session-end` already ran and can skip its own duplicate end phase:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ > .session-end-complete
```

The loop deletes this file after consuming it. Harmless if no loop is running — it can be gitignored or ignored entirely.

## Constraints

- If \`UPCOMING_BRANCH\` is configured, commit/push checkpoints automatically at session end
- Keep STATE.md Next Session to 3-5 bullets maximum
- MEMORY.md gets durable lessons; STATE.md gets navigation state — don't mix them
- If nothing happened this session worth preserving, say so rather than padding

## Special Note: Autonomous Loop

When running in an autonomous loop, if `session-end` detects there's no more work to do (e.g., `STATE.md` has no next session entry), it should create `BLOCK.md` to stop the loop:

```bash
cat > BLOCK.md << 'EOF'
BLOCKED: No more work - autonomous loop completed

## Summary
All tasks completed or no tasks remain. The autonomous loop should stop.

## Next Steps
Review completed work, update milestones, or add new tasks for the next cycle.
EOF
```
