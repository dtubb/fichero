# Mind Palace as Spatial Library — Phase 3 design

**Status:** proposal · **Date:** 2026-05-30 · **Issue:** #1297 follow-up

## Where we are

Mind Palace is the spatial layer of the Fichero library — already in 0.0.2:

- `#1297` Phase 1+2: SpatialScene3D RealityKit canvas, drag-to-move, viewport persistence.
- `#1309` page-image textures on cards + tap-to-select via `InputTargetComponent`.
- `#1321` surfaced as the folder/workspace view tab.
- `#1322` page images + camera interaction (orbit/zoom gestures).
- `#1298` mind_palace + research_agents promoted to core tier.

Today Mind Palace renders **one room at a time**: nodes the user (or an AI) explicitly placed, with `MindPalaceConnection` edges between them. Each room is a curated workspace.

## Where Daniel wants to go

The Mind Palace is the **spatial OS for the entire Fichero library** — not just curated rooms but the whole catalogue, with **visible link types** between documents, pages, and entities. Same code paths must run on **Mac (now)**, **iPhone tabletop AR (later)**, and **Apple Vision Pro (later)**.

Phase-1 ship target: a "Whole Library" view next to existing rooms that places every document and KG entity in space, draws the inter-entity citation/mention links, and lets the user tap-to-follow a link the way a room-curated node already behaves.

## Apple platform shape

The renderer must be one body of code; per-platform code stays at the edges. From the [RealityKit reference](https://developer.apple.com/documentation/realitykit/):

| Primitive | Macro symbol | Plays on macOS 15 | iOS 18 | visionOS 2 |
|---|---|---|---|---|
| `RealityView` (SwiftUI) | scene host | ✓ | ✓ | ✓ |
| `Entity`, `ModelEntity` | scene-graph nodes | ✓ | ✓ | ✓ |
| `PerspectiveCamera` | explicit camera | ✓ | ✓ | (managed by system on AVP) |
| `AnchorEntity(.world)` | world anchor | ✓ | ✓ | ✓ |
| `AnchorEntity(.plane)` | tabletop AR anchor | — | ✓ | ✓ |
| `InputTargetComponent` | gesture target | ✓ | ✓ | ✓ |
| `CollisionComponent` | required for input | ✓ | ✓ | ✓ |
| `HoverEffectComponent` | system highlight on hover | ✓ | ✓ | ✓ (strongest) |
| `MeshResource.generateBox/Sphere/Cylinder/Plane` | primitives | ✓ | ✓ | ✓ |
| `UnlitMaterial`, `SimpleMaterial`, `PhysicallyBasedMaterial` | shading | ✓ | ✓ | ✓ |
| `Material.Color` typealias (NSColor on mac, UIColor on iOS/visionOS) | color | ✓ | ✓ | ✓ |
| `targetedToAnyEntity()` (SwiftUI gesture binder) | gesture rig | ✓ | ✓ | ✓ |
| `MagnificationGesture` / `MagnifyGesture` | zoom | macOS keeps `MagnificationGesture`; visionOS prefers `MagnifyGesture` (alias). Both compile. | ✓ | ✓ |

**Rule:** colors flow as `Material.Color` (cross-platform typealias) inside the renderer; SwiftUI surfaces use `SwiftUI.Color`. `#if os(macOS)` is used **only** for AppKit chrome (background, pointer-style tweaks) that has no SwiftUI equivalent — never for primitives.

## Goal state

1. **Mac (today):** the user picks "Whole Library" in the rooms sidebar; the scene shows every document (as a page-card) and every KG entity (as a sphere), with directed lines for citation / mentions / depicts / related / contradicts / supersedes. Pan / zoom / tap behave like today's room view.
2. **iPhone tabletop AR (Phase 3 milestone):** the same `RealityView` content, anchored to a detected horizontal plane via `AnchorEntity(.plane(.horizontal, ...))` instead of `.world`. The user walks around the scene; the gesture rig switches from `MagnificationGesture` (trackpad pinch) to `MagnifyGesture` (touch pinch) — already the same code path because `MagnifyGesture` is the visionOS / iOS 18 form and SwiftUI aliases it.
3. **Apple Vision Pro:** no `PerspectiveCamera` (the system manages the head); RealityView content anchors to `.head` or `.world` and the scene presents at full scale. `HoverEffectComponent` already provides the per-platform highlight; no extra code.

## Object model

Every interactive thing in the palace is a `MindPalaceNode` (already in `SpatialModels.swift`). For the whole-library view the same node type carries new origins:

| Node kind | `nodeType` | `sourceId` | Mesh | Texture | Notes |
|---|---|---|---|---|---|
| Document card | `.source` | document ID | `Plane` (3:4 page aspect) | thumbnail via `/storage/thumbnail` | Reuses existing card path. |
| Page card | `.source` | child doc ID of the PDF page | `Plane` | per-page thumbnail | Already supported. |
| Entity orb | `.entity` | entity ID | `Sphere` (new) | colored by entity type | New in Phase 3. |
| Claim node | `.claim` | claim ID | `Box` | flat color | Already supported. |
| Note | `.note` | note ID | `Box` | flat color | Already supported. |

The only new mesh is the sphere for entity orbs — `MeshResource.generateSphere(radius:)` works on all three platforms.

**Field model.** `MindPalaceLink` carries the typed edge that the existing `MindPalaceConnection` doesn't fully express on its own:

```swift
struct MindPalaceLink {
    let id: String           // stable hash of (sourceId, targetId, linkType)
    let sourceId: String     // doc or entity ID — NOT a spatial node ID
    let targetId: String     // doc or entity ID
    let linkType: LinkType
    var label: String?       // optional predicate gloss ("cites", "mentions")
    var weight: Double       // for line thickness; 1.0 default
}
```

`MindPalaceLink` is **content-level** (between docs / entities). `MindPalaceConnection` is **room-level** (between spatial nodes a user placed). The whole-library projection emits `MindPalaceLink`s and the renderer converts them into edge entities the same way it converts room connections — same geometry, different colour palette.

## LinkType taxonomy

Drawn from `ClaimRelationType` already in the backend plus the spatial-room `ConnectionType`. Decoded leniently — unknown values fall back to `.related` so a new backend value can't drop the scene.

| Case | Raw | Visual | Source |
|---|---|---|---|
| `.citation` | `citation` / `cites` | solid line, blue | document → document (bibliography) |
| `.mentions` | `mentions` / `mentioned_in` | dashed thin, teal | entity ↔ document |
| `.depicts` | `depicts` / `pictured_in` | solid, magenta | image / page → entity |
| `.related` | `related` / `*` (default) | thin grey | KG `related_to` |
| `.contradicts` | `contradicts` | jagged, red | claim → claim |
| `.supersedes` | `supersedes` | arrow, amber | doc → doc (replaces) |
| `.parentChild` | `parent_child` / `contains` | grey, thick | folder → child, PDF → page |
| `.userDrawn` | `user_drawn` | dashed, neutral | manually drawn in a room |
| `.unknown` | (anything else) | dotted, secondary | safety net |

Phase 1 emits at minimum `.citation`, `.mentions`, `.parentChild`, `.related`. The rest light up as their backend producers come online (no client changes needed — the enum decoder already handles them).

## Gesture rig

All gestures use SwiftUI gesture modifiers + `InputTargetComponent` / `CollisionComponent` so the same code dispatches on every platform.

| Action | Mac (mouse/trackpad) | iOS (tabletop AR) | visionOS | Mapped to |
|---|---|---|---|---|
| **Select** | tap | tap | look + pinch | `TapGesture().targetedToAnyEntity()` (exists) |
| **Move** | click-drag node | touch-drag node | pinch-and-drag | `DragGesture().targetedToAnyEntity()` (exists) |
| **Orbit camera** | trackpad drag in empty space | two-finger swipe | n/a (head moves) | `DragGesture()` on background (exists) |
| **Zoom** | pinch on trackpad | pinch | n/a (walk closer) | `MagnificationGesture()` — visionOS aliases to `MagnifyGesture` (exists) |
| **Hover highlight** | mouse hover | (no equivalent — n/a) | look-at | `HoverEffectComponent` on every interactive entity — system handles per-platform (**new in Phase 3**) |
| **Draw link** | hold ⌥ + drag node-to-node | long-press + drag | pinch one + pinch other | New `DragGesture` variant, ⌥-key flag on Mac, long-press on iOS, system gesture on AVP — design for Phase 4 |
| **Follow link** | tap entity orb | tap | look + pinch | tap handler reads neighbors, centres camera, tints neighbors — **scaffolded in Phase 3 (this PR)** |
| **Filter by link type** | toolbar segmented control | bottom sheet | spatial menu | SwiftUI overlay over `RealityView` — Phase 4 |

`HoverEffectComponent` is the only addition needed for the per-platform highlight to "just work"; the system surfaces it as cursor change on Mac, system tint on visionOS, and skips it on iOS.

## Performance budget

The RealityKit renderer is bottlenecked by entity count (one draw call per `ModelEntity` unless instanced) and texture memory (page thumbnails).

| Scale | Mac (M1 / M3) | iPhone (A17) | Vision Pro (M2) |
|---|---|---|---|
| ≤ 200 nodes | 60 fps trivially | 60 fps | 90 fps |
| 200–1 000 | 60 fps with hover off on non-near nodes | 30–60 fps depending on textures | 90 fps |
| 1 000–5 000 | requires LOD: textured cards only within camera frustum; far cards become flat-colored planes; spheres become icosphere with 12 subdivisions | 30 fps with LOD | 60–90 fps with LOD |
| 5 000–20 000 | requires backend-side culling (return only on-screen + 1-hop), spatial chunking, mesh instancing | not viable without culling | 30 fps with culling + LOD |
| > 20 000 | levels-of-detail + paging: keep top-N relevant in cache; stream others on focus | n/a | streaming only |

**LOD strategy (Phase 4):**

1. **Mesh LOD:** spheres swap subdivisions by camera distance; cards drop their textured plane for a flat-color one past a threshold.
2. **Texture cache budget:** the existing `MindPalaceTextureCache` becomes LRU with a cap (e.g. 256 MB on Mac, 64 MB on iPhone, 256 MB on Vision Pro).
3. **Frustum culling:** maintain backend-side spatial chunking; the canvas only requests nodes whose position is in (or near) the camera frustum. This requires the **backend** to gain a `/api/mind-palace/library/scene?bounds=` endpoint (Phase 4).
4. **Edge throttle:** for `N` nodes, edges scale `O(N²)` worst case. Cap at top-K incident links per node (K=8 default), with the filter chip restoring the rest on demand.

Phase 1 ships with **no** LOD — small libraries (< 500 docs) render straightforwardly. The design doc reserves the capability for Phase 4.

## Phase plan

| Phase | Scope | Target |
|---|---|---|
| **1 (this PR)** | Whole-library Mac scene. Sphere mesh for entities, cylinder mesh for links, `MindPalaceLink` model, `LinkType` taxonomy, hover effect, tap-to-follow-link with neighbor highlight + camera recentre. **Cross-platform-clean renderer code.** | Mac, < 500 docs |
| **2** | Link-type filter chips, group-by-link-type selection (select all neighbors via type-N), per-link weight + thickness, claim/note projection. | Mac |
| **3** | iOS port: `AnchorEntity(.plane(.horizontal, ...))` for tabletop AR; switch `PerspectiveCamera` off when an anchor takes over; ARKit session plumbing. The renderer file is already cross-platform; only the host view changes. | iPhone (iOS 18) |
| **4** | LOD pipeline + backend `/api/mind-palace/library/scene` endpoint (frustum culling, layout authority moves to backend per `feedback_kg_logic_in_backend`). Edge cap + top-K incident links. | Mac + iPhone |
| **5** | visionOS app target: no camera (head is camera), shared scene module compiled into the visionOS bundle, hover-effect strong on AVP, immersive space. | Apple Vision Pro |

## Data plumbing

Phase 1 composes the projection from endpoints that already exist:

| Source | Endpoint | What we use |
|---|---|---|
| Documents | `GET /api/documents` | Every document becomes a node (`.source`, `sourceId` = doc ID). |
| KG entities | `GET /api/entities` | Every entity becomes an orb (`.entity`, `sourceId` = entity ID). |
| KG claims | `GET /api/claims` | Each claim carrying two entity IDs becomes a `MindPalaceLink` with `linkType` derived from its predicate. |
| Doc-doc citations | `GET /api/citations/edges` (planned `#1190`) — Phase 1 falls back to none. | Citation links. |
| Folder hierarchy | `GET /api/documents/{id}/children` | `parentChild` links between parents and children. |
| Thumbnails | `GET /storage/thumbnail/{doc_id}` | Page-card texture (existing). |

**Layout authority:** per `feedback_kg_logic_in_backend`, the *eventual* home of positions is the backend. Phase 1 uses a deterministic **client-side** phyllotaxis layout (golden-angle spiral, seeded by entity ID hash) as a placeholder so the design ships now. Phase 4 moves this to a `/api/mind-palace/library/scene` endpoint that returns nodes with positions already computed (and persists user moves).

The placeholder layout is deterministic — same input order → same positions — so re-opens stay stable.

## Inter-app consistency

Mind Palace selection threads through the same `MindPalaceState.shared` singleton as the rest of Fichero ([[wireframe]] + existing `ClaimFocusState`). The whole-library scene reuses the same selection rules:

- Tap a doc card → `selectedNodeId` updates → `SpatialNodeInspector` shows it.
- Inspector's "Open source" button posts `.ficheroOpenClaimSource` → `ContentView` switches mode to Library + reveals the doc. Phase-3 sources behave identically.
- Whole-library scope honours the active library (`LibraryManager.shared.currentLibraryId`); switching libraries clears the scene and reloads.

The whole-library "room" appears in the existing `RoomListView` as a pinned pseudo-room with `id == "__library__"`. The container detects this ID and switches to the projection loader instead of `service.listNodes(roomId:)`.

## File-by-file change set for Phase 1

| File | Change |
|---|---|
| `fichero/fichero/Models/SpatialModels.swift` | Add `LinkType` enum, `MindPalaceLink` struct, `wholeLibraryRoomId` constant, lenient `linkType` accessor on `MindPalaceConnection` (derived from `linkSubtype`). |
| `fichero/fichero/Models/MindPalaceTheme.swift` *(new)* | Cross-platform palette: `func materialColor(for: MindPalaceNodeType) -> Material.Color`, `func materialColor(for: LinkType) -> Material.Color`, SwiftUI `Color` adapters for non-RealityKit UI. |
| `fichero/fichero/Services/MindPalaceLibraryProjector.swift` *(new)* | Composes docs + entities + claims into `[MindPalaceNode]` + `[MindPalaceLink]`, seeded phyllotaxis layout, single-call `project(scope:)`. Annotated TODO for backend takeover. |
| `fichero/fichero/Views/MindPalace/SpatialScene3D.swift` | Replace `NSColor` palette with `MindPalaceTheme`. Sphere mesh for `.entity` nodes. `MeshResource.generateCylinder` for edges. `HoverEffectComponent` on every interactive entity. Accept optional `links: [MindPalaceLink]` alongside `connections`; emit edges from both. On `selectedNodeId` change, smoothly recentre camera focus on that node and tint first-degree neighbors. |
| `fichero/fichero/Views/MindPalace/MindPalaceWindow.swift` | When `selectedRoomId == wholeLibraryRoomId`, run the projector instead of `service.listNodes`. |
| `fichero/fichero/Views/MindPalace/RoomListView.swift` | Pin a "Whole Library" entry at the top of the rooms list. |
| `fichero/fichero-tests/MindPalaceLinkTypeTests.swift` *(new)* | `LinkType` decode coverage (raw + unknown fallback), `MindPalaceLink.id` stability, phyllotaxis determinism, `MindPalaceConnection.linkType` derivation from `linkSubtype`. |

## Open questions for later phases

- **Backend layout endpoint:** the Phase-4 `/api/mind-palace/library/scene` should accept a frustum + LOD hint and return nodes + edges already placed. Will it persist user moves on a per-library "default room" or a separate spatial index? Per `feedback_kg_logic_in_backend`, this belongs in backend; the client shouldn't recompute layout.
- **Link weight:** should weight come from claim count, recency, or graph centrality? For Phase 1 the renderer accepts a `weight` field but the projector emits `1.0`; the backend takeover picks the policy.
- **Immersive space vs windowed (visionOS):** Phase 5 likely wants both — a window app for browsing rooms and an immersive scene for the whole library. Decide before Phase 5.
- **Tabletop scale:** at what physical size does the iPhone AR projection feel right (entire library on a coffee table vs. on a desk)? Likely a user setting.
