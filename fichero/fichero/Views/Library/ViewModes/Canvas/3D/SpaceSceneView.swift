// swiftlint:disable file_length
import FicheroAPIClient
import OSLog
import SwiftUI
#if canImport(RealityKit)
import RealityKit
#endif

/// RealityKit 3D rendering of a Spatial room — the `.threeD` render mode,
/// and the forward path toward streaming the spatial library to Vision Pro.
///
/// Renders each `SpatialNode` as a page-card at its **backend-provided**
/// `positionX/Y/Z` (with `rotation_*` and `scale` applied) and draws
/// connections as thin links. When a node has a source thumbnail, the card is
/// textured with the actual page image; otherwise it falls back to the
/// coloured block. Positions are read from the backend and only normalized
/// into a bounded cube for the camera — relative geometry is never
/// recomputed (`feedback_kg_logic_in_backend`).
///
/// The scene is rebuilt when the room's data changes (the container keys this
/// view by a scene signature). Tap-to-select, orbit, and zoom are wired through
/// RealityKit gestures. When RealityKit is unavailable the view falls back to
/// the 2D canvas.
struct SpaceSceneView: View {
    let nodes: [SpatialNode]
    let connections: [SpatialConnection]
    /// Phase 3 (#1297 follow-up): content-level typed links (whole-library
    /// projection). Drawn with the same cylinder mesh as room `connections`,
    /// colored by `LinkType`. Empty by default — existing room scenes
    /// unaffected.
    var links: [SpatialLink] = []
    var initialViewport: SpatialViewport?
    var onNodePositionChanged: (String, SIMD3<Double>) -> Void = { _, _ in }
    var onNodeMoveEnded: (String, SIMD3<Double>) -> Void = { _, _ in }
    var onViewportChanged: (SIMD3<Double>, Double) -> Void = { _, _ in }
    @Binding var selectedNodeIds: Set<String>

    /// A single-selection PROJECTION for the legacy `Spatial2DCanvas`, which
    /// still takes one id (#4409).
    ///
    /// Computed from the set and written straight back to it — no parallel
    /// stored selection. Reads as nil unless exactly one node is selected, so a
    /// multi-selection is never misreported as one arbitrary member.
    private var legacySingleSelection: Binding<String?> {
        Binding(
            get: { selectedNodeIds.count == 1 ? selectedNodeIds.first : nil },
            set: { selectedNodeIds = $0.map { [$0] } ?? [] }
        )
    }

    /// Observable layout store (#2293) — the SAME instance the 2D canvas uses.
    /// When non-nil together with `folderScopeId`, the 3D scene becomes a second
    /// renderer on the shared model: it loads persisted positions on appear,
    /// overrides each node's backend default where a saved row exists, reflects
    /// `store.layout` changes (load or agent move) on the live entities, and
    /// writes positions back on drag-end — so a hand-arranged 3D layout survives
    /// a view-mode switch. The store is the only thing that touches the network;
    /// this view never calls the generated client. When nil (Spatial room,
    /// RealityKit fallback) the scene is view-only, exactly as before.
    var layoutStore: CanvasLayoutStore?
    /// Observable canvas-item store (#2294) — the SAME instance the 2D canvas
    /// uses. When non-nil together with `folderScopeId`, the 3D scene renders the
    /// folder's standalone heterogeneous items (note / quote / work_note / text
    /// as cards, `link` as connectors) as a second renderer on the shared model,
    /// loaded on appear and reflected on every `store.items` change. The store is
    /// the only thing that touches the network; this view never calls the
    /// generated client. Nil → no canvas items (Spatial room), exactly as
    /// before.
    var itemStore: CanvasItemStore?
    /// The scope these positions belong to — a real folder id, or the synthetic
    /// `wholeLibraryRoomId` ("__library__") for the unscoped whole-library view.
    var folderScopeId: String?

    /// The CURRENT library's storage service (#4160) — page textures fetch
    /// through it. Nil (Spatial room fallback) uses the global library, as
    /// before. Injected by the host; this view still never touches the
    /// generated client directly.
    var storageService: StorageService?

    /// Non-optional scope key for reading the per-scope shared stores (#3082):
    /// the folder id, or `wholeLibraryRoomId` when unscoped. Mirrors
    /// `Spatial2DCanvas.scopeKey` so both renderers read the SAME scope's rows.
    var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    /// Upper bound on entities the RealityKit scene will build at once (#1400).
    /// A folder projection (`FolderRealityKitSurface`) can scope hundreds of
    /// documents; each rendered node also spawns a concurrent texture
    /// download+decode Task. Unbounded, that storm of `ModelEntity`s + image
    /// I/O sustains GPU/CPU load and was the prime suspect for the macOS
    /// WindowServer watchdog crashes. Beyond the cap we render a bounded prefix
    /// and surface a banner — never a runaway scene.
    private let maxRenderedNodes = 250

    /// The bounded set actually placed in the scene. Backend order is
    /// preserved; relative geometry of the rendered subset is untouched
    /// (`feedback_kg_logic_in_backend`).
    private var renderedNodes: [SpatialNode] {
        nodes.count > maxRenderedNodes ? Array(nodes.prefix(maxRenderedNodes)) : nodes
    }

    private var isTruncated: Bool { nodes.count > maxRenderedNodes }

    /// Honest, non-blocking notice when the scene is bounded (#1400) so a large
    /// scope reads as "showing a subset" rather than silently dropping nodes.
    private var truncationBanner: some View {
        Text("Showing first \(maxRenderedNodes) of \(nodes.count) items")
            .font(.caption)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.regularMaterial, in: Capsule())
            .padding(.top, 8)
    }

    #if canImport(RealityKit)
    @State private var cameraDistance = 5.5
    @State private var orbitYaw = 0.0
    @State private var orbitPitch = 0.0
    /// The point the camera orbits around and looks at. Panning (option-drag)
    /// translates this across the view plane; orbit/zoom keep it fixed. Pure
    /// view state — not persisted (a saved pan offset is a FUTURE concern;
    /// ponytail: viewport persistence still records only orbit/zoom).
    @State private var lookAtTarget = SIMD3<Float>(0, 0, 0)
    /// Orbit angles (x = yaw, y = pitch) + the drag translation captured at the
    /// moment an orbit drag begins, so each frame is computed as an absolute
    /// offset from that baseline (the first delta is zero — no snap on start).
    @State private var orbitDragStart: (angles: SIMD2<Double>, translation: CGSize)?
    /// Look-at target + drag translation captured when a pan drag begins, for
    /// the same seed-from-current (no start-jump) reason as `orbitDragStart`.
    @State private var panDragStart: (target: SIMD3<Float>, translation: CGSize)?
    /// Whether the Option key is currently held — flips the background drag from
    /// orbit to pan. Tracked via `onModifierKeysChanged` so one drag gesture
    /// serves both without two conflicting simultaneous gestures.
    @State private var optionHeld = false
    @State private var magnificationStart = 1.0
    @State private var nodeDragOrigins: [String: SIMD3<Double>] = [:]
    @State private var nodeDragPositions: [String: SIMD3<Double>] = [:]
    /// Bumped whenever `layoutStore.layout` changes so the RealityView `update`
    /// pass re-runs and repositions entities to the new persisted positions.
    @State private var layoutRevision = 0
    #endif

    var body: some View {
        if nodes.isEmpty && (itemStore?.items(for: scopeKey).isEmpty ?? true) {
            ContentUnavailableView(
                "Empty Space",
                systemImage: "cube.transparent",
                description: Text("No source pages or spatial nodes are available in this scope yet.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(platformColor: .textBackgroundColor))
        } else {
        #if canImport(RealityKit)
        RealityView(
            make: { content in
                // Default virtual camera, pulled back to frame the normalized cube.
                let camera = PerspectiveCamera()
                camera.name = "spatial-camera"
                updateCamera(camera)
                content.add(camera)

                let root = buildScene()
                root.name = "spatial-root"
                content.add(root)
            },
            update: { content in
                if let camera = content.entities
                    .compactMap({ $0 as? PerspectiveCamera })
                    .first(where: { $0.name == "spatial-camera" }) {
                    updateCamera(camera)
                }
                // Drive the live entities from `store.layout`: re-place each
                // (non-dragging) node at its effective position so a load or
                // agent move is reflected without rebuilding the scene. Nodes
                // mid-drag are skipped so the gesture's transform isn't fought.
                if layoutStore != nil,
                    let root = content.entities.first(where: { $0.name == "spatial-root" }) {
                    let (scale, center) = normalize()
                    for node in renderedNodes where nodeDragOrigins[node.id] == nil {
                        root.findEntity(named: node.id)?
                            .position = position(for: node, scale: scale, center: center)
                    }
                }
                // Reflect `itemStore.items` (load or agent change) onto the live
                // canvas-item entities: add new cards, reposition existing ones,
                // drop removed ones, and rebuild link connectors. Reading
                // `itemStore?.items` here ties this pass to the observable store.
                if itemStore != nil,
                    let root = content.entities.first(where: { $0.name == "spatial-root" }) {
                    reconcileCanvasItems(in: root)
                }
            }
        )
        .gesture(
            TapGesture()
                .targetedToAnyEntity()
                .onEnded { value in
                    let nodeId = value.entity.name
                    guard !nodeId.isEmpty else { return }
                    selectedNodeIds = [nodeId]
                }
        )
        .simultaneousGesture(cameraDragGesture)
        .simultaneousGesture(cameraZoomGesture)
        .simultaneousGesture(nodeDragGesture)
        #if canImport(AppKit)
        .onModifierKeysChanged(mask: .option) { _, modifiers in
            optionHeld = modifiers.contains(.option)
        }
        #endif
        .onAppear {
            applyInitialViewportIfNeeded()
        }
        .onChange(of: initialViewport) { _, _ in
            applyInitialViewportIfNeeded()
        }
        .onChange(of: selectedNodeIds) { _, newValue in
            focusCamera(onNodeId: newValue.count == 1 ? newValue.first : nil)
        }
        // Load the shared store's persisted layout for this scope; the entities
        // then reflect `store.layout` via the `update` pass below.
        .task(id: folderScopeId) {
            guard let folderId = folderScopeId else { return }
            if let store = layoutStore { await store.loadLayout(folderId: folderId) }
            if let items = itemStore { await items.loadItems(folderId: folderId) }
            // Always bump layoutRevision after load completes so the update:
            // pass re-runs and repositions entities to the freshly-loaded
            // positions — even if the layout array value didn't change (e.g.
            // same positions as the store already held from a prior visit).
            // This fixes the circle-reset: buildScene() in make: places nodes
            // at phyllotaxis defaults; this bump forces the corrective
            // reposition once the persisted layout is confirmed from the server.
            layoutRevision += 1
        }
        // Reading `layoutStore?.layout` here ties the body to the observable
        // store: a load or agent move re-renders the view, re-runs `update`, and
        // repositions the live entities to the new persisted positions.
        .onChange(of: layoutStore?.layout(for: scopeKey)) { _, _ in
            layoutRevision += 1
        }
        // Canvas items changed (load / add / delete / agent edit) — bump the
        // revision so the RealityView `update` pass re-runs and reconciles the
        // live item entities against `store.items`.
        .onChange(of: itemStore?.items(for: scopeKey)) { _, _ in
            layoutRevision += 1
        }
        // Flush any in-progress node drag so positions are not lost when the
        // user navigates away mid-drag (gesture.onEnded never fires then).
        .onDisappear {
            guard !nodeDragOrigins.isEmpty else { return }
            for (nodeId, _) in nodeDragOrigins {
                if let position = Self.persistedDragEndPosition(
                    nodeId: nodeId,
                    dragPositions: nodeDragPositions,
                    nodes: nodes
                ) {
                    persistLayout(movedId: nodeId, to: position)
                }
            }
            nodeDragOrigins.removeAll()
            nodeDragPositions.removeAll()
        }
        .background(SpaceTheme.canvasBackground)
        .overlay(alignment: .top) {
            if isTruncated { truncationBanner }
        }
        .overlay(alignment: .topTrailing) {
            if layoutStore != nil, folderScopeId != nil, !renderedNodes.isEmpty {
                gridArrangeButton
            }
        }
        #else
        Spatial2DCanvas(
            nodes: nodes, connections: connections, selectedNodeId: legacySingleSelection,
            storageService: storageService
        )
        #endif
        }
    }
}

// MARK: - Drag-end snap (platform-independent, unit-tested)

extension SpaceSceneView {
    /// The grid-snapped rest position for a node when its drag ends: the tracked
    /// live drag position snapped to the grid if the node was actually moved,
    /// else the node's own snapped backend position. Pure (no RealityKit), so it
    /// is testable on every platform and reachable from `SpaceSceneViewTests`.
    static func persistedDragEndPosition(
        nodeId: String,
        dragPositions: [String: SIMD3<Double>],
        nodes: [SpatialNode]
    ) -> SIMD3<Double>? {
        if let dragged = dragPositions[nodeId] {
            return SIMD3<Double>(
                SpatialNode.snap(dragged.x),
                SpatialNode.snap(dragged.y),
                SpatialNode.snap(dragged.z)
            )
        }
        return nodes.first(where: { $0.id == nodeId })?.snappedPosition()
    }
}

#if canImport(RealityKit)
private extension SpaceSceneView {
    /// Background drag = orbit, or pan when Option is held. Both seed from the
    /// camera's current state at the gesture's first event and then compute an
    /// absolute offset from that baseline, so there is never a snap when the
    /// drag begins (the old code accumulated deltas from a zeroed `dragStart`,
    /// which jumped by the whole first translation on every new drag).
    private var cameraDragGesture: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                guard nodeDragOrigins.isEmpty else { return }
                if optionHeld {
                    panCamera(with: value.translation)
                } else {
                    orbitCamera(with: value.translation)
                }
            }
            .onEnded { _ in
                orbitDragStart = nil
                panDragStart = nil
                persistViewport()
            }
    }

    /// Orbit yaw/pitch as an absolute offset from the angles captured when the
    /// drag started — continuous, clamped, no start-jump.
    private func orbitCamera(with translation: CGSize) {
        let start = orbitDragStart ?? (SIMD2<Double>(orbitYaw, orbitPitch), translation)
        if orbitDragStart == nil { orbitDragStart = start }
        let deltaX = Double(translation.width - start.translation.width)
        let deltaY = Double(translation.height - start.translation.height)
        orbitYaw = start.angles.x + deltaX * 0.008
        orbitPitch = min(1.15, max(-1.15, start.angles.y + deltaY * 0.008))
    }

    /// Translate the look-at target across the camera's right/up plane (Option-
    /// drag). Speed scales with distance so the pan feels constant at any zoom.
    private func panCamera(with translation: CGSize) {
        let start = panDragStart ?? (lookAtTarget, translation)
        if panDragStart == nil { panDragStart = start }
        let deltaX = Float(translation.width - start.translation.width)
        let deltaY = Float(translation.height - start.translation.height)
        let yaw = Float(orbitYaw)
        let pitch = Float(orbitPitch)
        let right = SIMD3<Float>(cos(yaw), 0, -sin(yaw))
        let upVector = SIMD3<Float>(-sin(yaw) * sin(pitch), cos(pitch), -cos(yaw) * sin(pitch))
        let speed = Float(cameraDistance) * 0.0022
        lookAtTarget = start.target + (-right * deltaX + upVector * deltaY) * speed
    }

    private var cameraZoomGesture: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                let delta = value / magnificationStart
                guard delta.isFinite, delta > 0 else { return }
                cameraDistance = min(12.0, max(2.2, cameraDistance / delta))
                magnificationStart = value
            }
            .onEnded { _ in
                magnificationStart = 1.0
                persistViewport()
            }
    }

    private var nodeDragGesture: some Gesture {
        DragGesture(minimumDistance: 2)
            .targetedToAnyEntity()
            .onChanged { value in
                let nodeId = value.entity.name
                guard let node = nodes.first(where: { $0.id == nodeId }) else { return }
                if nodeDragOrigins[nodeId] == nil {
                    // Start the drag from the node's *effective* spot (persisted
                    // row if any, else backend default) so a saved position
                    // isn't lost on the first grab.
                    nodeDragOrigins[nodeId] = effectivePosition(for: node)
                    selectedNodeIds = [nodeId]
                }
                guard let origin = nodeDragOrigins[nodeId] else { return }
                let normalized = normalize()
                let rawDeltaX = Double(value.translation.width) * 0.01 / Double(normalized.scale)
                let rawDeltaY = -Double(value.translation.height) * 0.01 / Double(normalized.scale)
                // Track the drag *continuously* (no snap here): live-snapping
                // made the node jump cell-to-cell across the 0.25 grid while
                // dragging — the "jumpy grid". Snapping happens once on release
                // via `persistedDragEndPosition`, so the rest position is still
                // grid-aligned but the drag itself is smooth.
                let next = SIMD3<Double>(
                    origin.x + rawDeltaX,
                    origin.y + rawDeltaY,
                    origin.z
                )
                nodeDragPositions[nodeId] = next
                onNodePositionChanged(nodeId, next)
                let rawPosition = SIMD3<Float>(Float(next.x), Float(next.y), Float(next.z))
                value.entity.position = (rawPosition - normalized.center) * normalized.scale
            }
            .onEnded { value in
                let nodeId = value.entity.name
                if let position = Self.persistedDragEndPosition(
                    nodeId: nodeId,
                    dragPositions: nodeDragPositions,
                    nodes: nodes
                ) {
                    onNodeMoveEnded(nodeId, position)
                    persistLayout(movedId: nodeId, to: position)
                }
                nodeDragOrigins.removeValue(forKey: nodeId)
                nodeDragPositions.removeValue(forKey: nodeId)
            }
    }

    private func updateCamera(_ camera: PerspectiveCamera) {
        let yaw = Float(orbitYaw)
        let pitch = Float(orbitPitch)
        let distance = Float(cameraDistance)
        let offset = SIMD3<Float>(
            sin(yaw) * cos(pitch) * distance,
            sin(pitch) * distance,
            cos(yaw) * cos(pitch) * distance
        )
        camera.position = lookAtTarget + offset
        camera.look(at: lookAtTarget, from: camera.position, relativeTo: nil)
    }

    private var currentCameraPosition: SIMD3<Double> {
        let yaw = orbitYaw
        let pitch = orbitPitch
        let distance = cameraDistance
        return SIMD3<Double>(
            sin(yaw) * cos(pitch) * distance,
            sin(pitch) * distance,
            cos(yaw) * cos(pitch) * distance
        )
    }

    private func persistViewport() {
        onViewportChanged(currentCameraPosition, cameraDistance)
    }

    /// Phase 3 follow-link behavior: on selection (tap), orbit camera toward
    /// the node and expose its first-degree neighbor set for future tinting.
    private func focusCamera(onNodeId nodeId: String?) {
        // Don't yank the camera while a node is being dragged: the drag's first
        // `onChanged` sets `selectedNodeId`, which would otherwise fire this and
        // fight the grab. Deliberate tap-selection (no drag) still focuses.
        guard nodeDragOrigins.isEmpty else { return }
        guard let nodeId, let node = nodes.first(where: { $0.id == nodeId }) else { return }
        let (scale, center) = normalize()
        let pos = position(for: node, scale: scale, center: center)
        let length = max(simd_length(SIMD3<Float>(pos.x, 0, pos.z)), 0.0001)
        let targetYaw = Double(atan2(pos.x, pos.z))
        let targetPitch = Double(atan2(pos.y, length))
        withAnimation(.easeInOut(duration: 0.45)) {
            // Recenter the pan target so the focused node frames correctly even
            // after an Option-drag pan moved the look-at point.
            lookAtTarget = .zero
            orbitYaw = targetYaw
            orbitPitch = max(-1.15, min(1.15, targetPitch))
        }
        persistViewport()
    }

    /// First-degree neighbor IDs across both room connections and content
    /// links. Exposed (internal) so the inspector / future filter overlay can
    /// share the scan; renderer doesn't tint per-platform yet.
    func neighborIds(of nodeId: String) -> Set<String> {
        var result: Set<String> = []
        for connection in connections {
            if connection.sourceNodeId == nodeId { result.insert(connection.targetNodeId) }
            if connection.targetNodeId == nodeId { result.insert(connection.sourceNodeId) }
        }
        for link in links {
            if link.sourceId == nodeId { result.insert(link.targetId) }
            if link.targetId == nodeId { result.insert(link.sourceId) }
        }
        result.remove(nodeId)
        return result
    }

    private func applyInitialViewportIfNeeded() {
        guard let initialViewport else { return }
        let position = SIMD3<Double>(
            initialViewport.cameraX,
            initialViewport.cameraY,
            initialViewport.cameraZ
        )
        let distance = max(2.2, min(12.0, simd_length(position)))
        guard distance.isFinite, distance > 0 else { return }
        cameraDistance = distance
        lookAtTarget = .zero
        orbitYaw = atan2(position.x, position.z)
        orbitPitch = asin(max(-1.0, min(1.0, position.y / distance)))
    }

    /// Normalize backend positions into a bounded cube (~[-1.5, 1.5]) so the
    /// fixed camera frames any room. Uniform scale preserves relative layout.
    private func normalize() -> (scale: Float, center: SIMD3<Float>) {
        let scope = renderedNodes
        guard !scope.isEmpty else { return (1, .zero) }
        let effective = scope.map { effectivePosition(for: $0) }
        let xValues = effective.map { Float($0.x) }
        let yValues = effective.map { Float($0.y) }
        let zValues = effective.map { Float($0.z) }
        let center = SIMD3<Float>(
            (xValues.min()! + xValues.max()!) / 2,
            (yValues.min()! + yValues.max()!) / 2,
            (zValues.min()! + zValues.max()!) / 2
        )
        let span = max(
            xValues.max()! - xValues.min()!,
            yValues.max()! - yValues.min()!,
            zValues.max()! - zValues.min()!
        )
        let scale: Float = span > 0 ? 3.0 / span : 1
        return (scale, center)
    }

    private func position(for node: SpatialNode, scale: Float, center: SIMD3<Float>) -> SIMD3<Float> {
        let effective = effectivePosition(for: node)
        let raw = SIMD3<Float>(Float(effective.x), Float(effective.y), Float(effective.z))
        return (raw - center) * scale
    }

    /// The node's effective position: the persisted `CanvasItemLayout` row from
    /// the shared store where one exists, else the node's backend default. This
    /// is the single override point that makes the 3D scene a second renderer on
    /// the observable model (#2293) rather than a separate island.
    private func effectivePosition(for node: SpatialNode) -> SIMD3<Double> {
        if let row = layoutStore?.layout(for: scopeKey).first(where: { $0.itemId == node.id }) {
            return SIMD3<Double>(row.x, row.y, row.z)
        }
        return SIMD3<Double>(node.positionX, node.positionY, node.positionZ)
    }

    /// Persist the moved node's position through the shared store (#2293). All
    /// visible nodes missing a row are seeded at their current effective spot so
    /// the layout is stable on reload; the moved node is then patched to its
    /// drop point. x/y/z are written; angle and any extents on existing rows are
    /// preserved (the 3D drag changes neither). No-op without store + scope.
    private func persistLayout(movedId: String, to position: SIMD3<Double>) {
        guard let store = layoutStore, let folderId = folderScopeId else { return }
        var rows: [String: CanvasItemLayout] = Dictionary(
            store.layout(for: folderId).map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        for node in renderedNodes where rows[node.id] == nil {
            let effective = effectivePosition(for: node)
            rows[node.id] = CanvasItemLayout(
                itemId: node.id, x: effective.x, y: effective.y, z: effective.z
            )
        }
        rows[movedId]?.x = position.x
        rows[movedId]?.y = position.y
        rows[movedId]?.z = position.z
        let items = Array(rows.values)
        Task { await store.saveLayout(folderId: folderId, items: items) }
    }

    /// Native control to lay the source pages out in a grid by page order
    /// (#1726). Aspect ratio is already preserved per-card in `makeNodeEntity`.
    private var gridArrangeButton: some View {
        Button {
            arrangeInGrid()
        } label: {
            Image(systemName: "square.grid.3x3")
        }
        .buttonStyle(.borderless)
        .accessibilityLabel("Arrange pages in a grid")
        .padding(8)
        .help("Arrange pages in a grid by page order")
    }

    /// Lay every rendered node out on a regular grid, ordered by the page order
    /// in which the backend delivered them, and persist through the shared
    /// layout store (#1726). Mirrors the backend `grid` strategy
    /// (`spatial_arrange._grid`): `cols = ceil(sqrt(n))`, evenly spaced. Existing
    /// rows for these nodes are overwritten; rows for other items are preserved.
    /// No-op without store + scope.
    private func arrangeInGrid() {
        guard let store = layoutStore, let folderId = folderScopeId else { return }
        let ordered = renderedNodes
        guard !ordered.isEmpty else { return }
        var rows: [String: CanvasItemLayout] = Dictionary(
            store.layout(for: folderId).map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        let spacing = 1.0
        let cols = max(1, Int(ceil(Double(ordered.count).squareRoot())))
        for (index, node) in ordered.enumerated() {
            let posX = Double(index % cols) * spacing
            let posY = Double(index / cols) * spacing
            if rows[node.id] != nil {
                rows[node.id]?.x = posX
                rows[node.id]?.y = posY
                rows[node.id]?.z = 0
                rows[node.id]?.zIndex = index
            } else {
                rows[node.id] = CanvasItemLayout(itemId: node.id, x: posX, y: posY, z: 0, zIndex: index)
            }
        }
        let items = Array(rows.values)
        Task { await store.saveLayout(folderId: folderId, items: items) }
    }

    private func buildScene() -> Entity {
        let (scale, center) = normalize()
        let root = Entity()

        var positions: [String: SIMD3<Float>] = [:]
        for node in renderedNodes {
            let pos = position(for: node, scale: scale, center: center)
            positions[node.id] = pos
            root.addChild(makeNodeEntity(node, at: pos))
        }

        // Room-level connections — typed by `linkType` (lenient mapping from
        // the room `ConnectionType` + optional `linkSubtype`).
        for connection in connections {
            guard
                let from = positions[connection.sourceNodeId],
                let toEnd = positions[connection.targetNodeId]
            else { continue }
            root.addChild(makeEdgeEntity(from: from, to: toEnd, linkType: connection.linkType, weight: 1.0))
        }

        // Phase 3: content-level typed links from the whole-library
        // projection. Same cylinder geometry, palette comes from `LinkType`.
        for link in links {
            guard
                let from = positions[link.sourceId],
                let toEnd = positions[link.targetId]
            else { continue }
            root.addChild(makeEdgeEntity(from: from, to: toEnd, linkType: link.linkType, weight: link.weight))
        }

        // Standalone heterogeneous canvas items (#2294) — cards + link
        // connectors. Built here for items already loaded, and kept live by the
        // `update` pass which re-runs `reconcileCanvasItems` on store change.
        reconcileCanvasItems(in: root)

        return root
    }

    private func makeNodeEntity(_ node: SpatialNode, at position: SIMD3<Float>) -> ModelEntity {
        let scale = Float(max(node.scale, 0.25))
        let cardWidth: Float = 0.8 * scale
        let cardHeight: Float = cardWidth / pageAspectRatio
        let geometry = nodeGeometry(for: node, cardWidth: cardWidth, cardHeight: cardHeight)

        let entity = ModelEntity(mesh: geometry.mesh, materials: geometry.materials)
        entity.position = position
        entity.orientation = simd_quatf(angle: Float(node.rotationY), axis: SIMD3<Float>(0, 1, 0))
        entity.name = node.id
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(shapes: [geometry.collisionShape]))
        // Cross-platform highlight: cursor change on Mac, system tint on
        // visionOS. One line, no per-platform branch.
        entity.components.set(HoverEffectComponent())

        if let sourceId = node.sourceId, !sourceId.isEmpty, node.nodeType == .source {
            refineWithPageTexture(
                entity,
                sourceId: sourceId,
                cardWidth: cardWidth,
                cardHeight: cardHeight
            )
        }

        return entity
    }

    /// What a node is drawn with. A named type rather than a tuple: three
    /// members is past the point where positional access reads clearly, and
    /// the collision shape is deliberately part of the same value because it
    /// must always track the drawn mesh.
    private struct NodeGeometry {
        let mesh: MeshResource
        let materials: [any RealityFoundation.Material]
        let collisionShape: ShapeResource
    }

    /// The drawn shape for one node: a sphere for an entity, a true-aspect page
    /// plane for a source, a rounded box otherwise. Collision always tracks the
    /// drawn shape, or hit-testing drifts from what is on screen.
    private func nodeGeometry(
        for node: SpatialNode,
        cardWidth: Float,
        cardHeight: Float
    ) -> NodeGeometry {
        let nodeColor = SpaceTheme.materialColor(for: node.nodeType)
        let mesh: MeshResource
        let materials: [any RealityFoundation.Material]
        let collisionShape: ShapeResource

        switch node.nodeType {
        case .entity:
            // Phase 3: entity orbs (sphere). HoverEffectComponent gives the
            // per-platform highlight without #if.
            let radius: Float = cardWidth * 0.32
            mesh = MeshResource.generateSphere(radius: radius)
            materials = [SimpleMaterial(color: nodeColor, isMetallic: false)]
            collisionShape = ShapeResource.generateSphere(radius: radius)
        case .source:
            // True page shape (#4193): area-normalized to the old 3:4 card's
            // footprint, using the memoized texture aspect when the page has
            // already loaded (fallback ratio otherwise, so shapes don't jump
            // mid-load — the async texture task below refines it once).
            let dims = CanvasCardGeometry.dimensions(
                area: cardWidth * cardHeight,
                aspect: node.sourceId.flatMap { CanvasCardGeometry.knownAspect(forSourceId: $0) },
                fallback: pageAspectRatio
            )
            mesh = MeshResource.generatePlane(
                width: dims.width,
                height: dims.height,
                cornerRadius: min(dims.width, dims.height) * 0.07
            )
            materials = [UnlitMaterial(color: nodeColor)]
            // Collision tracks the drawn plane, or hit-testing drifts from
            // what's on screen.
            collisionShape = ShapeResource.generateBox(size: SIMD3<Float>(dims.width, dims.height, cardWidth * 0.12))
        default:
            let depth: Float = cardWidth * 0.12
            mesh = MeshResource.generateBox(
                size: SIMD3<Float>(cardWidth, cardHeight, depth),
                cornerRadius: min(cardWidth, cardHeight, depth) * 0.18
            )
            materials = [SimpleMaterial(color: nodeColor, isMetallic: false)]
            collisionShape = ShapeResource.generateBox(size: SIMD3<Float>(cardWidth, cardHeight, depth))
        }

        return NodeGeometry(mesh: mesh, materials: materials, collisionShape: collisionShape)
    }

    /// Swap the flat placeholder for the real page image once it decodes, and
    /// on the FIRST load re-cut the plane and its collision to the texture's
    /// true aspect (#4193). Failure keeps the coloured placeholder rather than
    /// blanking the card.
    private func refineWithPageTexture(
        _ entity: ModelEntity,
        sourceId: String,
        cardWidth: Float,
        cardHeight: Float
    ) {
        let service = storageService
        Task { @MainActor in
            do {
                let texture = try await SpaceTextureCache.shared.texture(
                    forSourceId: sourceId, using: service
                )
                entity.model?.materials = [UnlitMaterial(texture: texture)]
                // First load of this page: re-cut the plane + collision to
                // the texture's true aspect, area-normalized (#4193). The
                // memo makes every later synchronous rebuild keep it.
                if CanvasCardGeometry.recordAspect(of: texture, forSourceId: sourceId) {
                    let dims = CanvasCardGeometry.dimensions(
                        area: cardWidth * cardHeight,
                        aspect: CanvasCardGeometry.knownAspect(forSourceId: sourceId),
                        fallback: self.pageAspectRatio
                    )
                    entity.model?.mesh = MeshResource.generatePlane(
                        width: dims.width,
                        height: dims.height,
                        cornerRadius: min(dims.width, dims.height) * 0.07
                    )
                    entity.components.set(CollisionComponent(shapes: [
                        ShapeResource.generateBox(size: SIMD3<Float>(dims.width, dims.height, cardWidth * 0.12))
                    ]))
                }
            } catch {
                // Keep the colored placeholder when the page image cannot
                // be loaded — but say WHY in the log (#4160): silence made
                // 'no thumbnails' undiagnosable.
                SpaceTextureCache.logTextureFailure(sourceId: sourceId, error: error)
            }
        }
    }

    private var pageAspectRatio: Float { 3.0 / 4.0 }

    /// A typed link rendered as a cylinder spanning two node positions.
    /// Cylinder (not box) reads as a 3D tube from any camera angle. Color +
    /// thickness come from the link type and weight.
    private func makeEdgeEntity(
        from: SIMD3<Float>,
        to endPoint: SIMD3<Float>,
        linkType: LinkType,
        weight: Double
    ) -> ModelEntity {
        let delta = endPoint - from
        let length = max(simd_length(delta), 0.0001)
        let thickness: Float = 0.006 * Float(max(0.5, min(weight, 3.0)))
        let mesh = MeshResource.generateCylinder(height: length, radius: thickness)
        let color = SpaceTheme.materialColor(for: linkType, alpha: linkType.isSolid ? 0.85 : 0.45)
        let material = SimpleMaterial(color: color, isMetallic: false)
        let entity = ModelEntity(mesh: mesh, materials: [material])
        entity.position = (from + endPoint) / 2
        // generateCylinder is +Y-aligned; rotate +Y onto the link direction.
        entity.orientation = simd_quatf(from: SIMD3<Float>(0, 1, 0), to: delta / length)
        return entity
    }
}
#endif

// MARK: - Canvas items (#2294)

#if canImport(RealityKit)
/// Heterogeneous standalone canvas items (note / quote / work_note / text /
/// link) rendered in the 3D scene, bound to the SAME observable
/// `CanvasItemStore` the 2D canvas uses. Kept in a same-file extension (a
/// cross-file split breaks symbol resolution — see #2294) so the struct body
/// stays under the length limit.
private extension SpaceSceneView {

    /// Backend-space positions for the non-`link` canvas items: the persisted
    /// `CanvasItemLayout` row where one exists (the SAME rows the 2D canvas and
    /// node layout use), else a cascading arranged spot so a freshly-added item
    /// is visible until dragged. Mirrors the 2D canvas's `itemPositions`.
    private func itemRawPositions() -> [String: SIMD3<Double>] {
        guard let store = itemStore else { return [:] }
        let rows = Dictionary(
            (layoutStore?.layout(for: scopeKey) ?? []).map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        var result: [String: SIMD3<Double>] = [:]
        var fallback = 0
        for item in store.items(for: scopeKey) where item.kind != .link {
            if let row = rows[item.id] {
                result[item.id] = SIMD3<Double>(row.x, row.y, row.z)
            } else {
                let column = fallback % 3
                let line = fallback / 3
                result[item.id] = SIMD3<Double>(Double(column) * 0.6, Double(-line) * 0.6, 0)
                fallback += 1
            }
        }
        return result
    }

    /// Apply the same normalize transform used for nodes to a raw backend point.
    private func scenePosition(_ raw: SIMD3<Double>, scale: Float, center: SIMD3<Float>) -> SIMD3<Float> {
        let point = SIMD3<Float>(Float(raw.x), Float(raw.y), Float(raw.z))
        return (point - center) * scale
    }

    /// Find or create a named container child under `root` (idempotent), so the
    /// reconcile pass groups item cards / connectors without re-creating them.
    private func childEntity(named name: String, in root: Entity) -> Entity {
        if let existing = root.children.first(where: { $0.name == name }) { return existing }
        let entity = Entity()
        entity.name = name
        root.addChild(entity)
        return entity
    }

    /// Reflect `itemStore.items` onto the live scene: one card entity per
    /// non-`link` item (added / repositioned / removed to match the store) and a
    /// rebuilt connector per `link` item between its source/target endpoints. The
    /// `combined` map carries node AND item scene positions so a link can join a
    /// node and/or an item — the same endpoint model the 2D edge layer uses.
    private func reconcileCanvasItems(in root: Entity) {
        guard let store = itemStore else { return }
        let (scale, center) = normalize()

        var combined: [String: SIMD3<Float>] = [:]
        for node in renderedNodes {
            combined[node.id] = position(for: node, scale: scale, center: center)
        }
        let rawItems = itemRawPositions()
        for (id, raw) in rawItems {
            combined[id] = scenePosition(raw, scale: scale, center: center)
        }

        // Cards: find-or-create per item, drop entities whose item is gone.
        let itemsRoot = childEntity(named: "spatial-items", in: root)
        let liveIds = Set(rawItems.keys)
        for child in itemsRoot.children where !liveIds.contains(child.name) {
            child.removeFromParent()
        }
        for item in store.items(for: scopeKey) where item.kind != .link {
            guard let pos = combined[item.id] else { continue }
            if let existing = itemsRoot.findEntity(named: item.id) {
                existing.position = pos
            } else {
                itemsRoot.addChild(makeItemEntity(item, at: pos))
            }
        }

        // Link connectors: few and cheap, rebuilt wholesale from endpoints.
        let linksRoot = childEntity(named: "spatial-item-links", in: root)
        linksRoot.children.forEach { $0.removeFromParent() }
        for link in store.items(for: scopeKey) where link.kind == .link {
            guard
                let from = link.sourceItemId.flatMap({ combined[$0] }),
                let toEnd = link.targetItemId.flatMap({ combined[$0] })
            else { continue }
            linksRoot.addChild(makeEdgeEntity(from: from, to: toEnd, linkType: .userDrawn, weight: 1.0))
        }
    }

    /// One card entity for a non-`link` canvas item — a small rounded box tinted
    /// by kind. ONE builder switching on kind via the colour map; tap-selectable
    /// like a node (entity name = item id → `selectedNodeId`).
    private func makeItemEntity(_ item: CanvasItemDisplay, at position: SIMD3<Float>) -> ModelEntity {
        let cardWidth: Float = 0.6
        let cardHeight: Float = 0.42
        let depth: Float = cardWidth * 0.12
        let size = SIMD3<Float>(cardWidth, cardHeight, depth)
        let mesh = MeshResource.generateBox(size: size, cornerRadius: min(cardWidth, cardHeight, depth) * 0.18)
        let color = itemMaterialColor(for: item.kind)
        let entity = ModelEntity(mesh: mesh, materials: [SimpleMaterial(color: color, isMetallic: false)])
        entity.position = position
        entity.name = item.id
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(shapes: [ShapeResource.generateBox(size: size)]))
        entity.components.set(HoverEffectComponent())
        return entity
    }

    /// Renderer colour per canvas-item kind — the RealityKit twin of the 2D
    /// `kind.accent` palette (note=orange, quote=purple, work_note=blue, …).
    private func itemMaterialColor(for kind: Components.Schemas.CanvasItemKind) -> PlatformColor {
        switch kind {
        case .note:     return .systemOrange
        case .quote:    return .systemPurple
        case .workNote: return .systemBlue
        case .text:     return .systemGray
        case .link:     return .systemGray
        }
    }
}
#endif

#if canImport(RealityKit)
/// Caches RealityKit textures for Spatial source-page nodes, keyed by
/// library scope + the node's backend `sourceId`. Page bytes are fetched through the shared
/// `StorageService` (the canonical, authenticated thumbnail path) so
/// the 3D scene no longer hand-builds a storage URL or calls `URLSession`
/// directly (#1902).
actor SpaceTextureCache {
    static let shared = SpaceTextureCache()

    private static let logger = Logger(
        subsystem: "app.fichero.fichero",
        category: "SpaceTextureCache"
    )

    private var cache: [String: TextureResource] = [:]

    static func logTextureFailure(sourceId: String, error: Error) {
        logger.error(
            "page texture for \(sourceId, privacy: .public) failed: \(error.localizedDescription)"
        )
    }

    func texture(
        forSourceId sourceId: String, using service: StorageService? = nil
    ) async throws -> TextureResource {
        // The CURRENT library's service when the host injected one (#4160);
        // global-library fallback preserves the Spatial-room path. No `??`:
        // its autoclosure is nonisolated and LibraryManager is MainActor.
        let storage: StorageService?
        if let service {
            storage = service
        } else {
            storage = await LibraryManager.shared.globalLibrary?.storageService
        }
        // Key per-library, not just per-sourceId: this cache is a process-wide
        // singleton, and the same sourceId in two libraries is two images.
        let cacheKey = "\(await storage?.libraryScopeKey ?? "")|\(sourceId)"
        if let cached = cache[cacheKey] { return cached }

        let data = try await fetchImageData(forSourceId: sourceId, using: storage)
        let fileExtension = Self.fileExtension(for: data)
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(fileExtension)
        try data.write(to: tempURL, options: [.atomic])
        defer { try? FileManager.default.removeItem(at: tempURL) }

        let texture = try await TextureResource(contentsOf: tempURL)
        cache[cacheKey] = texture
        return texture
    }

    private func fetchImageData(
        forSourceId sourceId: String, using storage: StorageService?
    ) async throws -> Data {
        guard let data = try await storage?.thumbnailData(for: sourceId) else {
            Self.logger.error("No library available to load page thumbnail for \(sourceId, privacy: .public)")
            throw URLError(.badServerResponse)
        }
        return data
    }

    /// Pick a loader-friendly temp-file extension from the image's leading
    /// magic bytes — no Content-Type header needed now the bytes come back
    /// undecoded from the storage service.
    private static func fileExtension(for data: Data) -> String {
        let header = [UInt8](data.prefix(4))
        if header.starts(with: [0x89, 0x50, 0x4E, 0x47]) { return "png" }
        if header.starts(with: [0xFF, 0xD8, 0xFF]) { return "jpg" }
        if header.starts(with: [0x52, 0x49, 0x46, 0x46]) { return "webp" }
        return "png"
    }
}
#endif
