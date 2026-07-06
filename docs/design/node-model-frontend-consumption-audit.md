# Node-Model Fold — Frontend Consumption Audit (#2591 / EPIC #2081)

> **Status: PLANNING (read-only).** Frontend companion to the backend audit
> (`endpoints-vs-ux-audit.md`, landed on the backend line) and the staging doc
> (`docs/architecture/node_model_fold_staging.md`). Maps the **Swift surface**
> that consumes each fold-target endpoint family, so when a backend fold lands
> the frontend migration is pre-scoped. **No implementation here** — the fold is
> Daniel-deferred to post-TestFlight and is backend-first (every slice gates on
> foundation P1 Prototype / P2 Alias, which are codex-lane). Grounded in the
> `main` tree, 2026-07-05.

## How to read this

Each fold slice (F1–F5, from the staging-doc fold table) has a **backend half**
(migrate the endpoint onto the node/library family — codex lane) and a
**frontend half** (repoint the Swift store/service off the retired endpoint onto
the unified one). The frontend half **cannot start until its backend half lands**
— it's the same wait pattern as #2279 (frontend consumer waited on codex's emit).
This doc scopes the frontend half only.

## Frontend fold-surface table

| Slice | Backend target (staging doc) | Frontend surface (grounded) | Frontend migration | Readiness |
|---|---|---|---|---|
| **F1 · Saved searches** | `SavedSearch` CRUD + 5 `_action_*` → node type/attribute (gated P1) | `Services/SavedSearchService(+Generated)` (calls `client.api.*SavedSearch*` **directly**), sidebar (`SidebarItem`, `SidebarSearchTypes`, `SidebarItemBuilder`, `SidebarViewTypes`), `ViewContexts`, `LibraryManager` | Repoint `SavedSearchServiceGenerated` off `/api/search/saved*` onto the unified node/attribute endpoint; sidebar reads a node-typed list. Moderate surface, well-isolated behind the service. | Blocked on F1 backend |
| **F2 · Research workspace** | `ResearchProject` → "workspace" folder prototype (gated P1+P5) | `Models/ResearchStore` (**already on `ObservableDomainStore` substrate**, changeDomain `research`), `Services/ResearchService`, `Models/ResearchModels`, `Views/Research/*` (WorkspaceView, ProjectListView, Browser/Chat/TasksPane), `ContentView+Navigation` | `ResearchStore`/`ResearchService` repoint onto the container-prototype ("workspace") node endpoints; `Views/Research/` render a container's contents. Large surface but observability is already node-shaped. | Blocked on F2 backend (P1+P5) |
| **F3 · Research plans/tasks/steps** | `ResearchPlan`/`Task`/`Step` → prototype attributes (gated P1+P3) | Same `ResearchStore` + `Views/Research/ResearchTasksPane` | Tasks/steps read as container attributes rather than a separate CRUD; TasksPane binds to the attribute set. | Blocked on F3 backend |
| **F4 · Bookmarks** | net-new node type / alias relation (gated P2) | `Services/BookmarkServiceGenerated`, `Views/Library/BookmarksView`, `Views/Library/Inspector/FocusedDocument`, `Views/Library/Workspace/LibraryWorkspaceRoot` | Point the bookmark surface at the node-type/alias endpoint once defined. Small. | Blocked on F4 backend (P2 alias) |
| **F5 · Mind Palace `/rooms/*`** | retire legacy rooms; positions→attributes, connections→`LibraryItemLink` (gated P1+P2+P4) | **NONE** — `grep` for `mind-palace`/`/rooms`/`MindPalace` in `Models`/`Services`/`Views` returns **zero**. The spatial view already drives from `MindPalaceLibraryProjector` (a pure projection over library data) + `CanvasLayoutStore`/`CanvasItemStore` (already `@Observable`, node-shaped). | **Frontend already migrated.** Fold-E's remaining callers are CLI + MCP only (codex/backend lane). | Frontend done; backend/CLI/MCP pending |

## Key findings

1. **The frontend is further along than the backend for the node model.**
   - `Document` already carries `prototypeKey` (`prototype_key`, #1377) — the
     class tag. What's missing is the *definition* system (P1, backend), not the
     frontend field.
   - `CanvasLayoutStore` / `CanvasItemStore` / `ResearchStore` are already
     `@Observable` on the change-stream substrate — node-model-shaped.
   - The spatial view is already off `/rooms/*` (F5 frontend is done).

2. **One frontend gap, deliberately unadopted:** the newer typed `node_kind`
   field (backend `models.py` + the generated OpenAPI client on `main`) is **not**
   surfaced in the hand-written Swift `Document`. Adopting it read-only is a
   one-field, low-risk change — but it's **premature**: with no prototype
   *definitions* (P1) behind it, a `nodeKind` in the UI has no real behavior to
   drive. Hold until P1 lands (else we ship a dead field, against YAGNI).

3. **No frontend-lane implementation slice is unblocked in #107 right now.** F1–F4
   frontends each wait on their backend fold; F5 frontend is already done. This
   mirrors #2279: the frontend surface lands *after* the backend half.

## Frontend-lane sequencing (each gated on its backend half)

Post-TestFlight, once codex lands the foundation + a fold's backend, the frontend
slice for that fold is a bounded repoint:

1. **F1 frontend** (after F1 backend) — smallest; `SavedSearchServiceGenerated`
   repoint + sidebar list source. Regression: saved-search CRUD + reorder round-trip.
2. **F4 frontend** (after F4/P2) — small; bookmark surface → node/alias endpoint.
3. **F3 frontend** (after F3) — TasksPane binds task/step attributes.
4. **F2 frontend** (after F2/P5) — largest; `ResearchStore`/`Views/Research/`
   onto the workspace container prototype.
5. **node_kind read adoption** (after P1) — surface `Document.nodeKind`; drive
   node-type-aware sidebar/inspector affordances.

Each frontend slice: `@Observable` + native SwiftUI, iterate-not-replace,
swiftlint clean, single-accessor via the store, tests. Per the reimportable-library
rule, no client-side migration shims — the schema changes directly and reimports.

## Decisions / blockers for Daniel

- **Go/no-go on starting the fold** — the staging doc says "do not start any
  Phase 1/2 slice before TestFlight." Is TestFlight past / is the fold greenlit?
- **Phase 0 (file P1–P6 as issues, assignee dtubb)** is the gating step and a
  board task, not frontend coding.
- **The fold is backend-first** — the frontend lane can only pick up each slice
  after codex lands its backend half + the P1/P2 foundation. Until then there is
  no frontend implementation work in #107; this audit is the frontend plan.

## Cross-references

- `docs/architecture/node_model_fold_staging.md` — the fold path + P1–P6 gates.
- `endpoints-vs-ux-audit.md` (backend line) — the backend endpoint audit (#2588).
- #2081 — the node-model EPIC (foundation gaps P1–P6).
- #2636 — `LibraryItemLink` (relations target for F5 connections).
- #2293 / #369 — canvas position persistence (kept by F5).
