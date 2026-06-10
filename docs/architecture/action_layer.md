# Action Layer — One Audited Action (EPIC #1848)

**Status:** PROPOSED — awaiting Daniel's approval before implementation.
**Date:** 2026-06-10. **Twin of:** the Observable Data Layer (reads/change-stream); this is the writes/audit side.

## The idea

Every app capability that changes state becomes ONE named, typed **action** in a backend
registry, exposed once over the OpenAPI contract. The same action is then reached five ways:
**UI buttons · chat tools (#1847) · App Intents (#1837) · tests · audit log**. One definition,
one assertion, one record of who/when/how — and undo falls out of the audit.

## Why (it answers four threads at once)

- **Merge-bug class** → today there are ~95 mutating call sites, ~28 hand-rolled (raw
  URLRequest / `additionalProperties`), each its own untested path. One action + one test = caught.
- **UI verification** → a button that just calls a named action is testable: the test (and the
  chat agent) call the same action and assert the persisted effect. Finishes #1230/#1810 but
  asserts via the action contract, not pixel-poking.
- **Agentic chat (#1847)** → the registry IS the tool set.
- **Who-changed-what + undo** → the action layer is the single choke point to log actor +
  before/after, and the before/after IS the undo payload. Decoupled from permissions (#1844).

## Inventory (2026-06-10 audit) — what exists today

~95 distinct mutating actions across 18 domains (entity, claim, annotation, note, document,
batch, workflow, provider, conversation, saved-search, bibliography/citation, classification/
ontology, image-editing, import, interpretation, action, …). ~67 use the typed OpenAPI client;
**~28 are hand-rolled.** The 19 priority hand-rolled targets live in `ArtifactServiceGenerated`
(claim-links, claim transitions, classification/claim-kind/epistemic-status CRUD, entity aliases,
bibliography metadata/import/export). Image-editing (8 ops) hand-rolls for binary PNG previews.

**5 capabilities lack a single endpoint** (need an action defined): duplicate/merge/relink
annotation, UI search-index refresh, single-shot "run workflow" (today = batch+execute two-step).

Most non-annotation mutations have **no test asserting their effect**. (Annotations are the
exception — `AnnotationServiceTests.swift`.)

## Design

### 1. Backend action registry (iterate, don't replace)
Do **NOT** collapse 95 routes into one mega-endpoint. Introduce an `ActionRegistry` that existing
routes delegate to:

```
@action("entity.merge", params=MergeEntitiesParams, undoable=True)
def merge_entities(db, params, ctx) -> ActionResult: ...
```

- Each action: a stable **name** (`<domain>.<verb>`), a typed Pydantic **params** model, an
  `execute(db, params, ctx)`, and (if undoable) an `invert(before, after) -> Action|None`.
- Existing route handlers call `registry.invoke(name, params, ctx)` instead of mutating directly.
  The route signature stays — minimal churn, OpenAPI unchanged for now.
- `registry.invoke` is the choke point: it snapshots **before**, runs execute, snapshots **after**,
  writes the **audit record**, and `emit_change(...)` (reusing the observable layer). One place.
- A thin `POST /api/actions/invoke {name, params, actor, origin_window}` exposes the whole registry
  generically (this is what chat tools + App Intents + UI-action tests drive).

### 2. Audit record (reuse provenance #1832)
`action_audit`: `id, action_name, actor, target_ids[], params, before, after, run_id, ts, undone`.
Actor = device/session id now; a real user id once multi-user (#1844) lands. `before/after` are the
domain-object snapshots needed to invert. Generalizes the existing entity `undoEntityAudit`.

### 3. Undo
- Backend: `POST /api/actions/audit/{id}/undo` applies the action's `invert(before, after)` (itself
  an audited action → redo works, and undo-of-undo). Generalize entity audit-undo to all undoable
  actions.
- Frontend: register each invoked action with macOS **`UndoManager`** per window so **⌘Z / ⌘⇧Z**
  work with real names ("Undo Merge Entities"). The view calls the action → gets the audit id →
  registers an undo that POSTs the undo endpoint. The observable change-stream propagates the
  undone state to other windows automatically.

### 4. Per-action UI-action test
For each registered action, a test invokes it (via `/api/actions/invoke` or the typed route) and
asserts (a) the persisted effect and (b) an audit row was written. This is the durable
replacement for "does this button actually work".

### 5. Chat tools (#1847) + App Intents (#1837)
Generate both from the registry — same verbs, same params schemas. No second definition.

## Build order (sub-issues)

1. **Registry + audit core** (backend keystone): `ActionRegistry`, `@action`, `ActionContext`,
   `action_audit` table (via `db.py` `_ensure_table`, 0.0.x no-migration), `invoke` choke point
   (snapshot→execute→snapshot→audit→emit), generic `POST /api/actions/invoke`. + tests.
2. **Route mutations through the registry, exhibit-A first**: start with **entity.merge** (the
   merge bug), then fold the 19 hand-rolled `ArtifactServiceGenerated` ops onto typed + audited
   actions. Per-action UI-action test asserting effect + audit. (Several waves; one domain per worker.)
3. **Undo**: generalize audit-undo + `POST /api/actions/audit/{id}/undo` (backend) → **⌘Z
   UndoManager** wiring (frontend).
4. **Chat tools**: expose registry as agent tools (#1847).
5. **App Intents**: expose registry as App Intents / Shortcuts / Spotlight (#1837).
6. **Define the 5 missing actions** (annotation duplicate/merge/relink, search reindex, workflow
   single-run).

## Constraints
- Engine may be remote → actions go over OpenAPI/HTTP, never local paths.
- Iterate-not-replace: routes delegate to the registry; we do not rewrite the route surface.
- Milestone-at-a-time: pull these steps in as each milestone needs them; the registry+audit core
  (step 1) unblocks the rest.
