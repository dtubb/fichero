import SwiftUI

// MARK: - Preview

#Preview {
    struct PreviewWrapper: View {
        @State private var scale: CGFloat = 1.0
        @State private var snapToGrid: Bool = true
        @State private var executionObserver = WorkflowExecutionObserver()

        var body: some View {
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
                            outputPorts: [
                                PortInfo(
                                    id: "files", name: "Files", portType: "output",
                                    dataType: "files", required: true, description: ""
                                )
                            ]
                        ),
                        WorkflowNode(
                            tool: "transcribe",
                            label: "Transcribe",
                            positionX: 350,
                            positionY: 200,
                            inputPorts: [
                                PortInfo(
                                    id: "files", name: "Files", portType: "input",
                                    dataType: "files", required: true, description: ""
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "text", name: "Text", portType: "output",
                                    dataType: "text", required: true, description: ""
                                ),
                                PortInfo(
                                    id: "structured", name: "JSON", portType: "output",
                                    dataType: "json", required: true, description: ""
                                )
                            ]
                        ),
                        WorkflowNode(
                            tool: "to_word",
                            label: "To Word",
                            positionX: 550,
                            positionY: 200,
                            inputPorts: [
                                PortInfo(
                                    id: "content", name: "Content", portType: "input",
                                    dataType: "any", required: true, description: ""
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "file", name: "File", portType: "output",
                                    dataType: "file", required: true, description: ""
                                )
                            ]
                        )
                    ],
                    edges: []
                )),
                scale: $scale,
                snapToGrid: $snapToGrid
            )
            .environment(executionObserver)
            .environmentObject(FeatureManager.shared)
            .frame(width: 800, height: 500)
        }
    }

    return PreviewWrapper()
}
