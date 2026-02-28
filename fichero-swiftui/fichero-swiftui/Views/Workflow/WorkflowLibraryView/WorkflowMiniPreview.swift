import SwiftUI

/// Mini preview showing a schematic representation of the workflow
struct WorkflowMiniPreview: View {
    let nodeCount: Int
    let edgeCount: Int

    var body: some View {
        GeometryReader { _ in
            Canvas { context, size in
                let nodeRadius: CGFloat = 6
                let centerX = size.width / 2
                let centerY = size.height / 2

                // Draw placeholder nodes in a simple layout
                let displayNodes = min(nodeCount, 5)  // Max 5 nodes in preview
                let nodePositions = calculateNodePositions(
                    count: displayNodes,
                    in: CGRect(origin: .zero, size: size),
                    nodeRadius: nodeRadius
                )

                // Draw edges (simple lines between consecutive nodes)
                if displayNodes > 1 {
                    for idx in 0..<(displayNodes - 1) {
                        let start = nodePositions[idx]
                        let end = nodePositions[idx + 1]
                        var path = Path()
                        path.move(to: start)
                        path.addLine(to: end)
                        context.stroke(path, with: .color(.secondary.opacity(0.5)), lineWidth: 1)
                    }
                }

                // Draw nodes
                for position in nodePositions {
                    let rect = CGRect(
                        x: position.x - nodeRadius,
                        y: position.y - nodeRadius,
                        width: nodeRadius * 2,
                        height: nodeRadius * 2
                    )
                    context.fill(
                        Path(ellipseIn: rect),
                        with: .color(.accentColor)
                    )
                }

                // If no nodes, show placeholder
                if nodeCount == 0 {
                    let rect = CGRect(
                        x: centerX - 20,
                        y: centerY - 10,
                        width: 40,
                        height: 20
                    )
                    context.stroke(
                        Path(roundedRect: rect, cornerRadius: 4),
                        with: .color(.secondary.opacity(0.3)),
                        style: StrokeStyle(lineWidth: 1, dash: [4, 2])
                    )
                }
            }
        }
    }

    private func calculateNodePositions(count: Int, in rect: CGRect, nodeRadius: CGFloat) -> [CGPoint] {
        guard count > 0 else { return [] }

        let padding: CGFloat = nodeRadius + 4
        let availableWidth = rect.width - padding * 2
        let availableHeight = rect.height - padding * 2

        if count == 1 {
            return [CGPoint(x: rect.midX, y: rect.midY)]
        }

        // Arrange nodes in a simple left-to-right, top-to-bottom grid
        var positions: [CGPoint] = []
        let cols = min(count, 3)
        let rows = Int(ceil(Double(count) / Double(cols)))

        let xSpacing = availableWidth / CGFloat(max(cols - 1, 1))
        let ySpacing = availableHeight / CGFloat(max(rows - 1, 1))

        for idx in 0..<count {
            let col = idx % cols
            let row = idx / cols
            let positionX = padding + CGFloat(col) * xSpacing
            let positionY = padding + CGFloat(row) * ySpacing
            positions.append(CGPoint(x: positionX, y: positionY))
        }

        return positions
    }
}
