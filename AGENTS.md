# AGENTS.md — Operational Manual

How to work on Fichero as an AI agent. Read this at the start of every session alongside SOUL.md → MEMORY.md → STATE.md.

---

## Current Phase: Execution (Post-Phase-0)

**Phase 0 planning is approved.** Agents should execute milestone work from GitHub.

Execution focus:
- Implement and close milestone issues in priority order
- Keep feature tiers and release gates aligned with approved roadmap
- Record blockers in GitHub and `STATE.md` with concrete unblock conditions

---

## Session Startup

Run `/session-start` first. It reads SOUL.md → MEMORY.md → STATE.md and reports current state.

### What to Check

1. **Branch** — `git branch`. Should be on main or a feature branch (not codex/restructure-api-swiftui — that's merged).
2. **Uncommitted changes** — `git status`. Nothing should be left hanging.
3. **STATE.md** — Current focus, in-progress, blocked.
4. **GitHub Milestones/Issues** — Active scope, status, and priority (source of truth).
5. **GitHub Project board** — Current sprint execution status (source of truth).

---

## Skills Available

Run skills with `/skill-name` in Claude Code.

### Project Skills (`.claude/skills/`)

| Skill | What It Does |
|---|---|
| `/session-start` | Load memory, check git, report state |
| `/session-end` | Write session log, update STATE.md, commit if clean |
| `/build-and-test` | Full quality cycle: build + test + lint (Swift AND Python) |
| `/feature-audit` | Audit features — what works, broken, tested, untested |
| `/feature-flags` | List and manage feature flags (30 flags, 4 tiers) |
| `/toggle-feature` | Toggle an individual feature flag on/off |
| `/assign-task` | Pick up an issue from GitHub |
| `/pr-workflow` | Run pre-PR checks and create GitHub PR |
| `/milestone-check` | Check progress against current milestone |

### Reference Docs (not user-invocable, auto-loaded)

| File | What It Covers |
|---|---|
| `_shared/swift-principles.md` | SwiftUI patterns, concurrency, testing, Xcode |
| `_shared/python-principles.md` | FastAPI, Pydantic, ruff, pytest, project structure |
| `_shared/architecture-summary.md` | High-level architecture overview |
| `_shared/team-constitutions.md` | Agent team role definitions |

### Global Skills (`~/.claude/skills/`)

| Skill | What It Does |
|---|---|
| `/blocked` | List everything blocked and what's needed |
| `/scope-check` | Check if current work is in scope |
| `/pr-review` | Review a PR before merging |
| `/handoff` | Write handoff notes for next session |
| `/retrospective` | Post-milestone retrospective |
| `/status` | One-paragraph status report for Myco |
| `/decision` | Apply a human decision to unblock work |
| `/planning` | Interactive planning session |
| `/changelog` | Generate changelog from git log |

### Subagents (`.claude/agents/`)

| Agent | Model | What It Does |
|---|---|---|
| `code-reviewer` | haiku | Reviews diffs for correctness and convention compliance |
| `test-runner` | haiku | Runs test suite and reports failures |

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

## Decision-Making

### What to Work On (Execution)

Follow milestone priority:
- **M0**: Stabilize core. Disable (flag as dev) anything broken or untested.
- **M1**: Data integrity, 100% test coverage of core features.
- **M2**: Feature completeness — all flagged features working and tested.
- **M3**: Distribution — packaging, signing, ready for others.

### When to Proceed vs. Ask

**Proceed without asking:**
- Planning, auditing, documentation work
- Bug fixes with clear root cause and test coverage
- Adding tests for existing behavior
- Lint/build fixes

**Ask first (enter plan mode):**
- Architectural changes to either stack
- Changes to the OpenAPI schema (frontend + backend must stay in sync)
- Feature flag tier changes (what's release vs. dev)
- Anything touching the database schema

### Two-Stack Rule

Every significant change touches both stacks or touches neither. Before completing any backend route change:
1. Does the OpenAPI schema need updating?
2. Do the Swift generated files need regenerating?
3. Do frontend callers need updating?

If you change the backend API without regenerating the Swift client, the build breaks.

---

## Memory Management

### What to Update Each Session

- **STATE.md** — Current focus, in-progress, blocked, next session entry point
- **MEMORY.md** — Optional durable lessons/decisions (do not mirror project status)
- **memory/YYYY-MM-DD.md** — Session log (detailed notes, decisions made)

### Source of Truth Policy

- GitHub Issues + Milestones + Project are authoritative for scope, prioritization, and status.
- Local planning trackers (`PLAN.md`, `TASKS.md`, `docs/agent-workflow/TODO.md`) are legacy and non-authoritative.
- Use `STATE.md` only for local session handoff continuity.

### Commit Conventions

```
feat: add semantic search to document inspector (#42)
fix: correct PYTHONPATH in uvicorn startup (#38)
chore: regenerate OpenAPI client after endpoint changes
refactor: extract DocumentStore from LibraryView (#55)
test: add pytest coverage for ingestion pipeline
docs: update architecture-summary.md with LanceDB schema
```

Always reference GitHub issue number. One concern per commit. Don't mix feat + fix in one commit.

---

## Current Situation (Mar 2026)

**Phase 0 is complete and approved.**

The major restructure (codex/restructure-api-swiftui, 173 commits) has been merged to main. The app exists with many features in various states. Audit/flag/plan work is complete, and execution now proceeds from the approved GitHub roadmap.

**What's done:**
- Phase 0 audit of existing features (frontend + backend)
- Feature flag design (30 flags)
- Milestone plan M0–M4 (81 tasks)
- Dev environment verified (Python 3.14.3, .venv, swiftlint)

**What's active now:**
- Milestone execution and release-gate closure on GitHub
- Feature promotion only via milestone issues and approvals
- Ongoing QA evidence capture against release-gate issues

---

## How This Fits the Larger System

```
Fichero (THIS PROJECT — documents + AI)
    ↕ future integration
Tinderbox Router (MCP multiplexer — plumbing)
    ↕
Tinderbox (manuscript structure)
    ↕
research-assistant / Escribano (writing system agent)
    ↕
Daniel (author — all decisions his)
```

Fichero is the document layer. When the integration is built, documents in Fichero become accessible to the manuscript system — completing Daniel's research stack.

---

## Hard Rules (from CLAUDE.md and CONSTITUTION.md)

1. Never push to main without Daniel's explicit approval
2. Never deploy or publish without permission
3. Never edit generated files (`*Generated.swift`, `openapi.json`, api-client)
4. Never skip SwiftLint, ruff, pytest before completing work
5. Never start coding on unapproved scope (GitHub milestone/issues are the approval boundary)
6. `PYTHONPATH=fichero-api/src` on all Python commands
7. One concern per commit, conventional commit format
8. `trash` over `rm`
