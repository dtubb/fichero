# Agent Briefing — Fichero

Quick orientation for new sessions and teammates.

## Project

Fichero — macOS document management with AI processing (SwiftUI + Python FastAPI).

## Current Phase

**Phase 0: Planning.** No coding until plan is approved.

## Essential Files

| File | Purpose |
|---|---|
| `SOUL.md` | Agent identity and what Fichero is |
| `MEMORY.md` | Current state, conventions, lessons learned |
| `TASKS.md` | Session-level tasks (points to GitHub issues) |
| `STATE.md` | Current branch, focus, next session entry point |
| `docs/CLAUDE.md` | Full agent guidance (canonical, detailed) |
| `docs/agent-workflow/TODO.md` | Master task list in repo |

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

## Hard Rules

1. Never push to main without Daniel's approval
2. Never skip build/test/lint before completing work
3. Never modify generated files (`*Generated.swift`, openapi.json)
4. Never start coding before a plan exists
5. PYTHONPATH must be `fichero-api/src`
