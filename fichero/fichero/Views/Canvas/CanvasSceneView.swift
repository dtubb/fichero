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

    // Marquee state (shift-drag on the background).
    @State private var shiftHeld = false
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
            .modifier(ShiftKeyTracker(shiftHeld: $shiftHeld))
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
        self.controller = controller
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
                controller?.dispatch(.dragMoved(id: id, position: world))
            }
            .onEnded { value in
                guard let id = draggingNodeId, let start = dragStartScene else { return }
                let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
                controller?.dispatch(.dragEnded(id: id, position: world, dropTarget: nil, modifiers: []))
                if let controller, let origin = dragOriginWorld {
                    controller.registerMoveUndo(id: id, origin: origin, destination: world, undoManager: undoManager)
                }
                draggingNodeId = nil
                dragStartScene = nil
                dragOriginWorld = nil
            }
    }

    private func draggedWorld(start: SIMD3<Float>, translation: CGSize, viewHeight: CGFloat, id: String) -> SIMD3<Double> {
        let delta = Canvas2DProjection.sceneDelta(
            screenTranslation: translation,
            orthoScale: renderer.orthoScale,
            viewHeight: viewHeight
        )
        // Preserve the row's existing z (#3090): a 2D move never touches z, so a
        // z the 3D renderer set survives a 2D save — one row, two projections.
        let existingZ = layoutStore?.layout(for: scopeKey).first { $0.itemId == id }?.z ?? 0
        return Canvas2DProjection.worldPosition(start + delta, preservingZ: existingZ)
    }

    /// Background drag: shift-held → rubber-band marquee multi-select; otherwise
    /// pan the ortho camera across its plane.
    private func panOrMarquee(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                if shiftHeld {
                    marqueeRect = CGRect(
                        x: min(value.startLocation.x, value.location.x),
                        y: min(value.startLocation.y, value.location.y),
                        width: abs(value.location.x - value.startLocation.x),
                        height: abs(value.location.y - value.startLocation.y)
                    )
                } else {
                    let delta = CGSize(
                        width: value.translation.width - panBaseline.width,
                        height: value.translation.height - panBaseline.height
                    )
                    panBaseline = value.translation
                    // ponytail: shares Canvas2DProjection.worldPerPoint with drag +
                    // marquee — the ONE calibration knob to tune against the built app.
                    let delta3 = Canvas2DProjection.sceneDelta(
                        screenTranslation: delta, orthoScale: renderer.orthoScale, viewHeight: size.height
                    )
                    // Move content WITH the finger: pan the camera the opposite way.
                    renderer.panCamera(worldDelta: SIMD2<Float>(-delta3.x, -delta3.y))
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
                renderer.setOrthoScale(zoomBaseline / Float(max(value, 0.01)))
            }
            .onEnded { _ in zoomBaseline = 0 }
    }
}

// MARK: - Shift-key tracking (macOS marquee modifier)

/// Tracks whether ⇧ is held so a background drag becomes a marquee. macOS-only
/// (`onModifierKeysChanged`); a no-op elsewhere.
private struct ShiftKeyTracker: ViewModifier {
    @Binding var shiftHeld: Bool

    func body(content: Content) -> some View {
        #if canImport(AppKit)
        content.onModifierKeysChanged(mask: .shift) { _, modifiers in
            shiftHeld = modifiers.contains(.shift)
        }
        #else
        content
        #endif
    }
}
