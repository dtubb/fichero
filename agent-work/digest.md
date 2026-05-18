# Worker Digest — 0.0.2 autonomous loop
# Generated: 2026-05-18

## Branch + Milestone Context

- Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2/`)
- Milestone: bug-fix + contained feature sweep for Daniel's active test build
- Queue state: 27 pending, 3 blocked (architecture decisions needed)
- Recent ships: #801 (chunked summarize/rewrite/analyze), #925 (OCR cleanup), #1096 (catalogue case grouping), #1124 (hermeneutic predicates), #834 (Vision OCR retry)
- jCodemunch is the ONLY code exploration tool — never use Read/Grep/Glob on source files

## Top 5 Architectural Invariants for This Queue

1. **0.0.x no-migration rule**: Schema changes go into `db.py` `_ensure_table` via Pydantic model fields — fresh databases pick them up automatically. Never write `ALTER TABLE ADD COLUMN` migration functions. Only historical structural migrations (renames, backfills) belong in `db_migrations.py`.

2. **Pydantic fields must be declared**: `extra="allow"` silently accepts writes at runtime but `model_dump()` only serializes declared fields. Always add the Pydantic field AND confirm `_ensure_table` covers the column together.

3. **No inspector() or nested NavigationSplitView**: SwiftUI inspector panels must use `HStack + ResizableDivider` with global-coordinate `DragGesture`. Never nest `.inspector()` inside `NavigationSplitView`. Pane widths go in `AppStorage`, not `@State`.

4. **SidebarItem.id has type prefix**: `SidebarItem.id` is `"doc:UUID"` — always extract the actual doc UUID from `.itemType` before calling backend APIs. Passing the raw `SidebarItem.id` to endpoints silently sends the wrong value.

5. **KG slug_verb parity**: New KG modules must reuse `slug_verb()` from `fichero/kg/_common.py` to keep SPARQL ↔ aggregation parity. New enum members also go in `_common.py` so both paths agree.

## Pitfalls Filtered to This Queue's Issues

- **SwiftUI pane width (#1034, #1070)**: `.inspector()` + `NavigationSplitView` is the banned pattern. Use `HStack + ResizableDivider`. Width keys in `AppStorage` only.
- **PDF zoom (#1024)**: `PDFZoomController` uses `scaleFactorForSizeToFit` for fit-to-window — do NOT re-enable `autoScales` (causes #588 re-fit regression).
- **Workflow node display (#1040, #1049, #1042)**: Internal LangGraph nodes (`__dunder__`, UUID slots, `Runnable*`) are already filtered on the backend in `_is_internal_langchain_node()`; the Swift Activity view should trust the filtered stream.
- **WorkflowExecutionObserver.workflowCompletedCount** is the canonical "data may be stale" tick for KG and inspector views — subscribe via `.onChange` rather than adding manual refresh buttons (#1071, #1031).
- **Empty list ≠ None in tools**: In workflow tools with Priority 1/2/3 fallback chains, always guard with `if raw_files:` not `if raw_files is not None:` — an empty list passes the `is not None` check and short-circuits the fallback.
- **Ingest path for #1085, #975, #1101**: Use `search_symbols(query="ingest", language="python")` to find the ingest module entry point before editing — the previous blocker on #1085 was failing to locate it.
- **Claim SVO chips (#1036)**: subject/verb/object are already promoted to top-level DB columns (shipped in #984). Read them directly, not from `metadata`.
- **LangGraph SSE events (#1044, #1048)**: Per-page progress events are emitted from `_process` node; `parallel_file`, `parallel_index`, `parallel_total` are in `event.data.input` for each parallel file.

## Build / Test / Lint Commands (verbatim from CLAUDE.md)

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

**Xcode MCP tools** (prefer over xcodebuild):
- Build: `mcp__xcode__BuildProject` (needs `tabIdentifier` from `XcodeListWindows`)
- Tests: `mcp__xcode__RunAllTests` / `mcp__xcode__RunSomeTests`
- Errors: `mcp__xcode__GetBuildLog` / `mcp__xcode__XcodeListNavigatorIssues`

## Worker Protocol

1. **Open every task** with `plan_turn { "repo": ".", "query": "<issue title>", "model": "claude-sonnet-4-6" }` — returns confidence + recommended files.
2. **High confidence** → go directly to recommended symbols, max 2 supplementary reads.
3. **Medium confidence** → explore recommended files, max 5 supplementary reads.
4. **Low confidence / negative_evidence** → stop, mark blocked with reason, move on. Do NOT re-search hoping to find it.
5. **After editing** → run lint + tests. For SwiftUI: swiftlint + xcodebuild + RunAllTests (three-leg check is mandatory).
6. **Commit format**: `fix: <description> (#N)` or `feat: <description> (#N)` — always reference the issue.
7. **Never Read/Grep/Glob source files** — jcodemunch tools only for code exploration. `Read` is allowed only immediately before `Edit`/`Write` on a file already located via jcodemunch.
