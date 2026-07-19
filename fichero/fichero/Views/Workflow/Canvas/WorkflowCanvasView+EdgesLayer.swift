import SwiftUI

// MARK: - Edges Layer

extension WorkflowCanvasView {
    @ViewBuilder
    var edgesLayer: some View {
        let portPositions = calculatePortPositions()

        ForEach(workflow.edges) { edge in
            if let sourcePoint = portPositions["\(edge.sourceNodeId):\(edge.sourcePortId)"],
               let targetPoint = portPositions["\(edge.targetNodeId):\(edge.targetPortId)"] {
                let sourceTool = workflow.nodes.first { $0.id == edge.sourceNodeId }?.tool
                let targetTool = workflow.nodes.first { $0.id == edge.targetNodeId }?.tool
                WorkflowEdgeView(
                    edge: edge,
                    sourcePoint: sourcePoint,
                    targetPoint: targetPoint,
                    isSelected: edge.id == selectedEdgeId,
                    isConditional: edge.condition != nil,
                    fanRole: EdgeFanRoleResolver.role(
                        sourceTool: sourceTool,
                        targetTool: targetTool
                    ),
                    fanCount: liveFanCount(for: edge, targetTool: targetTool)
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
