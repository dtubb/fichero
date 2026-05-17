# Worker Digest — 0.0.2 backend loop
# Generated: 2026-05-17

## Branch + Milestone Context

Branch: `0.0.2` (worktree at `~/code/fichero-0.0.2`)
Milestone: 0.0.2 backend fixes and small features. Daniel is actively testing this build.
Do NOT start 0.0.3 work. All commits go directly to the `0.0.2` branch — no per-task branches.

## Issues This Cycle

| # | Title | Est tokens |
|---|-------|-----------|
| #834 | Apple Vision OCR empty → retry at .fast level | 18 k |
| #1085 | Maps importer: pair sidecar .iffy.json with image/PDF | 20 k |
| #840 | Save per-chunk catalogue summaries as catalogue.chunk.N artifacts | 25 k |

## Top 5 Architectural Invariants

1. **0.0.x no-migration rule** — schema changes go directly into `db.py` `_ensure_table` via the Pydantic model field. Never add `ALTER TABLE ADD COLUMN` for a column already in the model. Fresh DBs pick it up automatically.

2. **Pydantic-only DB writes** — all INSERT/UPDATE/UPSERT must go through the Pydantic model write path in `db.py`. No raw SQL outside `db.py`. Violations were audited in #1112/#1117.

3. **Artifact pattern** — workflow node outputs are persisted as `Artifact` rows (use the `Artifact` model, not ad-hoc fields). Artifact types follow a namespaced convention (`catalogue.chunk.N`, `catalogue.narrative`, etc.).

4. **PYTHONPATH must be set** — every Python command requires `PYTHONPATH=fichero-engine/src`. Omitting it causes import errors that look like missing modules.

5. **Workflow runs on the main FastAPI event loop** — `_run_workflow_in_background` is a `create_task` on the main loop. Any sync-blocking call inside a node freezes the entire backend. Use `asyncio.to_thread` for blocking I/O.

## Relevant Pitfalls

- **Verify the issue isn't already fixed** — open status ≠ unfinished work. `search` the code + check tests before implementing. Fichero has a strong fixed-but-not-closed pattern.
- **Pydantic field must be declared** — `extra="allow"` lets runtime writes succeed silently but `model_dump()` only serializes declared fields. Add both the field AND the `_ensure_table` column together.
- **Empty list is not None** — always use `if raw_value:` not `if raw_value is not None:` when checking optional list inputs with fallback chains.
- **`LINK` ingest mode heuristic** — `Document.isLinked` is detected via `metadata["bookmark"] != nil`; no schema column for this.
- **Catalogue writes KG via extract_all** — the `catalogue` node only emits the readable artifact; KG population happens in `extract_all`. Don't confuse the two.

## Build / Test / Lint Commands

```bash
# Backend server
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Python tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived

# Python lint
ruff check fichero-engine/src/
```

## trace-mcp Reminder

Worker MUST use trace-mcp tools for ALL code exploration. NEVER use Read/Grep/Glob/Bash(find/ls) on source files.

| Need | Use |
|------|-----|
| Find a function | `search` (fusion=true for best ranking) |
| File structure before editing | `get_outline <path>` |
| One symbol's source | `get_symbol <fqn>` |
| Who calls X | `find_usages` or `get_call_graph` |
| What breaks if I change X | `get_change_impact` |
| Task context | `get_task_context` |
