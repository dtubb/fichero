(AI generated. Not reviewed.)

# Observable Data Layer + Backend Change-Stream

**Status:** Design spec (keystone architecture) · **Date:** 2026-06-08
**EPICs:** #1851 (observers-everywhere) · #1863 (backend change-stream) · #1848 (one audited action layer) · #1072 (pure-display frontend)
**Memory:** `observable-data-layer`
**Reference pattern to generalize:** workflow-run SSE — `WorkflowStreamService` → `@Observable WorkflowExecutionObserver` (the *only* place the app already has consistent server-push).

This is the spec the migration workers (#1882–#1900, #1862) follow. It is **iterate-not-replace**: the `*Generated` service wrappers stay as the transport; we wrap them in stores and add one SSE fan-out. Nothing working is thrown away.

---

## 1. Principle

> **A view never calls a backend endpoint. It observes an `@Observable` domain store and renders what the store publishes. The store is the only endpoint accessor — it loads once, then subscribes to the per-library change-stream and updates itself on every mutation, from any source.**

This unifies three rules Daniel kept restating into one mechanism:

| Rule | Issue | What it becomes here |
|---|---|---|
| Pure-display frontend (no logic, no local paths) | #1072 / `no-local-paths-server-may-be-remote` | Views hold no fetched copies and call no endpoints; they bind to a store. |
| Observers everywhere (no stale lists after merge/edit) | #1851 | Every view observes a store; the store observes the stream. |
| Multi-window / multi-tab consistency | #1863 | One backend stream per library fans to every window's stores. |

**The data-flow contract (one direction, always):**

```
        ┌─────────────────────────── reads ────────────────────────────┐
        │                                                               │
   ┌────▼─────┐   named action    ┌──────────┐   POST/PATCH   ┌─────────┴────────┐
   │  View    │ ────────────────► │  Store   │ ─────────────► │  Backend (route) │
   │ @Bindable│                   │@Observable│                │  + audit (#1848) │
   └────▲─────┘                   └────▲─────┘                 └─────────┬────────┘
        │                              │                                 │ emits
        │  SwiftUI re-render           │  applies event                  │ {type,ids,…}
        │  (Observation)               │                                 ▼
        │                         ┌────┴───────────────┐         ┌──────────────┐
        └─────────────────────────┤ LibraryChangeStream │◄────────┤ SSE /events  │
                                  │   Observer (1/window)│  SSE    │ (per library)│
                                  └─────────────────────┘         └──────────────┘
```

A view **never** writes its own `@State` list after a mutation. It dispatches a named action; the backend does the work, audits it, and emits a change event; the per-window observer routes that event to the store; the store mutates its `@Observable` array; SwiftUI re-renders **every** view bound to it — including views in other windows. There is no optimistic ad-hoc reload anywhere.

**Why this is the keystone:** it kills three whole bug classes at once — stale lists after merge/edit (#1849), the cross-window/agent invisibility gap, and the view→endpoint spaghetti where each button hand-rolls a service call (the root cause of the merge bug, #1848).

---

## 2. Frontend store design

### 2.1 Where stores live — the per-library registry

Fichero is multi-window, multi-library. Services are **shared per library** (`LibraryManager.LibraryReference` already holds `entityService`, `chatService`, … per library; each window has its own `DocumentStore` + `APIClient`). Domain stores follow the **same lifetime as services: one per library, shared across that library's windows.** That is what makes multi-window sync free — two windows on the same library hold the *same* `EntityStore` instance.

Add a store registry next to the existing service wrappers on `LibraryReference`:

```swift
// Models/LibraryManager.swift — LibraryReference (augment, do not replace)
@MainActor final class LibraryReference {
    // existing transport wrappers stay exactly as they are:
    let entityService: EntityServiceGenerated
    let claimService:  ClaimServiceGenerated
    // …

    // NEW: domain stores wrap those wrappers. Lazy — built on first use.
    lazy var entityStore   = EntityStore(transport: entityService, libraryPath: path)
    lazy var claimStore    = ClaimStore(transport: claimService, libraryPath: path)
    lazy var documentStore = documentStoreInstance   // DocumentStore already exists — fold in, don't fork

    // ONE stream observer per library, owns the SSE subscription, fans to the stores above.
    lazy var changeStream  = LibraryChangeStream(libraryPath: path, registry: self)
}
```

`DocumentStore` already exists and is per-window today; it is the one store that ships. The migration *folds it into* this pattern (gives it a `apply(event:)` method and registers it with the stream) rather than building a parallel `DocumentStore-as-store` — see Rule "Iterate, never replace".

### 2.2 Injection + binding (the view side)

Stores are injected with the **Observation** environment API, not `@EnvironmentObject`:

```swift
// At the window root (DocumentTabView / LibraryWindow), once per library:
.environment(library.entityStore)
.environment(library.claimStore)
.environment(library.changeStream)   // starts the SSE subscription via .task

// In any view:
@Environment(EntityStore.self) private var entityStore
```

A view that needs two-way bindings (selection, filters owned by the store) uses `@Bindable`:

```swift
@Bindable var entityStore = entityStore   // inside body, or `@Environment` + `@Bindable var store`
List(selection: $entityStore.selection) { … }
```

Read-only views just read `entityStore.entities` — Observation tracks the access and re-renders on change. **No `.task { reload }`, no `@Published`, no Combine, no `onReceive`.**

### 2.3 Mutation flow — named actions, never raw service calls

A mutating control calls a **named action method on the store** (the store is the single choke point that maps to the audited action layer #1848). The store does the write and **does not** mutate local state optimistically by default — it waits for the stream to echo the change back. (Optional optimistic path: §3.5.)

```
button → store.merge(ids:into:) → transport POST → backend audits + emits → stream → store.apply(event) → re-render
```

### 2.4 CODE SKETCH — `EntityStore` (the template store)

```swift
import Observation
import OSLog

@MainActor
@Observable
final class EntityStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var entities: [Components.Schemas.KnowledgeEntity] = []
    var selection: Set<String> = []          // two-way via @Bindable
    private(set) var isLoading = false
    private(set) var loadError: String?

    // ─── Transport: the EXISTING generated wrapper, unchanged ───
    private let transport: EntityServiceGenerated
    private let libraryPath: String
    private let log = Logger(subsystem: "app.fichero.fichero", category: "EntityStore")

    // Per-document scoping cache — the inspector loads "entities for THIS document".
    private var loadedDocumentId: String?

    init(transport: EntityServiceGenerated, libraryPath: String) {
        self.transport = transport
        self.libraryPath = libraryPath
    }

    // ── LOAD ONCE (idempotent; the store, not the view, owns fetching) ──
    func loadEntities(forDocument documentId: String) async {
        guard loadedDocumentId != documentId || entities.isEmpty else { return }
        isLoading = true; loadError = nil
        defer { isLoading = false }
        do {
            entities = try await transport.listInspectorEntitiesForDocument(documentId: documentId)
            loadedDocumentId = documentId
        } catch {
            loadError = error.localizedDescription
            log.error("load entities failed: \(error.localizedDescription)")
        }
    }

    // ── NAMED ACTIONS (map 1:1 to audited actions #1848). No local optimistic write. ──
    func setCuration(_ ids: [String], to state: Components.Schemas.EntityCurationState,
                     scope: InspectorEntityBulkActionScope) async {
        do { _ = try await transport.curateEntities(ids: ids, state: state, scope: scope) }
        catch { surface(error) }        // stream echo (entity.updated) refreshes the list
    }

    func merge(_ absorbedIds: [String], into survivorId: String) async {
        do { _ = try await transport.mergeEntities(survivorId: survivorId, absorbed: absorbedIds) }
        catch { surface(error) }        // stream echo (entity.merged) refreshes the list
    }

    func delete(_ ids: [String]) async {
        do { _ = try await transport.deleteEntities(ids: ids) }
        catch { surface(error) }        // stream echo (entity.deleted) refreshes the list
    }

    // ── STREAM ENTRY POINT — called by LibraryChangeStream, NOT by views ──
    func apply(_ event: ChangeEvent) {
        switch event.type {
        case .entityUpdated, .entityMerged, .entityCreated:
            // Targeted patch when ids known; else reload the current document scope.
            Task { await reloadCurrentScope() }
        case .entityDeleted:
            entities.removeAll { event.entityIds.contains($0.id ?? "") }
            selection.subtract(event.entityIds)
        default:
            break   // not ours
        }
    }

    private func reloadCurrentScope() async {
        guard let doc = loadedDocumentId else { return }
        loadedDocumentId = nil          // force the guard in loadEntities to re-fetch
        await loadEntities(forDocument: doc)
    }

    private func surface(_ error: Error) {
        loadError = error.localizedDescription
        log.error("entity action failed: \(error.localizedDescription)")
    }
}
```

Notes:
- The store wraps `EntityServiceGenerated` (the existing transport at `Services/ArtifactServiceGenerated.swift::EntityServiceGenerated`). The action methods (`curateEntities`, `mergeEntities`, …) are the *same* calls the view's `applyBulkAction` / `applyMerge` / `applyDelete` make today — they move out of the view into the store unchanged.
- `apply(_:)` is the generalization of `WorkflowExecutionObserver.handleEvent(_:for:)` — same shape: typed event in, mutate observable state, SwiftUI re-renders.

### 2.5 CODE SKETCH — view migration (`DocumentInspectorEntitiesTab`, the template view)

**Before** (today): the view owns `@State private var entities`, `@State private var entitySelection`, loads via `.task(id: documentId) { await loadEntities() }`, and after every action calls `applyLocalStateUpdate` / reloads — and posts `.ficheroClaimUpdated` NotificationCenter to nudge siblings.

**After:**

```swift
struct DocumentInspectorEntitiesTab: View {
    let document: Document
    let documentId: String
    @Environment(EntityStore.self) private var entityStore        // ← injected store
    @AppStorage("inspector.entities.hiddenKinds") private var hiddenKindsCSV = ""

    var body: some View {
        @Bindable var store = entityStore                          // selection binding
        VStack(alignment: .leading, spacing: 12) {
            header                                                  // reads store.entities.count
            if store.isLoading {
                ProgressView()
            } else if let err = store.loadError {
                Label(err, systemImage: "exclamationmark.triangle")
            } else if store.entities.isEmpty {
                ContentUnavailableView("No entities yet", systemImage: "circle.grid.cross")
            } else {
                List(selection: $store.selection) {
                    ForEach(grouped(store.entities), id: \.0) { kind, items in
                        entityKindSection(kind: kind, entities: items)
                    }
                }
                .listStyle(.plain)
            }
        }
        // store owns fetching; the view just asks it to scope to this document
        .task(id: documentId) { await store.loadEntities(forDocument: documentId) }
    }

    // actions now delegate to the store — no service calls, no local mutation, no NotificationCenter
    private func approve(_ ids: [String], scope: InspectorEntityBulkActionScope) {
        Task { await entityStore.setCuration(ids, to: .verified, scope: scope) }
    }
    private func merge(_ plan: InspectorEntityBulkSelection.MergePlan) {
        Task { await entityStore.merge(plan.absorbedEntityIds, into: plan.survivorId) }
    }
    private func delete(_ ids: [String]) {
        Task { await entityStore.delete(ids) }
    }
}
```

What was deleted from the view: `@State entities`, `applyLocalStateUpdate`, `applyBulkAction`/`applyMerge`/`applyDelete` bodies (they move to the store as named actions), and every `NotificationCenter.default.post(.ficheroClaim*/.ficheroEntity*)`. Pure-selection helpers (`InspectorEntityBulkSelection`, merge-plan computation, `grouped`) stay in the view layer — they're display logic, not data access.

This is the exact template for all of §4.

---

## 3. Backend change-stream (#1863)

### 3.1 Mirror the workflow SSE infra

The workflow stream (`api/routes/workflow_execution/core.py::stream_workflow_events`) is the proven pattern: a `StreamingResponse(media_type="text/event-stream")` draining a thread-safe `queue.Queue` via `loop.run_in_executor`, with `: keepalive\n\n` comments on a 60s timeout and `X-Accel-Buffering: no`. **Generalize it from one-thread-id to one-library.**

```python
# api/routes/changes.py  (new route module, mounted in api/main.py dev+core)
@router.get("/changes/stream")
async def stream_library_changes(request: Request) -> StreamingResponse:
    """Per-library change-event SSE. One connection per app window.
    Library scope comes from the X-Fichero-Library-Path header (same as every
    other route). Drains a per-library asyncio.Queue fed by emit_change()."""
    library_path = request.headers["X-Fichero-Library-Path"]
    queue = _change_hub.subscribe(library_path)        # registers this window's queue

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                    yield format_sse(event)            # reuse the workflow formatter
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _change_hub.unsubscribe(library_path, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "Connection": "keep-alive",
                                      "X-Accel-Buffering": "no"})
```

`_change_hub` is a process-global registry: `library_path → set[asyncio.Queue]` (one queue per connected window). `emit_change(library_path, event)` pushes onto every queue for that library. This is intentionally simple (in-process fan-out, no broker) — matches the single-backend-process reality.

### 3.2 Event schema

```jsonc
{
  "type": "entity.merged",          // "{domain}.{verb}": entity.created|updated|deleted|merged,
                                     //   claim.created|updated|deleted, document.updated, …
  "entity_ids": ["e_123","e_456"],  // affected ids (domain-typed: entity_ids / claim_ids / document_ids)
  "claim_ids": [],
  "document_ids": ["d_9"],          // scope hint — lets a document-scoped store know if it cares
  "run_id": "wf_abc",               // present when the mutation came from a workflow/extraction
  "actor": "ui|chat|workflow|import|system",   // who (#1848 audit actor; device/session until multi-user)
  "origin_window": "win-7f3c",      // the window that initiated it (for self-echo de-dup, §3.5)
  "ts": "2026-06-08T22:40:00Z"
}
```

This is exactly the audit record (#1848) projected for transport: `{type, ids, run_id, actor}` from the memory + provenance (#1832), plus `origin_window` for de-dup.

### 3.3 Emit points — tie to the one-audited-action-layer (#1848)

**Do not scatter `emit_change()` through routes.** The audited action layer is the single choke point: every mutating action already (or will) write an audit record. Emit the change event in the *same* place the audit row is written — one helper, called once per action:

```python
def record_action(action, target_ids, actor, *, before=None, after=None, run_id=None,
                  origin_window=None, library_path):
    audit.write(...)                                   # #1848 audit row (who/when/diff)
    emit_change(library_path, ChangeEvent(             # #1863 transport projection
        type=f"{action.domain}.{action.verb}",
        **target_ids, run_id=run_id, actor=actor, origin_window=origin_window))
```

Until the full action registry lands, the **interim** emit points are the existing mutating routes (entities curate/merge/delete, claims create/update/delete, document update, ingest-complete, workflow-output-written). Each gets one `emit_change(...)` line. That interim wiring is the same code the action layer will absorb — no rework, just relocation.

Workflow runs already emit their own SSE; those stay. When a workflow *writes entities/claims*, it additionally calls `emit_change` so KG views (not just the workflow progress view) refresh — this is the multi-source win.

### 3.4 Frontend fan-out — one observer per window

`LibraryChangeStream` is the generalization of `WorkflowStreamService` + `WorkflowExecutionObserver`: one per window, owns the SSE `URLSession.bytes` loop, parses `data:` lines into `ChangeEvent`, and routes by domain to the library's stores.

```swift
@MainActor @Observable
final class LibraryChangeStream {
    private let libraryPath: String
    private unowned let registry: LibraryReference
    private var task: Task<Void, Never>?
    private let windowId: String                       // this window's origin tag

    func start() {
        task = Task { await subscribe() }              // GET /api/changes/stream, X-Fichero-Library-Path
    }

    private func route(_ event: ChangeEvent) {
        guard event.origin_window != windowId else { return }   // §3.5 self-echo de-dup
        switch event.domain {                          // "entity" / "claim" / "document" / …
        case "entity":   registry.entityStore.apply(event)
        case "claim":    registry.claimStore.apply(event)
        case "document": registry.documentStore.apply(event)
        default: break
        }
    }
}
```

The subscribe loop is copied from `WorkflowStreamService.subscribeToStream` (URLSession `.bytes`, `for try await line in bytes.lines`, `data:` prefix strip, JSON decode), with reconnect-with-backoff on drop. Start it with `.task` at the window root and cancel on disappear — same lifecycle as the workflow stream.

### 3.5 Multi-window / tab + per-library scoping + de-dup

- **Per-library scoping:** the SSE connection carries `X-Fichero-Library-Path` (same injection `APIClient.configureRequest` already does). A window only receives events for its own library; `_change_hub` keys queues by library path. Two libraries in two windows are fully isolated, as today.
- **Multi-window same library:** both windows hold the *same* store instances (§2.1) → a mutation in window A reaches window B's views through the shared store, the moment the stream delivers the event. No extra work per window beyond each having its own SSE connection.
- **Self-echo de-dup:** the originating window passes its `origin_window` id on the mutating request (new header `X-Fichero-Origin-Window`); the backend echoes it on the event; `LibraryChangeStream.route` drops events whose `origin_window == windowId`. This matters only if we add **optimistic** local updates (store mutates immediately, then ignores its own echo to avoid a double-apply). The default no-optimistic path (§2.3) can ignore de-dup and just apply every event — simpler, one network round-trip of latency. **De-dup is the seam that lets us turn optimism on later without changing the event contract.**

---

## 4. Migration plan

Stores are introduced **incrementally, lowest-risk first**. Each audit issue (#1882–#1900, #1862) becomes "wrap this service in a store + bind the view," using §2.4/§2.5 as the template. The backend stream (#1863) can land in parallel; **until it exists, stores still own access** and simply lack push (a store can keep an interim `reload()` the action methods call — identical to today's behavior, but centralized in the store, so swapping to push is a one-line change).

### 4.1 Store inventory (audit views → store)

| # | Audit issue (view) | Maps to store | Transport wrapper |
|---|---|---|---|
| #1862 | KG NotificationCenter claim bus (6 files) | **ClaimStore** | `ClaimServiceGenerated` |
| #1885 | Inspector EntitiesTab | **EntityStore** (template) | `EntityServiceGenerated` |
| #1886 | Inspector KGSection (`KnowledgeGraphInspectorLoadState`) | EntityStore + ClaimStore | Entity/Claim/KGCuration |
| #1887 | OntologyBrowser (`OntologyBrowserLoadState`) | EntityStore + ClaimStore | Entity/Claim |
| #1882 | Notes views (`NoteService` in view) | **NoteStore** | `NoteServiceGenerated` |
| #1883 | Annotations (`AnnotationService` in view) | **AnnotationStore** | `AnnotationServiceGenerated` |
| #1889 | EntityDetail+Notes (`NoteService` in view) | NoteStore | `NoteServiceGenerated` |
| #1899 | IntegrationsView (`IntegrationsService` in view) | **IntegrationsStore** | `IntegrationsServiceGenerated` |
| #1900 | ModelComparison (`ModelComparisonService` in view) | **ModelComparisonStore** | `ModelComparisonServiceGenerated` |
| #1892 | WorkflowExecutionView (`WorkflowExecutionService` in view) | reuse `WorkflowExecutionObserver` | (already observable) |
| #1895 | WorkflowChainListView (`ChainService` in view) | **ChainStore** | `ChainServiceGenerated` |
| #1896 | Agents (`AgentSettings` ObservableObject) | **AgentStore** | `AgentServiceGenerated` |
| #1897 | ActivityConsole/Detail | reuse activity SSE / **ActivityStore** | activity stream |
| #1884 | View-local state (`DocumentScrollSyncState`, `FolderAccessManager`) | local `@Observable` (NOT domain stores) | n/a — pure view-model migration |

(#1888/#1890/#1891/#1893/#1894/#1898 are list/empty-state/inline-edit polish that *ride along* once the view already binds a store — do them in the same PR as their store, not separately.)

### 4.2 Ordered migration sequence (lowest-risk first)

1. **Land `ChangeEvent` + `LibraryChangeStream` shell** (no emit points yet) — pure additive, decode-and-log only. De-risks the wire format.
2. **Backend `/changes/stream` + `_change_hub` + emit on the 3 KG mutating routes** (entity curate/merge/delete) — the highest-pain surface (#1849 merge bug). Verifiable end-to-end with one store.
3. **EntityStore (#1885)** — the template. One view, one store, the merge bug closes here. Reference PR for everyone.
4. **ClaimStore + retire NotificationCenter (#1862)** — now that a store exists, replace the `.ficheroClaim*` post/observe in all 6 files with `claimStore.apply(event)`. This is the §4.3 retirement.
5. **KGSection + OntologyBrowser (#1886, #1887)** — reuse EntityStore/ClaimStore; also collapses the two `*LoadState` ObservableObjects and the oversized files.
6. **Notes / Annotations (#1882, #1883, #1889)** — independent, low blast radius, no cross-window contention; good parallel lane.
7. **Sidebar / Workflow / Agents / Integrations / ModelComparison (#1895/#1896/#1899/#1900/#1892)** — each its own store, each its own emit point; fully parallelizable once the pattern is proven.
8. **Local view-models (#1884)** — `ObservableObject → @Observable` mechanical migration; no stream involvement.

Risk ordering rationale: steps 1–3 touch *additive* infra and one well-understood view; the high-blast-radius god-objects (`DocumentStore`, `LibraryManager`, `AppState`) are touched only to *register* stores (§2.1), never rewritten (SWIFTUI_PRINCIPLES: stage god-objects deliberately, never as a list-conversion side-effect).

### 4.3 Retiring the NotificationCenter stopgap (#1862)

The `.ficheroClaimUpdated` / `.ficheroClaimDeleted` / `.ficheroEntitySearchRequested` posts (audit S2; in `ClaimSummaryCardView`, `OntologyBrowser`, `ClaimReviewQueueSheet`, `ContradictionTriageSheet`, `DocumentInspectorArtifactsTab+*`) are the **interim** cross-view mutation bus. They are retired **per store, as that store lands**, not in a big-bang:

- A `.post(.ficheroClaimUpdated)` after a mutation → delete; the backend `emit_change("claim.updated", …)` now does the fan-out.
- An `.onReceive(.ficheroClaimUpdated) { reload() }` → delete; the view now reads `claimStore.claims` and re-renders on `claimStore.apply`.
- **Exception:** `.ficheroEntitySearchRequested` is a *navigation* signal, not a data mutation — that one migrates to `@FocusedValue` / an action, not the change-stream (per SWIFTUI_PRINCIPLES §2). Keep it out of the data layer.

Until a given store is migrated, its NotificationCenter posts stay (don't strand a half-migrated surface). The retirement is complete when no `.ficheroClaim*`/`.ficheroEntity*` mutation post remains.

---

## 5. Open questions / risks (for Daniel)

1. **SSE vs WebSocket.** SSE reuses the proven workflow infra verbatim (server→client only, auto-reconnect, no new dependency) and the mutating writes already go over normal HTTP POST — so one-way push is sufficient. WebSocket would only pay off if we later want the *client* to push presence/cursors. **Recommendation: SSE now**, revisit if collaborative presence becomes a goal. — *Decide before step 1.*

2. **Store granularity.** One store per domain (EntityStore, ClaimStore, …) vs one fat `KnowledgeStore` holding entities+claims+links. Entities and claims are tightly coupled in the KG views (merge affects both). **Recommendation: separate stores, but let a view observe several**; revisit a combined `KnowledgeStore` only if cross-store consistency (merge cascading claim updates) gets awkward. — *Affects §2.1 + the §4.1 table.*

3. **Where change events are emitted — now vs after #1848.** The clean home is the audited-action-layer choke point (one `record_action` helper). But that registry isn't built yet. Do we (a) wire interim `emit_change()` into existing mutating routes now and relocate later, or (b) block the change-stream on the action layer landing? **Recommendation: (a)** — the interim wiring is the exact code the action layer absorbs, and it unblocks the merge-bug fix immediately. — *Decide before step 2.*

4. **Optimistic updates + de-dup, or strict server-echo.** Strict (apply only on stream echo) is simpler and always-consistent but adds one round-trip of UI latency; optimistic needs the `origin_window` de-dup seam (§3.5). **Recommendation: strict first** (the seam is built in so we can enable optimism later without changing the contract). — *Affects §2.3, §3.5.*

5. **Reconnect / missed-event semantics.** If a window's SSE drops mid-mutation, events are missed (in-process queue, no replay log). Cheap fix: on reconnect, each store does one `reload()` to resync. Full fix: an event cursor/`Last-Event-ID` replay off the audit log. **Recommendation: reload-on-reconnect now**, cursor replay only if it proves lossy. — *Implementation detail of §3.4; flag for awareness.*
