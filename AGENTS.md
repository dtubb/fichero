# AGENTS.md — Operational Manual

How to work on Fichero as an AI agent. Read this at the start of every session alongside SOUL.md → MEMORY.md → STATE.md.

---

## Current Phase: Execution

**GitHub is the source of truth.** Implement and close milestone issues in priority order. Commit to `0.0.2` directly after each task — no per-task branches, no PRs.

---

## Session Startup

Run `/session-start` first. It reads SOUL.md → MEMORY.md → STATE.md and reports current state.

### What to Check

1. **Branch** — `git branch`. Should be on `0.0.2`.
2. **Uncommitted changes** — `git status`. Nothing should be left hanging.
3. **STATE.md** — Current focus, in-progress, blocked.
4. **GitHub Milestones/Issues** — Active scope, status, and priority (source of truth).

---

## Skills Available

Run skills with `/skill-name`.

### Project Skills

| Skill | What It Does |
|---|---|
| `/session-start` | Load memory, check git, report state |
| `/session-end` | Write session log, update STATE.md, commit |
| `/build-and-test` | Full quality cycle: build + test + lint (Swift AND Python) |
| `/feature-audit` | Audit features — what works, broken, tested, untested |
| `/feature-flags` | List and manage feature flags |
| `/assign-task` | Pick up an issue from GitHub |
| `/milestone-check` | Check progress against current milestone |

### Global Skills

| Skill | What It Does |
|---|---|
| `/blocked` | List everything blocked and what's needed |
| `/scope-check` | Check if current work is in scope |
| `/handoff` | Write handoff notes for next session |
| `/retrospective` | Post-milestone retrospective |
| `/changelog` | Generate changelog from git log |

---

## Build Commands — Both Stacks

**Python backend:**
```bash
# Start backend
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Run tests
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ \
  --ignore=fichero-api/tests/unit/_archived

# Lint
PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/
PYTHONPATH=fichero-api/src .venv/bin/ruff format fichero-api/src/
```

**Swift frontend:**
```bash
# Lint (must pass before any commit)
swiftlint lint fichero-swiftui/fichero-swiftui/

# Xcode build
xcodebuild -project fichero-swiftui/fichero-swiftui.xcodeproj \
  -scheme fichero-swiftui -configuration Debug -sdk macosx build
```

**CRITICAL:** `PYTHONPATH=fichero-api/src` must be set for ALL Python commands.

**Generated files (NEVER edit manually):**
- `*Generated.swift`
- `openapi.json`
- Swift api-client package
- Regenerate via `scripts/sync_openapi_schema.sh`

---

## Commit and Branch Discipline

All work happens on `0.0.2`. Do NOT create per-task worktrees or feature branches.

After each task:
1. Run build + test + lint (evidence before claiming complete)
2. Commit with conventional format referencing the GitHub issue
3. Push to `origin/0.0.2`

```
feat: add semantic search to document inspector (#42)
fix: correct PYTHONPATH in uvicorn startup (#38)
chore: regenerate OpenAPI client after endpoint changes
refactor: extract DocumentStore from LibraryView (#55)
test: add pytest coverage for ingestion pipeline
docs: update architecture-summary.md with LanceDB schema
```

One concern per commit. Don't mix feat + fix.

---

## Decision-Making

### When to Proceed vs. Plan

**Proceed without planning:**
- Bug fixes with clear root cause and test coverage
- Adding tests for existing behavior
- Lint/build fixes
- Documentation updates

**Enter plan mode first:**
- Architectural changes to either stack
- Changes to the OpenAPI schema (frontend + backend must stay in sync)
- Feature flag tier changes
- Anything touching the database schema

### Two-Stack Rule

Every significant change touches both stacks or touches neither. Before completing any backend route change:
1. Does the OpenAPI schema need updating?
2. Do the Swift generated files need regenerating?
3. Do frontend callers need updating?

If you change the backend API without regenerating the Swift client, the build breaks.

---

## Memory Management

- **STATE.md** — Current focus, in-progress, blocked, next session entry point
- **MEMORY.md** — Durable lessons/decisions (not project status)
- **memory/YYYY-MM-DD.md** — Session log (detailed notes)

GitHub Issues + Milestones are authoritative for scope and status.

---

## Hard Rules

1. Never push to `main` — all work goes to `0.0.2`
2. Never deploy or publish without permission
3. Never edit generated files (`*Generated.swift`, `openapi.json`, api-client)
4. Never skip SwiftLint, ruff, pytest before completing work
5. Never start coding on unapproved scope (GitHub milestone/issues are the approval boundary)
6. `PYTHONPATH=fichero-api/src` on all Python commands
7. One concern per commit, conventional commit format
8. `trash` over `rm`
