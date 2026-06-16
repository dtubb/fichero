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
    /// The scope these positions belong to — a real folder id, or the synthetic
    /// `wholeLibraryRoomId` ("__library__") for the unscoped whole-library view.
    var folderScopeId: String?

    // Live drag state for the chip currently being moved.
    @State private var dragItemId: String?
    @State private var dragTranslation: CGSize = .zero

    private let nodeDiameter: CGFloat = 14
    private let padding: CGFloat = 48

    private var isInteractive: Bool { layoutStore != nil && folderScopeId != nil }

    var body: some View {
        GeometryReader { geo in
            let layout = resolvedPositions(in: geo.size)
            ZStack {
                // Edges drawn beneath nodes.
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
                }

                // Node chips at resolved positions (saved layout overrides the
                // projector default per item where a row exists).
                ForEach(nodes) { node in
                    if let base = layout[node.id] {
                        let point = (dragItemId == node.id)
                            ? CGPoint(x: base.x + dragTranslation.width,
                                      y: base.y + dragTranslation.height)
                            : base
                        chip(for: node, at: point, base: base, in: geo.size)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(platformColor: .textBackgroundColor))
            .task(id: folderScopeId) {
                guard let store = layoutStore, let folderId = folderScopeId else { return }
                await store.loadLayout(folderId: folderId)
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
        let isSelected = node.id == selectedNodeId
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

    /// Map backend (x, y) coordinates into view space with a uniform
    /// fit-to-view transform. Y is flipped so positive-y reads as "up".
    private func projectedPositions(in size: CGSize) -> [String: CGPoint] {
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

    /// The positions actually rendered: the projector default per node, with a
    /// saved `CanvasItemLayout` (screen-space x/y) overriding it **only** where
    /// a row exists. Items with no saved row keep the projector default.
    private func resolvedPositions(in size: CGSize) -> [String: CGPoint] {
        let projected = projectedPositions(in: size)
        guard let store = layoutStore else { return projected }
        var result = projected
        for item in store.layout where result[item.itemId] != nil {
            result[item.itemId] = CGPoint(x: item.x, y: item.y)
        }
        return result
    }

    /// Persist the current screen positions of every displayed node through the
    /// store (the moved node at its drop point). Pinning all visible nodes on
    /// the first drag keeps the layout stable on reload regardless of which
    /// rows existed before. No-op unless the canvas is interactive.
    private func persistLayout(movedId: String, droppedAt: CGPoint, in size: CGSize) {
        guard let store = layoutStore, let folderId = folderScopeId else { return }
        let projected = projectedPositions(in: size)
        var rows: [String: CanvasItemLayout] = Dictionary(
            store.layout.map { ($0.itemId, $0) },
            uniquingKeysWith: { _, latest in latest }
        )
        for node in nodes {
            let point: CGPoint
            if node.id == movedId {
                point = droppedAt
            } else if let existing = rows[node.id] {
                point = CGPoint(x: existing.x, y: existing.y)
            } else {
                point = projected[node.id] ?? .zero
            }
            var row = rows[node.id] ?? CanvasItemLayout(itemId: node.id)
            row.x = point.x
            row.y = point.y
            rows[node.id] = row
        }
        let items = Array(rows.values)
        Task { await store.saveLayout(folderId: folderId, items: items) }
    }
}
