import FicheroAPIClient
import SwiftUI

/// 2D projection of a Mind Palace room — the `.twoD` render mode and the
/// fallback when RealityKit isn't available.
///
/// Renders each `MindPalaceNode` at its **backend-provided** `positionX/Y`,
/// draws `MindPalaceConnection` edges, labels nodes by kind, and supports
/// tap-to-select (writes `selectedNodeId`). The only client-side transform is
/// a fit-to-view camera (uniform translate + scale of the whole scene so it's
/// on-screen) — relative node geometry is never recomputed
/// (`feedback_kg_logic_in_backend`).
///
/// Slice 3 (#2293) adds **optional** position persistence: when both
/// `layoutStore` and `folderScopeId` are supplied the canvas loads the saved
/// layout on appear, lets the user drag chips, and persists screen positions on
/// drag-end — so a hand-arranged layout survives a view-mode switch (the #1
/// bug). When either is nil (Mind Palace room, RealityKit fallback) the canvas
/// is view-only, exactly as before. The store is the only thing that touches
/// the network; this view never calls the generated client directly.
struct Spatial2DCanvas: View {
    let nodes: [MindPalaceNode]
    let connections: [MindPalaceConnection]
    @Binding var selectedNodeId: String?

    /// Observable layout store. When non-nil (together with `folderScopeId`)
    /// the canvas becomes interactive and persists positions through it.
    var layoutStore: CanvasLayoutStore?
    /// Observable item store. When non-nil the canvas also renders the folder's
    /// standalone heterogeneous canvas items (notes / quotes / text / links).
    var itemStore: CanvasItemStore?
    /// The scope these positions belong to — a real folder id, or the synthetic
    /// `wholeLibraryRoomId` ("__library__") for the unscoped whole-library view.
    var folderScopeId: String?

    // Live drag state for the chip currently being moved.
    @State private var dragItemId: String?
    @State private var dragTranslation: CGSize = .zero

    // Camera (pure view state — never persisted). Zoom is committed; pinchScale
    // is the live in-flight magnification. Pan is committed offset + live drag.
    @State private var zoom: CGFloat = 1
    @GestureState private var pinchScale: CGFloat = 1
    @State private var panOffset: CGSize = .zero
    @GestureState private var livePan: CGSize = .zero

    /// Background-drag intent: pan the camera, or rubber-band a marquee.
    private enum CanvasMode { case pan, marquee }
    @State private var canvasMode: CanvasMode = .pan
    /// Live marquee rectangle in screen space (nil when not marqueeing).
    @State private var marqueeRect: CGRect?
    /// Multi-selection accumulated by the marquee (in addition to the single
    /// `selectedNodeId` tap-selection binding).
    @State private var marqueeSelection: Set<String> = []

    private let nodeDiameter: CGFloat = 14
    /// Non-private so the position-projection extension (in
    /// `Spatial2DCanvasItems.swift`) can read it.
    let padding: CGFloat = 48
    private let minZoom: CGFloat = 0.25
    private let maxZoom: CGFloat = 4.0

    private var isInteractive: Bool { layoutStore != nil && folderScopeId != nil }

    /// Clamped live zoom: committed zoom × in-flight pinch, bounded to range.
    private var effectiveZoom: CGFloat {
        min(max(zoom * pinchScale, minZoom), maxZoom)
    }

    /// Committed pan plus the live drag translation.
    private var effectiveOffset: CGSize {
        CGSize(width: panOffset.width + livePan.width,
               height: panOffset.height + livePan.height)
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
            .task(id: folderScopeId) {
                guard let folderId = folderScopeId else { return }
                await layoutStore?.loadLayout(folderId: folderId)
                await itemStore?.loadItems(folderId: folderId)
            }
        }
    }

    /// Edges + node chips. Extracted so the camera transform applies as a unit.
    @ViewBuilder
    private func canvasContent(layout: [String: CGPoint], in size: CGSize) -> some View {
        let itemPoints = itemPositions(in: size)
        // Combined endpoint lookup: link items can join nodes and/or items.
        let combined = layout.merging(itemPoints) { _, item in item }
        ZStack {
            // Edges + link connectors drawn beneath chips.
            edgeLayer(layout: layout, combined: combined)

            // Node chips at resolved positions (saved layout overrides the
            // projector default per item where a row exists).
            ForEach(nodes) { node in
                if let base = layout[node.id] {
                    let point = (dragItemId == node.id)
                        ? CGPoint(x: base.x + dragTranslation.width,
                                  y: base.y + dragTranslation.height)
                        : base
                    chip(for: node, at: point, base: base, in: size)
                }
            }

            // Standalone heterogeneous canvas items (notes / quotes / text)
            // rendered through the single `CanvasItemView`. Links draw above.
            ForEach(itemStore?.items ?? []) { item in
                if item.kind != .link, let base = itemPoints[item.id] {
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
    private func chip(for node: MindPalaceNode, at point: CGPoint, base: CGPoint, in size: CGSize) -> some View {
        let chipView = nodeChip(node)
            .position(point)
            .zIndex(dragItemId == node.id ? 1 : 0)
            .onTapGesture { selectedNodeId = node.id }
        if isInteractive {
            chipView.gesture(dragGesture(for: node, base: base, in: size))
        } else {
            chipView
        }
    }

    private func dragGesture(for node: MindPalaceNode, base: CGPoint, in size: CGSize) -> some Gesture {
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

    private func nodeChip(_ node: MindPalaceNode) -> some View {
        let isSelected = node.id == selectedNodeId || marqueeSelection.contains(node.id)
        return HStack(spacing: 5) {
            Image(systemName: node.nodeType.icon)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: nodeDiameter, height: nodeDiameter)
                .background(node.nodeType.color, in: Circle())
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
    private func itemChip(for item: CanvasItemDisplay, at point: CGPoint, base: CGPoint) -> some View {
        let card = CanvasItemView(item: item, isSelected: item.id == selectedNodeId)
            .position(point)
            .zIndex(dragItemId == item.id ? 2 : 1)
            .onTapGesture { selectedNodeId = item.id }
        if isInteractive {
            card.gesture(itemDragGesture(for: item, base: base))
        } else {
            card
        }
    }

    private func itemDragGesture(for item: CanvasItemDisplay, base: CGPoint) -> some Gesture {
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

    /// Native "+" menu to add a standalone item to the canvas. Shown only when
    /// the canvas is interactive (a real item store + folder scope). The new
    /// item appears at its arranged fallback position until dragged.
    @ViewBuilder
    private var addItemMenu: some View {
        if let store = itemStore, let folderId = folderScopeId {
            Menu {
                Button("Add Note") {
                    Task { await store.createItem(folderId: folderId, kind: .note, text: "New note") }
                }
                Button("Add Quote") {
                    Task { await store.createItem(folderId: folderId, kind: .quote, text: "New quote") }
                }
                Button("Add Text") {
                    Task { await store.createItem(folderId: folderId, kind: .text, text: "New text") }
                }
            } label: {
                Image(systemName: "plus")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .padding(8)
            .help("Add a note, quote, or text card to the canvas")
        }
    }
}

// MARK: - Camera & marquee gestures

extension Spatial2DCanvas {
    /// Background drag: pans the camera in `.pan` mode, draws a selection
    /// marquee in `.marquee` mode. A drag that starts on a node is intercepted
    /// by that chip's own gesture (child wins), so this only fires on empty
    /// canvas — that's how pan/node-drag/marquee are disambiguated.
    func backgroundGesture(layout: [String: CGPoint], in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .updating($livePan) { value, state, _ in
                if canvasMode == .pan { state = value.translation }
            }
            .onChanged { value in
                if canvasMode == .marquee {
                    marqueeRect = rect(from: value.startLocation, to: value.location)
                }
            }
            .onEnded { value in
                switch canvasMode {
                case .pan:
                    panOffset = CGSize(
                        width: panOffset.width + value.translation.width,
                        height: panOffset.height + value.translation.height
                    )
                case .marquee:
                    let box = rect(from: value.startLocation, to: value.location)
                    marqueeSelection = nodesIntersecting(box, layout: layout, in: size)
                    selectedNodeId = marqueeSelection.first
                    marqueeRect = nil
                }
            }
    }

    /// Trackpad pinch-to-zoom, clamped to `minZoom...maxZoom` on commit.
    var magnifyGesture: some Gesture {
        MagnifyGesture()
            .updating($pinchScale) { value, state, _ in state = value.magnification }
            .onEnded { value in
                zoom = min(max(zoom * value.magnification, minZoom), maxZoom)
            }
    }

    /// Build an axis-aligned rect from two drag corners.
    func rect(from start: CGPoint, to end: CGPoint) -> CGRect {
        CGRect(x: min(start.x, end.x), y: min(start.y, end.y),
               width: abs(start.x - end.x), height: abs(start.y - end.y))
    }

    /// Nodes whose transformed centre falls inside the marquee. Centre points
    /// are mapped through the same camera transform SwiftUI applies (scale
    /// about the canvas centre, then pan).
    func nodesIntersecting(_ box: CGRect, layout: [String: CGPoint], in size: CGSize) -> Set<String> {
        let centre = CGPoint(x: size.width / 2, y: size.height / 2)
        let scale = effectiveZoom
        let offset = effectiveOffset
        var hits: Set<String> = []
        for node in nodes {
            guard let base = layout[node.id] else { continue }
            let screen = CGPoint(
                x: centre.x + (base.x - centre.x) * scale + offset.width,
                y: centre.y + (base.y - centre.y) * scale + offset.height
            )
            if box.contains(screen) { hits.insert(node.id) }
        }
        return hits
    }

    func marqueeShape(_ box: CGRect) -> some View {
        Rectangle()
            .fill(Color.accentColor.opacity(0.12))
            .overlay(Rectangle().stroke(Color.accentColor, lineWidth: 1))
            .frame(width: box.width, height: box.height)
            .position(x: box.midX, y: box.midY)
            .allowsHitTesting(false)
    }

    var modeToggle: some View {
        Picker("Canvas tool", selection: $canvasMode) {
            Image(systemName: "hand.draw").tag(CanvasMode.pan)
            Image(systemName: "rectangle.dashed").tag(CanvasMode.marquee)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(width: 96)
        .padding(8)
        .help("Drag empty space to pan, or marquee-select nodes")
    }
}


// MARK: - Kind display helpers

extension Components.Schemas.CanvasItemKind {
    /// SF Symbol labelling a standalone canvas item by kind.
    var icon: String {
        switch self {
        case .note: return "note.text"
        case .quote: return "quote.opening"
        case .workNote: return "pencil.and.list.clipboard"
        case .text: return "text.alignleft"
        case .link: return "link"
        }
    }

    /// Stable accent colour per kind, so a glance distinguishes item types.
    var accent: Color {
        switch self {
        case .note: return .orange
        case .quote: return .purple
        case .workNote: return .blue
        case .text: return .secondary
        case .link: return .gray
        }
    }

    /// Human-readable label, used as the empty-text placeholder.
    var label: String {
        switch self {
        case .note: return "Note"
        case .quote: return "Quote"
        case .workNote: return "Work Note"
        case .text: return "Text"
        case .link: return "Link"
        }
    }
}

// MARK: - One card view for every standalone kind

/// The single item view for the 2D canvas — ONE view switching on `kind`, not a
/// view per kind (#2294). Renders note / quote / work_note / text as a native
/// card (RoundedRectangle + Text + SF Symbol). `link` items are NOT cards: they
/// draw as a connector line between their two endpoints in the canvas edge
/// layer, so this view renders nothing for them.
struct CanvasItemView: View {
    let item: CanvasItemDisplay
    let isSelected: Bool

    var body: some View {
        switch item.kind {
        case .link:
            // Drawn as a connector in the edge layer — no chip.
            EmptyView()
        case .note, .quote, .workNote, .text:
            card
        }
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                Image(systemName: item.kind.icon)
                    .font(.caption2)
                    .foregroundStyle(item.kind.accent)
                Text(item.kind.label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text(displayText)
                .font(item.kind == .quote ? .callout.italic() : .callout)
                .lineLimit(4)
                .foregroundStyle(.primary)
                .multilineTextAlignment(.leading)
        }
        .padding(8)
        .frame(width: 160, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8).stroke(
                isSelected ? Color.accentColor : item.kind.accent.opacity(0.4),
                lineWidth: isSelected ? 2 : 1
            )
        )
        .help("\(item.kind.label): \(displayText)")
    }

    private var displayText: String {
        let trimmed = item.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? item.kind.label : trimmed
    }
}

// MARK: - Edge & link drawing

extension Spatial2DCanvas {
    /// The folder's `link`-kind canvas items (drawn as connectors).
    var linkItems: [CanvasItemDisplay] {
        (itemStore?.items ?? []).filter { $0.kind == .link }
    }

    /// Node edges plus `link`-item connectors, drawn beneath the chips. `layout`
    /// holds node positions; `combined` adds canvas-item positions so a link can
    /// join a node and/or an item.
    func edgeLayer(layout: [String: CGPoint], combined: [String: CGPoint]) -> some View {
        Canvas { context, _ in
            for connection in connections {
                guard
                    let fromPoint = layout[connection.sourceNodeId],
                    let toPoint = layout[connection.targetNodeId]
                else { continue }
                var path = Path()
                path.move(to: fromPoint)
                path.addLine(to: toPoint)
                context.stroke(
                    path,
                    with: .color(connection.connectionType.color.opacity(0.5)),
                    lineWidth: 1.5
                )
            }
            for link in linkItems {
                guard
                    let fromPoint = link.sourceItemId.flatMap({ combined[$0] }),
                    let toPoint = link.targetItemId.flatMap({ combined[$0] })
                else { continue }
                var path = Path()
                path.move(to: fromPoint)
                path.addLine(to: toPoint)
                context.stroke(
                    path,
                    with: .color(.secondary.opacity(0.6)),
                    style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])
                )
            }
        }
    }
}

// MARK: - Position projection & persistence

extension Spatial2DCanvas {
    /// Map backend (x, y) node coordinates into view space with a uniform
    /// fit-to-view transform. Y is flipped so positive-y reads as "up".
    func projectedPositions(in size: CGSize) -> [String: CGPoint] {
        guard !nodes.isEmpty else { return [:] }

        let xValues = nodes.map(\.positionX)
        let yValues = nodes.map(\.positionY)
        let minX = xValues.min() ?? 0
        let maxX = xValues.max() ?? 0
        let minY = yValues.min() ?? 0
        let maxY = yValues.max() ?? 0

        let spanX = maxX - minX
        let spanY = maxY - minY

        let availableW = Double(size.width) - Double(padding) * 2
        let availableH = Double(size.height) - Double(padding) * 2

        let scaleX = spanX > 0 ? availableW / spanX : 1
        let scaleY = spanY > 0 ? availableH / spanY : 1
        let scale = min(scaleX, scaleY)

        let contentW = spanX * scale
        let contentH = spanY * scale
        let offsetX = (Double(size.width) - contentW) / 2
        let offsetY = (Double(size.height) - contentH) / 2

        var result: [String: CGPoint] = [:]
        for node in nodes {
            let pointX = offsetX + (node.positionX - minX) * scale
            // Flip Y: larger backend y → higher on screen (smaller view y).
            let pointY = offsetY + (maxY - node.positionY) * scale
            result[node.id] = CGPoint(x: pointX, y: pointY)
        }
        return result
    }

    /// The node positions actually rendered: the projector default per node,
    /// with a saved `CanvasItemLayout` (screen-space x/y) overriding it **only**
    /// where a row exists. Nodes with no saved row keep the projector default.
    func resolvedPositions(in size: CGSize) -> [String: CGPoint] {
        let projected = projectedPositions(in: size)
        guard let store = layoutStore else { return projected }
        var result = projected
        for item in store.layout where result[item.itemId] != nil {
            result[item.itemId] = CGPoint(x: item.x, y: item.y)
        }
        return result
    }

    /// Positions for the standalone canvas-item cards (kind != link). A saved
    /// layout row wins; items with no row get a cascading arranged default near
    /// the top-left so a freshly-added note is visible until it's dragged.
    func itemPositions(in size: CGSize) -> [String: CGPoint] {
        guard let store = itemStore else { return [:] }
        let rows = Dictionary(
            (layoutStore?.layout ?? []).map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        var result: [String: CGPoint] = [:]
        var fallback = 0
        for item in store.items where item.kind != .link {
            if let row = rows[item.id] {
                result[item.id] = CGPoint(x: row.x, y: row.y)
            } else {
                let column = fallback % 3
                let line = fallback / 3
                result[item.id] = CGPoint(
                    x: padding + 100 + Double(column) * 180,
                    y: padding + 40 + Double(line) * 110
                )
                fallback += 1
            }
        }
        return result
    }

    /// Persist the screen positions of every displayed node through the layout
    /// store (the moved node at its drop point). Pinning all visible nodes on
    /// the first drag keeps the layout stable on reload. No-op unless interactive.
    func persistLayout(movedId: String, droppedAt: CGPoint, in size: CGSize) {
        guard let store = layoutStore, let folderId = folderScopeId else { return }
        let projected = projectedPositions(in: size)
        var rows: [String: CanvasItemLayout] = Dictionary(
            store.layout.map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        for node in nodes where rows[node.id] == nil {
            let point = projected[node.id] ?? .zero
            rows[node.id] = CanvasItemLayout(itemId: node.id, x: point.x, y: point.y)
        }
        rows[movedId]?.x = droppedAt.x
        rows[movedId]?.y = droppedAt.y
        let items = Array(rows.values)
        Task { await store.saveLayout(folderId: folderId, items: items) }
    }

    /// Persist a single dragged canvas item's new position. Updates its existing
    /// `canvas_layout` row (or inserts one) and re-saves the folder layout,
    /// preserving every other row. No-op unless the canvas is interactive.
    func persistItemPosition(itemId: String, droppedAt: CGPoint) {
        guard let store = layoutStore, let folderId = folderScopeId else { return }
        var rows: [String: CanvasItemLayout] = Dictionary(
            store.layout.map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        if rows[itemId] != nil {
            rows[itemId]?.x = droppedAt.x
            rows[itemId]?.y = droppedAt.y
        } else {
            rows[itemId] = CanvasItemLayout(itemId: itemId, x: droppedAt.x, y: droppedAt.y)
        }
        let items = Array(rows.values)
        Task { await store.saveLayout(folderId: folderId, items: items) }
    }
}
