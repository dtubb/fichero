import SwiftUI

/// Represents an edge being drawn (during drag)
struct DraggedEdge {
    let sourceNodeId: String
    let sourcePortId: String
    let startPoint: CGPoint
    var currentPoint: CGPoint
}

/// Visual representation of an edge (connection between ports)
struct EdgeView: View {
    let edge: WorkflowEdge
    let sourcePoint: CGPoint
    let targetPoint: CGPoint
    let isSelected: Bool
    let isConditional: Bool

    var body: some View {
        ZStack {
            // Invisible wider stroke for easier click targeting
            edgePath
                .stroke(Color.clear, lineWidth: 20)
                .contentShape(edgePath.strokedPath(StrokeStyle(lineWidth: 20)))

            // Shadow for depth
            edgePath
                .stroke(
                    Color.black.opacity(0.2),
                    style: StrokeStyle(lineWidth: isSelected ? 5 : 4, lineCap: .round)
                )
                .offset(x: 1, y: 1)

            // Main edge stroke
            edgePath
                .stroke(
                    edgeColor,
                    style: StrokeStyle(
                        lineWidth: isSelected ? 4 : 2,
                        lineCap: .round,
                        dash: isConditional ? [8, 4] : []
                    )
                )

            // Direction arrow in the middle
            directionArrow

            // Arrow head at target
            arrowHead
                .fill(edgeColor)
                .position(targetPoint)

            // Label if present
            if let label = edge.label, !label.isEmpty {
                edgeLabel(label)
            }
        }
    }

    private var edgePath: Path {
        Path { path in
            let controlDistance = abs(targetPoint.x - sourcePoint.x) * 0.5
            let control1 = CGPoint(x: sourcePoint.x + controlDistance, y: sourcePoint.y)
            let control2 = CGPoint(x: targetPoint.x - controlDistance, y: targetPoint.y)

            path.move(to: sourcePoint)
            path.addCurve(to: targetPoint, control1: control1, control2: control2)
        }
    }

    /// Static direction arrow in the middle of the edge
    @ViewBuilder
    private var directionArrow: some View {
        let midX = (sourcePoint.x + targetPoint.x) / 2
        let midY = (sourcePoint.y + targetPoint.y) / 2
        let angle = atan2(targetPoint.y - sourcePoint.y, targetPoint.x - sourcePoint.x)

        // Single chevron arrow in middle
        Path { path in
            path.move(to: CGPoint(x: -5, y: -6))
            path.addLine(to: CGPoint(x: 5, y: 0))
            path.addLine(to: CGPoint(x: -5, y: 6))
        }
        .stroke(edgeColor, style: StrokeStyle(lineWidth: isSelected ? 2.5 : 1.5, lineCap: .round, lineJoin: .round))
        .rotationEffect(.radians(angle))
        .position(x: midX, y: midY)
        .opacity(isSelected ? 1.0 : 0.5)
    }

    private var arrowHead: Path {
        Path { path in
            let angle = atan2(targetPoint.y - sourcePoint.y, targetPoint.x - sourcePoint.x)
            let arrowLength: CGFloat = 10
            let arrowAngle: CGFloat = .pi / 6

            let point1 = CGPoint(
                x: -arrowLength * cos(angle - arrowAngle),
                y: -arrowLength * sin(angle - arrowAngle)
            )
            let point2 = CGPoint(
                x: -arrowLength * cos(angle + arrowAngle),
                y: -arrowLength * sin(angle + arrowAngle)
            )

            path.move(to: .zero)
            path.addLine(to: point1)
            path.addLine(to: point2)
            path.closeSubpath()
        }
    }

    private var edgeColor: Color {
        if isSelected {
            return .accentColor
        } else if isConditional {
            return .orange
        } else if edge.animated {
            return .blue
        } else {
            return Color.secondary.opacity(0.7)
        }
    }

    @ViewBuilder
    private func edgeLabel(_ text: String) -> some View {
        let midPoint = CGPoint(
            x: (sourcePoint.x + targetPoint.x) / 2,
            y: (sourcePoint.y + targetPoint.y) / 2
        )

        Text(text)
            .font(.caption2)
            .foregroundColor(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.windowBackgroundColor))
                    .shadow(radius: 1)
            )
            .position(midPoint)
    }
}

/// Edge being actively dragged from a port
struct DraggingEdgeView: View {
    let startPoint: CGPoint
    let currentPoint: CGPoint

    var body: some View {
        Path { path in
            let controlDistance = abs(currentPoint.x - startPoint.x) * 0.5
            let control1 = CGPoint(x: startPoint.x + controlDistance, y: startPoint.y)
            let control2 = CGPoint(x: currentPoint.x - controlDistance, y: currentPoint.y)

            path.move(to: startPoint)
            path.addCurve(to: currentPoint, control1: control1, control2: control2)
        }
        .stroke(
            Color.accentColor,
            style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [5, 3])
        )
    }
}

/// All edges in the workflow
struct EdgesView: View {
    let edges: [WorkflowEdge]
    let nodes: [WorkflowNode]
    let selectedEdgeId: String?
    let portPositions: [String: CGPoint]  // key: "nodeId:portId"

    var body: some View {
        ForEach(edges) { edge in
            if let sourcePoint = getPortPosition(nodeId: edge.sourceNodeId, portId: edge.sourcePortId, isOutput: true),
               let targetPoint = getPortPosition(nodeId: edge.targetNodeId, portId: edge.targetPortId, isOutput: false) {
                EdgeView(
                    edge: edge,
                    sourcePoint: sourcePoint,
                    targetPoint: targetPoint,
                    isSelected: edge.id == selectedEdgeId,
                    isConditional: edge.condition != nil
                )
            }
        }
    }

    private func getPortPosition(nodeId: String, portId: String, isOutput: Bool) -> CGPoint? {
        let key = "\(nodeId):\(portId)"
        return portPositions[key]
    }
}

/// Helper to calculate port positions based on node layout
struct PortPositionCalculator {
    let nodes: [WorkflowNode]
    let nodeSize: CGSize

    /// Calculate positions for all ports
    func calculatePositions() -> [String: CGPoint] {
        var positions: [String: CGPoint] = [:]

        for node in nodes {
            let nodePosition = CGPoint(x: node.positionX, y: node.positionY)

            // Input ports on left side
            let inputSpacing = nodeSize.height / CGFloat(node.inputPorts.count + 1)
            for (index, port) in node.inputPorts.enumerated() {
                let y = nodePosition.y - nodeSize.height / 2 + inputSpacing * CGFloat(index + 1)
                let x = nodePosition.x - nodeSize.width / 2 - 6  // Offset for port circle
                positions["\(node.id):\(port.id)"] = CGPoint(x: x, y: y)
            }

            // Output ports on right side
            let outputSpacing = nodeSize.height / CGFloat(node.outputPorts.count + 1)
            for (index, port) in node.outputPorts.enumerated() {
                let y = nodePosition.y - nodeSize.height / 2 + outputSpacing * CGFloat(index + 1)
                let x = nodePosition.x + nodeSize.width / 2 + 6  // Offset for port circle
                positions["\(node.id):\(port.id)"] = CGPoint(x: x, y: y)
            }
        }

        return positions
    }
}

// MARK: - Preview

#Preview("Edge Styles") {
    ZStack {
        // Normal edge
        EdgeView(
            edge: WorkflowEdge(
                sourceNodeId: "a",
                sourcePortId: "output",
                targetNodeId: "b",
                targetPortId: "input"
            ),
            sourcePoint: CGPoint(x: 50, y: 50),
            targetPoint: CGPoint(x: 250, y: 100),
            isSelected: false,
            isConditional: false
        )

        // Selected edge
        EdgeView(
            edge: WorkflowEdge(
                sourceNodeId: "a",
                sourcePortId: "output",
                targetNodeId: "c",
                targetPortId: "input"
            ),
            sourcePoint: CGPoint(x: 50, y: 150),
            targetPoint: CGPoint(x: 250, y: 200),
            isSelected: true,
            isConditional: false
        )

        // Conditional edge
        EdgeView(
            edge: WorkflowEdge(
                sourceNodeId: "a",
                sourcePortId: "true",
                targetNodeId: "d",
                targetPortId: "input",
                condition: "$.nodes.classify.category == 'invoice'",
                label: "invoice"
            ),
            sourcePoint: CGPoint(x: 50, y: 250),
            targetPoint: CGPoint(x: 250, y: 300),
            isSelected: false,
            isConditional: true
        )

        // Dragging edge
        DraggingEdgeView(
            startPoint: CGPoint(x: 50, y: 350),
            currentPoint: CGPoint(x: 200, y: 380)
        )
    }
    .frame(width: 300, height: 400)
    .background(Color(.windowBackgroundColor))
}
