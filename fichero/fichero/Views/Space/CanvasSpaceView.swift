import FicheroAPIClient
import RealityKit
import SwiftUI

// MARK: - 3D 'Space' — RealityKit perspective renderer on the shared contract (#3104)

/// The 3D 'Space' view: the perspective twin of `CanvasSceneView` (2D). A thin
/// SwiftUI shell over `CanvasScene3DRenderer` driving the SAME shared #3082
/// stores and #3103 `CanvasInteractionController` — so a move in the 2D Canvas
/// window shows up here live, and selection/drag/persist behave identically
/// because it IS the same controller.
///
/// Supersedes the internals of #3088's `SpaceSceneView` (kept as the working
/// stepping-stone behind the flag until cutover, #3087). Keeps what was proven:
/// orbit/pan/zoom camera, `SpaceTextureCache` thumbnails, the 250-entity cap +
/// truncation banner (WindowServer watchdog history), and the empty state.
struct CanvasSpaceView: View {
    let nodes: [SpatialNode]
    let connections: [SpatialConnection]
    var links: [SpatialLink] = []
    @Binding var selectedNodeId: String?
    var layoutStore: CanvasLayoutStore?
    var itemStore: CanvasItemStore?
    var folderScopeId: String?

    @Environment(\.undoManager) private var undoManager

    @State private var renderer = CanvasScene3DRenderer()
    @State private var controller: CanvasInteractionController?
    @State private var cameraBaseline: CGSize = .zero
    @State private var zoomBaseline: Float = 0
    @State private var optionHeld = false

    @State private var draggingNodeId: String?
    @State private var dragStartWorld: SIMD3<Double>?

    /// Upper bound on entities placed at once (#1400 WindowServer watchdog): a
    /// large scope renders a bounded prefix + a banner, never a runaway scene.
    private static let maxRenderedPlaceables = 250

    private var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    private var renderableItems: [CanvasItemDisplay] {
        (itemStore?.items(for: scopeKey) ?? []).filter { $0.kind != .link }
    }

    private var isTruncated: Bool { nodes.count + renderableItems.count > Self.maxRenderedPlaceables }
    private var isEmpty: Bool { nodes.isEmpty && (itemStore?.items(for: scopeKey).isEmpty ?? true) }

    private var resolvedState: CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: nodes,
            connections: connections,
            links: links,
            layoutRows: layoutStore?.layout(for: scopeKey) ?? [],
            items: itemStore?.items(for: scopeKey) ?? []
        )
        if state.placeables.count > Self.maxRenderedPlaceables {
            state.placeables = Array(state.placeables.prefix(Self.maxRenderedPlaceables))
        }
        state.selection = selectedNodeId.map { [$0] } ?? []
        return state
    }

    var body: some View {
        if isEmpty {
            emptyState
        } else {
            scene
        }
    }

    private var emptyState: some View {
        ContentUnavailableView(
            "Empty Space",
            systemImage: "cube.transparent",
            description: Text("No source pages or spatial nodes are available in this scope yet.")
        )
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(SpaceTheme.canvasBackground)
    }

    private var scene: some View {
        GeometryReader { _ in
            RealityView { content in
                content.add(renderer.camera)
                content.add(renderer.root)
                renderer.reconcile(to: resolvedState)
            } update: { _ in
                renderer.detailTier = CanvasDetailTier.forZoomScale(renderer.reportedZoomScale)
                renderer.reconcile(to: resolvedState)
            }
            .highPriorityGesture(nodeDrag)
            .highPriorityGesture(tapSelect)
            .gesture(orbitOrPan)
            .simultaneousGesture(zoom)
            .background(SpaceTheme.canvasBackground)
            .onTapGesture { controller?.dispatch(.tap(id: nil)) }
            .overlay(alignment: .top) { if isTruncated { truncationBanner } }
            .overlay(alignment: .topTrailing) { canvasToolbar }
            .modifier(OptionKeyTracker(optionHeld: $optionHeld))
            .task(id: folderScopeId) {
                configureController()
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
        }
    }

    // MARK: - CRUD + z toolbar (#3090)

    private var selectedIsItem: Bool {
        guard let id = selectedNodeId else { return false }
        return (itemStore?.items(for: scopeKey) ?? []).contains { $0.id == id }
    }

    /// Add note/quote/text, push/pull the selected item along z, and delete —
    /// ALL through the shared `CanvasInteractionController`, so 3D CRUD behaves
    /// identically to 2D (it IS the same controller).
    private var canvasToolbar: some View {
        HStack(spacing: 6) {
            Menu {
                Button("Note") { addItem(.note) }
                Button("Quote") { addItem(.quote) }
                Button("Text") { addItem(.text) }
            } label: {
                Image(systemName: "plus")
            }
            .fixedSize()
            .help("Add a canvas item at the camera focus")

            if let id = selectedNodeId {
                Button { adjustZ(of: id, by: 0.25) } label: { Image(systemName: "arrow.up.forward") }
                    .help("Push away (−z toward the camera axis)")
                Button { adjustZ(of: id, by: -0.25) } label: { Image(systemName: "arrow.down.backward") }
                    .help("Pull forward along z")
            }
            if selectedIsItem, let id = selectedNodeId {
                Button(role: .destructive) { controller?.dispatch(.deleteItem(id: id)) } label: {
                    Image(systemName: "trash")
                }
                .help("Delete this canvas item")
            }
        }
        .buttonStyle(.borderless)
        .padding(8)
        .background(.regularMaterial, in: Capsule())
        .padding(8)
    }

    private func addItem(_ kind: Components.Schemas.CanvasItemKind) {
        controller?.dispatch(.addItem(kind: kind, position: renderer.focusWorldPosition))
    }

    /// Push/pull the selected placeable along z, persisting through the shared
    /// controller (the 2D canvas ignores z, so this stays two projections of one
    /// row). Reads the resolved current position so it works with or without a row.
    private func adjustZ(of id: String, by delta: Double) {
        guard let current = resolvedState.placeables.first(where: { $0.id == id })?.position else { return }
        let moved = SIMD3<Double>(current.x, current.y, current.z + delta)
        Task { await controller?.moveItem(id: id, to: moved) }
    }

    private var truncationBanner: some View {
        Text("Showing first \(Self.maxRenderedPlaceables) of \(nodes.count + renderableItems.count) items")
            .font(.caption)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.regularMaterial, in: Capsule())
            .padding(.top, 8)
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

    private var tapSelect: some Gesture {
        TapGesture()
            .targetedToAnyEntity()
            .onEnded { value in
                let id = value.entity.name
                controller?.dispatch(.tap(id: id.isEmpty ? nil : id))
            }
    }

    /// Drag a card in 3D: move it in the camera's view plane and persist a single
    /// snapped row on release — same controller path as 2D, only the screen→world
    /// conversion is 3D (camera-plane) instead of ortho.
    private var nodeDrag: some Gesture {
        DragGesture(minimumDistance: 2)
            .targetedToAnyEntity()
            .onChanged { value in
                let id = value.entity.name
                guard !id.isEmpty else { return }
                if draggingNodeId == nil {
                    draggingNodeId = id
                    dragStartWorld = Canvas3DProjection.worldPosition(value.entity.position(relativeTo: nil))
                    controller?.dispatch(.dragBegan(id: id))
                }
                guard let start = dragStartWorld else { return }
                let world = start + renderer.worldDragDelta(screenTranslation: value.translation)
                renderer.liveMove(id: id, toWorld: world)
                controller?.dispatch(.dragMoved(id: id, position: world))
            }
            .onEnded { value in
                guard let id = draggingNodeId, let start = dragStartWorld else { return }
                let world = start + renderer.worldDragDelta(screenTranslation: value.translation)
                controller?.dispatch(.dragEnded(id: id, position: world, dropTarget: nil, modifiers: []))
                controller?.registerMoveUndo(id: id, origin: start, destination: world, undoManager: undoManager)
                draggingNodeId = nil
                dragStartWorld = nil
            }
    }

    /// Background drag: option-held → pan the look-at target; otherwise orbit.
    private var orbitOrPan: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                let delta = CGSize(
                    width: value.translation.width - cameraBaseline.width,
                    height: value.translation.height - cameraBaseline.height
                )
                cameraBaseline = value.translation
                if optionHeld {
                    renderer.pan(byScreenDelta: delta)
                } else {
                    renderer.orbit(byScreenDelta: delta)
                }
            }
            .onEnded { _ in cameraBaseline = .zero }
    }

    private var zoom: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                if zoomBaseline == 0 { zoomBaseline = renderer.currentDistance }
                renderer.setDistance(zoomBaseline / Float(max(value, 0.01)))
            }
            .onEnded { _ in zoomBaseline = 0 }
    }
}

// MARK: - Option-key tracking (orbit vs pan)

/// Tracks ⌥ so a background drag pans instead of orbiting. macOS-only; a no-op
/// elsewhere.
private struct OptionKeyTracker: ViewModifier {
    @Binding var optionHeld: Bool

    func body(content: Content) -> some View {
        #if canImport(AppKit)
        content.onModifierKeysChanged(mask: .option) { _, modifiers in
            optionHeld = modifiers.contains(.option)
        }
        #else
        content
        #endif
    }
}
