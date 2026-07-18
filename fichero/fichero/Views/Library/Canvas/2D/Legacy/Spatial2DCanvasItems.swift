import FicheroAPIClient
import SwiftUI

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
    /// Rendered card size. Driven by the persisted `CanvasItemLayout` w/h (or the
    /// default sticky-note size) and updated live while a resize handle is dragged
    /// (#1748).
    var width: CGFloat = CanvasItemView.defaultWidth
    var height: CGFloat = CanvasItemView.defaultHeight

    static let defaultWidth: CGFloat = 160
    static let defaultHeight: CGFloat = 92

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
        .frame(width: width, height: height, alignment: .topLeading)
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
        (itemStore?.items(for: scopeKey) ?? []).filter { $0.kind == .link }
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
        for item in store.layout(for: scopeKey) where result[item.itemId] != nil {
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
            (layoutStore?.layout(for: scopeKey) ?? []).map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        var result: [String: CGPoint] = [:]
        var fallback = 0
        for item in store.items(for: scopeKey) where item.kind != .link {
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
            store.layout(for: folderId).map { ($0.itemId, $0) },
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
            store.layout(for: folderId).map { ($0.itemId, $0) },
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

    /// Persist a resized item's new card size into its `canvas_layout` w/h,
    /// preserving every other row. No-op unless the canvas is interactive (#1748).
    func persistItemSize(itemId: String, size: CGSize) {
        guard let store = layoutStore, let folderId = folderScopeId else { return }
        var rows: [String: CanvasItemLayout] = Dictionary(
            store.layout(for: folderId).map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        if rows[itemId] != nil {
            rows[itemId]?.w = Double(size.width)
            rows[itemId]?.h = Double(size.height)
        } else {
            rows[itemId] = CanvasItemLayout(
                itemId: itemId, w: Double(size.width), h: Double(size.height)
            )
        }
        let items = Array(rows.values)
        Task { await store.saveLayout(folderId: folderId, items: items) }
    }
}
