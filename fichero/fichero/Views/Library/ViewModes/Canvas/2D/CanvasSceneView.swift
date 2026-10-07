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
    /// Double-clicking a card opens the item it stands for (a document id); nil keeps the old
    /// double-click, zooming onto the card (2026-09-30: double-click should take you to the item).
    var onOpenDocument: ((String) -> Void)?
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

    /// WHICH cards matter right now — the active search's score-weighted heat
    /// map today, an entity highlight when a picker lands (§25.4 step 2). One
    /// channel, so the two can never grow different visual languages. Neutral
    /// outside a search, and it moves nothing.
    var emphasis: CanvasEmphasis = .neutral

    /// WHAT each card is, in colour (§20.3 Colour by) — the other re-encode
    /// channel, produced by the host from document attributes.
    var tint: CanvasTint = .neutral

    /// The board's groups (`doc:<groupId>`), drawn as frames holding their pages (#5570). Known
    /// from the listed documents, so a group is a frame from its first frame on.
    var groupNodeIds: Set<String> = []
    /// A group's pages, in order, as page nodes; nil draws groups as empty frames.
    var pagesOfGroup: ((String) async -> [SpatialNode])?
    /// Each loaded group's pages, keyed by group node id (`CanvasSceneView+Groups.swift`).
    @State var groupPages: [String: [SpatialNode]] = [:]
    /// The pages a dragged group carries, with where each started. Moved live, never saved: they
    /// follow their group's saved place.
    @State var nestedDragOrigins: [String: SIMD3<Double>] = [:]

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
    @State var draggingNodeId: String?
    @State var dragStartScene: SIMD3<Float>?
    @State var dragOriginWorld: SIMD3<Double>?

    // Modifier state: ⌥ = force-link on drag-onto, Space = pan the view (#4290 —
    // the plain drag belongs to the ITEM). ⇧ is no longer tracked: a background
    // drag marquees whether or not it's held, so there is nothing to consult.
    @State var optionHeld = false
    @State private var spaceHeld = false
    // @GestureState, not @State (ghost-marquee fix, 2026-08-22): SwiftUI
    // never calls .onEnded on a CANCELLED gesture — a competing recognizer
    // winning, Space pressed mid-drag, the window losing focus — so a @State
    // rect cleared only in .onEnded stayed painted. @GestureState resets on
    // end AND cancel, so the rectangle structurally cannot outlive the drag.
    // Internal, not private: `marqueeOverlay` moved to +Gestures.swift (this
    // file is at its file_length ceiling) and Swift's `private` is FILE-scoped.
    @GestureState var marqueeRect: CGRect?

    // Resize-handle drag state (#4409). Internal, not private: the gesture that
    // reads it lives in `CanvasSceneView+Resize.swift` and Swift's `private` is
    // FILE-scoped.
    @State var resizeHandle: (itemId: String, corner: CanvasSelectionFrame.Corner)?
    @State var resizeOriginSize: CGSize?
    @State var resizeLiveSize: CGSize?

    private var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    /// The §20.3 "Arrange by" axis, written by `CanvasArrangePicker`. Both
    /// canvases READ this one key: they share a layout store, so a board they
    /// disagree about is two different boards.
    @AppStorage(CanvasArrangement.storageKey) private var arrangementRaw = CanvasArrangement.asFiled.rawValue

    /// How many cards the board lays out — nodes plus the non-link items, the
    /// same sequence `CanvasSceneState.resolve` slots.
    private var placeableCount: Int {
        nodes.count + (itemStore?.items(for: scopeKey) ?? []).filter { $0.kind != .link }.count
    }

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

    /// The current scene resolved from the shared stores (canonical world space),
    /// with the single selection mirrored into the scene's selection set. Reading
    /// the stores here ties re-render (→ reconcile) to their change stream.
    ///
    /// Row-less placeables are laid into a spaced GRID rather than taking their
    /// backend default (#4290): the projector's defaults sit on the XZ plane, and
    /// this renderer drops z, so every card in a folder collapsed onto the line
    /// `y = 0` — one row, cards on top of each other, and drops resolving as
    /// links against their own neighbours instead of as moves.
    /// `savedRows` nil reads the store; `[]` resolves the board as though nothing were placed, which
    /// is where an arrangement puts every card (#5302).
    private func resolvedState(in viewportSize: CGSize, savedRows: [CanvasItemLayout]? = nil) -> CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: nodes,
            connections: connections,
            links: links,
            layoutRows: savedRows ?? layoutStore?.layout(for: scopeKey) ?? [],
            items: itemStore?.items(for: scopeKey) ?? [],
            // Columns from the ONE shared derivation, identical in 2D and 3D
            // (user, 2026-08-20: one shared default so the two canvases show
            // the SAME board — they already share the layout store, so a move
            // in one is a move in the other). Viewport-derived now (§18.1
            // defect 3), but derived in a single renderer-independent place so
            // the two canvases still cannot drift apart.
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
        state = CanvasGroupNesting.nest(state, groupNodeIds: groupNodeIds, contents: groupContents)
        state.selection = selectedNodeIds
        state.emphasis = emphasis
        state.tint = tint
        return state
    }

    var body: some View {
        GeometryReader { geo in
            // The board is resolved HERE, in the body, not inside RealityView's closures (#5476).
            // Reading the saved rows, the items and the page aspects here is what makes SwiftUI
            // redraw when one of them changes. Read only inside `update`, they changed silently,
            // and the next unrelated update (a pinch) applied them all at once: the cards jumped
            // on zoom. Zoom itself changes no input here, so it moves the camera and nothing else.
            let board = resolvedState(in: geo.size)
            RealityView { content in
                // BEFORE the first reconcile (first-load fix, 2026-08-22, same
                // as CanvasSpaceView): configureController runs in `.task`,
                // after this closure — cards built here otherwise fetch with a
                // nil service and fall back to the global library.
                renderer.storageService = storageService
                content.add(renderer.camera)
                content.add(renderer.root)
                // Not before the pane has a size (#5476): a zero viewport lays the default grid
                // out ten columns wide, so the first frame showed a layout the next update replaced.
                guard geo.size.width > 0, geo.size.height > 0 else { return }
                renderer.viewportSize = geo.size
                renderer.reconcile(to: board)
            } update: { _ in
                guard geo.size.width > 0, geo.size.height > 0 else { return }
                renderer.viewportSize = geo.size
                renderer.storageService = storageService
                renderer.detailTier = CanvasDetailTier.forZoomScale(renderer.reportedZoomScale)
                renderer.reconcile(to: board)
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
            .onReceive(NotificationCenter.default.publisher(for: .canvasFocusZoomToggle)) { note in
                guard let id = note.object as? String else { return }
                toggleFocusZoom(on: id)
            }
            // Background tap clears — as a SIBLING gesture, not a separate
            // .onTapGesture on an outer wrapper: the wrapper's tap fired
            // ALONGSIDE the entity tap and instantly wiped the selection it
            // had just made ("only way to select is drag", 2026-08-20).
            // A click selects the card under it, found by the canvas's own hit test
            // (`placeableId(atScreenPoint:)`, 2026-09-30): RealityKit's entity-targeted tap
            // stopped reaching the cards, so a click on a card cleared the selection instead.
            .gesture(SpatialTapGesture().onEnded { value in
                let id = renderer.placeableId(atScreenPoint: value.location, viewSize: geo.size)
                pointTap(on: id)
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
                        by: CGSize(width: delta.width, height: delta.height),
                        in: geo.size
                    )
                }, onZoom: { delta, anchor in
                    // ⌘ + two-finger drag zooms INTO THE CURSOR (user,
                    // 2026-08-20): the world point under the pointer stays
                    // put while the scale changes — pan by the anchor times
                    // the world-per-point change, same mapping the pan uses.
                    let oldScale = renderer.orthoScale
                    renderer.setOrthoScale(oldScale * Float(1 + delta * 0.005))
                    let wppOld = Canvas2DProjection.worldPerPoint(
                        orthoScale: oldScale, viewHeight: geo.size.height
                    )
                    let wppNew = Canvas2DProjection.worldPerPoint(
                        orthoScale: renderer.orthoScale, viewHeight: geo.size.height
                    )
                    let factor = wppOld - wppNew
                    renderer.panCamera(worldDelta: SIMD2<Float>(
                        Float(anchor.x) * factor,
                        -Float(anchor.y) * factor
                    ))
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
            // Same strip, same corner as 3D — one board, one place to say
            // what it means.
            // Arrange/Colour-by moved to the library's ONE bottom bar
            // (Daniel, 2026-08-23): they filter/colourise, so they live with
            // sort and filter, not floating over the board.
            .focusedSceneValue(\.canvasViewActions, canvasCommandActions)
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
            // Over a corner handle the pointer becomes the diagonal resize cursor (2026-09-30), so
            // the handle reads as a handle before it is pressed.
            .onContinuousHover { phase in
                guard !spaceHeld, resizeHandle == nil else { return }
                if case .active(let point) = phase,
                   let handle = renderer.resizeHandle(atScreenPoint: point, viewSize: geo.size) {
                    applyResizeCursor(handle.corner)
                    overHandle = true
                } else if overHandle {
                    overHandle = false
                    applyPanCursor(false)
                }
            }
            // Arrange by is an ACTION (#5302, Finder's Clean Up By): choosing an order lays every
            // card out in it and saves those places. As a default for unplaced cards only, it did
            // nothing to any card a person had moved, and once positions save that is all of them.
            .onChange(of: arrangementRaw) { _, raw in
                guard CanvasArrangement.stored(raw) != .free, let layoutStore else { return }
                let rows = CanvasArrangement.rowsPinning(
                    // A page inside a group follows its group; it is never a row on this board.
                    resolvedState(in: geo.size, savedRows: []).placeables.filter { $0.containerId == nil },
                    keeping: layoutStore.layout(for: scopeKey)
                )
                let scope = scopeKey
                Task { await layoutStore.saveLayout(folderId: scope, items: rows) }
            }
            .task(id: folderScopeId) {
                configureController()
                // Frame the board once this scope has content — the default grid
                // is origin-anchored, so an unfitted camera shows a corner of it —
                // or return to where this person last left this folder's board.
                renderer.cameraToRestoreOnNextContent = CanvasCameraMemory.camera(for: scopeKey)
                renderer.needsFitOnNextContent = true
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
            .task(id: groupNodeIds) { await loadGroupPages() }
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
        let scope = scopeKey
        renderer.onCameraChange = { CanvasCameraMemory.remember($0, for: scope) }
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
    func dropTarget(near world: SIMD3<Double>, dragged: String) -> CanvasDropTarget? {
        renderer.dropTargetId(nearWorld: world, excluding: dragged)
            .map { CanvasDropTarget(id: $0, kind: targetKind($0)) }
    }

    /// Where double-click zoom returns to; nil = not zoomed into a node.
    @State var focusReturnSnapshot: (position: SIMD3<Float>, scale: Float)?

    /// Where this WINDOW has been looking (§16) — view state, saved nowhere.
    @State var jumpHistory = CanvasJumpHistory<(position: SIMD3<Float>, scale: Float)>()
    /// Manual double-click detection INSIDE tapSelect (2026-08-22): a
    /// separate simultaneous TapGesture(count: 2) joined the gesture set and
    /// broke the exclusivity that let tapSelect's success suppress the
    /// background-clear tap — every click selected and was instantly wiped
    /// ("you can't single click on an item"). One gesture, no interplay.
    @State var lastTapNodeId: String?
    /// True while a drag that started ON a card (found by the canvas's own hit test) moves it.
    @State var pressDragging = false
    /// Whether the pointer is over a resize handle, so leaving it restores the arrow once.
    @State var overHandle = false
    /// The OTHER selected cards a press-drag carries along, with where each started (2026-09-30:
    /// a rubber band selected cards and then nothing could be done with them).
    @State var groupDragOrigins: [String: SIMD3<Double>] = [:]
    @State var lastTapAt: Date = .distantPast

    // MARK: - Gestures

    func draggedWorld(
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
            .updating($marqueeRect) { value, state, _ in
                // A live resize is a drag too, and it starts on a handle rather
                // than on a card — so `draggingNodeId` is nil and the marquee
                // would rubber-band across the board while the user resizes.
                // A press ON a card is that card's drag, never a rubber band (2026-09-30).
                guard resizeHandle == nil, draggingNodeId == nil, !spaceHeld,
                      renderer.resizeHandle(atScreenPoint: value.startLocation, viewSize: size) == nil,
                      renderer.placeableId(atScreenPoint: value.startLocation, viewSize: size) == nil else {
                    state = nil
                    return
                }
                state = Canvas2DProjection.marqueeRect(
                    from: value.startLocation, to: value.location
                )
            }
            .onChanged { value in
                // A press on a selected card's corner handle resizes it.
                if !pressDragging, !spaceHeld, draggingNodeId == nil,
                   let handle = resizeHandle.map({ (itemId: $0.itemId, corner: $0.corner) })
                    ?? renderer.resizeHandle(atScreenPoint: value.startLocation, viewSize: size) {
                    resizeChanged(itemId: handle.itemId, corner: handle.corner, translation: value.translation, in: size)
                    return
                }
                if pressDragging || (resizeHandle == nil && draggingNodeId == nil && !spaceHeld) {
                    if pressMovesCard(value, in: size) { return }
                }
                guard resizeHandle == nil, draggingNodeId == nil, spaceHeld else { return }
                panCamera(by: value.translation, in: size)
            }
            .onEnded { value in
                if resizeHandle != nil {
                    resizeEnded()
                    return
                }
                if pressDragging {
                    endPressDrag(value, in: size)
                    return
                }
                // marqueeRect is already reset here (@GestureState), so the
                // commit rect is recomputed from the gesture's own value.
                if resizeHandle == nil, draggingNodeId == nil, !spaceHeld {
                    let rect = Canvas2DProjection.marqueeRect(
                        from: value.startLocation, to: value.location
                    )
                    // ⇧/⌘ held while rubber-banding ADDS to the selection
                    // (#4436) — read at .onEnded, the moment the marquee
                    // commits, exactly as the tap path reads them.
                    controller?.dispatch(.marquee(
                        ids: Set(renderer.placeableIds(inScreenRect: rect, viewSize: size).map { owningCardId(of: $0) }),
                        modifiers: CanvasInteractionController.liveSelectionModifiers()
                    ))
                }
                panBaseline = .zero
            }
    }

    // MARK: - Card press and drag by the canvas's own hit test (2026-09-30)

    /// A click on a card, or on the board (`id` nil): select it, or zoom on a double-click, exactly
    /// as the entity-targeted `tapSelect` did.
    private func pointTap(on id: String?) {
        // A page inside a group is part of the group's card here (#5570).
        let id = id.map { owningCardId(of: $0) }
        let now = Date()
        if let id, lastTapNodeId == id, now.timeIntervalSince(lastTapAt) < 0.35 {
            lastTapNodeId = nil
            if let onOpenDocument, let documentId = SpatialLibraryProjector.documentId(fromNodeId: id) {
                onOpenDocument(documentId)
            } else {
                toggleFocusZoom(on: id)
            }
            return
        }
        lastTapNodeId = id
        lastTapAt = now
        controller?.dispatch(.tap(id: id, modifiers: CanvasInteractionController.liveSelectionModifiers()))
    }

    /// Start or continue a drag that began on a card. True when this drag belongs to a card.
    private func pressMovesCard(_ value: DragGesture.Value, in size: CGSize) -> Bool {
        if !pressDragging {
            guard let id = renderer.placeableId(atScreenPoint: value.startLocation, viewSize: size)
                .map({ owningCardId(of: $0) }),
                  let world = renderer.worldPosition(of: id) else { return false }
            pressDragging = true
            draggingNodeId = id
            dragStartScene = Canvas2DProjection.scenePosition(world)
            dragOriginWorld = world
            // Pressing one card of a multiple selection moves the whole selection.
            if selectedNodeIds.contains(id), selectedNodeIds.count > 1 {
                groupDragOrigins = Dictionary(uniqueKeysWithValues: selectedNodeIds.filter { $0 != id }.compactMap { other in
                    renderer.worldPosition(of: other).map { (other, $0) }
                })
                renderer.setGroupDragging(true)
            } else {
                groupDragOrigins = [:]
                // Only a single card goes through the controller; a group is saved in one write at
                // the end (`saveGroupMove`), so the controller never holds a half-finished drag.
                controller?.dispatch(.dragBegan(id: id))
            }
            beginCarryingNestedPages(of: [id] + Array(groupDragOrigins.keys))
        }
        guard let id = draggingNodeId, let start = dragStartScene else { return true }
        let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
        renderer.liveMove(id: id, toWorld: world)
        if let origin = dragOriginWorld {
            for (other, otherOrigin) in groupDragOrigins {
                renderer.liveMove(id: other, toWorld: otherOrigin + (world - origin))
            }
            for (page, pageOrigin) in nestedDragOrigins {
                renderer.liveMove(id: page, toWorld: pageOrigin + (world - origin))
            }
        }
        renderer.setHoverTarget(renderer.dropTargetId(nearWorld: world, excluding: id))
        controller?.dispatch(.dragMoved(id: id, position: world))
        return true
    }

    /// Drop the card: the same end, save and undo as the entity-targeted `nodeDrag`.
    private func endPressDrag(_ value: DragGesture.Value, in size: CGSize) {
        defer {
            pressDragging = false
            draggingNodeId = nil
            dragStartScene = nil
            dragOriginWorld = nil
            groupDragOrigins = [:]
            nestedDragOrigins = [:]
            renderer.setGroupDragging(false)
        }
        guard let id = draggingNodeId, let start = dragStartScene else { return }
        let world = draggedWorld(start: start, translation: value.translation, viewHeight: size.height, id: id)
        if !groupDragOrigins.isEmpty, let origin = dragOriginWorld {
            saveGroupMove(pressed: id, to: world, from: origin)
            return
        }
        renderer.setHoverTarget(nil)
        let target = dropTarget(near: world, dragged: id)
        let modifiers: CanvasDropModifiers = optionHeld ? .forceLink : []
        controller?.dispatch(.dragEnded(id: id, position: world, dropTarget: target, modifiers: modifiers))
        if target == nil, let controller, let origin = dragOriginWorld {
            controller.registerMoveUndo(id: id, origin: origin, destination: world, undoManager: undoManager)
        }
    }

    /// Save a whole selection's move as ONE layout write: every carried card keeps its offset from
    /// the pressed one. No drop-into or link for a group; those stay single-card gestures.
    private func saveGroupMove(pressed id: String, to world: SIMD3<Double>, from origin: SIMD3<Double>) {
        guard let layoutStore else { return }
        let delta = world - origin
        var rows = layoutStore.layout(for: scopeKey)
        var moved = groupDragOrigins.mapValues { $0 + delta }
        moved[id] = world
        for (movedId, position) in moved {
            if let index = rows.firstIndex(where: { $0.itemId == movedId }) {
                rows[index].x = position.x
                rows[index].y = position.y
                rows[index].z = position.z
            } else {
                rows.append(CanvasItemLayout(itemId: movedId, x: position.x, y: position.y, z: position.z))
            }
        }
        let scope = scopeKey
        Task { await layoutStore.saveLayout(folderId: scope, items: rows) }
    }
}
