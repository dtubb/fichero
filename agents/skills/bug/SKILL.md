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

Use `scripts/file_issue.sh` — the ONE sanctioned way to create an issue. It checks
the milestone exists and is OPEN, enforces the 15 canonical labels, and keyword-routes
by title. Raw `gh issue create` is how duplicate and mis-placed milestones crept in.

```bash
scripts/file_issue.sh \
  --title "<short title>" \
  --type bug \
  --lane backend|client:swiftui|docs \
  --milestone auto \
  --body-file /tmp/fichero-bug.md \
  --dry-run
```

Run `--dry-run` first and read the milestone it resolved. If the router guesses
wrong, pass `--milestone "<Exact Name>"`. Drop `--dry-run` to file.

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
