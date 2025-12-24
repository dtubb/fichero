import SwiftUI

/// Canvas view for workflow nodes with free placement and port-based connections
struct WorkflowCanvasView: View {
    @Binding var workflow: Workflow

    // Focus state for keyboard commands
    @FocusState private var isCanvasFocused: Bool

    // Selection state
    @State private var selectedNodeIds: Set<String> = []
    @State private var selectedEdgeId: String? = nil
    @State private var editingNodeId: String? = nil

    // Edge dragging state
    @State private var draggedEdge: DraggedEdge? = nil

    // Node dragging state
    @State private var nodeDragStartPosition: CGPoint? = nil
    @State private var draggingNodeIndex: Int? = nil

    // Node dimensions for port positioning
    private let nodeWidth: CGFloat = 140
    private let nodeHeight: CGFloat = 100

    // Canvas size (large enough to scroll around)
    private let canvasSize: CGSize = CGSize(width: 2000, height: 1500)

    var body: some View {
        ScrollView([.horizontal, .vertical], showsIndicators: true) {
            ZStack(alignment: .topLeading) {
                // Layer 1: Grid background (decorative, no interaction)
                GridPattern()
                    .stroke(Color.gray.opacity(0.2), lineWidth: 0.5)
                    .allowsHitTesting(false)

                // Layer 2: Interactive background (tap-to-deselect)
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedNodeIds.removeAll()
                        selectedEdgeId = nil
                        editingNodeId = nil
                        isCanvasFocused = true  // Re-focus for keyboard commands
                    }

                // Layer 3: Canvas content (nodes and edges)
                canvasContent
            }
            .frame(width: canvasSize.width, height: canvasSize.height)
            .onDrop(of: [.plainText], isTargeted: nil) { providers, location in
                handleDrop(providers: providers, at: location)
            }
        }
        .background(Color(.textBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .focusable()
        .focused($isCanvasFocused)
        .focusEffectDisabled()
        .onAppear { isCanvasFocused = true }
        .onDeleteCommand {
            deleteSelection()
        }
    }

    /// Delete selected edge or nodes
    private func deleteSelection() {
        // Delete selected edge first
        if let edgeId = selectedEdgeId {
            workflow.edges.removeAll { $0.id == edgeId }
            selectedEdgeId = nil
            return
        }

        // Delete selected nodes
        if !selectedNodeIds.isEmpty {
            for nodeId in selectedNodeIds {
                // Remove connected edges
                workflow.edges.removeAll { $0.sourceNodeId == nodeId || $0.targetNodeId == nodeId }
                // Remove node
                workflow.nodes.removeAll { $0.id == nodeId }
            }
            selectedNodeIds.removeAll()
            editingNodeId = nil
        }
    }

    // MARK: - Canvas Content

    @ViewBuilder
    private var canvasContent: some View {
        ZStack {
            // Edges layer (behind nodes)
            edgesLayer

            // Edge being dragged
            if let dragged = draggedEdge {
                DraggingEdgeView(startPoint: dragged.startPoint, currentPoint: dragged.currentPoint)
            }

            // Nodes layer
            nodesLayer
        }
    }

    // MARK: - Edges Layer

    @ViewBuilder
    private var edgesLayer: some View {
        let portPositions = calculatePortPositions()

        ForEach(workflow.edges) { edge in
            if let sourcePoint = portPositions["\(edge.sourceNodeId):\(edge.sourcePortId)"],
               let targetPoint = portPositions["\(edge.targetNodeId):\(edge.targetPortId)"] {
                EdgeView(
                    edge: edge,
                    sourcePoint: sourcePoint,
                    targetPoint: targetPoint,
                    isSelected: edge.id == selectedEdgeId,
                    isConditional: edge.condition != nil
                )
                .onTapGesture {
                    selectedNodeIds.removeAll()
                    editingNodeId = nil
                    selectedEdgeId = edge.id
                    isCanvasFocused = true  // Re-focus for keyboard commands
                }
                .contextMenu {
                    Button(role: .destructive) {
                        workflow.edges.removeAll { $0.id == edge.id }
                        selectedEdgeId = nil
                    } label: {
                        Label("Delete Connection", systemImage: "trash")
                    }
                }
            }
        }
    }

    // MARK: - Nodes Layer

    @ViewBuilder
    private var nodesLayer: some View {
        ForEach(Array(workflow.nodes.enumerated()), id: \.element.id) { index, node in
            nodeView(for: node, at: index)
        }
    }

    @ViewBuilder
    private func nodeView(for node: WorkflowNode, at index: Int) -> some View {
        // Container with explicit frame for proper popover anchoring
        WorkflowNodeView(
            node: node,
            isSelected: selectedNodeIds.contains(node.id),
            connectedInputPorts: connectedInputPorts(for: node.id),
            connectedOutputPorts: connectedOutputPorts(for: node.id),
            canAcceptDrop: draggedEdge != nil && draggedEdge?.sourceNodeId != node.id,
            onPortDragStarted: { port, _ in
                startEdgeDrag(from: node, port: port)
            },
            onPortDragChanged: { translation in
                updateEdgeDrag(translation: translation)
            },
            onPortDragEnded: {
                endEdgeDrag()
            },
            onPortDropReceived: { port, _ in
                completeEdge(to: node, port: port)
            },
            onInputPortDetach: { port, nodeId in
                detachAndRedrag(fromNode: nodeId, port: port)
            }
        )
        .frame(width: nodeWidth, height: nodeHeight)
        .popover(
            isPresented: Binding(
                get: { editingNodeId == node.id },
                set: { if !$0 { editingNodeId = nil } }
            ),
            attachmentAnchor: .rect(.bounds),
            arrowEdge: .top
        ) {
            NodePopover(
                node: Binding(
                    get: { workflow.nodes[index] },
                    set: { workflow.nodes[index] = $0 }
                ),
                onDelete: {
                    deleteNode(at: index)
                },
                onDuplicate: {
                    duplicateNode(at: index)
                }
            )
        }
        .position(x: node.positionX, y: node.positionY)
        // Tap to select and open popover
        .onTapGesture {
            selectedEdgeId = nil
            selectedNodeIds = [node.id]
            editingNodeId = node.id
            isCanvasFocused = true  // Re-focus for keyboard commands
        }
        // Drag to move node
        .gesture(
            DragGesture(minimumDistance: 8)
                .onChanged { value in
                    handleNodeDrag(value: value, index: index)
                }
                .onEnded { _ in
                    nodeDragStartPosition = nil
                    draggingNodeIndex = nil
                }
        )
        // Context menu for node
        .contextMenu {
            Button {
                editingNodeId = node.id
            } label: {
                Label("Edit", systemImage: "pencil")
            }

            Button {
                duplicateNode(at: index)
            } label: {
                Label("Duplicate", systemImage: "doc.on.doc")
            }

            Divider()

            Button(role: .destructive) {
                deleteNode(at: index)
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    // MARK: - Node Interaction

    private func handleNodeDrag(value: DragGesture.Value, index: Int) {
        // On first drag event, store starting position
        if nodeDragStartPosition == nil {
            nodeDragStartPosition = CGPoint(
                x: workflow.nodes[index].positionX,
                y: workflow.nodes[index].positionY
            )
            draggingNodeIndex = index
        }

        // Move node relative to start position
        if let startPos = nodeDragStartPosition {
            let newX = startPos.x + value.translation.width
            let newY = startPos.y + value.translation.height

            workflow.nodes[index].positionX = newX
            workflow.nodes[index].positionY = newY

            // Push other nodes out of the way if they would overlap
            resolveCollisions(for: index)
        }
    }

    /// Push nodes apart to avoid overlap (with smooth animation)
    private func resolveCollisions(for draggedIndex: Int) {
        let draggedNode = workflow.nodes[draggedIndex]
        let minDistance: CGFloat = nodeWidth + 20  // Minimum space between node centers

        for i in workflow.nodes.indices where i != draggedIndex {
            let otherNode = workflow.nodes[i]
            let dx = otherNode.positionX - draggedNode.positionX
            let dy = otherNode.positionY - draggedNode.positionY
            let distance = hypot(dx, dy)

            // If nodes are too close, push the other node away with animation
            if distance < minDistance && distance > 0 {
                let overlap = minDistance - distance
                let pushX = (dx / distance) * overlap
                let pushY = (dy / distance) * overlap

                withAnimation(.spring(response: 0.15, dampingFraction: 0.8)) {
                    workflow.nodes[i].positionX += pushX
                    workflow.nodes[i].positionY += pushY
                }
            } else if distance == 0 {
                // Exactly same position - push right
                withAnimation(.spring(response: 0.15, dampingFraction: 0.8)) {
                    workflow.nodes[i].positionX += minDistance
                }
            }
        }
    }

    private func deleteNode(at index: Int) {
        let nodeId = workflow.nodes[index].id

        // Remove connected edges
        workflow.edges.removeAll { $0.sourceNodeId == nodeId || $0.targetNodeId == nodeId }

        // Remove node
        workflow.nodes.remove(at: index)
        editingNodeId = nil
        selectedNodeIds.remove(nodeId)
    }

    private func duplicateNode(at index: Int) {
        let original = workflow.nodes[index]
        let duplicate = WorkflowNode(
            tool: original.tool,
            label: "\((original.label ?? original.tool)) Copy",
            positionX: original.positionX + 50,
            positionY: original.positionY + 50,
            inputPorts: original.inputPorts,
            outputPorts: original.outputPorts,
            providerName: original.providerName,
            modelName: original.modelName
        )
        workflow.nodes.insert(duplicate, at: index + 1)
        editingNodeId = duplicate.id
    }

    // MARK: - Edge Connection

    /// Check if two port types are compatible for connection
    private func canConnect(outputType: String, inputType: String) -> Bool {
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
    private func getPortDataType(nodeId: String, portId: String, isOutput: Bool) -> String? {
        guard let node = workflow.nodes.first(where: { $0.id == nodeId }) else { return nil }
        let ports = isOutput ? node.outputPorts : node.inputPorts
        return ports.first(where: { $0.id == portId })?.dataType
    }

    private func startEdgeDrag(from node: WorkflowNode, port: PortInfo) {
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
    private func detachAndRedrag(fromNode targetNodeId: String, port: PortInfo) {
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

    private func updateEdgeDrag(translation: CGSize) {
        guard let edge = draggedEdge else { return }

        // Simple: add translation to start point
        let currentPoint = CGPoint(
            x: edge.startPoint.x + translation.width,
            y: edge.startPoint.y + translation.height
        )
        draggedEdge?.currentPoint = currentPoint
    }

    private func endEdgeDrag() {
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

    private func completeEdge(to node: WorkflowNode, port: PortInfo) {
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

    // MARK: - Port Positions

    private func calculatePortPositions() -> [String: CGPoint] {
        var positions: [String: CGPoint] = [:]

        for node in workflow.nodes {
            let nodePosition = CGPoint(x: node.positionX, y: node.positionY)

            // Input ports on left side
            let inputCount = max(node.inputPorts.count, 1)
            let inputSpacing = nodeHeight / CGFloat(inputCount + 1)
            for (index, port) in node.inputPorts.enumerated() {
                let y = nodePosition.y - nodeHeight / 2 + inputSpacing * CGFloat(index + 1)
                let x = nodePosition.x - nodeWidth / 2
                positions["\(node.id):\(port.id)"] = CGPoint(x: x, y: y)
            }

            // Output ports on right side
            let outputCount = max(node.outputPorts.count, 1)
            let outputSpacing = nodeHeight / CGFloat(outputCount + 1)
            for (index, port) in node.outputPorts.enumerated() {
                let y = nodePosition.y - nodeHeight / 2 + outputSpacing * CGFloat(index + 1)
                let x = nodePosition.x + nodeWidth / 2
                positions["\(node.id):\(port.id)"] = CGPoint(x: x, y: y)
            }
        }

        return positions
    }

    private func connectedInputPorts(for nodeId: String) -> Set<String> {
        Set(workflow.edges.filter { $0.targetNodeId == nodeId }.map { $0.targetPortId })
    }

    private func connectedOutputPorts(for nodeId: String) -> Set<String> {
        Set(workflow.edges.filter { $0.sourceNodeId == nodeId }.map { $0.sourcePortId })
    }

    // MARK: - Drop Handling

    private func handleDrop(providers: [NSItemProvider], at location: CGPoint) -> Bool {
        for provider in providers {
            provider.loadObject(ofClass: NSString.self) { item, _ in
                if let jsonString = item as? String {
                    DispatchQueue.main.async {
                        // Try to decode as ToolInfo JSON first
                        if let data = jsonString.data(using: .utf8),
                           let toolInfo = try? JSONDecoder().decode(ToolInfo.self, from: data) {
                            addNodeFromToolInfo(toolInfo, at: location)
                        } else {
                            // Fallback: treat as plain tool name (legacy)
                            addNodeFromToolName(jsonString, at: location)
                        }
                    }
                }
            }
        }
        return true
    }

    /// Add node from full ToolInfo (preferred - has all metadata)
    private func addNodeFromToolInfo(_ toolInfo: ToolInfo, at position: CGPoint) {
        // Find selected node to auto-connect from
        let sourceNode = selectedNodeIds.first.flatMap { selectedId in
            workflow.nodes.first { $0.id == selectedId }
        }

        // Adjust position to avoid overlapping existing nodes
        let adjustedPosition = findNonOverlappingPosition(near: position)

        // Create node with full tool metadata
        let node = WorkflowNode(from: toolInfo, positionX: adjustedPosition.x, positionY: adjustedPosition.y)
        workflow.nodes.append(node)

        // Auto-connect: if there's a selected node with output ports, connect to new node's input
        if let source = sourceNode,
           let outputPort = source.outputPorts.first,
           let inputPort = node.inputPorts.first {
            let newEdge = WorkflowEdge(
                sourceNodeId: source.id,
                targetNodeId: node.id,
                sourcePortId: outputPort.id,
                targetPortId: inputPort.id
            )
            workflow.edges.append(newEdge)
        }

        selectedNodeIds = [node.id]
        editingNodeId = node.id
    }

    /// Add node from tool name only (legacy fallback)
    private func addNodeFromToolName(_ toolName: String, at position: CGPoint) {
        // Find selected node to auto-connect from
        let sourceNode = selectedNodeIds.first.flatMap { selectedId in
            workflow.nodes.first { $0.id == selectedId }
        }

        // Adjust position to avoid overlapping existing nodes
        let adjustedPosition = findNonOverlappingPosition(near: position)

        let node = WorkflowNode(
            tool: toolName,
            label: toolName.capitalized,
            positionX: adjustedPosition.x,
            positionY: adjustedPosition.y
        )
        workflow.nodes.append(node)

        // Auto-connect: if there's a selected node with output ports, connect to new node's input
        if let source = sourceNode,
           let outputPort = source.outputPorts.first,
           let inputPort = node.inputPorts.first {
            let newEdge = WorkflowEdge(
                sourceNodeId: source.id,
                targetNodeId: node.id,
                sourcePortId: outputPort.id,
                targetPortId: inputPort.id
            )
            workflow.edges.append(newEdge)
        }

        selectedNodeIds = [node.id]
        editingNodeId = node.id
    }

    /// Find a position that doesn't overlap existing nodes
    private func findNonOverlappingPosition(near position: CGPoint) -> CGPoint {
        let minDistance: CGFloat = nodeWidth + 20
        var adjusted = position

        // Check for overlaps and adjust
        for _ in 0..<10 {  // Max 10 iterations
            var hasOverlap = false
            for node in workflow.nodes {
                let dx = node.positionX - adjusted.x
                let dy = node.positionY - adjusted.y
                let distance = hypot(dx, dy)

                if distance < minDistance {
                    hasOverlap = true
                    // Move position away from the overlapping node
                    if distance > 0 {
                        adjusted.x -= (dx / distance) * (minDistance - distance + 10)
                        adjusted.y -= (dy / distance) * (minDistance - distance + 10)
                    } else {
                        adjusted.x += minDistance
                    }
                }
            }
            if !hasOverlap { break }
        }

        return adjusted
    }

}

// MARK: - Preview

#Preview {
    WorkflowCanvasView(
        workflow: .constant(Workflow(
            name: "Test Workflow",
            nodes: [
                WorkflowNode(
                    tool: "files",
                    label: "Input Files",
                    positionX: 150,
                    positionY: 200,
                    inputPorts: [],
                    outputPorts: [PortInfo(id: "files", name: "Files", portType: "output", dataType: "files", required: true, description: "")]
                ),
                WorkflowNode(
                    tool: "transcribe",
                    label: "Transcribe",
                    positionX: 350,
                    positionY: 200,
                    inputPorts: [PortInfo(id: "files", name: "Files", portType: "input", dataType: "files", required: true, description: "")],
                    outputPorts: [
                        PortInfo(id: "text", name: "Text", portType: "output", dataType: "text", required: true, description: ""),
                        PortInfo(id: "structured", name: "JSON", portType: "output", dataType: "json", required: true, description: "")
                    ]
                ),
                WorkflowNode(
                    tool: "to_word",
                    label: "To Word",
                    positionX: 550,
                    positionY: 200,
                    inputPorts: [PortInfo(id: "content", name: "Content", portType: "input", dataType: "any", required: true, description: "")],
                    outputPorts: [PortInfo(id: "file", name: "File", portType: "output", dataType: "file", required: true, description: "")]
                )
            ],
            edges: []
        ))
    )
    .frame(width: 800, height: 500)
}
