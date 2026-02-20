# Fichero Agent Loop — Make Fichero an Excellent Mac App

## Goal

Make Fichero an excellent native macOS document management app by:
1. **Code quality**: Refactor all oversized files (>400 lines) to clean, maintainable SwiftUI
2. **Resolve open issues**: Address open GitHub issues (QA audits, workflow editor refactor)
3. **Library UX**: File and begin the 18-week library view improvement plan as GitHub issues
4. **Build stability**: Ensure zero SwiftLint violations and passing builds at all times

## Available Tools

- **Xcode MCP**: XcodeRead, XcodeWrite, XcodeUpdate, XcodeGrep, XcodeGlob, BuildProject, RunAllTests, XcodeLS — full IDE integration
- **GitHub MCP**: `mcp__github__issue_write`, `mcp__github__list_issues`, `mcp__github__add_issue_comment`, `mcp__github__create_pull_request`, etc. — use these for ALL GitHub operations (NOT `gh` CLI)
- **Branch**: `codex/restructure-api-swiftui` (43 commits ahead of main)
- **Repo**: `dtubb/fichero`

## Scope

**In scope — Swift/SwiftUI:**
- All files under `fichero-swiftui/fichero-swiftui/Views/` — refactoring oversized views
- All files under `fichero-swiftui/fichero-swiftui/Services/` — refactoring non-generated services
- All files under `fichero-swiftui/fichero-swiftui/Models/` — refactoring oversized models
- **Swift unit tests** — currently ZERO XCTests exist; add tests as components are extracted
- **SwiftLint** — violations to work down to 0

**Out of scope:**
- Generated service files (`*Generated.swift`) — auto-generated, don't touch
- Generated API client (`fichero-api-client/`) — auto-generated
- **Python backend** — stable, 787 tests passing, out of scope for refactoring

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  OPUS ORCHESTRATOR (claudman ralph loop)    │
│  - Reads agents/progress.md                 │
│  - Creates GitHub issues via MCP tools      │
│  - Spawns Sonnet/Haiku agents               │
│  - Reviews results, verifies builds         │
│  - Updates progress tracker on exit         │
└──────────┬──────────────┬───────────────────┘
           │              │
    ┌──────▼──────┐ ┌─────▼───────┐
    │ REFACTOR    │ │ REFACTOR    │
    │ AGENT A     │ │ AGENT B     │
    │ (Sonnet)    │ │ (Sonnet)    │
    │ - 1 file    │ │ - 1 file    │
    │ - Extract   │ │ - Extract   │
    │ - Build     │ │ - Build     │
    │ - Commit    │ │ - Commit    │
    │ - Push      │ │ - Push      │
    └─────────────┘ └─────────────┘
```

---

## Session Continuity — How to Resume

**On every session startup, do this:**

1. Read `agents/progress.md` → see what's completed, in-progress, and next
2. Read `agents/plan.md` (this file) → understand the goal and patterns
3. Check GitHub issues on `dtubb/fichero` via `mcp__github__list_issues` → closed = done, open + `status:in-progress` = resume
4. Pick the next uncompleted batch from the progress file
5. Spawn Sonnet agents for 2-3 files (non-overlapping)
6. Wait for agents, verify build, push
7. Update `agents/progress.md` with results
8. Exit cleanly — claudman will restart you

**The loop prompt for claudman:**
```
Read agents/progress.md and agents/plan.md.
Resume the refactoring loop from where it left off.
Use Sonnet/Haiku agents only (never Opus).
Use GitHub MCP tools for issues. Use Xcode MCP tools for builds.
```

---

## Folder Structure

```
agents/
├── plan.md          # This file — goal, patterns, work items
├── progress.md      # Live tracker — what's done, what's next
└── checkpoints/     # Optional: agent team state snapshots
```

---

## Backend Operations

If agents need to run Python tests or regenerate the API client:

```bash
# Start backend (dev mode)
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Start backend (production/bundled mode)
python fichero-api/scripts/start_backend.py

# Run Python tests
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived

# Regenerate OpenAPI schema (after Python API changes)
./fichero-api/scripts/sync_openapi_schema.sh
```

---

## Adding More Orchestrators (Parallel Loops)

To run multiple orchestrators simultaneously:

1. **Same repo, same branch** — all orchestrators work on `codex/restructure-api-swiftui`
2. **GitHub issues as locks** — before touching a file, check if its issue is `status:in-progress`. If yes, skip it and pick another file
3. **Each orchestrator picks different batches** — they read `agents/progress.md` and claim the next unclaimed batch by marking it `status:in-progress` in GitHub
4. **Git coordination** — `git pull --rebase` before pushing; resolve conflicts if they happen

To start a second orchestrator:
```bash
# Terminal 2 — same prompt, claudman will pick different unclaimed work
claudman --prompt "Read agents/progress.md and agents/plan.md. Execute the next unclaimed batch..."
```

The locking mechanism (GitHub issues with `status:in-progress`) prevents two orchestrators from doing the same file.

---

## Refactoring Pattern (for all agents)

```
PATTERNS:
1. Extract self-contained views to separate files
2. Subfolder: Views/<Domain>/<ViewName>/
3. Extensions: <ViewName>+<Category>.swift
4. Change `private` → internal for extension access
5. Use @Binding for extracted component state
6. Environment objects propagate automatically

WORKFLOW:
1. XcodeRead the target file
2. Identify 4-6 extractable components
3. XcodeWrite new component files
4. XcodeUpdate the main file (slim it down)
5. BuildProject — fix errors immediately
6. git add <specific files> && git commit && git push
7. Comment on GitHub issue via mcp__github__add_issue_comment with before/after stats
```

## GitHub Operations — Always Use MCP Tools

```
Creating issues:     mcp__github__issue_write (method: "create")
Updating issues:     mcp__github__issue_write (method: "update")
Listing issues:      mcp__github__list_issues
Adding comments:     mcp__github__add_issue_comment
Creating PRs:        mcp__github__create_pull_request
Searching issues:    mcp__github__search_issues
```

**Owner**: `dtubb`  |  **Repo**: `fichero`

## Locking & Conflict Avoidance

### GitHub Issues as Locks

GitHub issues serve as the locking mechanism. Before starting work on any file:

1. **Check**: Search for an existing open issue for that file via `mcp__github__search_issues`
2. **If exists with `status:in-progress`**: Skip it — another agent/loop owns it
3. **If exists with `status:ready`**: Claim it — update label to `status:in-progress` and set assignee
4. **If no issue exists**: Create one with `status:in-progress` immediately

This means **multiple orchestrator loops can run in parallel safely** — GitHub issues are the single source of truth for who's working on what.

### Additional Safeguards

- Each agent owns exactly one file + its new extracted files
- Agents work on non-overlapping files (assigned by orchestrator after checking issue locks)
- Sequential git push within a single orchestrator (one agent at a time)
- Cross-orchestrator: pull before push, resolve any merge conflicts
- If `git push` fails due to remote changes: `git pull --rebase` then retry

## Quality Gates (after every change)

### Swift
1. `BuildProject` via Xcode MCP — 0 errors
2. `swiftlint lint fichero-swiftui/fichero-swiftui/` — violation count must not increase (goal: reduce to 0)
3. `RunAllTests` or `RunSomeTests` via Xcode MCP — all tests pass
4. New extracted components should have basic XCTests where feasible

### Git & GitHub
1. `git pull origin codex/restructure-api-swiftui` before starting work
2. Commit and push after each file refactoring
3. GitHub issues updated via MCP tools
4. `agents/progress.md` updated after each batch
5. PR created after each batch for Daniel to review

### Testing Philosophy
- **Add tests as you refactor** — when extracting a component, write a basic test for it
- **Never break existing tests** — run the full suite before pushing
- **Swift test gap is a priority** — currently 0 XCTests; each refactored view should get at least a smoke test

## Agent Model Choices

| Task | Model | Why |
|------|-------|-----|
| Orchestration | Opus (claudman) | Complex coordination |
| View refactoring | Sonnet | Code comprehension + Xcode MCP |
| Issue creation | Haiku | Templated, simple |
| Build verification | Haiku | Just run commands |
| Bug fixes | Sonnet | Needs code understanding |

**IMPORTANT: Never spawn Opus agents. All sub-agents must be Sonnet or Haiku.**

## Process Autonomy

The orchestrator agent is free to adjust the process, patterns, batching strategy, or priorities as it learns what works — **provided it keeps `agents/progress.md` and `agents/plan.md` updated** to reflect any changes. The files in `agents/` are the source of truth for loop continuity.

---

## Human-in-the-Loop

1. **Push early, push often** — commit and push after every file refactoring
2. **GitHub issues as the dashboard** — create issues before work starts, comment with progress, close when done
3. **PR for each batch** — after completing a batch, create a PR via `mcp__github__create_pull_request`
4. **Ask before risky changes** — if a refactoring would change behavior (not just extract), stop and ask
5. **Tag issues** — use labels (`type:task`, `status:in-progress`, `status:done`, `area:swiftui-*`) so Daniel can filter

**GitHub workflow per file:**
```
1. Create issue: "[Refactor] Extract <FileName> components"
2. Label: type:task, area:swiftui-<domain>, status:in-progress
3. Agent does the work
4. Agent comments on issue with before/after stats
5. Agent pushes commit to branch
6. Orchestrator updates issue label: status:in-progress → status:done
7. After batch complete: create PR for Daniel to review
```
