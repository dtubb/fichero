import SwiftUI

// MARK: - Edge Connection

extension WorkflowCanvasView {
    /// Check if two port types are compatible for connection
    func canConnect(outputType: String, inputType: String) -> Bool {
        // "any" accepts everything
        if inputType == "any" || outputType == "any" { return true }
        // Same type always compatible
        if outputType == inputType { return true }
        // Implicit conversions
        let conversions: [String: Set<String>] = [
            "json": ["text"],
            "array": ["json", "text"],
            "file": ["files"],
            "files": ["file"],
            "image": ["file", "files"],
        ]
        return conversions[outputType]?.contains(inputType) ?? false
    }

    /// Get the data type of a port by node and port ID
    func getPortDataType(nodeId: String, portId: String, isOutput: Bool) -> String? {
        guard let node = workflow.nodes.first(where: { $0.id == nodeId }) else { return nil }
        let ports = isOutput ? node.outputPorts : node.inputPorts
        return ports.first(where: { $0.id == portId })?.dataType
    }

    func startEdgeDrag(from node: WorkflowNode, port: PortInfo) {
        let portPositions = calculatePortPositions()
        guard let startPoint = portPositions["\(node.id):\(port.id)"] else { return }

        draggedEdge = DraggedEdge(
            sourceNodeId: node.id,
            sourcePortId: port.id,
            startPoint: startPoint,
            currentPoint: startPoint
        )
    }

    /// Detach an edge from an input port and start dragging from the original source
    func detachAndRedrag(fromNode targetNodeId: String, port: PortInfo) {
        // Find the edge connected to this input port
        guard let edgeIndex = workflow.edges.firstIndex(where: {
            $0.targetNodeId == targetNodeId && $0.targetPortId == port.id
        }) else { return }

        let edge = workflow.edges[edgeIndex]
        let sourceNodeId = edge.sourceNodeId
        let sourcePortId = edge.sourcePortId

        // Remove the edge
        workflow.edges.remove(at: edgeIndex)

        // Find the source node and port to start a new drag
        guard let sourceNode = workflow.nodes.first(where: { $0.id == sourceNodeId }),
              let sourcePort = sourceNode.outputPorts.first(where: { $0.id == sourcePortId }) else { return }

        // Start a new edge drag from the original source
        startEdgeDrag(from: sourceNode, port: sourcePort)
    }

    func updateEdgeDrag(translation: CGSize) {
        guard let edge = draggedEdge else { return }

        // Simple: add translation to start point
        let currentPoint = CGPoint(
            x: edge.startPoint.x + translation.width,
            y: edge.startPoint.y + translation.height
        )
        draggedEdge?.currentPoint = currentPoint
    }

    func endEdgeDrag() {
        guard let edge = draggedEdge else { return }

        // Find nearest input port within threshold
        let threshold: CGFloat = 30
        let portPositions = calculatePortPositions()

        var nearestNode: WorkflowNode?
        var nearestPort: PortInfo?
        var nearestDistance: CGFloat = threshold

        // Get source port data type for compatibility checking
        let sourceType = getPortDataType(nodeId: edge.sourceNodeId, portId: edge.sourcePortId, isOutput: true) ?? "any"

        for node in workflow.nodes {
            // Skip the source node
            guard node.id != edge.sourceNodeId else { continue }

            for port in node.inputPorts {
                // Check type compatibility
                guard canConnect(outputType: sourceType, inputType: port.dataType) else { continue }

                guard let portPos = portPositions["\(node.id):\(port.id)"] else { continue }
                let distance = hypot(edge.currentPoint.x - portPos.x, edge.currentPoint.y - portPos.y)
                if distance < nearestDistance {
                    nearestDistance = distance
                    nearestNode = node
                    nearestPort = port
                }
            }
        }

        // Complete connection if we found a compatible target
        if let targetNode = nearestNode, let targetPort = nearestPort {
            let newEdge = WorkflowEdge(
                sourceNodeId: edge.sourceNodeId,
                targetNodeId: targetNode.id,
                sourcePortId: edge.sourcePortId,
                targetPortId: targetPort.id
            )
            workflow.edges.append(newEdge)
        }

        draggedEdge = nil
    }

    func completeEdge(to node: WorkflowNode, port: PortInfo) {
        guard let dragged = draggedEdge else { return }

        // Don't connect to same node
        guard dragged.sourceNodeId != node.id else {
            endEdgeDrag()
            return
        }

        // Check type compatibility
        let sourceType = getPortDataType(nodeId: dragged.sourceNodeId, portId: dragged.sourcePortId, isOutput: true) ?? "any"
        guard canConnect(outputType: sourceType, inputType: port.dataType) else {
            endEdgeDrag()
            return
        }

        // Create the edge
        let newEdge = WorkflowEdge(
            sourceNodeId: dragged.sourceNodeId,
            targetNodeId: node.id,
            sourcePortId: dragged.sourcePortId,
            targetPortId: port.id
        )

        workflow.edges.append(newEdge)
        endEdgeDrag()
    }
}

// MARK: - Port Positions

extension WorkflowCanvasView {
    func calculatePortPositions() -> [String: CGPoint] {
        var positions: [String: CGPoint] = [:]

        for node in workflow.nodes {
            let nodePosition = CGPoint(x: node.positionX, y: node.positionY)

            // Input ports on left side
            let inputCount = max(node.inputPorts.count, 1)
            let inputSpacing = nodeHeight / CGFloat(inputCount + 1)
            for (index, port) in node.inputPorts.enumerated() {
                let portY = nodePosition.y - nodeHeight / 2 + inputSpacing * CGFloat(index + 1)
                let portX = nodePosition.x - nodeWidth / 2
                positions["\(node.id):\(port.id)"] = CGPoint(x: portX, y: portY)
            }

            // Output ports on right side
            let outputCount = max(node.outputPorts.count, 1)
            let outputSpacing = nodeHeight / CGFloat(outputCount + 1)
            for (index, port) in node.outputPorts.enumerated() {
                let portY = nodePosition.y - nodeHeight / 2 + outputSpacing * CGFloat(index + 1)
                let portX = nodePosition.x + nodeWidth / 2
                positions["\(node.id):\(port.id)"] = CGPoint(x: portX, y: portY)
            }
        }

        return positions
    }

    func connectedInputPorts(for nodeId: String) -> Set<String> {
        Set(workflow.edges.filter { $0.targetNodeId == nodeId }.map { $0.targetPortId })
    }

    func connectedOutputPorts(for nodeId: String) -> Set<String> {
        Set(workflow.edges.filter { $0.sourceNodeId == nodeId }.map { $0.sourcePortId })
    }
}
