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

### 1. Backend action registry — the ONE write path (do it right, systematically)
The app is unreleased, so we standardize the **entire** mutation surface now rather than leaving
two styles. **Every** mutation becomes a registered action; the **28 hand-rolled ops get
rewritten** onto typed + audited actions (raw `URLRequest`/`additionalProperties` silently loses
writes under Pydantic `extra="allow"` — constitution rule #4, and how merge broke — so none
survive). The ONE thing we wrap-not-rewrite is each route's proven **business logic** (merge's
reconciliation algorithm, the extraction pipeline): re-deriving correct algorithms risks
regressions for no gain. So: rewrite all the **plumbing** to one uniform audited path; keep the
**algorithms** intact behind it. **Test-first per domain** — capture current behavior in a test,
refactor onto the action layer, keep it green, then add audit/undo assertions.

Introduce an `ActionRegistry` that routes delegate to:

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
2. **Route ALL mutations through the registry, test-first, domain-by-domain**: start with
   **entity.merge** (exhibit A), then sweep every domain — **rewriting all 28 hand-rolled ops**
   (the 19 `ArtifactServiceGenerated` + 8 image-editing) onto typed + audited actions, and threading
   the ~67 already-typed ones through `invoke`. Each action gets a test that captures current
   behavior first, stays green through the refactor, then asserts the persisted effect + audit row.
   Several waves; one domain per worker; full coverage, not just the priority subset.
3. **Undo**: generalize audit-undo + `POST /api/actions/audit/{id}/undo` (backend) → **⌘Z
   UndoManager** wiring (frontend).
4. **Chat tools**: expose registry as agent tools (#1847).
5. **App Intents**: expose registry as App Intents / Shortcuts / Spotlight (#1837).
6. **Define the 5 missing actions** (annotation duplicate/merge/relink, search reindex, workflow
   single-run).

## Constraints
- Engine may be remote → actions go over OpenAPI/HTTP, never local paths.
- **Rewrite the plumbing, wrap the algorithms.** All 28 hand-rolled ops get rewritten onto typed +
  audited actions; routes' proven business logic is wrapped, not re-derived (no gratuitous algorithm
  rewrites). This is consistent with the iterate-not-replace rule: we retire *genuine wrong-pattern
  duplication* by collapsing onto the canonical audited path — we don't build a parallel system.
- **Test-first, no false greens:** capture behavior before refactor; the full unit suite is the gate
  after any change to a shared file (change_stream/db/registry).
- Milestone-at-a-time: the registry+audit core (step 1) unblocks the rest.
