# Fichero — Agent Constitution

## What This Is

Fichero is a macOS document management system with LangChain-powered AI toolchains. Two-part architecture: SwiftUI frontend (`fichero-swiftui/`) + Python FastAPI backend (`fichero-api/`). Current phase: active development on milestone issues.

## Session Configuration

```
UPCOMING_BRANCH: 0.0.2
AUTONOMOUS_COMMITS: true
AUTONOMOUS_PRS: true
TASK_TRACKING: github
```

**Branch discipline**: Each milestone gets its own branch and worktree at `~/code/fichero-<version>/`. Do NOT create per-task branches within a milestone — commit all milestone work directly to the milestone branch. When finishing a branch, push, create a PR, then merge it yourself.

**Worktree pattern**: `git worktree add ~/code/fichero-0.0.3 -b 0.0.3`
Convention: `~/code/fichero-<version>` (e.g. `~/code/fichero-0.0.3`, `~/code/fichero-0.0.4`)

**Two-ahead rule**: Never work more than one milestone ahead of what Daniel is testing.
- Released: N (e.g. 0.0.1)
- Daniel testing: N+1 (e.g. 0.0.2) — bug fixes happen here
- Claude building: N+2 (e.g. 0.0.3) — one worktree, one agent loop
- Do NOT start N+3 until Daniel approves N+1.

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

## Xcode MCP Tools

When the Xcode MCP server is connected, prefer these over raw `xcodebuild`:

| Tool | Use |
|---|---|
| `mcp__xcode__BuildProject` | Build the project (needs `tabIdentifier` from `XcodeListWindows`) |
| `mcp__xcode__RunAllTests` | Run all tests from the active scheme |
| `mcp__xcode__RunSomeTests` | Run specific test suites (pass `targetName` + `testIdentifier`) |
| `mcp__xcode__GetBuildLog` | Check build errors/warnings after a failed build |
| `mcp__xcode__XcodeListNavigatorIssues` | List Xcode Issue Navigator warnings/errors |
| `mcp__xcode__RenderPreview` | Render a `#Preview` to get a visual snapshot |
| `mcp__xcode__DocumentationSearch` | Search Apple developer docs |
| `mcp__xcode__XcodeGlob` | Find files in the Xcode project structure |

**Previews**: `RenderPreview` requires `#Preview` macros in the source file. Previews that depend on backend (`@EnvironmentObject var appState`) will timeout — make previews self-contained with mock data. Use previews to visually verify settings layouts, inspector tabs, and static UI.

**Testing flow**: `BuildProject` → `RunAllTests` → `GetBuildLog` (if failures) → `XcodeListNavigatorIssues` (for warnings).

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

1. Never push directly to `main` — always go through a PR (create it and merge it yourself).
2. Never skip build, test, lint before marking work complete.
3. Never modify genuinely auto-generated files: `openapi.json`, anything under `fichero-swiftui/fichero-api-client/.build/`, anything under `fichero-swiftui/fichero-api-client/Sources/FicheroAPIClient/` that's produced by the OpenAPI generator. **Note:** `fichero-swiftui/fichero-swiftui/Services/*Generated.swift` files are *hand-written service wrappers* (despite the confusing suffix) and CAN be edited.
4. When editing a service wrapper that builds a request body, **always use the OpenAPI-typed fields** on `Components.Schemas.*`, not `additionalProperties`, for any field that's declared in `openapi.json`. Dumping declared fields into `additionalProperties` silently loses writes under Pydantic `extra="allow"` — see commit 31fc4141 for the pattern and `docs/architecture/swiftui/api_client.md` for context.
5. Never start coding before a plan exists for non-trivial work.
6. `PYTHONPATH` must be set to `fichero-api/src` for all Python commands.
7. Never create per-task branches — commit all work to the milestone branch directly.
8. Never start a milestone more than one ahead of what Daniel is currently testing.

## Before editing backend or API-client code

Read `docs/architecture/` first — specifically:
- `docs/architecture/swiftui/api_client.md` for the OpenAPI round-trip contract.
- `docs/architecture/api/development_standards.md` for backend conventions.
- `docs/architecture/swiftui/development_standards.md` for Swift conventions.

The `docs/CLAUDE.md` file at the root of the project is the canonical agent guidance and also references these.
