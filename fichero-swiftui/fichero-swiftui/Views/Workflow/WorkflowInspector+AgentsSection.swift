import SwiftUI

extension WorkflowInspector {

    // MARK: - Agents Section

    var agentsSection: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                Label("Agent Nodes", systemImage: "person.2.wave.2")
                    .font(.headline)
                Spacer()
            }

            // Agent types
            VStack(spacing: 8) {
                ForEach(AgentType.allCases, id: \.self) { agentType in
                    AgentNodeBlockView(agentType: agentType) {
                        // Create agent node at smart position
                        let tool = ToolInfo(
                            name: "agent",
                            displayName: agentType.displayName,
                            description: agentType.description,
                            category: "agent",
                            icon: agentType.icon,
                            color: "purple",
                            inputPorts: [
                                PortInfo(
                                    id: "input",
                                    name: "Input",
                                    portType: "input",
                                    dataType: "any",
                                    required: true,
                                    description: "Agent input"
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "output",
                                    name: "Output",
                                    portType: "output",
                                    dataType: "any",
                                    required: false,
                                    description: "Agent output"
                                )
                            ],
                            configSchema: [:],
                            usesLLM: true,
                            supportsBatch: false,
                            supportsStreaming: true,
                            supportsStructuredOutput: true,
                            sortOrder: 0
                        )
                        onAddNode(tool, nextNodePosition)
                    }
                    .onDrag {
                        // Drag as agent tool - use proper JSON encoding
                        let tool = ToolInfo(
                            name: "agent",
                            displayName: agentType.displayName,
                            description: agentType.description,
                            category: "agent",
                            icon: agentType.icon,
                            color: "purple",
                            inputPorts: [
                                PortInfo(
                                    id: "input", name: "Input", portType: "input",
                                    dataType: "any", required: true, description: "Agent input"
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "output", name: "Output", portType: "output",
                                    dataType: "any", required: false, description: "Agent output"
                                )
                            ],
                            configSchema: [:],
                            usesLLM: true,
                            supportsBatch: false,
                            supportsStreaming: true,
                            supportsStructuredOutput: true,
                            sortOrder: 0
                        )
                        if let data = try? JSONEncoder().encode(tool),
                           let json = String(data: data, encoding: .utf8) {
                            return NSItemProvider(object: json as NSString)
                        }
                        assertionFailure("Failed to encode drag payload for agent node")
                        return NSItemProvider()
                    }
                }
            }

            Divider()

            // Info
            VStack(alignment: .leading, spacing: 8) {
                Text("About Agent Nodes")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Text(
                    "Agent nodes use AI to reason and select tools dynamically. " +
                        "They can handle complex multi-step tasks by breaking them down " +
                        "and executing appropriate actions."
                )
                .font(.caption)
                .foregroundColor(.secondary)
            }
            .padding()
            .background(Color.secondary.opacity(0.1))
            .cornerRadius(8)
        }
    }

}
