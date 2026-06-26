---
name: session-start-cli
description: Orient a CLI/import agent (pi, open-source models) at session start. No code writes — operates the running backend via the fichero CLI. Used for document import, workflow runs, entity queries, and data operations.
---

# /session-start-cli

CLI-only session start. **This agent does NOT write code.** It operates the running Fichero backend via the CLI.

Primary use: bulk document import, running workflows on batches, querying entities/claims, populating libraries for testing.

---

## Step 0 — Check backend is running

```bash
fichero health 2>/dev/null || echo "BACKEND DOWN — start with: PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765"
```

If backend is down, stop and report. Do not proceed.

---

## Step 1 — Load context

```bash
cat STATE.md | grep -A 20 "CLI\|import\|library"
```

Check `.ai/inbox/for-cli-*.md` for messages from other agents:

```bash
ls .ai/inbox/for-cli-*.md 2>/dev/null && cat .ai/inbox/for-cli-*.md 2>/dev/null
```

Move processed inbox files to `.ai/inbox/processed/`.

---

## Step 2 — Check available libraries

```bash
fichero library list 2>/dev/null || echo "No libraries registered"
```

---

## Step 3 — Report and wait

```
SESSION START — Fichero CLI — [date]

BACKEND: [up/down at http://127.0.0.1:8765]
LANE: CLI only — no code writes

LIBRARIES:
  [list from library list]

INBOX MESSAGES:
  [any .ai/inbox/for-cli-* items]

CLI QUICK REFERENCE:
  Import:   fichero --library <path> import <file-or-dir> [--recursive]
  Search:   fichero --library <path> search "<query>"
  Entities: fichero --library <path> entity list
  Workflow: fichero --library <path> workflow run <name> --doc <id>
  Health:   fichero check

TWO-LIBRARY PATTERN:
  fichero --library ~/path/to/A.fichero import /docs/type-a/
  fichero --library ~/path/to/B.fichero import /docs/type-b/

INTER-AGENT:
- Findings → write .ai/inbox/for-swiftui-YYYY-MM-DD.md or for-backend-YYYY-MM-DD.md

What would you like to import or query?
```

Then wait.

---

## Constraints

- NEVER edit source files (Python, Swift, JSON)
- NEVER commit or push
- If backend needs a fix: write a message to `.ai/inbox/for-backend-YYYY-MM-DD.md`
