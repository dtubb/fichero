# Fichero — Agent Constitution

## What This Is

Fichero is a macOS document management system with LangChain-powered AI toolchains. Two-part architecture: SwiftUI frontend (`fichero/fichero/`, Xcode project at `fichero/fichero.xcodeproj`) + Python FastAPI backend (`fichero-engine/src/fichero/`). Current phase: active development on milestone issues.

## Session Configuration

```
WORKING_BRANCH: 0.0.2          # current working branch; NOT a release gate
AUTONOMOUS_COMMITS: true
AUTONOMOUS_PRS: true
TASK_TRACKING: github
RELEASE_MODEL: dated           # releases are cut by date, not semantic version
```

**Releases are dated, not versioned.** There is no 0.0.3 / N+2 milestone, no
per-version branch, and **no per-version worktree** (`~/code/fichero-<version>` is retired).
Commit work to the current working branch; cut a dated release when a slice is ready.

**The organizing unit is the GitHub feature milestone** (Chat, KG & Hermeneutics,
Window Chrome & Toolbars, Importers, …) — NOT a version number. Work **one milestone at a
time**: groom it first (make sure the milestone's issues are all there and complete), work it
to done, then pick the next. Features are **not gated behind a release** — the active lane is
whatever milestone is in focus.

**Branch discipline**: commit milestone work directly to the working branch; do NOT create
per-task branches. For a risky/large slice, an isolated agent worktree under
`.claude/worktrees/` is fine, but it is keyed to the work, not to a version.

## Iterate, never replace (HARD RULE)

**Build on the existing code; do not rewrite or start over.** Daniel likes what
is already there — the frontend and backend as they stand are an asset, not a
draft. Replacing working code is *costly*: it throws away tested behaviour and
forces him to re-learn / re-test from scratch.

- **Augment, don't replace.** Extend existing views/services/modules in place.
  Add a layer, a parameter, an overlay — do not swap a working component for a
  new parallel one. (See `docs/architecture/swiftui/document_canvas.md`: the
  right move was to fold the editor onto the *existing* viewer stack, not build
  a third wrapper.)
- **Resist the urge to "start over" / "rewrite cleanly."** If a fix feels like
  it needs a rewrite, scope it down to the smallest in-place change instead.
- The ONLY thing you retire is genuine **duplication** you just found — and only
  by collapsing the duplicates onto the existing canonical one, never by
  introducing a fresh replacement.
- Applies to BOTH layers (SwiftUI and Python). When unsure, iterate.

This rule is embedded in every worker dispatch prompt.

## How I Work

**Priority order:**
1. Plan before coding. Enter plan mode for non-trivial work.
2. One concern per commit. Small, complete increments.
3. Verify everything: build, test, lint — then mark complete.

**Parallel execution & context hygiene** (full guide: `docs/agent-workflow/parallel-execution.md`):
- Offload build/lint/test and bug investigation to **subagents** — the lead reads a verdict, not a log.
- Use a **single session** for the 0.0.2 backend fix cluster (overlapping files) and SwiftUI fixes (one Xcode).
- Use an **agent team** for the QA review gate (#1061), competing-hypothesis debugging, and 0.0.3+ cross-layer features.
- Before committing a bug-fix sweep to `0.0.2`, run the QA review gate: stage the diff, spawn 3 review-only teammates (`backend-reviewer`, `silent-failure-hunter`, `code-reviewer`), synthesize, then commit.

## Build + Test + Lint

```bash
# Backend server
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Python tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived

# Python lint
ruff check fichero-engine/src/

# Swift lint
swiftlint lint fichero/fichero/
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

## Code Intelligence — jCodemunch First, ALWAYS

**Primary tool**: `jcodemunch` (MCP server, tree-sitter AST index, ~95% token savings vs Read/Grep). Migrated from trace-mcp 2026-05-17.

**Start every session** with `plan_turn { repo: ".", query: "<task>", model: "<your-model-id>" }` — returns confidence + recommended files in one call. Use `resolve_repo { path: "." }` to confirm the index is fresh; if not, `index_folder { path: "." }`.

**Hard rule for ANY code question — use jcodemunch tools, NOT Read/Grep/Glob/Bash(ls,find):**

| Question | jcodemunch tool | Instead of |
|---|---|---|
| Where is `extract_all` defined? | `search_symbols { query: "extract_all", language: "python" }` | Grep |
| What's in this file before I edit? | `get_file_outline { path: "..." }` | Read (whole file) |
| Show me just `WorkflowExecutor.run`'s source | `get_symbol_source { symbol_id: "..." }` | Read (whole file) |
| Symbol + its imports in one call | `get_context_bundle { symbol_id: "..." }` | multiple reads |
| What breaks if I change `KnowledgeClaim`? | `get_blast_radius { symbol_id: "..." }` | guessing |
| Who imports this file? | `find_importers { path: "..." }` | Grep |
| Where is this name used? | `find_references { name: "..." }` | Grep |
| Is identifier X used anywhere? | `check_references { name: "..." }` | Grep |
| Class hierarchy / implementations | `get_class_hierarchy { class: "..." }` | ls/find |
| Untested public API? | `get_untested_symbols` | manual audit |
| Dead code? | `find_dead_code` | Grep for unused |
| Changed symbols since last commit | `get_changed_symbols` | git diff + parse |
| Repo overview / file tree | `get_repo_outline` / `get_file_tree` | ls -R |
| String/comment/config search | `search_text { query: "..." }` | Grep |

**After editing files:** PostToolUse hooks auto-reindex. For bulk edits (5+ files) call `register_edit { paths: [...] }` to batch-invalidate.

**Read/Grep/Glob is allowed ONLY** for non-code files (`.md`, `.json`, `.yaml`, `.toml`) or as the mandatory `Read` immediately before `Edit`/`Write` on a file you just located via jcodemunch.

**Top god nodes (high blast radius — `get_blast_radius` BEFORE touching)**: `Database`, `KnowledgeClaim`, `KnowledgeEntity`, `Document`, `LLMConfig`, `EntityType`, `DocType`, `Artifact`, `WorkflowDef`.

## Key Paths

| Path | What |
|---|---|
| `CONSTITUTION.md` | Product north star: what we're building, why, what it's not, hard constraints |
| `AGENTS.md` | Execution rules, build commands, decisions |
| `USER.md` | About Daniel — who he is, constraints |
| `STATE.md` | Current branch, focus, next session |
| `MEMORY.md` | Persistent lessons and decisions |
| `docs/CLAUDE.md` | Full agent guidance (canonical, detailed) |
| `docs/agent-workflow/parallel-execution.md` | When to use single session / subagents / agent teams + QA review gate |
| `docs/architecture/` | Architecture docs |
| `fichero/fichero/` | Swift/SwiftUI frontend (Xcode project: `fichero/fichero.xcodeproj`) |
| `fichero/fichero-api-client/` | Generated Swift OpenAPI client package |
| `fichero-engine/src/fichero/` | Python FastAPI backend |
| `fichero-engine/tests/` | Python tests (`unit/`, `integration/`, `contracts/`) |

## Rules I Don't Break

1. Never push directly to `main` — always go through a PR (create it and merge it yourself).
2. Never skip build, test, lint before marking work complete.
3. Never modify genuinely auto-generated files: `openapi.json`, anything under `fichero/fichero-api-client/.build/`, anything under `fichero/fichero-api-client/Sources/FicheroAPIClient/` that's produced by the OpenAPI generator. **Note:** `fichero/fichero/Services/*Generated.swift` files are *hand-written service wrappers* (despite the confusing suffix) and CAN be edited. The `openapi.json` files ARE regenerated from the backend (via `fichero-engine/scripts/sync_openapi_schema.sh`) and that regen output should be committed — what's forbidden is hand-editing them.
4. When editing a service wrapper that builds a request body, **always use the OpenAPI-typed fields** on `Components.Schemas.*`, not `additionalProperties`, for any field that's declared in `openapi.json`. Dumping declared fields into `additionalProperties` silently loses writes under Pydantic `extra="allow"` — see commit 31fc4141 for the pattern and `docs/architecture/swiftui/api_client.md` for context.
5. Never start coding before a plan exists for non-trivial work.
6. `PYTHONPATH` must be set to `fichero-engine/src` for all Python commands.
7. Never create per-task branches — commit all work to the milestone branch directly.
8. Never start a milestone more than one ahead of what Daniel is currently testing.
9. **0.0.x is no-migration**: schema changes go directly into `db.py` `_ensure_table` (via the Pydantic model field). Never add an `ALTER TABLE ADD COLUMN` migration function for a column that's already in the model — fresh databases pick it up automatically. Only historical structural migrations (table renames, data backfills) belong in `db_migrations.py`. Once 0.1.0 ships to real users, this rule changes.
10. **New .swift files must be registered with `scripts/add-swift-file.rb`**: The `Fichero` main target uses traditional PBX file references — a file written to disk is invisible to the compiler until registered. Always run `ruby scripts/add-swift-file.rb <path>` after creating any new `.swift` file. The `xcodeproj` gem is installed at `~/.gem/ruby/2.6.0/gems/xcodeproj-1.27.0/`. Test-target files are the exception (sync'd groups). Never edit `project.pbxproj` by hand. The build gate (`bash scripts/verify_all.sh`) will catch unregistered files as "Cannot find type" errors.

## Before editing backend or API-client code

Read `docs/architecture/` first — specifically:
- `docs/architecture/swiftui/api_client.md` for the OpenAPI round-trip contract.
- `docs/architecture/api/development_standards.md` for backend conventions.
- `docs/architecture/swiftui/development_standards.md` for Swift conventions.

The `docs/CLAUDE.md` file at the root of the project is the canonical agent guidance and also references these.
