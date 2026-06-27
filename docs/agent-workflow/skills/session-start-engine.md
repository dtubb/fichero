---
name: session-start-engine
description: Orient a backend/engine agent at session start. Loads Python/FastAPI context, backend-only issues, Python-specific rules. Use instead of /session-start when this agent only touches fichero-engine files.
---

# /session-start-engine

Backend-only session start. **This agent touches ONLY `fichero-engine/**` files.**
Do not edit Swift files, openapi.json (hand-editing), or the Swift API client.

---

## Step 0 — BLOCK gate

```bash
if [ -f BLOCK.md ]; then head -n 40 BLOCK.md; fi
```

Stop if first non-empty line starts with `BLOCKED`.

---

## Step 1 — Load context

```bash
pwd && git status && git log --oneline -5
```

Read in order:
1. `STATE.md` — "Next Session — Start Here (backend Claude)" section
2. `MEMORY.md` — Python/FastAPI relevant entries
3. `AGENTS.md` — hard rules (PYTHONPATH, migration policy, envelope conventions)

---

## Step 2 — Open backend issues

```bash
gh issue list --label backend --state open --limit 20
```

Report top 3 by priority.

---

## Step 3 — Python health check

```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/ 2>&1 | tail -5
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ -q --tb=no 2>&1 | tail -5
```

Note any failures.

---

## Step 4 — Report and wait

```
SESSION START — Fichero Engine — [date]

BRANCH: [branch]
LANE: backend — Python only (fichero-engine/**)

FOCUS: [from STATE.md backend section]
TOP ISSUES:
  #NNNN [title]
  #NNNN [title]
  #NNNN [title]

PYTHON RULES:
- Always set PYTHONPATH=fichero-engine/src for all commands
- 0.0.x is no-migration: add columns via _ensure_table, never ALTER TABLE
- New routes: move to _CORE_ROUTE_SPECS only if they should ship in release; otherwise _DEV_ROUTE_SPECS
- After adding routes: run ./fichero-engine/scripts/sync_openapi_schema.sh and commit generated files
- envelope convention: list endpoints return {items: [...], count: N}

INTER-AGENT:
- Need Swift UI changes? Write .ai/inbox/for-swiftui-YYYY-MM-DD.md
- Need CLI test? Write .ai/inbox/for-cli-YYYY-MM-DD.md

What would you like to work on?
```

Then wait.

---

## Constraints

- NEVER edit .swift files or hand-edit openapi.json
- NEVER push directly to main
- After any route change: run sync_openapi_schema.sh
- Run `bash scripts/verify_python.sh` before marking work complete
