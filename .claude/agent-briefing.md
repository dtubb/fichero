# Agent Briefing — Fichero

Quick orientation for new sessions.

## Project

Fichero — macOS document management with AI processing (SwiftUI + Python FastAPI).

## Current Phase

**Execution.** Implement milestone issues from GitHub on branch `0.0.2`. Commit directly after each task — no per-task branches, no PRs.

## Essential Files

| File | Purpose |
|---|---|
| `SOUL.md` | What Fichero is and what matters |
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

## Hard Rules

1. Never push to `main` — all work goes to `0.0.2`
2. Never skip build/test/lint before completing work
3. Never modify generated files (`*Generated.swift`, openapi.json)
4. GitHub milestones/issues are source of truth for scope/status
5. PYTHONPATH must be `fichero-api/src`
