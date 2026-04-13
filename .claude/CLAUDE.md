# Fichero — Agent Constitution

## What This Is

Fichero is a macOS document management system with LangChain-powered AI toolchains. Two-part architecture: SwiftUI frontend (`fichero-swiftui/`) + Python FastAPI backend (`fichero-api/`). Current phase: active development on milestone issues.

## Session Configuration

```
UPCOMING_BRANCH: 0.0.2
AUTONOMOUS_COMMITS: true
AUTONOMOUS_PRS: false
TASK_TRACKING: github
```

**Branch discipline**: All work happens on `0.0.2`. Do NOT create per-task worktrees or feature branches. Commit to `0.0.2` after each task. Push when the task is complete. No PRs — commit directly.

## How I Work

**Priority order:**
1. Plan before coding. Enter plan mode for non-trivial work.
2. One concern per commit. Small, complete increments.
3. Verify everything: build, test, lint — then mark complete.

## Build + Test + Lint

```bash
# Backend server
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Python tests
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived

# Python lint
ruff check fichero-api/src/

# Swift lint
swiftlint lint fichero-swiftui/fichero-swiftui/
```

## Commit Format

Conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `style:`

Always reference GitHub issue: `feat: add tasks router (#420)`

## GitHub Workflow

GitHub Issues + Milestones is the source of truth for the backlog.

```bash
gh issue list --state open
gh issue list --milestone "0.0.4"
```

## Architecture

```
SwiftUI App → HTTP localhost:8765 → FastAPI → DuckDB/LanceDB
                                             → LangGraph (workflows)
                                             → LiteLLM (100+ providers)
```

Full architecture: `docs/CLAUDE.md`, `docs/architecture/`

## Key Paths

| Path | What |
|---|---|
| `VISION.md` | What we're building and why |
| `CONSTITUTION.md` | Project north star and hard constraints |
| `AGENTS.md` | Execution rules, build commands, decisions |
| `SOUL.md` | Agent identity and values |
| `USER.md` | About Daniel — who he is, constraints |
| `STATE.md` | Current branch, focus, next session |
| `MEMORY.md` | Persistent lessons and decisions |
| `docs/CLAUDE.md` | Full agent guidance (canonical, detailed) |
| `docs/architecture/` | Architecture docs |
| `fichero-swiftui/` | Swift/SwiftUI frontend |
| `fichero-api/src/fichero/` | Python FastAPI backend |

## Rules I Don't Break

1. Never push to `main` — all work stays on `0.0.2` (or feature branch if explicitly directed).
2. Never skip build, test, lint before marking work complete.
3. Never modify generated files manually (`*Generated.swift`, `openapi.json`, the api-client package).
4. Never start coding before a plan exists for non-trivial work.
5. `PYTHONPATH` must be set to `fichero-api/src` for all Python commands.
6. Never create per-task worktrees or feature branches during autonomous sessions — commit to `0.0.2` directly.
