---
name: bug
description: File a structured Fichero bug report with branch, commit, repro, and recent log context.
---

# /bug

Ask Daniel what happened, what he expected, and the shortest repro steps. Capture `git branch --show-current`, `git rev-parse --short HEAD`, and recent `/tmp/fichero-backend.log` lines if present.

Create a GitHub issue with label `type:bug` using the bug report template fields: Branch, Repro, Expected, Actual, Logs / Screenshots. Print the issue URL and stop; do not fix the bug unless Daniel asks.
