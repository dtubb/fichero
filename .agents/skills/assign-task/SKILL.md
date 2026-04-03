---
description: Create or assign a task — adds to TASKS.md and optionally creates a GitHub issue. Pass a description, e.g. "/assign-task implement login flow".
name: assign-task
---

# /assign-task

Add a task to the project. Works from TASKS.md (session view) and optionally GitHub Issues (source of truth for code projects).

## Step 1 — Understand the task

If a description was passed (e.g. `/assign-task implement feature flags`), use it.
If not, ask: what is the task? What does done look like?

Clarify if needed:
- Is this for the current session or a future one?
- What milestone does it belong to?
- Is it blocked on anything?
- Priority: P0 (now) / P1 (soon) / P2 (later)?

## Step 2 — Add to TASKS.md

Add to the appropriate section:
- **Active This Session** — if starting now
- **Up Next** — if queued for soon
- **Blocked on Human** — if needs a decision first

Format:
```
| — | [task description] | [priority] |
```

For code projects — also note the issue number if one exists.

## Step 3 — Optionally create a GitHub issue

For code projects with GitHub, ask if this should also be a GitHub issue:
```bash
gh issue create --title "[task]" --body "[done criteria]"
```

If yes, add the issue number to TASKS.md.

## Step 4 — Confirm

Print what was added and where. One line.
