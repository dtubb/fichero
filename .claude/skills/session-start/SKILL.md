---
description: Start a new session — load project memory, check git state, and report what's active. Run at the beginning of every session.
name: session-start
---

# Session Start — Fichero

Load context and report the current state. Don't ask permission — just do it.

## 1. Load Project Memory

Read in order:
1. `SOUL.md` — who you are and how to behave on this project
2. `MEMORY.md` — current state, conventions, lessons learned
3. `STATE.md` — current branch, focus, next session entry point
4. `TASKS.md` — what's active this session

## 2. Check Git State

```bash
git status
git log --oneline -10
git branch
```

Note: current branch, any uncommitted changes, recent commits.

## 3. Report

Print a concise session brief:
- **Current branch** and any uncommitted changes
- **This week's focus** (from STATE.md)
- **In progress** (from TASKS.md / STATE.md)
- **Blocked** (from STATE.md)
- **Next step** — what to do first today
- "What would you like to work on?"

Keep the report short. One screen. If something looks wrong (wrong branch, stale state), flag it.

## 4. Hard Rules Reminder

Read SOUL.md and note the hard rules. Never push to main without explicit approval.
