import SwiftUI

// MARK: - Nodes Layer

extension WorkflowCanvasView {
    @ViewBuilder
    var nodesLayer: some View {
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
            },
            executionState: nodeStates[node.id]
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
            nodePopoverContent(node: node, index: index)
        }
        .position(x: node.positionX, y: node.positionY)
        // Double tap to open popover for editing (must come before single tap)
        .onTapGesture(count: 2) {
            selectedEdgeId = nil
            selectedNodeIds = [node.id]
            editingNodeId = node.id
        }
        // Single tap to select (allows delete key to work)
        .onTapGesture {
            selectedEdgeId = nil
            selectedNodeIds = [node.id]
            editingNodeId = nil  // Close any open popover
            isCanvasFocused = true  // Keep focus on canvas for keyboard commands
        }
        // Drag to move node - use regular gesture so port's highPriorityGesture takes precedence
        .gesture(nodeDragGesture(index: index))
        // Context menu for node
        .contextMenu {
            nodeContextMenu(node: node, index: index)
        }
    }

    @ViewBuilder
    private func nodePopoverContent(node: WorkflowNode, index: Int) -> some View {
        NodePopover(
            node: Binding(
                get: { workflow.nodes[index] },
                set: { workflow.nodes[index] = $0 }
            ),
            allNodes: workflow.nodes,
            workflowId: workflow.id,
            onDelete: {
                deleteNode(at: index)
            },
            onDuplicate: {
                duplicateNode(at: index)
            }
        )
        .environment(executionObserver)
    }

    // Drag to move node - use regular gesture so port's highPriorityGesture takes precedence
    private func nodeDragGesture(index: Int) -> some Gesture {
        DragGesture(minimumDistance: 3)
            .onChanged { value in
                handleNodeDrag(value: value, index: index)
            }
            .onEnded { _ in
                finishNodeDrag()
            }
    }

    @ViewBuilder
    private func nodeContextMenu(node: WorkflowNode, index: Int) -> some View {
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

    func deleteNode(at index: Int) {
        let previousWorkflow = workflow
        let nodeId = workflow.nodes[index].id

        // Remove connected edges
        workflow.edges.removeAll { $0.sourceNodeId == nodeId || $0.targetNodeId == nodeId }

        // Remove node
        workflow.nodes.remove(at: index)
        editingNodeId = nil
        selectedNodeIds.remove(nodeId)
        registerUndo(from: previousWorkflow, actionName: "Delete Node")
    }

    func duplicateNode(at index: Int) {
        let previousWorkflow = workflow
        let original = workflow.nodes[index]
        let duplicate = WorkflowNode(
            tool: original.tool,
            label: "\((original.label ?? original.tool)) Copy",
            positionX: original.positionX + Double(nodeWidth) + 80,
            positionY: original.positionY + 30,
            inputPorts: original.inputPorts,
            outputPorts: original.outputPorts,
            providerName: original.providerName,
            modelName: original.modelName
        )
        workflow.nodes.insert(duplicate, at: index + 1)
        editingNodeId = duplicate.id
        registerUndo(from: previousWorkflow, actionName: "Duplicate Node")
    }
}
