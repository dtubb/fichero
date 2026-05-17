# Worker Digest — 0.0.2 backend loop
# Generated: 2026-05-17

## Branch + Milestone Context

Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2`)
Milestone: 0.0.2 backend fixes and small features. Daniel is actively testing this build.
Do NOT start 0.0.3 work. All commits go directly to the `0.0.2` branch — no per-task branches.
Conventional commits required: `feat:`, `fix:`, `chore:`, etc. Always reference the GitHub issue number.

## Queue Summary (30 issues)

| # | Area | Title | Est tokens |
|---|------|-------|-----------|
| #840 | backend | Save per-chunk catalogue summaries as catalogue.chunk.N | 25 k |
| #984 | backend | Promote SVO from KnowledgeClaim.metadata to top-level columns | 15 k |
| #801 | backend | Chunk summarize/rewrite/analyze/classify tools | 30 k |
| #873 | backend | pytest integration test: workflow e2e | 20 k |
| #925 | backend | OCR cleanup workflow step (dehyphenate + column-rejoin) | 22 k |
| #1096 | backend | Catalogue: case grouping sub-groups | 25 k |
| #1097 | backend | Catalogue: HITL confirmation for ambiguous groupings | 28 k |
| #1098 | backend | Catalogue: bulk fan-out for 500 folders | 35 k |
| #971 | backend | Cross-page paragraph overlap for NER | 20 k |
| #1115 | backend | KG-write as explicit workflow node | 30 k |
| #1124 | backend | Hermeneutics controlled predicate vocabulary | 18 k |
| #924 | backend | Citation extraction with role-tagged entities | 35 k |
| #974 | backend | Citation graph: in-text → bibliography → claim | 40 k |
| #1118 | backend | NER multi-provider abstraction | 40 k |
| #868 | backend | LLMProvider abstraction layer | 50 k |
| #874 | backend | User-extensible entity type registry | 45 k |
| #1108 | backend | MCP server: expose engine to agents | 35 k |
| #975 | backend | Structured transcript ingest (SRT/VTT) | 25 k |
| #926 | backend | Translation + modernization workflow nodes | 22 k |
| #970 | backend | OCR bounding boxes from Apple Vision | 25 k |
| #1049 | swiftui | Workflow editor: nodes too far apart | 12 k |
| #1042 | swiftui | Workflow editor: missing merge→catalogue edge | 15 k |
| #1040 | swiftui | Activity: wrong node shown as running | 15 k |
| #1044 | swiftui | PDF per-page progress not visible | 20 k |
| #1036 | swiftui | Claim SVO display: tappable chips | 15 k |
| #1034 | swiftui | KG entities pane width not persisted | 12 k |
| #1070 | swiftui | Pane widths jump between views | 12 k |
| #961 | swiftui | Console hygiene: NaN + FocusedValue warnings | 10 k |
| #1031 | swiftui | KG claim source link: page-child parent lookup | 18 k |
| #1085 | blocked | Maps importer: pair .iffy.json sidecar at ingest | 20 k |

## Top 5 Architectural Invariants

1. **0.0.x no-migration rule** — schema changes go directly into `db.py` `_ensure_table` via the Pydantic model field. Never add `ALTER TABLE ADD COLUMN` for a column already in the Pydantic model. Fresh DBs pick it up automatically; existing DBs need the column added to `_ensure_table` only.

2. **Pydantic-only DB writes** — all INSERT/UPDATE/UPSERT must go through the Pydantic model write path in `db.py`. No raw SQL writes outside `db.py`. Bypasses silently omit declared fields on `model_dump()` (see memory: `feedback_pydantic_field_must_be_declared`).

3. **Artifact pattern** — workflow node outputs are persisted as `Artifact` rows. Use the `Artifact` model; follow namespaced type conventions (`catalogue.chunk.N`, `catalogue.narrative`, `transcription`, etc.). Catalogue node emits artifacts; KG population is a side-effect of `extract_all`, not catalogue.

4. **PYTHONPATH must be set** — every Python command requires `PYTHONPATH=fichero-engine/src`. Omitting it produces misleading import errors. Set it on every shell invocation.

5. **Workflow runs on the main FastAPI event loop** — `_run_workflow_in_background` is a `create_task` on the main loop. Any sync-blocking call inside a node freezes the entire backend. Use `asyncio.to_thread` for blocking I/O inside nodes.

## Relevant Pitfalls

- **Verify the issue isn't already fixed** — open GitHub status ≠ unfinished code. Search the codebase + check tests before implementing. Fichero has a strong fixed-but-not-closed pattern.
- **Pydantic field must be declared** — `extra="allow"` lets runtime writes succeed silently but `model_dump()` only serializes declared fields. Always add both the Pydantic field AND the `_ensure_table` column together.
- **Empty list ≠ None** — use `if raw_value:` not `if raw_value is not None:` for optional list inputs with fallback chains.
- **Catalogue writes KG via extract_all** — `catalogue` node only emits the readable artifact; `extract_all` is what writes `KnowledgeEntity`/`KnowledgeClaim`. Don't duplicate KG writes in catalogue.
- **KG god nodes — check blast radius first** — `Database`, `KnowledgeClaim`, `KnowledgeEntity`, `Document`, `LLMConfig`, `Artifact` have high fan-out. Run `get_blast_radius` before touching them.

## Build / Test / Lint Commands

```bash
# Backend server
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Python tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived

# Python lint
ruff check fichero-engine/src/

# Swift lint (if touching SwiftUI)
swiftlint lint fichero/fichero/
```

## jcodemunch Reminder

Worker MUST use jcodemunch for ALL code exploration. NEVER use Read/Grep/Glob/Bash(find/ls) on source files. (Migrated from trace-mcp 2026-05-17.)

**Opening move:** `mcp__jcodemunch__plan_turn { repo: "local/fichero-engine-9ae88c40", query: "<issue title>", model: "claude-haiku-4-5" }` — returns confidence + recommended files in one call.

| Need | Use |
|------|-----|
| Find a function/class | `search_symbols { query: "...", language: "python" }` |
| String/comment search | `search_text { query: "..." }` |
| File structure before editing | `get_file_outline { path: "..." }` |
| One symbol's source | `get_symbol_source { symbol_id: "..." }` |
| Symbol + its imports (one call) | `get_context_bundle { symbol_id: "..." }` |
| Who imports this file | `find_importers { path: "..." }` |
| Where is this name used | `find_references { name: "..." }` |
| What breaks if I change X | `get_blast_radius { symbol_id: "..." }` |
| Class hierarchy | `get_class_hierarchy { class: "..." }` |
| Repo overview | `get_repo_outline { repo: "..." }` |

Note: if a query returns `negative_evidence` or `verdict: no_implementation_found`, the feature likely doesn't exist — report the gap. Do NOT keep re-searching or fall back to Grep/Read on source. After Edit/Write, PostToolUse hooks auto-reindex.
