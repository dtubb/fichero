# Worker Digest — 0.0.2 autonomous loop
# Generated: 2026-05-18 (Round 2 curator pass)

## Branch + Milestone Context

Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2`). Daniel is actively testing this milestone.
Commit all work directly to `0.0.2` — no per-task branches.
Push → create PR → merge it yourself (AUTONOMOUS_PRS: true).

**Done this round**: #743 #1061 #764 #1038
**Blocked**: #873 (arch decision), #1097 (depends #873), #971 (arch review)

## Top 5 Architectural Invariants for These Issues

1. **0.0.x no-migration rule**: New DB columns go into `_ensure_table` via the Pydantic model field only. Never add `ALTER TABLE ADD COLUMN` for columns already in the model. Historical structural migrations only go in `db_migrations.py`. Applies to: #730, #1085, #1101, #1102, #874.

2. **Pydantic `extra="allow"` silently drops undeclared fields from `model_dump()`**: Always declare new fields on the model AND in `_ensure_table` together. Never dump declared fields into `additionalProperties`. Applies to: #730, #1102, #916, #1101, #1085.

3. **Use OpenAPI-typed fields, not `additionalProperties`**: When building Swift request bodies, use `Components.Schemas.*` typed fields for any field declared in `openapi.json`. Applies to: #768, #797, #735, #1059, #732.

4. **SidebarItem.id has type prefix `"doc:UUID"`**: Always extract `doc.id` from `.itemType` before calling backend APIs. Never pass the raw `SidebarItem.id` as a document UUID. Applies to: #1031, #1071, #1052, #1036, #916.

5. **slug_verb is the shared canonical verb normalizer**: New KG modules must reuse `slug_verb` from `fichero/kg/_common.py` to keep SPARQL ↔ aggregation parity. Applies to: #730, #1111, #1036, #916.

## Pitfalls Filtered to Relevant Issues

- **Activity view is now 4-tab** (#1038 shipped): Overview / Progress / Log / Timing. Issues #1040/#1045/#1048 add content to this simplified structure — don't recreate removed tabs.
- **LangGraph internal node name filtering**: Hide UUID slots, `__dunder__`, `fan_out`; show user nodes as snake_case→Title Case via `activityHumanNodeName()`. Backend drops `Runnable*` LCEL nodes via `_is_internal_langchain_node()` in runner.py. Applies to: #1040, #1045, #1048.
- **PDFZoomController bridge**: `fitToWindow` uses `scaleFactorForSizeToFit`, NOT re-enabling `autoScales` (avoids #588 re-fit regression). Applies to: #1024, #928.
- **`confirmationDialog` beats `alert(isPresented:presenting:)`** on macOS inside `List(selection:)` — alert races on same-tick `@Published` updates and silently skips. Use `confirmationDialog` for destructive actions. Applies to: #916, #1036.
- **`@State` parent properties invisible to child views** — pass `browserSelection`, `detailDocument` explicitly as `let`/`Binding`; child views cannot see parent `@State` directly. Applies to: #1032, #1045.
- **`WorkflowExecutionObserver.workflowCompletedCount`** is the canonical "data may be stale" tick — subscribe via `.onChange` instead of adding manual refresh buttons. Applies to: #1052, #1071, #916.
- **Empty list is not None**: `inputs["files"] = []` passes `is not None` and short-circuits fallback chain; use `if raw_files:` not `if raw_files is not None:` in nodes with Priority 1/2/3 fallback. Applies to: #926, #1111.
- **`cancelExecution` must mirror `endExecution` archive logic**: Any path removing from `activeExecutions` must also archive to `completedExecutions`. Applies to: #1044.
- **Top blast-radius nodes** — run `get_blast_radius` before touching: `Database`, `KnowledgeClaim`, `KnowledgeEntity`, `Document`, `LLMConfig`.

## Build / Test / Lint Commands (verbatim)

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

**Three-leg Swift check is mandatory** before marking any Swift issue complete:
1. `swiftlint lint fichero/fichero/`
2. Xcode MCP `BuildProject` (use `XcodeListWindows` for `tabIdentifier`)
3. Xcode MCP `RunAllTests`

## Code Navigation — jCodemunch First, ALWAYS

**Never use Read/Grep/Glob/Bash(find/ls) to explore source.** Use jCodemunch tools:

| Task | Tool |
|---|---|
| Opening move for any issue | `plan_turn { repo: "dtubb/fichero", query: "...", model: "claude-sonnet-4-6" }` |
| Find symbol by name | `search_symbols { query: "...", language: "swift" }` |
| File structure before edit | `get_file_outline { path: "..." }` |
| Symbol source | `get_symbol_source { symbol_id: "..." }` |
| Impact of changing X | `get_blast_radius { symbol_id: "..." }` |
| Who imports a file | `find_importers { path: "..." }` |
| Where is name used | `find_references { name: "..." }` |

**Read is allowed ONLY** immediately before `Edit`/`Write` on a file you already located via jCodemunch.

## Dependency Order Notes

- **#730 → #1036**: Backend SVO fields (#730) must exist before frontend SVO chips (#1036).
- **#1038 done → #1040, #1045, #1048**: All three Activity tab issues can now proceed; #1038 simplified the tab structure.
- **#768 → #797 → #1059**: Migrate provider type (#768), add submenu (#797), then consolidate all pickers (#1059).
- **#868 → #1059**: LLMProvider abstraction layer (#868) is a structural gate for the consolidated picker (#1059).
- **#1024 → #928**: PDF zoom toolbar (#1024) provides the infrastructure before adding loupe/magnifier (#928).
- **#874 → #1102 → #916**: Entity type registry (#874) and epistemic status registry (#1102) both gate user CRUD (#916).
- **#1031 + #1071**: Companion — #1031 fixes KG viewer navigation, #1071 adds document-scoped inspector filtering.
