# Worker Digest — 0.0.2 autonomous loop
# Generated: 2026-05-18

## Branch + Milestone Context

Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2/`).
Daniel is actively testing this build. All bug fixes go directly to this branch — no per-issue branches.
Architecture: SwiftUI frontend (`fichero/fichero/`) + Python FastAPI backend (`fichero-engine/src/fichero/`).
Queue: 27 pending, 3 blocked. Done this session: #961, #1049, #1034, #1070, #788.
Next up: #998 (crash), #783 (loupe), #795 (inspector), #759 (log), #758 (startup failure detection).

## Top 5 Architectural Invariants for These Issues

1. **AppStorage over SceneStorage for anything that should survive navigation or restart.**
   Pane widths, column widths, UI toggles — use `@AppStorage`. `@SceneStorage` is reset on navigation transitions. Pattern established in #1034/#1070 fixes already on this branch.

2. **No nested `.inspector()` or `HSplitView` inside `NavigationSplitView`.**
   Use `HStack + ResizableDivider` with a global-coordinate `DragGesture`. See `OntologyBrowser` for the working pattern; it was just migrated this session.

3. **0.0.x no-migration rule.**
   Schema changes go in `_ensure_table` via the Pydantic model field. Never add `ALTER TABLE ADD COLUMN`. Fresh databases pick up columns automatically. Only historical structural migrations (table renames, data backfills) belong in `db_migrations.py`.

4. **KG / entity logic belongs in the backend — frontend only renders.**
   Aggregation, dedup, scoping, summary generation are backend endpoints. If a SwiftUI view is computing KG data, that's a bug (#1072). For inspector entity lists (#1071), add a `?document_id` filter to the endpoint rather than filtering client-side.

5. **WorkflowExecutionObserver.workflowCompletedCount is the canonical "data may be stale" tick.**
   Subscribe via `.onChange(of: observer.workflowCompletedCount)` to refresh KG/inspector views post-run. Do not add manual refresh buttons. Also use this for #1008 (auto-trigger KG embed tools after a run completes).

## Pitfalls Relevant to This Queue

- **SidebarItem.id has a type prefix** — `"doc:UUID"`. Always extract `doc.id` from `.itemType` before calling backend APIs (#795, #1031).
- **focusable() swallows first click** — never put `.focusable()` on pane wrappers; use `simultaneousGesture(TapGesture())` to track focus without consuming taps.
- **@State parent properties invisible to child views** — `ContentView` `@State` must be passed explicitly as `let`/`Binding` params; child views cannot see parent `@State` directly.
- **NSViewRepresentable Coordinator must be `@MainActor`** — annotate entire Coordinator when all PDFKit / AppKit notification callbacks fire on main thread (#1024 PDFZoomToolbar).
- **PDFZoomController bridge pattern** — `fitToWindow` uses `scaleFactorForSizeToFit`; never re-enable `autoScales` (causes #588 re-fit regression).
- **Pydantic field must be declared** — `extra="allow"` lets runtime writes succeed silently but `model_dump()` only serializes declared fields. Add `_ensure_table` column AND the model field together (#1101, #1102).
- **confirmationDialog beats alert(presenting:)** — on macOS inside `List(selection:)`, `.alert(title:isPresented:presenting:)` can race on same-tick `@Published` updates and silently skip presentation.
- **TimelineView snapshot count** — never re-read live `@State.count` inside helpers consuming a snapshot; bound by `snapshot.count` to avoid brk #0x1 (#998 graph crash may have a related root cause).
- **Pipe exit-code shadowing** — `cmd | head; echo $?` reads head's exit, not cmd's. Use `${PIPESTATUS[0]}` or `set -o pipefail` for lint/test commands (#1043 dep audit).

## Build / Test / Lint Commands

```bash
# Swift lint (run after every SwiftUI change)
swiftlint lint fichero/fichero/

# Xcode build (prefer Xcode MCP BuildProject; fallback CLI)
xcodebuild -workspace fichero/fichero.xcodeproj/project.xcworkspace \
  -scheme fichero -configuration Debug \
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

Key tools:
- `search_symbols` — find symbol by name/kind
- `get_file_outline` — file structure before editing
- `get_symbol_source` — read just the symbol, not the whole file
- `get_blast_radius` — verify impact before touching high-churn symbols
- `find_references` — gauge how many call sites need updating
- `register_edit` — call after editing to keep the index fresh (auto-reindex hook may already handle this)

Read/Grep is ONLY allowed for non-code files (.md, .json, .yaml, .toml) or as the mandatory Read immediately before Edit/Write on a file you just located via jcodemunch.
