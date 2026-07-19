import SwiftUI

// MARK: - Canvas Content

extension WorkflowCanvasView {
    @ViewBuilder
    var canvasContent: some View {
        ZStack {
            // Edges layer (behind nodes)
            edgesLayer

            // Edge being dragged
            if let dragged = draggedEdge {
                DraggingWorkflowEdgeView(startPoint: dragged.startPoint, currentPoint: dragged.currentPoint)
            }

            // Nodes layer
            nodesLayer
        }
    }
}
