# Worker Digest — fichero 0.0.2

## Branch + milestone
- Working branch: `0.0.2` (commit directly — no per-task branches).
- Worktree root: `/Users/danieltubb/code/fichero-0.0.2`.
- Autonomous: commits + PRs allowed. Push, open PR, merge yourself. Never push to `main`.
- Two-ahead rule: 0.0.1 released, 0.0.2 testing (this branch is for bug-cluster fixes), 0.0.3 building.

## Tooling — trace-mcp is MANDATORY

**⚠️  CRITICAL: Use ONLY trace-mcp tools for code exploration. NEVER use Bash ls/find/cat, Read, Grep on .py/.ts files. The system will block these.**

### Examples for this queue:

**#841 (middleware fix):**
```
search("loopback", language="python")  # Find loopback middleware
get_outline("fichero-engine/src/fichero/api/main.py")  # See file structure
get_symbol("fqn_of_middleware_function")  # Read it
```

**#840 (catalogue artifacts):**
```
search("catalogue", language="python", kind="function")
get_symbol("src/fichero/workflows/nodes/catalogue.py::catalogue_node")
get_outline("src/fichero/models/artifact.py")
```

### Complete tool reference:

| Need | Tool |
|---|---|
| Find a symbol | `search` (set `fusion=true`) |
| File shape before edit | `get_outline <path>` |
| One symbol's source | `get_symbol <fqn>` |
| Blast radius | `get_change_impact` |
| Callers / callees | `find_usages`, `get_call_graph` |
| Interface impls | `get_type_hierarchy` |
| Tests for a symbol | `get_tests_for` |
| Task kickoff | `get_task_context` |

Read/Grep/Glob allowed ONLY for `.md`, `.json`, `.yaml`, `.toml` or immediately before `Edit` of a file already located via trace-mcp.

After every Edit/Write, call `register_edit` to keep the index fresh.

## Top architectural invariants for THESE issues

1. **DuckDB writes go through Pydantic models.** All persistence happens in `fichero-engine/src/fichero/db.py`. Raw SQL outside `db.py` is a bug (this is the entire premise of #1112 / #1117). New columns: add the field on the Pydantic model and `_ensure_table` picks it up — 0.0.x is the no-migration regime.
2. **Pydantic field must be declared.** `extra="allow"` lets a runtime write succeed but `model_dump()` only serializes declared fields — so the value disappears from the next read. Always add a real field, not metadata. (See MEMORY: `feedback_pydantic_field_must_be_declared`.)
3. **Workflow runs on the main event loop.** `_run_workflow_in_background` is a `create_task` on the FastAPI loop — any sync-blocking call in a node freezes the backend (#1000 root cause). Workflow tool nodes execute on a worker thread with a per-thread `db_manager` and DBWriter.
4. **KG/entity logic belongs in the backend.** Frontend only renders. Aggregation, dedup, scoping, summary are backend endpoints. Shared KG helpers live in `fichero/kg/_common.py` (`enum_value`, `slug_verb`, `extract_svo`) — reuse `slug_verb` to keep SPARQL ↔ aggregation parity.
5. **Catalogue writes KG via `extract_all`.** The `extract_all` node populates `KnowledgeEntity` + `KnowledgeClaim`; the catalogue node only emits the readable artifact. Extractor shared instruction strings (`_SECTIONS`) drive both per-section tools AND `extract_all` — fix prompt quality there, not in `extract_all.py`.

## Common pitfalls (filtered to this queue)

- **Empty list ≠ None** — `inputs["files"] = []` passes `is not None` and short-circuits the Priority 1/2/3 fallback chain. Use `if raw_files:` not `if raw_files is not None:`.
- **Endpoint filter defaults vs seed-data drift** — strict-equality query params silently hide rows when seed JSONs change shape. Default to `Optional`, audit on every seed change (relevant to #1102, #1117).
- **HTTP header arbitrary text** — uvicorn rejects non-ASCII / multi-line header values. base64 or percent-encode; prefer body over header.
- **TestClient loopback** — #841: middleware rejects `testserver` Host header.
- **Pipe exit-code shadowing** — `cmd | head; echo $?` reads `head`'s exit, not `cmd`'s. Use `set -o pipefail` or `${PIPESTATUS[0]}`.
- **Verify "open" ≠ "unfinished"** — fichero has a strong fixed-but-not-closed pattern. Before implementing any queued issue, `search` for the relevant symbol/tests and confirm the work isn't already merged. If it is, mark `done` with the existing commit hash and move on.

## Build / test / lint (verbatim from CLAUDE.md)

```bash
# Backend server
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Python tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived

# Python lint
ruff check fichero-engine/src/
```

Three-leg check (build + test + lint) is mandatory before commit.

## Commit + PR

- Conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`. Always reference the issue: `fix: ... (#1117)`.
- One concern per commit.
- Push → create PR → merge PR yourself.

## Queue protocol

- Read `agent-work/queue.md`. Pick the first `status: pending` issue.
- Mark `status: in_progress` BEFORE starting work.
- On finish: set `status: done`, fill `commit:` (short hash) and `completed_at:` (ISO).
- On block: set `status: blocked` + `blocked_reason:` (one sentence) and continue to next pending issue.
- Never edit shared STATE.md / MEMORY.md / HISTORY.md from inside a worker iteration.

## Reminder

Use trace-mcp tools. Not Read. Not Grep. Not Glob. Not `ls`. Not `find`.
