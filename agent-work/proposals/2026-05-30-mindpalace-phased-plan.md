# Mind Palace → Spatial Library — Phased Plan (2026-05-30)

**Goal:** Mind Palace becomes the spatial view of the *whole* Fichero corpus (every doc + entity + link), one codebase across Mac (now) → iPhone tabletop AR → Apple Vision Pro. Same RealityKit scene graph + same backend data everywhere; only the host shell (window vs AR anchor vs immersive space) differs per platform.

**Existing surface to build on (do NOT reinvent):**
- Swift: `SpatialScene3D.swift` (RealityKit `RealityView` + `ModelEntity` spheres, `SpatialTapGesture().targetedToAnyEntity()`), `SpatialView.swift` (2D toggle), `MindPalaceState.swift`, `MindPalaceService.swift`, `SpatialModels.swift`, `SpatialNodeInspector.swift`, `RoomListView`.
- Backend: `api/routes/mind_palace.py` — rooms, nodes (place/move/remove), **connections (create/remove/list)**, stacks, notes, viewport (save/capture/restore), `focus_node`, `suggest_arrangement`, `scene_summary`. Models: `MindPalaceRoom/Node/Connection/Stack/Viewport/Note`.

**Cross-platform rule (all phases):** render only via RealityKit primitives present on **macOS 15 / iOS 18 / visionOS 2** — `RealityView`, `Entity`, `ModelEntity`, `InputTargetComponent`, `CollisionComponent`, `HoverEffectComponent`, `AnchorEntity`. **No AppKit-only calls and no visionOS-only calls in shared code.** KG/aggregation logic stays in the backend ([[feedback_kg_logic_in_backend]]).

---

## P1 — Mac, NOW: full-library navigation + visible LinkType links

**Verified state of `SpatialScene3D.swift`:** already RealityKit — `RealityView`, `ModelEntity` cards, `TapGesture().targetedToAnyEntity()`, with `InputTargetComponent`+`CollisionComponent` set on every node unconditionally (Mac hit-testing already works). Drag-to-move, camera orbit/zoom, viewport persistence exist. Nodes carry `.source/.claim/.entity/.note`; connections carry `ConnectionType`+`link_subtype`. **Extend, don't rebuild.**

**Real gaps P1 must close:**
1. **No full-library population.** Today nodes are room-scoped and manually placed (`place_node`). Core P1 work = a backend snapshot that auto-builds nodes from every `Document` + `KnowledgeEntity` and edges from every `KnowledgeClaim`, no manual placement.
2. **Edges have no label.** `makeEdgeEntity` draws a colored box only — add the LinkType text (predicate via `slug_verb`, [[project_kg_common_helpers]]) so connections are readable.
3. **AppKit-only color = the real cross-platform blocker.** Lines 47/88/318–338 use `NSColor` + `Color(nsColor: .textBackgroundColor)` — won't compile on iOS/visionOS. Replace with a shared color helper (SwiftUI `Color`, or `#if os` UIColor/NSColor) **now**, before P3, so later targets need no rewrite.
4. **Scene built only in `make:`** (re-keyed view rebuilds whole `RealityView`) — fine for a room, won't scale to a corpus. Move to incremental add/remove/move by `entity.name` in `update:`.

**Data plumbing:** new `GET /api/mind_palace/library_snapshot` → nodes (one per `Document` + `KnowledgeEntity`) + edges (one per `KnowledgeClaim`, predicate → `link_subtype`). `include_children` settable (default `false` hides page entities — [[project_known_red_dedup_test]] sibling). `ConnectionType`/`link_subtype` already exist (no new field) — populate them from the claim predicate. Keep aggregation backend-side ([[feedback_kg_logic_in_backend]]).

**Interaction list → RealityKit mapping:**
- Select node → `TapGesture().targetedToAnyEntity()` (present) + `InputTargetComponent`/`CollisionComponent` (present).
- Drag-reposition → `DragGesture().targetedToAnyEntity()` (present) persisting via `move_node`.
- Orbit/pan/zoom → SwiftUI gestures on `RealityView` (present).
- Hover highlight → **add `HoverEffectComponent`** (cross-platform; not yet used).
- Edges → existing thin `ModelEntity` box + **new LinkType label**.

**Child tickets:**
1. Backend `GET /api/mind_palace/library_snapshot` (docs+entities+claims → nodes+edges, `include_children`).
2. Wire snapshot into `MindPalaceService`/`MindPalaceState` so the scene loads the whole corpus, not a room.
3. Replace `NSColor`/`Color(nsColor:)` with a cross-platform color helper.
4. Add LinkType edge labels + `HoverEffectComponent` highlight.
5. Incremental scene diffing in `update:` (replace make-only build) for corpus scale.

---

## P2 — Link-type filters, group ops, saved arrangements

**Data plumbing:** arrangement persistence already exists (`save_viewport`/`capture_viewport`/restore) — extend to per-workspace named arrangements. Filtering/grouping query the snapshot endpoint by `LinkType`/entity-type; keep aggregation backend-side. `suggest_arrangement` already exists → wire as an auto-layout.

**Interaction list → mapping:**
- Toggle link-type filter → show/hide edge entities (no rebuild); LinkType list comes from backend, not hardcoded ([[feedback_user_editable_not_hardcoded]]).
- Marquee multi-select → collect `targetedToAnyEntity` hits into a selection set.
- Group move/collapse → reparent selection under a transform `Entity`.
- Save/restore arrangement → reuse viewport endpoints, keyed per workspace.

**Child tickets:**
1. Link-type filter chips (backend-driven list).
2. Multi-select + group move/collapse (selection set in `MindPalaceState`).
3. Named per-workspace arrangements over existing viewport endpoints.
4. Auto-layout button wired to `suggest_arrangement`.
5. Entity-type / cluster grouping endpoint (backend).

---

## P3 — iOS port: iPhone tabletop AR (ARKit + RealityKit)

Same `SpatialScene3D` scene builder + same endpoints. New shell only.

**Data plumbing:** identical (HTTP to same engine). Real gap is remote-backend reachability (auth + base URL) — track with existing remote-backend work, not new KG code.

**Interaction → mapping:**
- Place library on a detected surface → `AnchorEntity(.plane(...))` (iOS/visionOS) parenting the graph root; ARKit plane detection.
- Tap-select / drag-node → unchanged `targetedToAnyEntity` (works because P1 made components cross-platform).
- Pinch-scale / two-finger rotate whole table → gestures on the anchor root.

**Platform-only APIs (confine to iOS shell):** `ARKit` session, `AnchorEntity(.plane)`. P1/P2 must inject the scene root (not assume a fixed camera) so the anchor swaps in cleanly.

**Child tickets:**
1. Extract shared scene+data into a Swift package (used by Mac + iOS + visionOS targets).
2. iOS app target + plane-detection `AnchorEntity` table placement.
3. Touch gesture shell (tap/drag/pinch/rotate) reusing component targeting.
4. iOS remote-backend connectivity (auth + base URL).

---

## P4 — visionOS app (Apple Vision Pro)

Same scene; immersive shell. Gaze+pinch select needs **no code change** — `InputTargetComponent` + `targetedToAnyEntity` already resolve it (this is why P1 fixes pay off here).

**visionOS-only APIs (confine to visionOS target):** `ImmersiveSpace`, volumetric `WindowGroup`, hand/world ARKit data, `.ornament` (the one removed from shared code in P1 may return *here*).

**Child tickets:**
1. visionOS target + `ImmersiveSpace` host for the shared scene package.
2. Volumetric window ↔ full-immersive toggle.
3. Room-scale depth/scale ergonomics tuning.

---

## Risks / cross-stack
- **Scale:** thousands of nodes — snapshot needs paging / level-of-detail; incremental diffing (P1) mandatory.
- **OpenAPI round-trip:** new snapshot regenerates `openapi.json` → run `sync_openapi_schema.sh` + BuildProject ([[feedback_backend_merge_needs_swift_build]]); typed `Components.Schemas.*` only (rule 4).
- **Dev-tier:** Mind Palace 404s on the release engine ([[project_fichero_mcp_server_architecture]]).
- **Worker tiers:** backend snapshot = Sonnet; RealityKit scene work + P3/P4 scaffolding = frontier.

## Test plan
- Backend: unit tests for `library_snapshot` + `link_type` (trunk venv, tiny `-k` only — [[feedback_no_full_pytest_on_daniels_machine]]).
- Swift: 3-leg check (swiftlint + BuildProject + RunAllTests) per surface. `RenderPreview` won't help — `RealityView` needs a live scene ([[feedback_renderpreview_app_launch_blocked]]); verify in Xcode canvas / running app.
- Manual (Mac, before any port): snapshot loads → tap selects (proves the component fix) → drag persists → filter → save → reload restores.
