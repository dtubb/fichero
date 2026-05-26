# Agent Briefing — Fichero

Quick orientation for new sessions.

## Project

Fichero — macOS document management with AI processing (SwiftUI + Python FastAPI).

## Current Phase

**Execution.** Implement milestone issues from GitHub on the current milestone branch. Commit directly after each task — no per-task branches, no PRs.

## Essential Files

| File | Purpose |
|---|---|
| `CONSTITUTION.md` | What Fichero is, what it's not, and what matters |
| `MEMORY.md` | Conventions, lessons, durable decisions |
| `AGENTS.md` | Execution rules, build commands, hard constraints |
| `STATE.md` | Current branch, focus, next session entry point |
| `docs/CLAUDE.md` | Full agent guidance (canonical, detailed) |

## Key Commands

```bash
# Start backend
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Run tests
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived

# Lint
swiftlint lint fichero-swiftui/fichero-swiftui/
ruff check fichero-api/src/
```

## Task Priority (override default lowest-issue-number ordering)

When picking the next task in an autonomous session, use this priority order:

1. **`type:bug` issues** — fix all open bugs before any feature work, regardless of milestone or issue number
2. **Current milestone feature issues** — lowest issue number first
3. **Future milestone issues** — only if current milestone is empty

To find bugs:
```bash
gh issue list --state open --label "type:bug" --limit 20
```

**Why:** Daniel files bugs via `/bug` while testing the app. Bugs must be fixed before the next session ships new features or they pile up and block testing.

## Hard Rules

1. Never push to `main` — all work goes to `0.0.2`
2. Never skip build/test/lint before completing work
3. Never modify generated files (`*Generated.swift`, openapi.json)
4. GitHub milestones/issues are source of truth for scope/status
5. PYTHONPATH must be `fichero-api/src`
