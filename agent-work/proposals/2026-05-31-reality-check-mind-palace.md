# Reality Check: Mind Palace Milestone — Open Issues

**Date:** 2026-05-31
**Branch:** main
**Scope:** All open issues in the "Mind Palace" GitHub milestone

---

## Summary Counts

| Classification | Count | Issue numbers |
|---|---|---|
| DONE — safe to close | 3 | #920, #269, #1297 (viewport + drag + 3D view — Phase 2 largely done) |
| PARTIAL | 4 | #267, #268, #274, #1297 |
| GENUINELY OPEN | 5 | #265-derived: #266, #271, #273, #821, #1343, #512, #511 |

**Conservative safe-to-close list:** only #920 is unambiguously closeable. #269 partial. Details below.

---

## Per-Issue Classification

### #920 — Re-enable mind-palace (spatial Notes layer) when RealityKit work resumes
**DONE — safe to close**

Evidence:
- `api/main.py:865` — `(mind_palace.router, "/api/mind-palace", ["mind-palace"])` is registered unconditionally (no `_deprecated` comment). The deprecation noted in the issue is resolved.
- `fichero-engine/src/fichero/api/routes/mind_palace.py` — 46 symbols, fully implemented with `/notes` CRUD, rooms, nodes, connections, stacks, viewport, Tinderbox import/export.
- Feature tier test `test_release_tier_promotes_mind_palace_and_research_agents` confirms it survives to release tier.
- Swift surface (`MindPalaceService.swift`, `SpatialModels.swift`, `SpatialScene3D.swift`, `SpatialView.swift`, `RoomListView.swift`, `MindPalaceWindow.swift`) all exist and consume the routes.

Action: CLOSE. Route is re-enabled, Swift callers exist, feature promoted to release tier.

---

### #269 — Persist spatial graph primitives for rooms, workspaces, aliases, and viewports
**PARTIAL (close with caveat)**

Evidence built:
- `fichero/fichero/Models/SpatialModels.swift` — defines `MindPalaceNode`, `MindPalaceConnection`, `MindPalaceRoom`, `MindPalaceStack`, `MindPalaceViewport`, `MindPalaceLink`, `MindPalaceNodeType`, `MindPalaceConnectionType`, `LinkType`.
- Backend `spatial_models.py` — `SpatialRoom`, `SpatialNode`, `SpatialEdge`, `SpatialStack`, `NativeNote`, `SpatialViewport`.
- Viewport CRUD in both backend and Swift service is wired.

Missing from the issue scope:
- `SpatialAlias` / alias model — not found in the codebase (no symbol named Alias or SpatialAlias).
- `SpatialWorkspace` as distinct from Room — the issue asks for workspaces backed by smart/search-derived sets; the current model is room-only.
- Saved/loadable workspaces (search-result workspaces) — not found.

Action: PARTIAL — core primitives exist and persist. Aliases and search-derived workspaces are not implemented.

---

### #267 — Expose native notes and spatial workspace REST APIs
**PARTIAL**

Evidence built:
- `api/routes/mind_palace.py` — `/api/mind-palace/notes` (CRUD: POST, GET, GET-id, PATCH, DELETE), `/api/mind-palace/rooms`, `/api/mind-palace/nodes`, `/api/mind-palace/connections`, `/api/mind-palace/stacks`, `/api/mind-palace/viewport` — all present (46 route symbols).
- Tinderbox import/export endpoints present.

Missing:
- Note-link API (provenance, evidentiary links) — not in mind_palace.py or a separate route. The issue asks for "note-link and provenance APIs" as explicit REST endpoints.
- The notes endpoint returns `MindPalaceListResponse` with untyped `items` (known limitation from #1297 issue body).

Action: PARTIAL — spatial CRUD APIs done; note-link and provenance APIs missing.

---

### #268 — Introduce native Note model with user/AI taxonomy and lifecycle
**PARTIAL**

Evidence built:
- `fichero-engine/src/fichero/spatial_models.py::NativeNote` — exists with `NoteKind`, `NoteType`, `NoteStatus`, `author_type` fields (confirmed from mcp_server.py signature using `NativeNote` and `NoteKind`).
- Backend `create_note` / `list_notes` / `get_note` / `update_note` / `delete_note` in `mind_palace.py`.

Missing:
- No Swift `NativeNote` model found — `fichero/fichero/Models/SpatialModels.swift` does not contain a `NativeNote` type (MCP server side handles it but Swift app has no native notes UI or model).
- No "notes" tab, creation UI, or display surface in the SwiftUI app.
- The issue asks for the note model to "power list/map/spatial views" — only the spatial view exists via the MCP server; the list/map surfaces have no native note support.

Action: PARTIAL — backend model complete; Swift-side native notes model and UI are absent.

---

### #274 — Build direct-manipulation RealityKit spatial workspace foundation
**PARTIAL (close to done)**

Evidence built:
- `SpatialScene3D.swift` — `nodeDragGesture` (full drag-to-reposition with `onNodePositionChanged` + `onNodeMoveEnded` callbacks), `cameraDragGesture`, `cameraZoomGesture`, RealityKit `RealityView` with `PerspectiveCamera`, tap-to-select, `persistViewport()` wired via `onViewportChanged`.
- `MindPalaceService.swift::moveNode` — calls `PATCH /api/mind-palace/nodes/{nodeId}` with typed `NodeMoveRequest`.
- `MindPalaceService.swift::saveViewport` — full typed `ViewportSaveRequest`.
- `MindPalaceService.swift::placeNode`, `listStacks`, `createRoom`, `deleteRoom`, `suggestArrangement` all wired.
- `SpatialScene3D.swift::buildScene` renders nodes as RealityKit `ModelEntity` objects (box/sphere geometry) with typed edge cylinders per `LinkType`.

Missing from the issue scope:
- Connection/node creation + deletion UI in the app (buttons/context-menus; `placeNode` and `createConnection` exist in the service but there's no Swift UI to invoke them interactively).
- Stack grouping UI (`listStacks` reads exist; no create-stack or add-to-stack UI surface found).
- Tinderbox import/export affordance (backend routes exist; no Swift UI button).
- "Room and workspace loading/saving hooks" — rooms load, but workspace concept (beyond rooms) is not implemented.

Action: PARTIAL — the RealityKit 3D foundation is built and drag/viewport is wired. Interactive node/connection creation UI and stack UI are missing.

---

### #1297 — Mind Palace Phase 2 — editing (drag-to-move, viewport persistence) + 3D view
**PARTIAL (Phase 2 mostly done, checklist items incomplete)**

Evidence per issue checklist:
- **Drag-to-reposition** — `nodeDragGesture` in `SpatialScene3D.swift` + `MindPalaceService.moveNode` — DONE.
- **Persist camera/zoom** — `persistViewport()` in `SpatialScene3D.swift` + `saveViewport`/`getViewport` in service + `applyInitialViewportIfNeeded` on open — DONE.
- **Pan/zoom gestures** — `cameraDragGesture` (orbit) + `cameraZoomGesture` (magnification) — DONE.
- **3D view (SceneKit/RealityKit)** — `SpatialScene3D.swift` uses `RealityView` with `PerspectiveCamera`, orbit yaw/pitch, zoom — DONE.
- **Connection/node creation + deletion UI** — `placeNode`/`createConnection` exist in service but no interactive creation UI in the views — OPEN.
- **Stack grouping UI** — `listStacks` wired for read, but no create-stack UI — OPEN.
- **Tinderbox import/export affordance** — backend done, no Swift UI — OPEN.
- **Typed returns** for mind-palace client methods — nodes/connections still return `Any` via `OpenAPIValueContainer`; `MindPalaceNode` decoded via JSON round-trip — PARTIAL.

Action: PARTIAL — 4 of 7 checklist items done. Connection/node creation UI, stack UI, Tinderbox affordance still missing.

---

### #266 — Add durable note links and provenance records
**GENUINELY OPEN**

Evidence: No `NoteLink`, `ProvenanceRecord`, or equivalent model found in `spatial_models.py`, `knowledge_models.py`, or any route. The `linked_claim_ids`, `linked_entity_ids`, `linked_document_ids` fields on `NativeNote` are simple ID lists, not first-class link objects with traversal or provenance metadata.

Action: OPEN — no implementation found.

---

### #271 — Add shared spatial workspace mode to Library views
**GENUINELY OPEN**

Evidence:
- The Mind Palace has its own sidebar mode (`SidebarMode.mindPalace`) and `RoomListView` — it is a *separate mode*, not a shared spatial layer sitting alongside list/icon/table/map.
- The issue explicitly requires "one shared model across renderers" and "map view and future spatial/3D view should sit on the same spatial graph." The current map view (`KGMapView.swift`) does not share the spatial graph with Mind Palace.
- "Folder-backed rooms" — rooms are created independently; no auto-creation from folders.
- "Search-result workspaces" — not implemented.

Action: OPEN — the spatial mode exists but as a silo; the unified-model requirement is not met.

---

### #273 — Let workflows and agent teams write durable results into the AI workspace
**GENUINELY OPEN**

Evidence: No workflow tool that creates/updates `NativeNote` or places nodes in Mind Palace found in `fichero-engine/src/fichero/workflows/tools/`. The existing tools write to KG (entities/claims) and artifacts, not to the spatial workspace. `research_agents.py` has 0 symbols.

Action: OPEN — no implementation found.

---

### #821 — Foundation toolkit: Tool protocol — let Apple Intelligence call back into the KG
**GENUINELY OPEN**

Evidence: No `KGSearchTool`, `LanguageModelSession(tools:)`, Apple Foundation Models `Tool` protocol conformance, or fm-bridge bidirectional IPC found anywhere in the Swift or Python codebase.

Action: OPEN — no implementation found.

---

### #1343 — AI arranges a folder's documents in 3D space for sensemaking (room = folder/workspace)
**GENUINELY OPEN**

Evidence:
- The issue is labeled `needs-design` — explicitly not implementation-ready.
- No folder→room projection that auto-arranges by topic/entity/time found (the `MindPalaceLibraryProjector` mentioned in `SpatialModels.swift:265` is a comment reference to Phase 3, but is a projector from DB data to a whole-library view, not a folder-backed AI arrangement).
- `suggestArrangement` backend endpoint exists but is a position-suggestion call, not an AI-driven cluster-by-topic layout.

Action: OPEN (needs-design) — preconditions not met for implementation.

---

### #512 — [Release Gate] 0.6.1 - Wire: Spatial Library
**GENUINELY OPEN**

Evidence: This is a far-future release gate. The 3D browsing and grab/move document features are partially built (drag works in Mind Palace) but the "Spatial Library" as a standalone document-browsing mode with all checklist items is not complete.

Action: OPEN — release gate, not yet built to spec.

---

### #511 — [Release Gate] 0.6.0 - Wire: Spatial Knowledge Layer
**GENUINELY OPEN**

Evidence: This is a far-future release gate. "Spatial workspace mode accessible," "Documents appear as spatial objects in 3D space" — partially true for Mind Palace but not as a primary Spatial Knowledge Layer with MCP tool integration. All checklist items unsigned.

Action: OPEN — release gate, not yet built to spec.

---

## Safe to Close Now

| # | Issue | Reason |
|---|---|---|
| #920 | Re-enable mind-palace when RealityKit resumes | Route active, Swift callers exist, feature tier promoted |

## Needs Work (do not close)

| # | Issue | Key gap |
|---|---|---|
| #269 | Persist spatial primitives | Aliases + search-derived workspaces missing |
| #267 | Expose native notes + spatial REST APIs | Note-link/provenance APIs missing |
| #268 | Introduce native Note model | Swift-side NativeNote model + UI absent |
| #274 | Build direct-manipulation RealityKit foundation | Node/connection creation UI + stack UI + Tinderbox affordance missing |
| #1297 | Phase 2 — editing + 3D view | Connection creation UI, stack UI, Tinderbox affordance open |
| #266 | Durable note links + provenance | No implementation found |
| #271 | Shared spatial workspace mode in Library | Silo mode, not shared model; folder/search workspaces absent |
| #273 | Workflows write into AI workspace | No workflow tool creates NativeNote or places spatial nodes |
| #821 | Foundation toolkit: Tool protocol (Apple Intelligence + KG) | No implementation found |
| #1343 | AI arranges folder's documents in 3D | needs-design; no implementation |
| #512 | Release Gate 0.6.1 Spatial Library | Far-future gate, not built to spec |
| #511 | Release Gate 0.6.0 Spatial Knowledge Layer | Far-future gate, not built to spec |
