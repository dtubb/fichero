# Worker Digest — 0.0.2 autonomous loop
# Generated: 2026-05-18

## Branch + Milestone Context

Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2/`).
Daniel is actively testing this build. All bug fixes go directly to this branch — no per-issue branches.
Architecture: SwiftUI frontend (`fichero/fichero/`) + Python FastAPI backend (`fichero-engine/src/fichero/`).
Queue: 27 pending, 3 blocked. Done this session: #759, #758, #783, #795, #1046, #1043, #747, #746, #745, #1008.
Next up: #879 (auth 401s), #750 (test fixture auth), #743 (lazy ML imports), then #764 (workflow frozen UX).

## Top 5 Architectural Invariants for These Issues

1. **0.0.x no-migration rule.**
   Schema changes go in `_ensure_table` via the Pydantic model field. Never add `ALTER TABLE ADD COLUMN`. Fresh databases pick up columns automatically. Only historical structural migrations belong in `db_migrations.py`. Applies to #1085, #1101, #1102.

2. **WorkflowExecutionObserver.workflowCompletedCount is the canonical "data may be stale" tick.**
   Subscribe via `.onChange(of: observer.workflowCompletedCount)` to refresh KG/inspector views post-run. Use for #1052 (color-code refresh). Do not add manual refresh buttons.

3. **KG / entity logic belongs in the backend — frontend only renders.**
   Aggregation, dedup, scoping, summary generation are backend endpoints. For #1071 inspector entity lists, add `?document_id` filter to the endpoint rather than filtering client-side.

4. **@State parent properties invisible to child views.**
   `ContentView` `@State` (browserSelection, detailDocument) must be passed explicitly as `let`/`Binding` params to child views. Applies to any SwiftUI fix touching inspector or sidebar state (#1031, #1036, #1071).

5. **NSViewRepresentable Coordinator must be `@MainActor`.**
   Annotate entire Coordinator when all PDFKit/AppKit notification callbacks fire on main thread. Applies to #1024 (PDFZoomToolbar) and #928 (PDF loupe overlay). PDFZoomController uses `scaleFactorForSizeToFit`; never re-enable `autoScales` (causes #588 re-fit regression).

## Pitfalls Relevant to This Queue

- **Auth token path** — `#879` and `#750`: token file location written at engine startup must match the path the middleware reads. For tests, AuthTokenMiddleware needs a fixture bypass — don't hardcode a real token path in test fixtures.
- **SidebarItem.id has a type prefix** — `"doc:UUID"`. Always extract `doc.id` from `.itemType` before calling backend APIs (#1031, #1071).
- **Pydantic field must be declared** — `extra="allow"` lets runtime writes succeed silently but `model_dump()` only serializes declared fields. Add `_ensure_table` column AND the model field together (#1101, #1102, #1085).
- **Empty list is not None** — `inputs["files"] = []` passes `is not None`; use `if raw_files:` not `if raw_files is not None:` in tools with fallback chains (#743, backend nodes).
- **LangGraph internal node name filtering** — hide UUID slots, `__dunder__`, `fan_out`; show user nodes as `snake_case → Title Case`. Backend also drops `Runnable*` LCEL nodes at SSE source via `_is_internal_langchain_node()` in runner.py. Applies to #1040.
- **TimelineView snapshot count** — never re-read live `@State.count` inside helpers consuming a snapshot; bound by `snapshot.count` to avoid brk #0x1 (#998 pattern). Applies to #1045/#1048 activity grid work.
- **confirmationDialog beats alert(presenting:)** — on macOS inside `List(selection:)`, `.alert(title:isPresented:presenting:)` can race on same-tick `@Published` updates. Use `.confirmationDialog` instead.
- **focusable() swallows first click** — never put `.focusable()` on pane wrappers; use `simultaneousGesture(TapGesture())` to track focus without consuming taps.
- **Verify an issue isn't already fixed** — open status ≠ unfinished work; check the code + tests before implementing. Fichero has a strong fixed-but-not-closed pattern.

## Build / Test / Lint Commands

```bash
# Swift lint (run after every SwiftUI change)
swiftlint lint fichero/fichero/

# Xcode build (prefer Xcode MCP; fallback CLI)
xcodebuild -workspace fichero/fichero.xcodeproj/project.xcworkspace \
  -scheme Fichero -configuration Debug \
  -skipPackagePluginValidation \
  CODE_SIGNING_ALLOWED=NO build

# Python backend
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Python unit tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived

# Python lint
ruff check fichero-engine/src/
```

Three-leg check is MANDATORY before marking any SwiftUI issue done: swiftlint + xcodebuild + RunAllTests.

## jCodemunch Usage Reminder

Worker MUST use jcodemunch tools for ALL code navigation. Never use Read/Grep/Glob/Bash(find/ls) on source files.

Opening move for every issue:
```
plan_turn { "repo": "danieltubb/fichero", "query": "<issue description>", "model": "claude-haiku-4-5" }
```

Use full repo identifier `danieltubb/fichero` — relative paths (`.`) do not work with jcodemunch.
If index is missing: `index_folder { "path": "/Users/danieltubb/code/fichero-0.0.2" }` then retry.

Key tools:
- `search_symbols` — find symbol by name/kind
- `get_file_outline` — file structure before editing
- `get_symbol_source` — read just the symbol, not the whole file
- `get_blast_radius` — verify impact before touching high-churn symbols
- `find_references` — gauge how many call sites need updating
- `register_edit` — call after editing to keep the index fresh

Read/Grep is ONLY allowed for non-code files (.md, .json, .yaml, .toml) or as the mandatory Read immediately before Edit/Write on a file you just located via jcodemunch.
