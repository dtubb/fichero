import SwiftUI

/// Input mappings configuration for workflow nodes
struct NodeInputMappings: View {
    @Binding var node: WorkflowNode

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Input Mappings")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.secondary)

            ForEach(node.inputPorts, id: \.id) { port in
                HStack(spacing: 8) {
                    // Port name label
                    HStack(spacing: 4) {
                        Circle()
                            .fill(colorForDataType(port.dataType))
                            .frame(width: 8, height: 8)
                        Text(port.name)
                            .font(.caption)
                            .frame(width: 60, alignment: .leading)
                    }

                    // Source path field
                    TextField(
                        "$.nodes.<id>.<key>",
                        text: bindingForMapping(portId: port.id)
                    )
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
                    .help("Path expression to data source (e.g., $.nodes.files_abc.files)")
                }
            }

            Text("Use path expressions like $.nodes.<nodeId>.<outputKey>")
                .font(.caption2)
                .foregroundColor(.secondary)
                .italic()
        }
    }

    private func colorForDataType(_ dataType: String) -> Color {
        switch dataType {
        case "files", "file": return .green
        case "text": return .blue
        case "json": return .orange
        case "array": return .purple
        case "image": return .pink
        case "number": return .yellow
        case "boolean": return .red
        case "any": return .gray
        default: return .gray
        }
    }

    private func bindingForMapping(portId: String) -> Binding<String> {
        Binding(
            get: {
                node.inputMappings.first(where: { $0.portId == portId })?.sourcePath ?? ""
            },
            set: { newValue in
                // Update or add mapping
                if let index = node.inputMappings.firstIndex(where: { $0.portId == portId }) {
                    if newValue.isEmpty {
                        // Remove mapping if empty
                        node.inputMappings.remove(at: index)
                    } else {
                        // Update existing
                        node.inputMappings[index] = InputMapping(
                            portId: portId,
                            sourcePath: newValue,
                            transform: node.inputMappings[index].transform
                        )
                    }
                } else if !newValue.isEmpty {
                    // Add new mapping
                    node.inputMappings.append(InputMapping(
                        portId: portId,
                        sourcePath: newValue,
                        transform: nil
                    ))
                }
            }
        )
    }
}
