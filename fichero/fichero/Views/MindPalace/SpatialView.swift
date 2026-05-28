import SwiftUI

/// 2D projection of a Mind Palace room — the `.twoD` render mode and the
/// fallback when RealityKit isn't available.
///
/// Renders each `MindPalaceNode` at its **backend-provided** `positionX/Y`,
/// draws `MindPalaceConnection` edges, labels nodes by kind, and supports
/// tap-to-select (writes `selectedNodeId`). The only client-side transform is
/// a fit-to-view camera (uniform translate + scale of the whole scene so it's
/// on-screen) — relative node geometry is never recomputed
/// (`feedback_kg_logic_in_backend`). View-only: dragging is Phase 2.
struct Spatial2DCanvas: View {
    let nodes: [MindPalaceNode]
    let connections: [MindPalaceConnection]
    @Binding var selectedNodeId: String?

    private let nodeDiameter: CGFloat = 14
    private let padding: CGFloat = 48

    var body: some View {
        GeometryReader { geo in
            let layout = projectedPositions(in: geo.size)
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

                // Node chips at projected positions.
                ForEach(nodes) { node in
                    if let point = layout[node.id] {
                        nodeChip(node)
                            .position(point)
                            .onTapGesture { selectedNodeId = node.id }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .textBackgroundColor))
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
}
