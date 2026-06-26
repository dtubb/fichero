---
name: status
description: Quick project status summary — reads STATE.md and active tasks (TASKS.md or GitHub Issues per CLAUDE.md), returns a the assistant-friendly one-paragraph report.
---

# /status

Read the current project state and report concisely. Designed to be run non-interactively via `pi -p "/status"` by the assistant or cron.

## Steps

1. Read `STATE.md` — current branch, focus, in progress, blocked
2. Read active tasks — check `TASK_TRACKING:` in CLAUDE.md: `local` → read TASKS.md, `github` → `gh issue list`, `both` → both
3. Read `MEMORY.md` — any recent decisions worth surfacing
4. Run `git log --oneline -3` — what was recently committed

## Report format

Print exactly this structure (the assistant parses it):

```
PROJECT: [project name]
BRANCH: [current branch]
STATUS: [one word — Active / Blocked / Waiting / Idle]
FOCUS: [one sentence — what's being worked on]
BLOCKED: [list blockers, or "None"]
NEEDS MAINTAINER: [anything requiring approval or input, or "Nothing"]
LAST COMMIT: [most recent commit message]
```

No prose. No padding. the assistant will relay this to the maintainer.
