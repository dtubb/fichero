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
    @Binding var selectedNodeIds: Set<String>

    /// Operand for commands that act on exactly ONE node — nil otherwise.
    ///
    /// Named for the command, not for selection (#4409). Three call sites used
    /// to read `selectedNodeId` and looked like a second selection concept;
    /// they are not. They are z-push, z-pull and delete, each of which needs a
    /// single subject and must be unavailable when several things are chosen.
    ///
    /// COMPUTED from the set and never assigned to. `.first` of a
    /// multi-selection would reintroduce the arbitrary-member lie one layer
    /// down — the same defect the bridge had.
    private var singleItemCommandTarget: String? {
        selectedNodeIds.count == 1 ? selectedNodeIds.first : nil
    }
    var layoutStore: CanvasLayoutStore?
    /// The CURRENT library's storage service for thumbnail textures (#4160).
    var storageService: StorageService?

    var itemStore: CanvasItemStore?
    var folderScopeId: String?
    /// Container spatial node ids (folder / workspace) from LibraryView — drives
    /// drag-onto move-into vs link (#3086).
    var containerIds: Set<String> = []
    /// Move a dragged node into a container (→ audited `document.move`), wired by
    /// LibraryView. `(nodeId, containerNodeId)`.
    var moveIntoContainer: (String, String) -> Void = { _, _ in }

    /// WHICH cards matter right now — the active search's score-weighted heat
    /// map today, an entity highlight when a picker lands (§25.4 step 2). One
    /// channel, so the two can never grow different visual languages. Neutral
    /// outside a search, and it moves nothing.
    var emphasis: CanvasEmphasis = .neutral

    /// WHAT each card is, in colour (§20.3 Colour by) — the other re-encode
    /// channel, produced by the host from document attributes.
    var tint: CanvasTint = .neutral

    @Environment(\.undoManager) var undoManager

    @State var renderer = CanvasScene3DRenderer()
    @State var controller: CanvasInteractionController?
    @State private var cameraBaseline: CGSize = .zero
    @State private var zoomBaseline: Float = 0
    @State var optionHeld = false

    /// Where this WINDOW has been looking (§16). View state: per window, saved
    /// nowhere, never near the layout store.
    @State var jumpHistory = CanvasJumpHistory<(lookAt: SIMD3<Float>, distance: Float)>()

    @State var draggingNodeId: String?
    @State var dragStartWorld: SIMD3<Double>?

    /// Upper bound on entities placed at once (#1400 WindowServer watchdog): a
    /// large scope renders a bounded prefix + a banner, never a runaway scene.
    ///
    /// Internal, not private: `LibraryView.renderedSpaceDocumentIds` reads it so
    /// ⌘A covers exactly what this view renders. One constant, one meaning of
    /// "visible" — duplicating the bound is how the two would drift.
    static let maxRenderedPlaceables = 10_000

    private var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    /// The §20.3 "Arrange by" axis, written by `CanvasArrangePicker`. Both
    /// canvases READ this one key: they share a layout store, so a board they
    /// disagree about is two different boards.
    @AppStorage(CanvasArrangement.storageKey) private var arrangementRaw = CanvasArrangement.asFiled.rawValue

    private var renderableItems: [CanvasItemDisplay] {
        (itemStore?.items(for: scopeKey) ?? []).filter { $0.kind != .link }
    }

    private var isTruncated: Bool { nodes.count + renderableItems.count > Self.maxRenderedPlaceables }
    private var isEmpty: Bool { nodes.isEmpty && (itemStore?.items(for: scopeKey).isEmpty ?? true) }

    /// The default grid's cell pitch, from the page aspects loaded so far
    /// (§18.1 defect 4). Aspects arrive as textures load, so a board of
    /// row-less cards can re-flow ONCE as they land — the same class of re-flow
    /// as resizing the window, and bounded the same way: a saved row always
    /// wins, so nothing the user has placed ever moves.
    private var gridCell: CGSize {
        CanvasGridPlacement.cell(
            forAspects: CanvasCardGeometry.knownAspects(
                forSourceIds: nodes.compactMap(\.sourceId)
            )
        )
    }

    /// How many cards the board lays out — nodes plus the non-link items, the
    /// same sequence `CanvasSceneState.resolve` slots.
    private var placeableCount: Int { nodes.count + renderableItems.count }

    private func resolvedState(in viewportSize: CGSize) -> CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: nodes,
            connections: connections,
            links: links,
            layoutRows: layoutStore?.layout(for: scopeKey) ?? [],
            items: itemStore?.items(for: scopeKey) ?? [],
            // Daniel's ruling (2026-08-19, #4601): a folder with no saved
            // layout opens as a PAGE-ORDER grid, left to right, in BOTH
            // canvases — the phyllotaxis default made 3D open scattered and
            // different from 2D. Columns come from the ONE shared derivation
            // (§18.1 defect 3), which takes no camera precisely so this and the
            // 2D canvas cannot produce different boards; saved rows still win.
            defaultPlacement: .grid(
                columns: CanvasGridPlacement.sharedColumnCount(
                    itemCount: placeableCount, viewportSize: viewportSize, cell: gridCell
                )
            ),
            // Pitch from the board's ACTUAL card extents, not the nominal
            // 1.0 × 0.75 (§18.1 defect 4): CanvasCardGeometry normalises on
            // area, so a double-spread is 1.22 wide and needs the room.
            gridCell: gridCell,
            arrangement: CanvasArrangement.stored(arrangementRaw)
        )
        if state.placeables.count > Self.maxRenderedPlaceables {
            state.placeables = Array(state.placeables.prefix(Self.maxRenderedPlaceables))
        }
        state.selection = selectedNodeIds
        state.emphasis = emphasis
        state.tint = tint
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
        GeometryReader { geo in
            RealityView { content in
                // BEFORE the first reconcile (first-load fix, 2026-08-22):
                // `configureController()` runs in `.task`, which fires after
                // this closure — cards built here fetched thumbnails with a
                // nil service, fell back to the global library, 404'd, and
                // sat out a retry wait before the right library was asked.
                renderer.storageService = storageService
                content.add(renderer.camera)
                content.add(renderer.root)
                renderer.reconcile(to: resolvedState(in: geo.size))
            } update: { _ in
                renderer.storageService = storageService
                renderer.detailTier = CanvasDetailTier.forZoomScale(renderer.reportedZoomScale)
                renderer.reconcile(to: resolvedState(in: geo.size))
            }
            .highPriorityGesture(marqueeGesture(in: geo.size), isEnabled: marqueeModifiersHeld)
            .highPriorityGesture(nodeDrag)
            .highPriorityGesture(tapSelect)
            .simultaneousGesture(doubleTapZoom)
            .onReceive(NotificationCenter.default.publisher(for: .canvasFocusZoomToggle)) { note in
                guard let id = note.object as? String else { return }
                toggleFocusZoom(on: id)
            }
            .overlay {
                if let rect = marqueeScreenRect {
                    Rectangle()
                        .fill(Color.accentColor.opacity(0.12))
                        .overlay(Rectangle().stroke(Color.accentColor, lineWidth: 1))
                        .frame(width: rect.width, height: rect.height)
                        .position(x: rect.midX, y: rect.midY)
                        .allowsHitTesting(false)
                }
            }
            // Sibling background-clear tap — same fix as the 2D canvas: an
            // outer .onTapGesture fired alongside the entity tap and wiped
            // the selection it had just made.
            .gesture(TapGesture().onEnded {
                controller?.dispatch(.tap(id: nil, modifiers: []))
            })
            .gesture(orbitOrPan)
            .simultaneousGesture(zoom)
            .background(SpaceTheme.canvasBackground)
            // Two-finger scroll pans the camera (user, 2026-08-19: "right now
            // you have to use Space") — same input bridge as the 2D canvas.
            #if canImport(AppKit)
            .overlay {
                CanvasScrollPanView(onScroll: { delta in
                    // Raw-delta mapping (see CanvasScrollCaptureView) against
                    // the perspective camera's screen-delta convention.
                    renderer.pan(byScreenDelta: CGSize(width: delta.width, height: delta.height))
                }, onZoom: { delta, anchor in
                    // ⌘ + two-finger drag zooms INTO THE CURSOR: the look-at
                    // shifts so the content under the pointer stays put as
                    // the camera closes in.
                    let oldDistance = renderer.currentDistance
                    renderer.setDistance(oldDistance * Float(1 - delta * 0.005))
                    renderer.shiftLookAtForCursorZoom(anchor: anchor, oldDistance: oldDistance)
                })
                .allowsHitTesting(false)
            }
            #endif
            // Arrow keys pan, ⌘A selects all — the shared canvas keyboard
            // grammar (user, 2026-08-19).
            .modifier(CanvasKeyboardNav(
                nodeIds: nodes.map(\.id),
                nodePositions: renderer.placeablesById.mapValues {
                    CGPoint(x: $0.position.x, y: $0.position.y)
                },
                selectedNodeIds: $selectedNodeIds
            ))
            .focusedSceneValue(\.canvasViewActions, canvasCommandActions)
            .overlay(alignment: .top) { if isTruncated { truncationBanner } }
            .overlay(alignment: .topTrailing) { canvasToolbar }
            .modifier(CanvasModifierTracker(optionHeld: $optionHeld))
            .task(id: folderScopeId) {
                configureController()
                // Frame the arrangement once this scope has content (#4411).
                // The camera parked at a fixed distance showed part of an
                // origin-anchored grid, and — worse — the zoom-OUT ceiling
                // derives from the arrangement's span, which nothing computed
                // until something asked to fit. Same shape as the 2D canvas.
                renderer.needsFitOnNextContent = true
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
        }
    }

    // MARK: - CRUD + z toolbar (#3090)

    private var commandTargetIsCanvasItem: Bool {
        guard let id = singleItemCommandTarget else { return false }
        return (itemStore?.items(for: scopeKey) ?? []).contains { $0.id == id }
    }

    /// Add note/quote/text, push/pull the selected item along z, and delete —
    /// ALL through the shared `CanvasInteractionController`, so 3D CRUD behaves
    /// identically to 2D (it IS the same controller).
    private var canvasToolbar: some View {
        HStack(spacing: 6) {
            CanvasControlStrip()
            Menu {
                Button("Note") { addItem(.note) }
                Button("Quote") { addItem(.quote) }
                Button("Text") { addItem(.text) }
            } label: {
                Image(systemName: "plus")
            }
            .fixedSize()
            .accessibilityLabel("Add canvas item")
            .help("Add a canvas item at the camera focus")

            if let id = singleItemCommandTarget {
                Button { adjustZ(of: id, by: 0.25) } label: { Image(systemName: "arrow.up.forward") }
                    .accessibilityLabel("Push canvas item away")
                    .help("Push away (−z toward the camera axis)")
                Button { adjustZ(of: id, by: -0.25) } label: { Image(systemName: "arrow.down.backward") }
                    .accessibilityLabel("Pull canvas item forward")
                    .help("Pull forward along z")
            }
            if commandTargetIsCanvasItem, let id = singleItemCommandTarget {
                Button(role: .destructive) { controller?.dispatch(.deleteItem(id: id)) } label: {
                    Image(systemName: "trash")
                }
                .accessibilityLabel("Delete canvas item")
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
        // From the renderer's applied placeables rather than a fresh resolve:
        // it IS the state on screen, and resolving needs a viewport now that
        // columns are viewport-derived (§18.1 defect 3).
        guard let current = renderer.placeablesById[id]?.position else { return }
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
            selection: $selectedNodeIds
        )
        renderer.onIntent = { controller.dispatch($0) }
        renderer.isDragSuppressed = { controller.isDragging($0) }
        renderer.storageService = storageService
        controller.onMoveInto = { moveIntoContainer($0, $1) }
        self.controller = controller
    }

    /// Classify a drop target: canvas items are leaves (→ link); a node is a
    /// container only if LibraryView said so (→ move-into).
    private func targetKind(_ id: String) -> CanvasTargetKind {
        if (itemStore?.items(for: scopeKey) ?? []).contains(where: { $0.id == id }) { return .leaf }
        return containerIds.contains(id) ? .container : .leaf
    }

    func dropTarget(near world: SIMD3<Double>, dragged: String) -> CanvasDropTarget? {
        renderer.dropTargetId(nearWorld: world, excluding: dragged)
            .map { CanvasDropTarget(id: $0, kind: targetKind($0)) }
    }

    // MARK: - Gestures

    /// Where double-click zoom returns to; nil = not zoomed into a node.
    @State var focusReturnSnapshot: (lookAt: SIMD3<Float>, distance: Float)?

    /// ⇧⌥ rubber band (user, 2026-08-20). Screen-space: nodes whose projected
    /// centers fall inside the rect join the selection through the SAME
    /// SelectionGrammar.marquee path the 2D canvas uses.
    @State var marqueeStart: CGPoint?
    @State var marqueeScreenRect: CGRect?

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
