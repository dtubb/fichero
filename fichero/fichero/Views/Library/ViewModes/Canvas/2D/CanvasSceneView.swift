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
    var itemStore: CanvasItemStore?
    var folderScopeId: String?
    /// Spatial node ids that are containers (folder / workspace), from LibraryView
    /// — drives drag-onto move-into vs link (#3086).
    var containerIds: Set<String> = []
    /// Move a dragged node into a container (→ audited `document.move`), wired by
    /// LibraryView which owns the document store. `(nodeId, containerNodeId)`.
    var moveIntoContainer: (String, String) -> Void = { _, _ in }
    /// The CURRENT library's storage service for thumbnail textures — without
    /// it the cache falls back to the GLOBAL library and every other library's
    /// canvas renders colored placeholders (user, live 2026-08-19).
    var storageService: StorageService?

    // These three are internal, not private, for the same reason as the resize
    // state above: `CanvasSceneView+Resize.swift` needs them and `private` is
    // FILE-scoped in Swift.
    @Environment(\.undoManager) var undoManager

    @State var renderer = CanvasOrtho2DRenderer()
    @State var controller: CanvasInteractionController?

    // Camera-pan bookkeeping. Internal, not private: the camera-input
    // extension lives in `CanvasSceneView+Camera.swift` and Swift's
    // `private` is FILE-scoped (same trade as the resize state below).
    @State var panBaseline: CGSize = .zero
    @State var zoomBaseline: Float = 0

    // Node-drag state.
    @State private var draggingNodeId: String?
    @State private var dragStartScene: SIMD3<Float>?
    @State private var dragOriginWorld: SIMD3<Double>?

    // Modifier state: ⌥ = force-link on drag-onto, Space = pan the view (#4290 —
    // the plain drag belongs to the ITEM). ⇧ is no longer tracked: a background
    // drag marquees whether or not it's held, so there is nothing to consult.
    @State private var optionHeld = false
    @State private var spaceHeld = false
    @State private var marqueeRect: CGRect?

    // Resize-handle drag state (#4409). Internal, not private: the gesture that
    // reads it lives in `CanvasSceneView+Resize.swift` and Swift's `private` is
    // FILE-scoped.
    @State var resizeHandle: (itemId: String, corner: CanvasSelectionFrame.Corner)?
    @State var resizeOriginSize: CGSize?
    @State var resizeLiveSize: CGSize?

    private var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    /// The current scene resolved from the shared stores (canonical world space),
    /// with the single selection mirrored into the scene's selection set. Reading
    /// the stores here ties re-render (→ reconcile) to their change stream.
    ///
    /// Row-less placeables are laid into a spaced GRID rather than taking their
    /// backend default (#4290): the projector's defaults sit on the XZ plane, and
    /// this renderer drops z, so every card in a folder collapsed onto the line
    /// `y = 0` — one row, cards on top of each other, and drops resolving as
    /// links against their own neighbours instead of as moves.
    private func resolvedState(in viewportSize: CGSize) -> CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: nodes,
            connections: connections,
            links: links,
            layoutRows: layoutStore?.layout(for: scopeKey) ?? [],
            items: itemStore?.items(for: scopeKey) ?? [],
            // TEN columns, identical in 2D and 3D (user, 2026-08-20): one
            // shared default so the two canvases show the SAME board — they
            // already share the layout store, so a move in one is a move in
            // the other; the default must match too.
            defaultPlacement: .grid(columns: 10)
        )
        state.selection = selectedNodeIds
        return state
    }

    /// Columns for the default grid, measured at the camera's FIT scale — not its
    /// live one, so zooming never re-flows the board under the pointer.
    private func gridColumns(in viewportSize: CGSize) -> Int {
        CanvasGridPlacement.columnCount(
            viewportSize: viewportSize,
            worldPerPoint: Canvas2DProjection.worldPerPoint(
                orthoScale: CanvasOrtho2DRenderer.defaultOrthoScale,
                viewHeight: viewportSize.height
            )
        )
    }

    var body: some View {
        GeometryReader { geo in
            RealityView { content in
                content.add(renderer.camera)
                content.add(renderer.root)
                renderer.reconcile(to: resolvedState(in: geo.size))
            } update: { _ in
                renderer.detailTier = CanvasDetailTier.forZoomScale(renderer.reportedZoomScale)
                renderer.reconcile(to: resolvedState(in: geo.size))
            }
            // Plain drag on a card MOVES the card (#4290). It is disabled only
            // while Space is held, which is the deliberate "move the view"
            // gesture — so the two can never contend for the same drag.
            // Resize is attached alongside the card drag rather than above it.
            // Ordering between two `highPriorityGesture`s is not something to
            // rely on, so the two are made mutually exclusive BY SUBJECT
            // instead: each guards on whether the targeted entity is a resize
            // handle, so exactly one of them ever acts on a given drag.
            .highPriorityGesture(resizeDrag(in: geo.size), isEnabled: !spaceHeld)
            .highPriorityGesture(nodeDrag(in: geo.size), isEnabled: !spaceHeld)
            .highPriorityGesture(tapSelect)
            // Background tap clears — as a SIBLING gesture, not a separate
            // .onTapGesture on an outer wrapper: the wrapper's tap fired
            // ALONGSIDE the entity tap and instantly wiped the selection it
            // had just made ("only way to select is drag", 2026-08-20).
            .gesture(TapGesture().onEnded {
                controller?.dispatch(.tap(id: nil, modifiers: []))
            })
            .gesture(panOrMarquee(in: geo.size))
            .simultaneousGesture(zoom)
            .background(SpaceTheme.canvasBackground)
            // Two-finger scroll pans (#4408). A SECOND input to the same
            // `panCamera` — Space-drag keeps working unchanged, because some
            // people already have it in their hands and a mouse has no
            // two-finger scroll. The overlay is hit-test transparent, so
            // selection and node drag are untouched.
            #if os(macOS)
            .overlay {
                CanvasScrollPanView(onScroll: { delta in
                    // Raw-delta mapping (user, 2026-08-20, trackpad + Magic
                    // Mouse both verified against the ortho (x, −y)
                    // projection).
                    scrollPanCamera(
                        by: CGSize(width: -delta.width, height: delta.height),
                        in: geo.size
                    )
                }, onZoom: { delta in
                    // ⌘ + two-finger drag zooms (user, 2026-08-20): scroll up
                    // = zoom in, matching pinch. Same setter as pinch, so the
                    // detail-tier gating stays consistent.
                    renderer.setOrthoScale(renderer.orthoScale * Float(1 + delta * 0.005))
                })
                .allowsHitTesting(false)
            }
            #else
            // iPad: TWO fingers pan (#4408). The macOS half above wired scroll;
            // touch has no scroll and no Space key, and one finger is already
            // the marquee — so before this there was no way to pan a spatial
            // canvas on iPad at all. Two fingers is a different touch COUNT
            // from every gesture here, so it cannot steal one, and it feeds the
            // SAME `scrollPanCamera` the scroll path does.
            .overlay {
                CanvasTouchPanView { delta in
                    scrollPanCamera(by: delta, in: geo.size)
                }
            }
            #endif
            .overlay { marqueeOverlay }
            // Arrow keys pan, ⌘A selects all — the shared canvas keyboard
            // grammar (user, 2026-08-19).
            .modifier(CanvasKeyboardNav(
                nodeIds: nodes.map(\.id),
                nodePositions: renderer.placeablesById.mapValues {
                    CGPoint(x: $0.position.x, y: $0.position.y)
                },
                selectedNodeIds: $selectedNodeIds
            ))
            .modifier(CanvasModifierTracker(optionHeld: $optionHeld, spaceHeld: $spaceHeld))
            .onChange(of: spaceHeld) { _, held in applyPanCursor(held) }
            .task(id: folderScopeId) {
                configureController()
                // Frame the board once this scope has content — the default grid
                // is origin-anchored, so an unfitted camera shows a corner of it.
                renderer.needsFitOnNextContent = true
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
        }
    }

    @ViewBuilder
    private var marqueeOverlay: some View {
        if let rect = marqueeRect {
            // SAME style as the icon grid's LibraryMarquee (#4601): the
            // full-opacity stroke read darker than every other marquee.
            Rectangle()
                .fill(Color.accentColor.opacity(0.15))
                .overlay(Rectangle().stroke(Color.accentColor.opacity(0.6), lineWidth: 1))
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
            selection: $selectedNodeIds
        )
        renderer.onIntent = { controller.dispatch($0) }
        renderer.isDragSuppressed = { controller.isDragging($0) }
        renderer.storageService = storageService
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
                // A tap on the frame or a handle is not a tap on a placeable:
                // decoration entities carry synthetic names that match nothing
                // in the scene, so dispatching one would select a placeable
                // that does not exist and silently clear the real selection.
                guard !CanvasSelectionFrame.isDecoration(id) else { return }
                controller?.dispatch(.tap(
                    id: id.isEmpty ? nil : id,
                    modifiers: CanvasInteractionController.liveSelectionModifiers()
                ))
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
                // A drag that started on a resize handle belongs to
                // `resizeDrag`. Without this the same gesture would ALSO move
                // the card, so resizing would drag the thing being resized.
                guard !CanvasSelectionFrame.isDecoration(id) else { return }
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

    private func draggedWorld(
        start: SIMD3<Float>, translation: CGSize, viewHeight: CGFloat, id: String
    ) -> SIMD3<Double> {
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

    /// Background drag. The policy this encodes (#4290), and it is the INVERSE of
    /// what shipped: a plain drag never pans. Space held → pan the ortho camera;
    /// otherwise → rubber-band marquee multi-select (⇧ or not, so the old
    /// ⇧-marquee habit still works). Panning is the deliberate act because on a
    /// Tinderbox-style canvas the plain drag has to belong to the card under the
    /// pointer, and a camera pan competing for it is why moving items didn't work.
    ///
    /// `minimumDistance` is deliberately LOOSER than `nodeDrag`'s 2pt: the card
    /// drag therefore activates first and sets `draggingNodeId`, so the guard
    /// below is decided rather than racing whichever handler SwiftUI runs first.
    private func panOrMarquee(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 6)
            .onChanged { value in
                // A live resize is a drag too, and it starts on a handle rather
                // than on a card — so `draggingNodeId` is nil and the marquee
                // would rubber-band across the board while the user resizes.
                guard resizeHandle == nil else { marqueeRect = nil; return }
                guard draggingNodeId == nil else { marqueeRect = nil; return }
                if spaceHeld {
                    panCamera(by: value.translation, in: size)
                } else {
                    marqueeRect = Canvas2DProjection.marqueeRect(
                        from: value.startLocation, to: value.location
                    )
                }
            }
            .onEnded { _ in
                if resizeHandle == nil, draggingNodeId == nil, !spaceHeld, let rect = marqueeRect {
                    // ⇧/⌘ held while rubber-banding ADDS to the selection
                    // (#4436) — read at .onEnded, the moment the marquee
                    // commits, exactly as the tap path reads them.
                    controller?.dispatch(.marquee(
                        ids: renderer.placeableIds(inScreenRect: rect, viewSize: size),
                        modifiers: CanvasInteractionController.liveSelectionModifiers()
                    ))
                }
                marqueeRect = nil
                panBaseline = .zero
            }
    }
}
