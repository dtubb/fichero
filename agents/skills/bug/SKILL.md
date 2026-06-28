---
name: bug
description: File a structured Fichero bug report with branch, commit, repro, and recent log context.
---

# /bug

Capture a bug without interrupting the current development session.

## Inputs

Ask Daniel for only what is missing:

1. What happened?
2. What did you expect?
3. What are the shortest repro steps?

## Context To Capture

Run:

```bash
branch="$(git branch --show-current)"
commit="$(git rev-parse --short HEAD)"
recent_log="$(tail -n 80 /tmp/fichero-backend.log 2>/dev/null || true)"
```

If the bug is frontend/WebKit-related, suggest:

```bash
scripts/tail-fichero-logs.sh
```

## File The Issue

Create one GitHub issue:

```bash
gh issue create \
  --title "[Bug] <short title>" \
  --label "type:bug" \
  --body-file /tmp/fichero-bug.md
```

Use this body:

```markdown
## Branch

- <branch> @ <commit>

## Repro

1. <step>

## Expected

- <expected>

## Actual

- <actual>

## Logs / Screenshots

- <recent relevant log lines, or "none captured">
```

Print the issue URL and stop. Do not start fixing the bug unless Daniel explicitly asks.
