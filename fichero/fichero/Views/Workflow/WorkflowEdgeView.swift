// swiftlint:disable file_length
import SwiftUI

// MARK: - Fan role classification
//
// The backend's LangGraph builder runs implicit fan-out/fan-in around
// per-file tools: Transcribe runs N times in parallel, Catalogue collects
// the N results before running once. That structure is invisible in a
// linear `Files → Transcribe → Catalogue` canvas, which is exactly the
// confusion the user reported. These role annotations let us render a
// badge on the edge so the user can SEE when files fan out and when
// they merge back.
//
// Static tool-name → role for 0.0.2. A future revision pushes this
// metadata from the backend ToolDef so adding a tool doesn't need a
// frontend edit.

enum EdgeFanRole: Equatable {
    case fanOut
    case fanIn
    case none

    func label(count: Int?) -> String {
        switch self {
        case .fanOut: return count.map { "→ \($0) files" } ?? "fan-out"
        case .fanIn:  return count.map { "∑ \($0) files" } ?? "merge"
        case .none:   return ""
        }
    }
}

/// Tools whose invocation fans out across files (one call per file).
private let fanOutTools: Set<String> = [
    "transcribe", "describe", "classify", "caption", "analyze", "tags",
    "colors", "faces", "layout", "compare", "convert", "extract", "objects",
    "scene", "quality", "safety", "diagram", "table_extract", "handwriting",
    "style", "similarity",
    "audio_transcribe", "video_describe"
]

/// Tools that collapse fan-out results into a single payload.
private let fanInTools: Set<String> = [
    "aggregate",
    "catalogue",
    "write_file",
    "people_extract", "dates_extract", "rivers_extract", "events_extract",
    "mines_extract", "properties_extract", "legal_references_extract",
    "keywords_extract"
]

enum EdgeFanRoleResolver {
    static func role(sourceTool: String?, targetTool: String?) -> EdgeFanRole {
        if let target = targetTool, fanInTools.contains(target) {
            return .fanIn
        }
        if let source = sourceTool, fanOutTools.contains(source) {
            return .fanOut
        }
        return .none
    }
}

/// Visual representation of an edge (connection between ports)
struct WorkflowEdgeView: View {
    let edge: WorkflowEdge
    let sourcePoint: CGPoint
    let targetPoint: CGPoint
    let isSelected: Bool
    let isConditional: Bool
    /// Optional classification — when .fanOut or .fanIn, a labelled
    /// badge is rendered on the edge so the user can see the topology
    /// change visually. Defaults to .none so existing call sites don't
    /// need to pass a value.
    var fanRole: EdgeFanRole = .none
    /// Live file count during an active run. `nil` when idle — badge
    /// falls back to a static label.
    var fanCount: Int?

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

            // Fan-in / fan-out badge — shown even at idle so users see
            // the topology before running. A live count overrides the
            // static label when available.
            if fanRole != .none {
                fanBadge
            }
        }
    }

    /// Pill-shaped badge near the target end of the edge. Colored by
    /// role so fan-out (branching) and fan-in (merging) read at a
    /// glance.
    @ViewBuilder
    private var fanBadge: some View {
        let text = fanRole.label(count: fanCount)
        if !text.isEmpty {
            let position: CGPoint = {
                // Place fan-in badges near the target (where merging
                // happens), fan-out near the source (where branching
                // happens). Makes the direction of the topology bend
                // obvious.
                switch fanRole {
                case .fanIn:
                    return CGPoint(
                        x: sourcePoint.x * 0.3 + targetPoint.x * 0.7,
                        y: sourcePoint.y * 0.3 + targetPoint.y * 0.7 - 14
                    )
                case .fanOut:
                    return CGPoint(
                        x: sourcePoint.x * 0.7 + targetPoint.x * 0.3,
                        y: sourcePoint.y * 0.7 + targetPoint.y * 0.3 - 14
                    )
                case .none:
                    return .zero
                }
            }()
            let tint: Color = fanRole == .fanIn ? .teal : .blue
            Text(text)
                .font(.caption2.weight(.semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(
                    Capsule()
                        .fill(tint)
                        .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
                )
                .position(position)
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
struct DraggingWorkflowEdgeView: View {
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
            if let sourcePoint = getPortPosition(
                nodeId: edge.sourceNodeId, portId: edge.sourcePortId, isOutput: true
            ),
            let targetPoint = getPortPosition(
                nodeId: edge.targetNodeId, portId: edge.targetPortId, isOutput: false
            ) {
                let sourceTool = nodes.first { $0.id == edge.sourceNodeId }?.tool
                let targetTool = nodes.first { $0.id == edge.targetNodeId }?.tool
                WorkflowEdgeView(
                    edge: edge,
                    sourcePoint: sourcePoint,
                    targetPoint: targetPoint,
                    isSelected: edge.id == selectedEdgeId,
                    isConditional: edge.condition != nil,
                    fanRole: EdgeFanRoleResolver.role(
                        sourceTool: sourceTool,
                        targetTool: targetTool
                    )
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
                let portY = nodePosition.y - nodeSize.height / 2 + inputSpacing * CGFloat(index + 1)
                let portX = nodePosition.x - nodeSize.width / 2 - 6  // Offset for port circle
                positions["\(node.id):\(port.id)"] = CGPoint(x: portX, y: portY)
            }

            // Output ports on right side
            let outputSpacing = nodeSize.height / CGFloat(node.outputPorts.count + 1)
            for (index, port) in node.outputPorts.enumerated() {
                let portY = nodePosition.y - nodeSize.height / 2 + outputSpacing * CGFloat(index + 1)
                let portX = nodePosition.x + nodeSize.width / 2 + 6  // Offset for port circle
                positions["\(node.id):\(port.id)"] = CGPoint(x: portX, y: portY)
            }
        }

        return positions
    }
}

// MARK: - Preview

#Preview("Edge Styles") {
    ZStack {
        // Normal edge
        WorkflowEdgeView(
            edge: WorkflowEdge(
                sourceNodeId: "a",
                targetNodeId: "b",
                sourcePortId: "output",
                targetPortId: "input"
            ),
            sourcePoint: CGPoint(x: 50, y: 50),
            targetPoint: CGPoint(x: 250, y: 100),
            isSelected: false,
            isConditional: false
        )

        // Selected edge
        WorkflowEdgeView(
            edge: WorkflowEdge(
                sourceNodeId: "a",
                targetNodeId: "c",
                sourcePortId: "output",
                targetPortId: "input"
            ),
            sourcePoint: CGPoint(x: 50, y: 150),
            targetPoint: CGPoint(x: 250, y: 200),
            isSelected: true,
            isConditional: false
        )

        // Conditional edge
        WorkflowEdgeView(
            edge: WorkflowEdge(
                sourceNodeId: "a",
                targetNodeId: "d",
                sourcePortId: "true",
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
        DraggingWorkflowEdgeView(
            startPoint: CGPoint(x: 50, y: 350),
            currentPoint: CGPoint(x: 200, y: 380)
        )
    }
    .frame(width: 300, height: 400)
    .background(Color(.windowBackgroundColor))
}
