import FicheroAPIClient
import RealityKit
import SwiftUI

// MARK: - 2D 'Canvas' — RealityKit ortho renderer on the shared contract (#3083)

/// The 2D 'Canvas' view: a thin SwiftUI shell over `CanvasOrtho2DRenderer` (the
/// `CanvasSceneRenderer` impl, #3103). It resolves the shared #3082 stores into a
/// `CanvasSceneState`, hands the renderer the minimal diff (never a rebuild), and
/// routes gestures as `CanvasIntent`s through the shared `CanvasInteractionController`
/// — so a move made in the 3D 'Space' window shows up here live, and vice-versa.
///
/// This slice (#3083) is the skeleton: render placeables + connectors, ortho
/// camera pan/zoom, tap-to-select, thumbnail LOD. Node drag/persist is #3084;
/// CRUD #3085; drag-onto #3086; SwiftUI-canvas cutover #3087.
struct CanvasSceneView: View {
    let nodes: [SpatialNode]
    let connections: [SpatialConnection]
    var links: [SpatialLink] = []
    @Binding var selectedNodeId: String?
    var layoutStore: CanvasLayoutStore?
    var itemStore: CanvasItemStore?
    var folderScopeId: String?

    @State private var renderer = CanvasOrtho2DRenderer()
    @State private var controller: CanvasInteractionController?
    @State private var panBaseline: CGSize = .zero
    @State private var zoomBaseline: Float = 0

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
            .highPriorityGesture(tapSelect)
            .simultaneousGesture(pan(in: geo.size))
            .simultaneousGesture(zoom)
            .background(SpaceTheme.canvasBackground)
            .onTapGesture { controller?.dispatch(.tap(id: nil)) }   // background → clear
            .task(id: folderScopeId) {
                configureController()
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
        }
    }

    // MARK: - Controller

    /// (Re)build the controller for the current scope and wire the renderer's
    /// intent + drag-suppression hooks to it.
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

    /// Background drag pans the ortho camera across its plane.
    private func pan(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                let delta = CGSize(
                    width: value.translation.width - panBaseline.width,
                    height: value.translation.height - panBaseline.height
                )
                panBaseline = value.translation
                // ponytail: world-per-point = visible world height (2·orthoScale)
                // over the view height. Signs move content WITH the finger. This
                // is the calibration knob — tune against the built app (#3084 run).
                let worldPerPoint = (2 * renderer.orthoScale) / Float(max(size.height, 1))
                renderer.panCamera(worldDelta: SIMD2<Float>(
                    Float(-delta.width) * worldPerPoint,
                    Float(delta.height) * worldPerPoint
                ))
            }
            .onEnded { _ in panBaseline = .zero }
    }

    /// Pinch zooms the ortho camera: magnify > 1 → zoom IN → smaller ortho scale.
    private var zoom: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                if zoomBaseline == 0 { zoomBaseline = renderer.orthoScale }
                let magnification = Float(max(value, 0.01))
                renderer.setOrthoScale(zoomBaseline / magnification)
            }
            .onEnded { _ in zoomBaseline = 0 }
    }
}
