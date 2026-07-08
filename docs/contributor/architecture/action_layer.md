(AI generated. Not reviewed.)

# Action Layer — Current Architecture

**Status:** BUILT core, with ongoing route-by-route adoption. This page
describes what is on `main` today and marks remaining rollout work as planned.

## What exists now

Fichero has a shipped backend action registry in
`fichero-engine/src/fichero/actions/registry.py`. The registry is the canonical
audited mutation path for routes that have been folded onto it.

The core pieces are built:

- `ActionContext`: carries `actor`, `origin_window`, `run_id`, and
  `library_path`.
- `ActionResult`: returns `ok`, `result`, `audit_id`, and `changed_domains`.
- `ChangeSpec`: actions return audit payload (`before`, `after`, `target_ids`)
  and change-stream payload (`emit_type`, typed id lists, optional `emit_fn`).
- `registry.invoke(...)`: validates params, enforces write auth, executes the
  action, writes `ActionAudit`, then emits the observable-layer change event.

This is not just a design sketch. The registry code is live and used by shipped
mutation routes such as:

- documents in `api/routes/documents.py`
- claims in `api/routes/claims.py`
- notes in `api/routes/notes.py`
- entities in `api/routes/entities.py`
- bookmarks in `api/routes/bookmarks.py`
- saved searches in `api/routes/search.py`
- room writes in `api/routes/mind_palace.py`

## Actual invoke contract

`registry.invoke(...)` does **not** compute separate before/after snapshots on
its own. The built contract is:

1. look up the registered action by name
2. validate the raw params against the action's Pydantic model
3. enforce write access through `authz.py`
4. run `execute(db, params, ctx) -> (result, ChangeSpec)`
5. write an `ActionAudit` row from the returned `ChangeSpec`
6. emit the observable-layer event from the same `ChangeSpec`
7. return `ActionResult`

That detail matters because the action implementation can include ids it
created in `ChangeSpec.after`, which a blind registry snapshot could not.

## Atomicity on current main

The registry now has an `atomic` flag on each action registration. For normal
actions (`atomic=True`, the default), `registry.invoke(...)` wraps the execute +
audit write in `db.transaction()`. That means an audit-write failure rolls back
the mutation for actions using the default atomic path.

Emission is intentionally **best-effort after audit**:

- `ActionAudit` write failure is fatal
- `emit_change(...)` failure is logged and does not roll back the committed
  mutation

This matches the shipped split between durable mutation history and live UI
observer updates.

## Eager schema reconciliation on the write path

The other part of the current write-path hardening lives in
`fichero-engine/src/fichero/db.py`.

`Database.save(...)`, `save_many(...)`, `delete(...)`, and the main query/count
helpers call `_ensure_table(...)` before using a model's table. `_ensure_table`
does two things on current `main`:

- `CREATE TABLE IF NOT EXISTS ... PRIMARY KEY (id)` for first use on a
  connection
- reconcile missing declared Pydantic fields by issuing idempotent
  `ALTER TABLE ... ADD COLUMN ...` statements for columns that are not yet in
  the existing DuckDB table

That means schema reconciliation is eager at the normal typed DB boundary, not
a separate manual "remember to run an upgrade step first" phase for ordinary
additive model changes.

This does **not** replace real migrations for destructive or app-db changes.
The accurate current rule is narrower:

- additive library-table fields are usually picked up by the model declaration
  plus `_ensure_table(...)`
- destructive reshapes, data backfills, and app-db changes still need explicit
  migration handling

## What "single audited write path" means in practice

For a migrated mutation, the route should:

- build or resolve an `ActionContext`
- call `registry.invoke(...)`
- let the registered action return a `ChangeSpec`

The action should:

- perform the business mutation
- return the durable undo/audit payload in `before` / `after`
- return the observer payload in `emit_type` and typed changed-id lists

This is the invariant documented in
`docs/contributor/backend-development-standards.md`: a complete mutation must
do both audit and change-stream on the same path.

## Current rollout boundary

The registry core is built, but not every historical mutation in the engine has
been normalized yet. Treat these categories separately:

- **Built and canonical:** the folded routes already using `registry.invoke(...)`
- **Still being migrated:** older direct-write routes that have not yet been
  folded onto the action layer

So the accurate statement on current `main` is:

- the action layer is real and production code
- it is the standard path for migrated mutations
- full route-surface adoption is still ongoing, not finished

## Why other docs refer to it

This action layer is the write-side counterpart to the observable data layer:

- `ActionAudit` gives durable mutation history and undo metadata
- `emit_change(...)` gives live observer refresh
- chat tools and other automation surfaces can reuse the same mutation path by
  calling `registry.invoke(...)` instead of inventing a second writer

That is why architecture docs for chat tools, node-model folds, and multi-user
authorization all point back to the action registry.
