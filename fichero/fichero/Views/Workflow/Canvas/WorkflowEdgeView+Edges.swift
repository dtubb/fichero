import SwiftUI

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
