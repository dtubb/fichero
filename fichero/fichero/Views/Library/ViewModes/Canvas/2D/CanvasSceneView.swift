import FicheroAPIClient
import RealityKit
import SwiftUI

// MARK: - 2D 'Canvas' — RealityKit ortho renderer on the shared contract (#3083/#3084)

/// The 2D 'Canvas' view: a thin SwiftUI shell over `CanvasOrtho2DRenderer` (the
/// `CanvasSceneRenderer` impl, #3103). It resolves the shared #3082 stores into a
/// `CanvasSceneState`, hands the renderer the minimal diff (never a rebuild), and
/// routes gestures as `CanvasIntent`s through the shared `CanvasInteractionController`
/// — so a move made in the 3D 'Space' window shows up here live, and vice-versa.
///
/// #3083 delivered render + camera pan/zoom + tap-select + LOD. #3084 adds node
/// drag (single-row persist + snap-on-release + mid-drag echo suppression),
/// marquee multi-select, animated store-driven repositioning, and move undo.
struct CanvasSceneView: View {
    let nodes: [SpatialNode]
    let connections: [SpatialConnection]
    var links: [SpatialLink] = []
    @Binding var selectedNodeId: String?
    var layoutStore: CanvasLayoutStore?
    var itemStore: CanvasItemStore?
    var folderScopeId: String?
    /// Spatial node ids that are containers (folder / workspace), from LibraryView
    /// — drives drag-onto move-into vs link (#3086).
    var containerIds: Set<String> = []
    /// Move a dragged node into a container (→ audited `document.move`), wired by
    /// LibraryView which owns the document store. `(nodeId, containerNodeId)`.
    var moveIntoContainer: (String, String) -> Void = { _, _ in }

    @Environment(\.undoManager) private var undoManager

    @State private var renderer = CanvasOrtho2DRenderer()
    @State private var controller: CanvasInteractionController?

    // Camera-pan bookkeeping.
    @State private var panBaseline: CGSize = .zero
    @State private var zoomBaseline: Float = 0

    // Node-drag state.
    @State private var draggingNodeId: String?
    @State private var dragStartScene: SIMD3<Float>?
    @State private var dragOriginWorld: SIMD3<Double>?

    // Modifier state: ⇧ = marquee, ⌥ = force-link on drag-onto.
    @State private var shiftHeld = false
    @State private var optionHeld = false
    @State private var marqueeRect: CGRect?

    private var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    /// The current scene resolved from the shared stores (canonical world space),
    /// with the single selection mirrored into the scene's selection set. Reading
    /// the stores here ties re-render (→ reconcile) to their change stream.
    private var resolvedState: CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: nodes,
            connections: connections,
            links: links,
            layoutRows: layoutStore?.layout(for: scopeKey) ?? [],
            items: itemStore?.items(for: scopeKey) ?? []
        )
        state.selection = selectedNodeId.map { [$0] } ?? []
        return state
    }

    var body: some View {
        GeometryReader { geo in
            RealityView { content in
                content.add(renderer.camera)
                content.add(renderer.root)
                renderer.reconcile(to: resolvedState)
            } update: { _ in
                renderer.detailTier = CanvasDetailTier.forZoomScale(renderer.reportedZoomScale)
                renderer.reconcile(to: resolvedState)
            }
            .highPriorityGesture(nodeDrag(in: geo.size))
            .highPriorityGesture(tapSelect)
            .gesture(panOrMarquee(in: geo.size))
            .simultaneousGesture(zoom)
            .background(SpaceTheme.canvasBackground)
            .onTapGesture { controller?.dispatch(.tap(id: nil)) }   // background → clear
            .overlay { marqueeOverlay }
            .modifier(CanvasModifierTracker(shiftHeld: $shiftHeld, optionHeld: $optionHeld))
            .task(id: folderScopeId) {
                configureController()
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
        }
    }

    @ViewBuilder
    private var marqueeOverlay: some View {
        if let rect = marqueeRect {
            Rectangle()
                .fill(Color.accentColor.opacity(0.12))
                .overlay(Rectangle().stroke(Color.accentColor, lineWidth: 1))
                .frame(width: rect.width, height: rect.height)
                .position(x: rect.midX, y: rect.midY)
                .allowsHitTesting(false)
        }
    }

    // MARK: - Controller

    private func configureController() {
        guard let layoutStore, let itemStore else { return }
        let controller = CanvasInteractionController(
            layoutStore: layoutStore,
            itemStore: itemStore,
            scopeId: scopeKey,
            selection: $selectedNodeId
        )
        renderer.onIntent = { controller.dispatch($0) }
        renderer.isDragSuppressed = { controller.isDragging($0) }
        controller.onMoveInto = { moveIntoContainer($0, $1) }
        self.controller = controller
    }

    /// Classify a drop target for `DropOutcome.classify`: canvas items are always
    /// leaves (drop → link); a node is a container only if LibraryView said so.
    private func targetKind(_ id: String) -> CanvasTargetKind {
        if (itemStore?.items(for: scopeKey) ?? []).contains(where: { $0.id == id }) { return .leaf }
        return containerIds.contains(id) ? .container : .leaf
    }

    /// The `CanvasDropTarget` (id + kind) under a drop world position, or nil for
    /// empty space → a plain place.
    private func dropTarget(near world: SIMD3<Double>, dragged: String) -> CanvasDropTarget? {
        renderer.dropTargetId(nearWorld: world, excluding: dragged)
            .map { CanvasDropTarget(id: $0, kind: targetKind($0)) }
    }

    // MARK: - Gestures

    /// Tap a card → select it through the controller (writes `selectedNodeId`).
    private var tapSelect: some Gesture {
        TapGesture()
            .targetedToAnyEntity()
            .onEnded { value in
                let id = value.entity.name
                controller?.dispatch(.tap(id: id.isEmpty ? nil : id))
            }
    }

    /// Drag a card → move it live and persist a single snapped row on release
    /// (#3084). The controller suppresses store echoes for the dragged id
    /// mid-drag, so the gesture is never fought.
    private func nodeDrag(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .targetedToAnyEntity()
            .onChanged { value in
                let id = value.entity.name
                guard !id.isEmpty else { return }
                if draggingNodeId == nil {
                    draggingNodeId = id
                    let startScene = value.entity.position(relativeTo: nil)
                    dragStartScene = startScene
                    dragOriginWorld = Canvas2DProjection.worldPosition(startScene)
                    controller?.dispatch(.dragBegan(id: id))
                }
                guard let start = dragStartScene else { return }
                let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
                renderer.liveMove(id: id, toWorld: world)
                renderer.setHoverTarget(renderer.dropTargetId(nearWorld: world, excluding: id))
                controller?.dispatch(.dragMoved(id: id, position: world))
            }
            .onEnded { value in
                guard let id = draggingNodeId, let start = dragStartScene else { return }
                let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
                renderer.setHoverTarget(nil)
                let target = dropTarget(near: world, dragged: id)
                let modifiers: CanvasDropModifiers = optionHeld ? .forceLink : []
                controller?.dispatch(.dragEnded(id: id, position: world, dropTarget: target, modifiers: modifiers))
                // Only a plain place (no drop target) registers a move-undo — a
                // move-into / link is undone through its own action's audit trail.
                if target == nil, let controller, let origin = dragOriginWorld {
                    controller.registerMoveUndo(id: id, origin: origin, destination: world, undoManager: undoManager)
                }
                draggingNodeId = nil
                dragStartScene = nil
                dragOriginWorld = nil
            }
    }

    private func draggedWorld(start: SIMD3<Float>, translation: CGSize, viewHeight: CGFloat, id: String) -> SIMD3<Double> {
        // Preserve the row's existing z (#3090): a 2D move never touches z, so a
        // z the 3D renderer set survives a 2D save — one row, two projections.
        let existingZ = layoutStore?.layout(for: scopeKey).first { $0.itemId == id }?.z ?? 0
        return Canvas2DProjection.draggedWorldPosition(
            startScene: start,
            screenTranslation: translation,
            orthoScale: renderer.orthoScale,
            viewHeight: viewHeight,
            preservingZ: existingZ
        )
    }

    /// Background drag: shift-held → rubber-band marquee multi-select; otherwise
    /// pan the ortho camera across its plane.
    private func panOrMarquee(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                if shiftHeld {
                    marqueeRect = Canvas2DProjection.marqueeRect(
                        from: value.startLocation, to: value.location
                    )
                } else {
                    let delta = CGSize(
                        width: value.translation.width - panBaseline.width,
                        height: value.translation.height - panBaseline.height
                    )
                    panBaseline = value.translation
                    // ponytail: shares Canvas2DProjection.worldPerPoint with drag +
                    // marquee — the ONE calibration knob to tune against the built app.
                    renderer.panCamera(
                        worldDelta: Canvas2DProjection.cameraPanDelta(
                            screenTranslation: delta,
                            orthoScale: renderer.orthoScale,
                            viewHeight: size.height
                        )
                    )
                }
            }
            .onEnded { _ in
                if shiftHeld, let rect = marqueeRect {
                    controller?.dispatch(.marquee(ids: renderer.placeableIds(inScreenRect: rect, viewSize: size)))
                }
                marqueeRect = nil
                panBaseline = .zero
            }
    }

    /// Pinch zooms the ortho camera: magnify > 1 → zoom IN → smaller ortho scale.
    private var zoom: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                if zoomBaseline == 0 { zoomBaseline = renderer.orthoScale }
                renderer.setOrthoScale(
                    Canvas2DProjection.orthoScale(zoomBaseline: zoomBaseline, magnification: value)
                )
            }
            .onEnded { _ in zoomBaseline = 0 }
    }
}
