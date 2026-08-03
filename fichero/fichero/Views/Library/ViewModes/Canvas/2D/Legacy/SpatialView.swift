import FicheroAPIClient
import SwiftUI

/// 2D projection of a Spatial room — the `.twoD` render mode and the
/// fallback when RealityKit isn't available.
///
/// Renders each `SpatialNode` at its **backend-provided** `positionX/Y`,
/// draws `SpatialConnection` edges, labels nodes by kind, and supports
/// tap-to-select (writes `selectedNodeId`). The only client-side transform is
/// a fit-to-view camera (uniform translate + scale of the whole scene so it's
/// on-screen) — relative node geometry is never recomputed
/// (`feedback_kg_logic_in_backend`).
///
/// Slice 3 (#2293) adds **optional** position persistence: when both
/// `layoutStore` and `folderScopeId` are supplied the canvas loads the saved
/// layout on appear, lets the user drag chips, and persists screen positions on
/// drag-end — so a hand-arranged layout survives a view-mode switch (the #1
/// bug). When either is nil (Spatial room, RealityKit fallback) the canvas
/// is view-only, exactly as before. The store is the only thing that touches
/// the network; this view never calls the generated client directly.
struct Spatial2DCanvas: View {
    let nodes: [SpatialNode]
    let connections: [SpatialConnection]
    /// The SAME selection set every other view mode holds (#4409). This was a
    /// single optional, so a marquee over five cards published one of them —
    /// whichever `Set` ordering happened to yield first.
    @Binding var selectedNodeIds: Set<String>

    /// The row a ⌘-click extends from. Held here because `SelectionGrammar` is
    /// pure and keeps no state, and this renderer has no
    /// `CanvasInteractionController` to hold it for them (#4436).
    @State var canvasSelectionAnchor: String?

    /// Observable layout store. When non-nil (together with `folderScopeId`)
    /// the canvas becomes interactive and persists positions through it.
    var layoutStore: CanvasLayoutStore?
    /// Observable item store. When non-nil the canvas also renders the folder's
    /// standalone heterogeneous canvas items (notes / quotes / text / links).
    var itemStore: CanvasItemStore?
    /// The scope these positions belong to — a real folder id, or the synthetic
    /// `wholeLibraryRoomId` ("__library__") for the unscoped whole-library view.
    var folderScopeId: String?
    /// The CURRENT library's storage service for node thumbnails (#4160).
    /// nil falls back to the global library (whole-library Spatial room only).
    var storageService: StorageService?

    /// Non-optional scope key for reading the per-scope stores (#3082): the
    /// folder id, or `wholeLibraryRoomId` when unscoped. The stores cache rows
    /// per scope so this window never reads another folder's layout.
    var scopeKey: String { folderScopeId ?? wholeLibraryRoomId }

    // Live drag state for the chip currently being moved.
    @State var dragItemId: String?
    @State var dragTranslation: CGSize = .zero
    /// Last-known canvas size, captured each frame so `.onDisappear` can flush
    /// any in-progress drag without access to the `GeometryReader` closure.
    @State var lastCanvasSize: CGSize = .zero

    // Live resize state for the standalone item currently being resized via its
    // corner grab handle (#1748). `resizeItemId` is the item being sized;
    // `resizeSize` is the in-flight card size (committed to w/h on release).
    @State var resizeItemId: String?
    @State var resizeSize: CGSize = .zero
    /// Card size captured when a resize drag begins, so the cumulative gesture
    /// translation isn't compounded against the live (growing) frame.
    @State var resizeOrigin: CGSize?

    // Camera (pure view state — never persisted). Zoom is committed; pinchScale
    // is the live in-flight magnification. Pan is committed offset + live drag.
    @State var zoom: CGFloat = 1
    @GestureState var pinchScale: CGFloat = 1
    @State var panOffset: CGSize = .zero
    @GestureState var livePan: CGSize = .zero

    /// Background-drag intent: pan the camera, or rubber-band a marquee.
    enum CanvasMode { case pan, marquee }
    @State var canvasMode: CanvasMode = .pan
    /// Live marquee rectangle in screen space (nil when not marqueeing).
    @State var marqueeRect: CGRect?

    let nodeDiameter: CGFloat = 14
    /// Non-private so the position-projection extension (in
    /// `Spatial2DCanvasItems.swift`) can read it.
    let padding: CGFloat = 48
    let minZoom: CGFloat = 0.25
    let maxZoom: CGFloat = 4.0

    // MARK: - Level of detail (#2298)
    //
    // ponytail: pragmatic LOD = cull by visible rect + skip thumbnail fetches
    // when zoomed out. This is the smallest diff that keeps the canvas smooth
    // toward ~30k items: SwiftUI still walks `nodes`/`items` to build the
    // `ForEach`, but offscreen chips emit no subview and zoomed-out chips never
    // touch the network. A full texture-streaming engine (tiled atlases,
    // mip levels, async eviction) is a FUTURE pass — only if profiling at
    // 30k+ shows the per-frame `ForEach` walk itself is the bottleneck.

    /// Below this effective zoom, nodes render as cheap kind glyphs and skip
    /// the thumbnail fetch (#1744 path); at/above it the real page thumbnail
    /// loads. Picked so a chip's thumbnail is only fetched once it's large
    /// enough on screen to actually read.
    let thumbnailZoomThreshold: CGFloat = 0.6

    /// Canvas-space margin added around the visible rect so chips just past the
    /// edge still render — avoids pop-in while panning at the current zoom.
    let cullMargin: CGFloat = 240

    var isInteractive: Bool { layoutStore != nil && folderScopeId != nil }

    /// Clamped live zoom: committed zoom × in-flight pinch, bounded to range.
    var effectiveZoom: CGFloat {
        min(max(zoom * pinchScale, minZoom), maxZoom)
    }

    /// Committed pan plus the live drag translation.
    var effectiveOffset: CGSize {
        CGSize(width: panOffset.width + livePan.width,
               height: panOffset.height + livePan.height)
    }

    /// The slice of pre-transform canvas space currently on screen (#2298).
    ///
    /// `canvasContent` is laid out untransformed, then the body applies
    /// `.scaleEffect(effectiveZoom, anchor: .center).offset(effectiveOffset)`.
    /// Inverting that maps the on-screen viewport `[0, size]` back into canvas
    /// coordinates, so we can cull chips whose base point falls outside it.
    /// Reads `effectiveZoom`/`effectiveOffset`, so the cull updates live as the
    /// camera pans/zooms.
    func visibleCanvasRect(in size: CGSize) -> CGRect {
        let scale = effectiveZoom
        let offset = effectiveOffset
        let centre = CGPoint(x: size.width / 2, y: size.height / 2)
        // screen = centre + (canvas - centre) * scale + offset  ⇒  invert:
        func canvasX(_ screenX: CGFloat) -> CGFloat { centre.x + (screenX - centre.x - offset.width) / scale }
        func canvasY(_ screenY: CGFloat) -> CGFloat { centre.y + (screenY - centre.y - offset.height) / scale }
        return CGRect(
            x: canvasX(0),
            y: canvasY(0),
            width: canvasX(size.width) - canvasX(0),
            height: canvasY(size.height) - canvasY(0)
        )
        .insetBy(dx: -cullMargin, dy: -cullMargin)
    }

    var body: some View {
        GeometryReader { geo in
            let layout = resolvedPositions(in: geo.size)
            ZStack {
                // Scene content rides the camera transform (scale about centre,
                // then pan). Pure view-space — node positions are untouched.
                canvasContent(layout: layout, in: geo.size)
                    .scaleEffect(effectiveZoom)
                    .offset(effectiveOffset)

                // Rubber-band marquee, drawn in unscaled screen space.
                if let rect = marqueeRect {
                    marqueeShape(rect)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(platformColor: .textBackgroundColor))
            .contentShape(Rectangle())
            .gesture(backgroundGesture(layout: layout, in: geo.size))
            .simultaneousGesture(magnifyGesture)
            .overlay(alignment: .topTrailing) {
                HStack(spacing: 4) {
                    addItemMenu
                    modeToggle
                }
            }
            // Capture canvas size every frame so onDisappear can flush mid-drag.
            .onChange(of: geo.size, initial: true) { _, size in
                lastCanvasSize = size
            }
            .task(id: folderScopeId) {
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
            // Flush any in-progress node drag so positions are not lost when the
            // user navigates away mid-drag (gesture.onEnded never fires then).
            .onDisappear {
                guard let itemId = dragItemId, lastCanvasSize != .zero else { return }
                let base = resolvedPositions(in: lastCanvasSize)[itemId] ?? .zero
                let dropped = CGPoint(
                    x: base.x + dragTranslation.width,
                    y: base.y + dragTranslation.height
                )
                dragItemId = nil
                dragTranslation = .zero
                persistLayout(movedId: itemId, droppedAt: dropped, in: lastCanvasSize)
            }
        }
    }

    /// Edges + node chips. Extracted so the camera transform applies as a unit.
    @ViewBuilder
    func canvasContent(layout: [String: CGPoint], in size: CGSize) -> some View {
        let itemPoints = itemPositions(in: size)
        // Combined endpoint lookup: link items can join nodes and/or items.
        let combined = layout.merging(itemPoints) { _, item in item }
        // LOD (#2298): only emit chips inside the visible rect, and only fetch
        // page thumbnails once zoomed in enough to read them.
        let visible = visibleCanvasRect(in: size)
        let loadThumbnails = effectiveZoom >= thumbnailZoomThreshold
        ZStack {
            // Edges + link connectors drawn beneath chips.
            // ponytail: edges still draw as a single Path over all connections;
            // at 30k+ this Path build can dominate — split it by `visible` only
            // if profiling flags it. Node/thumbnail cost is the first-order win.
            edgeLayer(layout: layout, combined: combined)

            // Node chips at resolved positions (saved layout overrides the
            // projector default per item where a row exists). Offscreen chips
            // are culled so a 30k-node room only materializes what's in view.
            ForEach(nodes) { node in
                if let base = layout[node.id], visible.contains(base) {
                    let point = (dragItemId == node.id)
                        ? CGPoint(x: base.x + dragTranslation.width,
                                  y: base.y + dragTranslation.height)
                        : base
                    chip(for: node, at: point, base: base, in: size, loadThumbnail: loadThumbnails)
                }
            }

            // Standalone heterogeneous canvas items (notes / quotes / text)
            // rendered through the single `CanvasItemView`. Links draw above.
            ForEach(itemStore?.items(for: scopeKey) ?? []) { item in
                if item.kind != .link, let base = itemPoints[item.id], visible.contains(base) {
                    let point = (dragItemId == item.id)
                        ? CGPoint(x: base.x + dragTranslation.width,
                                  y: base.y + dragTranslation.height)
                        : base
                    itemChip(for: item, at: point, base: base)
                }
            }
        }
    }

    @ViewBuilder
    func chip(for node: SpatialNode, at point: CGPoint, base: CGPoint, in size: CGSize, loadThumbnail: Bool) -> some View {
        let chipView = nodeChip(node, loadThumbnail: loadThumbnail)
            .position(point)
            .zIndex(dragItemId == node.id ? 1 : 0)
            // Through the shared grammar (#4436): this was a bare replace, so
            // ⌘-click could not add a second card to the selection here even
            // though every list mode has done that for two releases.
            .onTapGesture {
                CanvasTapSelection.tap(
                    node.id, selection: &selectedNodeIds, anchor: &canvasSelectionAnchor
                )
            }
        if isInteractive {
            chipView.gesture(dragGesture(for: node, base: base, in: size))
        } else {
            chipView
        }
    }

    func dragGesture(for node: SpatialNode, base: CGPoint, in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 3)
            .onChanged { value in
                dragItemId = node.id
                dragTranslation = value.translation
            }
            .onEnded { value in
                let dropped = CGPoint(
                    x: base.x + value.translation.width,
                    y: base.y + value.translation.height
                )
                dragItemId = nil
                dragTranslation = .zero
                persistLayout(movedId: node.id, droppedAt: dropped, in: size)
            }
    }

    func nodeChip(_ node: SpatialNode, loadThumbnail: Bool) -> some View {
        // ONE source of "is this selected" (#4436). This used to OR in a
        // private `marqueeSelection`, so a marqueed chip drew selected while
        // the inspector, toolbar and every selection-driven command saw a
        // different set.
        let isSelected = selectedNodeIds.contains(node.id)
        return HStack(spacing: 5) {
            // Image / PDF-page nodes render their actual thumbnail (#1744);
            // non-source nodes keep the kind-coloured icon glyph. When zoomed
            // out (`loadThumbnail == false`) the thumbnail view draws the cheap
            // glyph placeholder and skips the network fetch — LOD (#2298).
            if let sourceId = node.sourceId, !sourceId.isEmpty {
                SpatialNodeThumbnail(
                    sourceId: sourceId,
                    fallbackIcon: node.nodeType.icon,
                    tint: node.nodeType.color,
                    side: nodeDiameter + 6,
                    enabled: loadThumbnail,
                    storageService: storageService
                )
            } else {
                Image(systemName: node.nodeType.icon)
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: nodeDiameter, height: nodeDiameter)
                    .background(node.nodeType.color, in: Circle())
            }
            Text(node.displayLabel)
                .font(.caption)
                .lineLimit(1)
                .foregroundStyle(.primary)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(.regularMaterial, in: Capsule())
        .overlay(
            Capsule().stroke(
                isSelected ? Color.accentColor : node.nodeType.color.opacity(0.4),
                lineWidth: isSelected ? 2 : 1
            )
        )
        .help("\(node.nodeType.label): \(node.displayLabel)")
    }

    /// One standalone canvas-item card, draggable when the canvas is
    /// interactive. Mirrors `chip(for:)` — same drag state and persistence
    /// plumbing — but persists through `persistItemPosition` (single row) since
    /// items have no projector default to pin.
    @ViewBuilder
    func itemChip(for item: CanvasItemDisplay, at point: CGPoint, base: CGPoint) -> some View {
        let size = itemSize(for: item)
        let showHandle = isInteractive && selectedNodeIds.contains(item.id) && item.kind != .link
        let card = CanvasItemView(
            item: item,
            isSelected: selectedNodeIds.contains(item.id),
            width: size.width,
            height: size.height
        )
        .overlay(alignment: .bottomTrailing) {
            if showHandle { resizeHandle(for: item) }
        }
        .position(point)
        .zIndex(dragItemId == item.id ? 2 : 1)
        .onTapGesture {
            CanvasTapSelection.tap(
                item.id, selection: &selectedNodeIds, anchor: &canvasSelectionAnchor
            )
        }
        if isInteractive {
            card.gesture(itemDragGesture(for: item, base: base))
        } else {
            card
        }
    }

    func itemDragGesture(for item: CanvasItemDisplay, base: CGPoint) -> some Gesture {
        DragGesture(minimumDistance: 3)
            .onChanged { value in
                dragItemId = item.id
                dragTranslation = value.translation
            }
            .onEnded { value in
                let dropped = CGPoint(
                    x: base.x + value.translation.width,
                    y: base.y + value.translation.height
                )
                dragItemId = nil
                dragTranslation = .zero
                persistItemPosition(itemId: item.id, droppedAt: dropped)
            }
    }

}
