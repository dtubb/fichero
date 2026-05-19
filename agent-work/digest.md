# Worker Digest — 0.0.2 autonomous loop
# Generated: 2026-05-18

## Branch + Milestone Context

Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2`). Daniel is actively testing this milestone.
Commit all work directly to `0.0.2` — no per-task branches.
Push → create PR → merge it yourself (AUTONOMOUS_PRS: true).

**Done this session**: #879, #750, #759, #758, #783, #795, #745, #1046, #1043, #1008, #746, #747
**Blocked**: #873 (arch decision), #1097 (depends #873), #971 (arch review)

## Top 5 Architectural Invariants for These Issues

1. **0.0.x no-migration rule**: New DB columns go into `_ensure_table` via the Pydantic model field only. Never add `ALTER TABLE ADD COLUMN` migrations for columns already in the model. Only historical structural migrations (table renames, data backfills) belong in `db_migrations.py`. Applies to: #1085, #1101, #1102, #916.

2. **Pydantic `extra="allow"` silently drops undeclared fields from `model_dump()`**: Always declare new fields on the model AND in `_ensure_table` together. Dumping declared fields into `additionalProperties` loses data. Applies to: #1102, #916, #1101, #1085.

3. **Use OpenAPI-typed fields, not `additionalProperties`**: When building Swift request bodies, use `Components.Schemas.*` typed fields — not `additionalProperties` — for any field declared in `openapi.json`. Applies to: #768, #797, #735, #1059.

4. **SidebarItem.id has type prefix `"doc:UUID"`**: Always extract `doc.id` from `.itemType` before calling backend APIs. Never pass the raw SidebarItem.id as a document UUID. Applies to: #1031, #1071, #1052, #1036, #916.

5. **slug_verb is the shared canonical verb normalizer**: New KG modules must reuse `slug_verb` from `fichero/kg/_common.py` to keep SPARQL ↔ aggregation parity. Applies to: #1111, #1036, #916.

## Pitfalls Filtered to Relevant Issues

- **`confirmationDialog` beats `alert(isPresented:presenting:)`** on macOS inside `List(selection:)` — the alert can race on same-tick `@Published` updates and silently skip presentation. Use `confirmationDialog` for any destructive action modals. (#916, #1036)
- **`@State` parent properties are invisible to child views** — pass `browserSelection`, `detailDocument`, etc. explicitly as `let`/`Binding` params; child views cannot see parent `@State` directly. (#1032, #1038, #1045)
- **`WorkflowExecutionObserver.workflowCompletedCount`** is the canonical "data may be stale" tick for KG/inspector views — subscribe via `.onChange` instead of adding manual refresh buttons. (#1052, #1071, #916)
- **Empty list is not None** — `inputs["files"] = []` passes `is not None` and short-circuits fallback chain; always use `if raw_files:` not `if raw_files is not None:` in nodes with Priority 1/2/3 fallback. (#926, #1111)
- **PDFZoomController bridge**: `fitToWindow` uses `scaleFactorForSizeToFit`, NOT re-enabling `autoScales` (avoids #588 re-fit regression). (#1024, #928)
- **LangGraph internal node name filtering**: Hide UUID slots, `__dunder__`, `fan_out`; show user nodes as snake_case→Title Case via `activityHumanNodeName()`. Backend drops `Runnable*` LCEL nodes at SSE source via `_is_internal_langchain_node()`. (#1040, #1045, #1048)
- **`cancelExecution` must mirror `endExecution` archive logic**: Any path that removes from `activeExecutions` must also archive to `completedExecutions`. (#764, #1044)

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

## Issue-Specific Notes

- **#743**: `langgraph` imports already done (commit `aa7a3be2`). Verify `torch`/`spacy`/`transformers` sites remain and move them.
- **#1038 → #1045 → #1048**: Do in order — #1038 restructures Activity tabs, #1045 and #1048 add content to the simplified structure.
- **#768 → #797 → #1059**: Do in order — #768 migrates the provider type, #797 adds the submenu, #1059 consolidates all picker sites.
- **#1031 + #1071**: Companion issues — #1031 fixes navigation from the KG viewer, #1071 adds document-scoped filtering in the inspector.
- **#1102 → #916**: #1102 adds epistemic status + claim kind registries; #916 (user CRUD) can reuse those registries.
- **#1111**: Reuse `slug_verb` + `enum_value` from `fichero/kg/_common.py`; expose new endpoint, don't inline rendering in existing endpoints.
- **Top blast-radius nodes** — run `get_blast_radius` before touching: `Database`, `KnowledgeClaim`, `KnowledgeEntity`, `Document`, `LLMConfig`.
