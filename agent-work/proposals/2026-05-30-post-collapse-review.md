# Post-Collapse Review — KG read-path collapse + regression-restore cluster

**Reviewer:** f_reviewer (read-only) · **Date:** 2026-05-30
**Range:** `origin/main..origin/0.0.2`, scoped to the session's collapse/restore commits (#1302, #1304, #1306–#1314, #1319–#1323).
**Verdict:** Mergeable, but **two MAJOR single-code-path findings** and **two MAJOR test holes** should be addressed before this is called "collapsed."

---

## 1. Single-code-path violations

**MAJOR — KG read is NOT actually one path.** #1304 cleanly collapsed the *inspector summary + KG section* onto `entityService.documentKnowledgeGraph(...)` (`DocumentInspector.swift:613`, `DocumentInspectorArtifactsTab.swift:1091`) — old per-entity/per-claim fetch + client grouping deleted. **But** `KGMapView.swift:221` and `KGTimelineView.swift:279` still read via the old `listClaims(sourceDocumentId:includeDescendants:)`, and both are instantiated *inside* `DocumentKGSurface` (`:110/:116`). So the same document-scoped surface reads claims two ways — the canonical endpoint dedupes merged entities and drops tautological claims; raw `listClaims` does not. They can drift. (`EntityDigestView.swift`, `DocumentInspectorInfoTab.swift:173` also still call `listClaims`/`listEntities`.)

**MAJOR — two descendant-walk implementations.** #1313's `_folder_descendant_documents` (folders.py, BFS on `parent_id`, excludes root, returns `list[Document]`) duplicates `_descendant_doc_ids` (claims.py:407, BFS on `parent_id`, includes root, returns `set[str]`). Folder-views scope and document-KG scope now resolve "everything under this folder" via two independent walks with different shapes — exactly the divergence this cluster meant to remove. Recommend one shared helper.

**MINOR — two claim renderers.** OntologyBrowser → `ClaimSummaryCard`; DocumentInspectorArtifactsTab → its own grouped-row render (`:870/:1133`). Pre-existing and arguably intentional (card vs digest), but `ClaimSummaryCard` is not reused in the inspector.

**CLEAN:** #1310 (Map tab) and #1302 (KG sidebar mode) are genuinely *deleted*, not flag-hidden — grep for leftover refs returns 0. Good.

---

## 2. State-preservation regressions

**Sound:** #1306 is real — `OntologyBrowser.selectedEntityId` is now `@SceneStorage`, loaded data moved to `@StateObject OntologyBrowserLoadState` / `KnowledgeGraphInspectorLoadState`. `KGFocusState.shared` is a single `@MainActor @Observable` source of truth injected once — not duplicated. #1319's mutator guards (value-equality early-return in `focusEntity`/`focusClaim`/`clear`) are robust.

**MAJOR — unfixed sibling surface.** `DocumentKGSurface.swift:55–56` still uses plain `@State` for `activeTab`, `selectedEntityId`, `selectedSpatialNodeId` — these reset on navigation, the exact bug #1306 fixed elsewhere ("fixed-one-surface-missed-sibling"). The `@State selectedEntityId` also *shadows* the `let selectedEntityId` parameter at `:49`, leaving the param dead. Should move to `@SceneStorage`/shared state.

**MAJOR — fragile timing guard.** `DocumentKGWebPane.swift:317` breaks the JS↔Swift page echo with `suppressActivePageSyncUntil = Date()+0.25s`. A slow main-thread tick or a legitimate page change inside that 250 ms window is silently dropped (`:269–271`). This papers over the loop with wall-clock timing rather than making page selection one-directional. (Same fragility I flagged on #1253's 180 ms suppress — recurring pattern.)

---

## 3. Cross-platform readiness (MindPalace / SpatialScene3D)

RealityKit usage is **portable** — `RealityView` (not `ARView`), `PerspectiveCamera`, `targetedToAnyEntity()`, `MagnificationGesture`; texture loading uses `URLSession` → `TextureResource.loadAsync` (correct cross-platform path, no `NSImage`). `SpatialModels.swift` is fully portable.

**MAJOR (blocks iOS/visionOS compile) — color APIs, not behind any `os()` guard** (the only guard is `#if canImport(RealityKit)`, true on iOS/visionOS):
- `SpatialScene3D.swift:318/329` — `nsColor(for:)` returns `NSColor` (no iOS equiv); uses `.secondaryLabelColor`/`.systemGray`.
- `SpatialScene3D.swift:47/88` — `Color(nsColor: .textBackgroundColor)`; same at `RoomListView.swift:60` (`Color(NSColor.windowBackgroundColor)`).

Fix is small (~5 lines): return the SwiftUI `Color` the models already expose (`SpatialModels.swift:50/85`) or add an `#if os(macOS)` NSColor/UIColor typealias. Worth doing now to keep the visionOS path open per Daniel's intent.

---

## 4. Test coverage holes

| Behavior | Test? | Hole |
|---|---|---|
| #1304 collapse | backend deep, Swift partial | Backend `knowledge_graph` well-tested; Swift collapse wiring untested (logic is backend-side — minor) |
| #1314 SVO render | yes | Real typed-vs-legacy + provenance assertions |
| #1311/#1312 inspector | yes | `visibleItems` cap, button states covered |
| #1310 / #1313 | yes | Map-tab removal + workspace-folder views covered |
| **#1319 focus-guard** | **NO — MAJOR** | Idempotent drive-direction guards are pure, deterministic, trivially testable; no-oscillation property has zero tests. Highest-value hole — regression reintroduces the loop silently. |
| **#1322 MindPalace texture/camera/tap** | **shallow — MAJOR** | 181 lines of texture-load/tap-select shipped; tests only cover `thumbnailURL` string-building. |
| **#1306 view-state preservation** | **NO** | 92-line state-restore change, no test; regresses with no signal. |
| #1320 force-directed layout | NO | JS/d3 template only — cosmetic, untestable as written (minor) |

**Priority:** (1) #1319 guard idempotency, (2) #1322 texture/tap, (3) #1306 preservation.

---

## Recommended before merge to main
1. Route KGMapView/KGTimelineView through the canonical KG endpoint (or document why they're exempt).
2. Share one folder-descendant walk between folders.py and claims.py.
3. Promote `DocumentKGSurface` `@State` to scene/shared state; delete the shadowed param.
4. Add the #1319 guard unit test (cheap, high value).
5. Optional-but-cheap: `#if os(macOS)` color shim in SpatialScene3D/RoomListView.

The fragile 250 ms page-sync timer and the second-render-path are acceptable to ship with a tracking issue.
