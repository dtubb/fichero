<!-- Verified against fichero/api/routes/actions.py, actions_registry.py, models.py:ActionAudit (2026-07-18). -->

# Action Registry

> Architecture status: in-progress as of mid-2026 (EPIC #1848). The registry is live for the majority of backend domains. Undo, chat-tool bindings, and App Intents integration are still being wired up.

## What It Is

The action registry is the audited write path for mutations in Fichero: a route handler resolves an `ActionContext` and calls `registry.invoke(name, params, ctx)` instead of writing to DuckDB directly. Most domains route through it — including the ingest routes, which now wrap `import_file_impl`/`import_folder_impl` in the `import.file`/`import.folder` actions (`api/routes/ingest.py`, #3274). A few write paths are still being migrated (the status line above tracks this); new mutations should go through the registry.

`registry.invoke(name, params, ctx)`:

1. resolves the named action
2. snapshots the affected rows before the change
3. runs the action's `execute` implementation
4. snapshots the affected rows after the change
5. writes an `action_audit` record
6. emits a change event to all subscribers

This pattern was introduced to fix an entire class of bugs at once: the merge-bug class (mutations that silently succeeded but left the UI stale), missing UI verification (no before/after diff available), chat-tool and App Intents invocations that had no audit trail, and the absence of a reliable undo path.

Actions are named `<domain>.<verb>`: `entity.merge`, `import.file`, `claim.delete`, `activity.cleanup`, and so on (the ingest action is `import.file`/`import.folder`, not `document.ingest`). Domains register their actions at startup.

## How to Add a New Action

### 1. Define the action

Params are a Pydantic model, and the function returns a `(result, ChangeSpec)`
pair — the `ChangeSpec` is what lets `invoke` write the audit row and emit the
observer change from one path:

```python
from pydantic import BaseModel
from fichero_server.actions.registry import ActionContext, ChangeSpec, action

class TagDocumentParams(BaseModel):
    doc_id: str
    tag: str

def _untag_document(db, params: TagDocumentParams, ctx: ActionContext):
    ...  # remove the tag; return (result, ChangeSpec) like the forward action

@action(
    "document.tag",
    TagDocumentParams,
    domains=["document"],
    undoable=True,
    invert=_untag_document,
)
def tag_document(db, params: TagDocumentParams, ctx: ActionContext):
    before = ...  # JSON-able snapshot, becomes the undo payload
    db.execute(
        "UPDATE documents SET tags = list_append(tags, ?) WHERE id = ?",
        [params.tag, params.doc_id],
    )
    after = ...
    spec = ChangeSpec(
        domains=["document"],
        target_ids=[params.doc_id],
        before=before,
        after=after,
        emit_type="document.updated",
    )
    return {"doc_id": params.doc_id, "tag": params.tag}, spec
```

`undoable=True` with `invert=` registers the inverse function; the undo
endpoint replays it against the audit row's `before`/`after` payloads.

### 2. Call it from a route handler

```python
from fichero_server.actions.registry import registry

@router.post("/documents/{doc_id}/tags")
def add_tag(doc_id: str, tag: str, request: Request, db=Depends(get_db)):
    ctx = ActionContext(actor=request.state.user, origin_window=request.headers.get("X-Window-Id"))
    result = registry.invoke(db, "document.tag", {"doc_id": doc_id, "tag": tag}, ctx)
    return result
```

That is the entire route handler: `invoke` runs validate -> execute -> audit ->
emit. No direct DB writes in routes. When adding a real action, copy a shipped
audited pair (e.g. `claim.create` in `api/routes/claim/claims.py` or
`document.move` in `api/routes/document/documents.py`) rather than writing
from scratch.

## The Audit Record

Every `registry.invoke` call writes a row to `action_audit`:

| Column | Type | Description |
|---|---|---|
| `id` | str | primary key |
| `action_name` | str | e.g. `entity.merge` |
| `actor` | str | `ui` / `chat` / `workflow` / `import` / `system` / a device id (default `system`) |
| `target_ids` | list[str] | IDs of the affected rows |
| `params` | dict | the params dict passed to invoke |
| `before` | dict \| None | row snapshot(s) before execute |
| `after` | dict \| None | row snapshot(s) after execute |
| `run_id` | str \| None | groups actions from one request/session |
| `created_at` | datetime | wall-clock time of the action |
| `undone` | bool | true once an undo has been applied |
| `inverse_of` | str \| None | audit id this row undoes (set on undo rows) |
| `chain_seq` | int \| None | position in the per-database append-only chain |
| `prev_hash` | str \| None | previous row's `row_hash` (chain link) |
| `row_hash` | str | tamper-evident hash of this row |

The `before`/`after` fields make it possible to answer "what changed and when" without a separate diff computation. `prev_hash`/`row_hash`/`chain_seq` form a per-database append-only hash chain so the audit log is tamper-evident.

## Generic Invocation

Any caller (a route handler, a chat tool, an App Intent, a test) can invoke an action through the generic HTTP endpoint:

```
POST /api/actions/invoke
{
  "name": "entity.merge",
  "params": { "source_id": "abc", "target_id": "xyz" },
  "actor": "dtubb",
  "origin_window": "w-1"
}
```

This is intentional. Chat tools do not get a special code path. App Intents do not get a special code path. They all go through the same registry and produce the same audit rows.

## Undo

```
POST /api/actions/audit/{audit_id}/undo
```

The endpoint looks up the audit row, calls `invert(before, after)` on the registered action, and writes a new `action_audit` row with `action_name` set to `<original_name>.undo` and `undone=true` on the original row. The undo is itself audited.

Undo is only available for actions registered with `undoable=True`. Calling undo on a non-undoable action returns `422`.

## Testing Expectations

Every action must have at least one test that:

1. invokes the action via `registry.invoke` (not by calling the route directly)
2. asserts the persisted effect (query the DB and check the row changed as expected)
3. asserts an `action_audit` row was written with the correct `action_name` and `actor`

```python
async def test_tag_document_writes_audit(db, test_document):
    ctx = ActionContext(actor="test-user", origin_window=None)
    registry.invoke(db, "document.tag", {"doc_id": test_document.id, "tag": "important"}, ctx)

    row = await db.fetchone("SELECT * FROM documents WHERE id = ?", [test_document.id])
    assert "important" in row["tags"]

    audit = await db.fetchone(
        "SELECT * FROM action_audit WHERE action_name = 'document.tag' ORDER BY created_at DESC LIMIT 1"
    )
    assert audit is not None
    assert audit["actor"] == "test-user"
```

## What Not To Do

Do not write to DuckDB directly from a route handler:

```python
# Wrong
@router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: str, db=Depends(get_db)):
    await db.execute("DELETE FROM entities WHERE id = ?", [entity_id])
    return {"ok": True}
```

Do not hand-roll mutations in Swift with custom `URLRequest` calls that bypass the registered action path. All mutations on the Swift side go through the generated API client to a route that calls `registry.invoke`.

The audit chain, undo, and change events only work when every mutation goes through the registry.
