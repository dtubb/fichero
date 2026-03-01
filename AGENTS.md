# AGENTS.md — Operational Manual

How to work on Fichero as an AI agent. Read this at the start of every session alongside SOUL.md → MEMORY.md → STATE.md → TASKS.md.

---

## Current Phase: Planning (Phase 0)

**No coding until Daniel approves the plan.** This is not optional.

Phase 0 work:
- Audit existing features (what works / broken / partial / untested)
- Design feature flag system (30 flags across 4 tiers: release, beta, dev, off)
- Create milestone plan M0–M4
- Get Daniel's sign-off

When he approves, Phase 1 begins: implement M0 (stabilize core, gate everything else).

---

## Session Startup

Run `/session-start` first. It reads SOUL.md → MEMORY.md → STATE.md → TASKS.md and reports current state.

### What to Check

1. **Branch** — `git branch`. Should be on main or a feature branch (not codex/restructure-api-swiftui — that's merged).
2. **Uncommitted changes** — `git status`. Nothing should be left hanging.
3. **STATE.md** — Current focus, in-progress, blocked.
4. **TASKS.md** — Active issue, what's next.
5. **docs/agent-workflow/TODO.md** — Master backlog (GitHub Issues are source of truth for scope).

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
| `/assign-task` | Pick up an issue from TASKS.md |
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

### What to Work On (Phase 0)

In strict priority order:
1. Feature audit (what exists and what state is it in)
2. Feature flag system (30 flags, 4 tiers)
3. Milestone plan (M0–M4, shippable increments)
4. Get Daniel to approve the plan

Don't start Phase 1 coding until he approves.

### What to Work On (Phase 1+)

Follow milestone priority:
- **M0**: Stabilize core. Disable (flag as dev) anything broken or untested.
- **M1**: Data integrity, 100% test coverage of core features.
- **M2**: Feature completeness — all flagged features working and tested.
- **M3**: Distribution — packaging, signing, ready for others.

### When to Proceed vs. Ask

**Proceed without asking:**
- Planning, auditing, documentation work (Phase 0 is all of this)
- Bug fixes with clear root cause and test coverage
- Adding tests for existing behavior
- Lint/build fixes

**Ask first (enter plan mode):**
- Any feature work (requires Phase 1 approval first)
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
- **MEMORY.md** — Lessons learned, architecture decisions, non-obvious behaviors
- **TASKS.md** — Active tasks; reference GitHub Issues (don't duplicate them)
- **memory/YYYY-MM-DD.md** — Session log (detailed notes, decisions made)

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

## Current Situation (Feb 2026)

**We are in Phase 0: Planning.**

The major restructure (codex/restructure-api-swiftui, 173 commits) has been merged to main. The app exists with many features in various states. We need to audit, flag, and plan before coding more.

**What's done:**
- Phase 0 audit of existing features (frontend + backend)
- Feature flag design (30 flags)
- Milestone plan M0–M4 (81 tasks)
- Dev environment verified (Python 3.14.3, .venv, swiftlint)

**What's blocked on Daniel:**
- Plan approval (Phase 0 → Phase 1 transition)
- Feature flag tier decisions
- Milestone scope sign-off

**While blocked:** Keep constitution files current. Review the plan docs in `memory/2026-02-26.md`. Don't start M0 coding without approval.

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
5. Never start coding before plan is approved
6. `PYTHONPATH=fichero-api/src` on all Python commands
7. One concern per commit, conventional commit format
8. `trash` over `rm`
