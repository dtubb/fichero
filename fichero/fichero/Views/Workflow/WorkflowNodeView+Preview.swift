import SwiftUI

#Preview {
    VStack(spacing: 40) {
        HStack(spacing: 40) {
            WorkflowNodeView(
                node: WorkflowNode(
                    tool: "files",
                    label: "Input Files",
                    positionX: 0,
                    positionY: 0,
                    inputPorts: [],
                    outputPorts: [
                        PortInfo(
                            id: "files",
                            name: "Files",
                            portType: "output",
                            dataType: "files",
                            required: true,
                            description: ""
                        )
                    ]
                ),
                isSelected: false,
                connectedInputPorts: [],
                connectedOutputPorts: [],
                canAcceptDrop: false,
                onPortDragStarted: { _, _ in },
                onPortDragChanged: { _ in },
                onPortDragEnded: {},
                onPortDropReceived: { _, _ in }
            )

            WorkflowNodeView(
                node: WorkflowNode(
                    tool: "transcribe",
                    label: "Transcribe",
                    positionX: 0,
                    positionY: 0,
                    inputPorts: [
                        PortInfo(
                            id: "input",
                            name: "Files",
                            portType: "input",
                            dataType: "files",
                            required: true,
                            description: ""
                        )
                    ],
                    outputPorts: [
                        PortInfo(
                            id: "text",
                            name: "Text",
                            portType: "output",
                            dataType: "text",
                            required: true,
                            description: ""
                        )
                    ],
                    modelName: "gpt-4o"
                ),
                isSelected: true,
                connectedInputPorts: ["input"],
                connectedOutputPorts: [],
                canAcceptDrop: false,
                onPortDragStarted: { _, _ in },
                onPortDragChanged: { _ in },
                onPortDragEnded: {},
                onPortDropReceived: { _, _ in }
            )
        }

        HStack(spacing: 40) {
            WorkflowNodeView(
                node: WorkflowNode(
                    tool: "transcribe",
                    label: "Transcribe",
                    positionX: 0,
                    positionY: 0,
                    inputPorts: [
                        PortInfo(
                            id: "input",
                            name: "Files",
                            portType: "input",
                            dataType: "files",
                            required: true,
                            description: ""
                        )
                    ],
                    outputPorts: [
                        PortInfo(
                            id: "text",
                            name: "Text",
                            portType: "output",
                            dataType: "text",
                            required: true,
                            description: ""
                        )
                    ]
                ),
                isSelected: false,
                connectedInputPorts: ["input"],
                connectedOutputPorts: [],
                canAcceptDrop: false,
                onPortDragStarted: { _, _ in },
                onPortDragChanged: { _ in },
                onPortDragEnded: {},
                onPortDropReceived: { _, _ in },
                executionState: NodeExecutionState(
                    nodeId: "test",
                    status: .parallelRunning,
                    progress: 0.5,
                    fileTotal: 10,
                    successCount: 5
                )
            )

            WorkflowNodeView(
                node: WorkflowNode(
                    tool: "transcribe",
                    label: "Transcribe",
                    positionX: 0,
                    positionY: 0,
                    inputPorts: [
                        PortInfo(
                            id: "input",
                            name: "Files",
                            portType: "input",
                            dataType: "files",
                            required: true,
                            description: ""
                        )
                    ],
                    outputPorts: [
                        PortInfo(
                            id: "text",
                            name: "Text",
                            portType: "output",
                            dataType: "text",
                            required: true,
                            description: ""
                        )
                    ]
                ),
                isSelected: false,
                connectedInputPorts: ["input"],
                connectedOutputPorts: [],
                canAcceptDrop: false,
                onPortDragStarted: { _, _ in },
                onPortDragChanged: { _ in },
                onPortDragEnded: {},
                onPortDropReceived: { _, _ in },
                executionState: NodeExecutionState(
                    nodeId: "test",
                    status: .completed,
                    progress: 1.0,
                    fileTotal: 10,
                    successCount: 8,
                    errorCount: 2
                )
            )
        }
    }
    .padding(40)
    .background(Color(.textBackgroundColor))
}
