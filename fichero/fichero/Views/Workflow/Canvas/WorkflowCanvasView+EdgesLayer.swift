import SwiftUI

// MARK: - Edges Layer

extension WorkflowCanvasView {
    @ViewBuilder
    var edgesLayer: some View {
        let portPositions = calculatePortPositions()
        // Edges whose stored ports resolve to identical endpoints get a
        // symmetric vertical fan-out so parallel connections stay visually
        // distinct (#4322).
        let segments: [EdgeParallelOffset.Segment] = workflow.edges.compactMap { edge in
            guard let source = portPositions["\(edge.sourceNodeId):\(edge.sourcePortId)"],
                  let target = portPositions["\(edge.targetNodeId):\(edge.targetPortId)"] else { return nil }
            return EdgeParallelOffset.Segment(id: edge.id, source: source, target: target)
        }
        let parallelOffsets = EdgeParallelOffset.offsets(for: segments)

        ForEach(workflow.edges) { edge in
            if let sourcePoint = portPositions["\(edge.sourceNodeId):\(edge.sourcePortId)"],
               let targetPoint = portPositions["\(edge.targetNodeId):\(edge.targetPortId)"] {
                let offset = parallelOffsets[edge.id] ?? 0
                let sourceNode = workflow.nodes.first { $0.id == edge.sourceNodeId }
                let targetNode = workflow.nodes.first { $0.id == edge.targetNodeId }
                WorkflowEdgeView(
                    edge: edge,
                    sourcePoint: CGPoint(x: sourcePoint.x, y: sourcePoint.y + offset),
                    targetPoint: CGPoint(x: targetPoint.x, y: targetPoint.y + offset),
                    isSelected: edge.id == selectedEdgeId,
                    isConditional: edge.condition != nil,
                    fanRole: EdgeFanRoleResolver.role(
                        edge: edge,
                        sourceNode: sourceNode,
                        targetNode: targetNode,
                        toolRegistry: workflowStore.toolRegistry
                    ),
                    fanCount: liveFanCount(for: edge, targetTool: targetNode?.tool)
                )
                .onTapGesture {
                    selectedNodeIds.removeAll()
                    editingNodeId = nil
                    selectedEdgeId = edge.id
                    isCanvasFocused = true  // Re-focus for keyboard commands
                }
                .contextMenu {
                    Button(role: .destructive) {
                        let previousWorkflow = workflow
                        workflow.edges.removeAll { $0.id == edge.id }
                        selectedEdgeId = nil
                        registerUndo(from: previousWorkflow, actionName: "Delete Connection")
                    } label: {
                        Label("Delete Connection", systemImage: "trash")
                    }
                }
            }
        }
    }
}
