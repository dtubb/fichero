# 5. Actions, Audit, and Undo


The action registry is the audited write path for mutations: a route handler resolves an `ActionContext` and calls `registry.invoke(name, params, ctx)` instead of writing to DuckDB directly. The registry is live for the majority of backend domains (EPIC \#1848) — including ingest, whose routes wrap `import_file_impl`/`import_folder_impl` in the `import.file`/`import.folder` actions. A few write paths are still being migrated; **new mutations go through the registry.**

`registry.invoke(name, params, ctx)`:

1.  resolves the named action
2.  snapshots the affected rows before the change
3.  runs the action’s `execute` implementation
4.  snapshots the affected rows after the change
5.  writes an `action_audit` record
6.  emits a change event to all subscribers

This fixes an entire class of bugs at once: mutations that silently succeed but leave the UI stale, chat-tool and App Intents invocations with no audit trail, and the absence of a reliable undo path. Actions are named `<domain>.<verb>`: `entity.merge`, `import.file`, `claim.delete`, `activity.cleanup`.

### The two invariants

Every engine mutation must satisfy both:

1.  **Audit** — go through `registry.invoke(...)` so an `ActionAudit` row is written.
2.  **Change-stream** — emit an observable-layer change so views and other observers update.

Doing only one is a bug: audit without change-stream leaves stale UI observers; change-stream without audit silently drops the durable record. The registered action returns a `ChangeSpec` carrying both the audit payload (`before`, `after`, `target_ids`) and the observer payload (`emit_type` and the changed ids); `ActionRegistry.invoke` performs validate → execute → audit → emit on one path.

### How to add a new action

Params are a Pydantic model; the function returns a `(result, ChangeSpec)` pair:

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

The route handler is then one call:

    from fichero_server.actions.registry import registry

    @router.post("/documents/{doc_id}/tags")
    def add_tag(doc_id: str, tag: str, request: Request, db=Depends(get_db)):
        ctx = ActionContext(actor=request.state.user, origin_window=request.headers.get("X-Window-Id"))
        result = registry.invoke(db, "document.tag", {"doc_id": doc_id, "tag": tag}, ctx)
        return result

When adding a real action, copy a shipped audited pair rather than writing from scratch: `claim.create` / `claim.patch` / `claim.delete` in `api/routes/claim/claims.py`, `document.create` / `document.move` in `api/routes/document/documents.py`, `note.create` in `api/routes/research/notes.py`, or `entity.create` in `api/routes/entity/entities.py`.

### The audit record

Every invoke writes a row to `action_audit`: `id`, `action_name`, `actor` (`ui` / `chat` / `workflow` / `import` / `system` / a device id), `target_ids`, `params`, `before`, `after`, `run_id`, `created_at`, `undone`, `inverse_of`, plus the tamper-evidence fields `chain_seq`, `prev_hash`, and `row_hash`. The before/after snapshots answer “what changed and when” without a separate diff computation; the hash fields form a per-database append-only chain (the HMAC audit chain is shipped — `actions/audit_chain.py`, \#2127).

### Generic invocation and undo

Any caller — a route handler, a chat tool, an App Intent, a test — can invoke an action through the generic endpoint:

    POST /api/actions/invoke
    { "name": "entity.merge", "params": { "source_id": "abc", "target_id": "xyz" } }

This is intentional: chat tools and App Intents do not get special code paths. Undo:

    POST /api/actions/audit/{audit_id}/undo

The endpoint replays the registered `invert` against the audit row’s before/after payloads, writes a new audit row named `<original>.undo`, and marks the original `undone=true`. The undo is itself audited. Undo is only available for actions registered `undoable=True`; anything else returns `422`.

### Testing expectations

Every action needs at least one test that (1) invokes via `registry.invoke` (not the route), (2) asserts the persisted effect by querying the DB, and (3) asserts an `action_audit` row with the correct `action_name` and `actor`.

### Gotchas

- **Some route tests call handlers directly** (no FastAPI `Depends` resolution). The claim/entity routes use `_resolve_action_ctx(...)` and tolerate unresolved `Depends(...)` sentinels — keep audited routes callable both via HTTP and via direct unit-test invocation.
- **The duplicate-path guard**: `scripts/check_duplicate_paths.py` fails on a second HTTP handler or KG-write path for the same concern. Collapse to one canonical path, or add an allowlist entry with an explicit reason.
- Request-model tightening to `extra="forbid"` is still open work (#2822).

What not to do: no direct DuckDB writes from route handlers, and no hand-rolled Swift `URLRequest` mutations that bypass the registered path. Audit, undo, and change events only work when every mutation goes through the registry.
