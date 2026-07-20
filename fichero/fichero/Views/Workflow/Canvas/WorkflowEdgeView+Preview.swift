import SwiftUI

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
