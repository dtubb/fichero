(AI generated. Not reviewed.)

# Action Registry

> Architecture status: in-progress as of mid-2026 (EPIC #1848). The registry is live for the majority of backend domains. Undo, chat-tool bindings, and App Intents integration are still being wired up.

## What It Is

The action registry is the single audited write path for every mutation in Fichero. No route handler writes to DuckDB directly. Instead, it calls `registry.invoke(name, params, ctx)`, which:

1. resolves the named action
2. snapshots the affected rows before the change
3. runs the action's `execute` implementation
4. snapshots the affected rows after the change
5. writes an `action_audit` record
6. emits a change event to all subscribers

This pattern was introduced to fix an entire class of bugs at once: the merge-bug class (mutations that silently succeeded but left the UI stale), missing UI verification (no before/after diff available), chat-tool and App Intents invocations that had no audit trail, and the absence of a reliable undo path.

Actions are named `<domain>.<verb>`: `entity.merge`, `document.ingest`, `claim.delete`, and so on. Every domain (documents, entities, claims, folders, workflows, sources, artifacts, tasks) has its actions registered at startup.

## How to Add a New Action

### 1. Define the action

In the relevant domain module, decorate a function with `@action`:

```python
from fichero.actions import action, ActionContext

@action("document.tag", params={"doc_id": str, "tag": str}, undoable=True)
async def tag_document(db, params: dict, ctx: ActionContext):
    doc_id = params["doc_id"]
    tag = params["tag"]
    await db.execute(
        "UPDATE documents SET tags = list_append(tags, ?) WHERE id = ?",
        [tag, doc_id],
    )
    return {"doc_id": doc_id, "tag": tag}
```

`params` declares the expected keys and types. `undoable=True` means the registry will also call `invert` when an undo is requested.

### 2. Implement invert (if undoable)

```python
@action("document.tag", params={"doc_id": str, "tag": str}, undoable=True)
async def tag_document(db, params: dict, ctx: ActionContext):
    ...

@tag_document.invert
async def _(db, before: dict, after: dict, ctx: ActionContext):
    doc_id = before["id"]
    tag = after["tag"]
    await db.execute(
        "UPDATE documents SET tags = list_filter(tags, t -> t != ?) WHERE id = ?",
        [tag, doc_id],
    )
```

`before` and `after` are the snapshots taken by the registry around the `execute` call.

### 3. Call it from a route handler

```python
from fichero.actions import registry

@router.post("/documents/{doc_id}/tags")
async def add_tag(doc_id: str, tag: str, request: Request, db=Depends(get_db)):
    ctx = ActionContext(actor=request.state.user, origin_window=request.headers.get("X-Window-Id"))
    result = await registry.invoke("document.tag", {"doc_id": doc_id, "tag": tag}, ctx)
    return result
```

That is the entire route handler. No direct DB writes.

## The Audit Record

Every `registry.invoke` call writes a row to `action_audit`:

| Column | Type | Description |
|---|---|---|
| `id` | UUID | primary key |
| `action_name` | TEXT | e.g. `entity.merge` |
| `actor` | TEXT | user id from `request.state.user` |
| `target_ids` | TEXT[] | IDs of the affected rows |
| `params` | JSONB | the params dict passed to invoke |
| `before` | JSONB | row snapshot(s) before execute |
| `after` | JSONB | row snapshot(s) after execute |
| `run_id` | UUID | groups actions from one request/session |
| `ts` | TIMESTAMPTZ | wall-clock time of the action |
| `undone` | BOOLEAN | true once an undo has been applied |

The `before`/`after` fields make it possible to answer "what changed and when" without a separate diff computation.

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
    await registry.invoke("document.tag", {"doc_id": test_document.id, "tag": "important"}, ctx)

    row = await db.fetchone("SELECT * FROM documents WHERE id = ?", [test_document.id])
    assert "important" in row["tags"]

    audit = await db.fetchone(
        "SELECT * FROM action_audit WHERE action_name = 'document.tag' ORDER BY ts DESC LIMIT 1"
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
