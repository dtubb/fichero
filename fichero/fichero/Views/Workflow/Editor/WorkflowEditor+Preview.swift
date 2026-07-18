import SwiftUI

private struct WorkflowEditorPreviewWrapper: View {
    @State private var workflow = Workflow(name: "Test Workflow", description: "A test workflow")

    var body: some View {
        NavigationSplitView {
            Text("Sidebar")
                .frame(width: 200)
        } content: {
            WorkflowEditor(
                workflow: nil,
                editingWorkflow: $workflow
            )
        } detail: {
            WorkflowInspector(
                workflow: $workflow,
                onAddNode: { tool, position in
                    let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
                    workflow.nodes.append(newNode)
                }
            )
            .frame(width: 280)
        }
    }
}

#Preview {
    WorkflowEditorPreviewWrapper()
        .frame(width: 1000, height: 600)
}
