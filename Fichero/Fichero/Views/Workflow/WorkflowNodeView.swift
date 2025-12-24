import SwiftUI

/// Visual representation of a workflow node with ports
struct WorkflowNodeView: View {
    let node: WorkflowNode
    let isSelected: Bool
    let connectedInputPorts: Set<String>
    let connectedOutputPorts: Set<String>
    let canAcceptDrop: Bool
    let onPortDragStarted: (PortInfo, String) -> Void
    let onPortDragChanged: (CGSize) -> Void  // Translation, not absolute position
    let onPortDragEnded: () -> Void
    let onPortDropReceived: (PortInfo, String) -> Void
    var onInputPortDetach: ((PortInfo, String) -> Void)? = nil  // Detach from connected input

    private let width: CGFloat = 140
    private let height: CGFloat = 100

    var body: some View {
        HStack(spacing: 0) {
            // Input ports (left)
            if !node.inputPorts.isEmpty {
                InputPortsView(
                    ports: node.inputPorts,
                    nodeId: node.id,
                    nodeColor: nodeColor,
                    connectedPortIds: connectedInputPorts,
                    canAcceptDrop: canAcceptDrop,
                    onDropReceived: onPortDropReceived,
                    onDetachDrag: onInputPortDetach
                )
                .frame(width: 20)
            }

            // Node body
            nodeBody

            // Output ports (right)
            if !node.outputPorts.isEmpty {
                OutputPortsView(
                    ports: node.outputPorts,
                    nodeId: node.id,
                    nodeColor: nodeColor,
                    connectedPortIds: connectedOutputPorts,
                    onDragStarted: onPortDragStarted,
                    onDragChanged: onPortDragChanged,
                    onDragEnded: onPortDragEnded
                )
                .frame(width: 20)
            }
        }
    }

    private var nodeBody: some View {
        VStack(spacing: 6) {
            // Icon
            ZStack {
                Circle()
                    .fill(nodeColor)
                    .frame(width: 40, height: 40)

                Image(systemName: iconForTool)
                    .font(.system(size: 18))
                    .foregroundColor(.white)
            }

            // Label
            Text(node.label)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            // Provider/model subtitle
            if let modelName = node.modelName {
                Text(modelName)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(width: width - 40, height: height)
        .padding(.horizontal, 8)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(.windowBackgroundColor))
                .shadow(
                    color: isSelected ? nodeColor.opacity(0.5) : .black.opacity(0.1),
                    radius: isSelected ? 8 : 4
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? nodeColor : .clear, lineWidth: 2)
        )
        .opacity(node.enabled ? 1.0 : 0.5)
    }

    // MARK: - Node Styling

    private var nodeColor: Color {
        Self.colorForTool(node.tool)
    }

    private var iconForTool: String {
        Self.iconForTool(node.tool)
    }

    // MARK: - Static Helpers (reusable by other views)

    static func iconForTool(_ tool: String) -> String {
        switch tool {
        case "files": return "doc.on.doc"
        case "collection": return "folder"
        case "search": return "magnifyingglass"
        case "transcribe": return "text.viewfinder"
        case "describe": return "eye"
        case "analyze": return "doc.text.magnifyingglass"
        case "enhance": return "wand.and.stars"
        case "crop": return "crop"
        case "rotate": return "rotate.right"
        case "segment": return "rectangle.split.3x1"
        case "summarize": return "text.quote"
        case "translate": return "globe"
        case "extract_entities": return "person.text.rectangle"
        case "classify": return "tag"
        case "custom_llm": return "text.bubble"
        case "if": return "arrow.triangle.branch"
        case "switch": return "arrow.triangle.swap"
        case "loop": return "repeat"
        case "filter": return "line.3.horizontal.decrease.circle"
        case "merge": return "arrow.triangle.merge"
        case "to_pdf": return "doc.richtext"
        case "to_word": return "doc.text"
        case "to_excel": return "tablecells"
        case "to_json": return "curlybraces"
        case "save_to_library": return "square.and.arrow.down"
        case "export": return "folder.badge.plus"
        default: return "gearshape"
        }
    }

    static func colorForTool(_ tool: String) -> Color {
        switch tool {
        // Sources (green)
        case "files", "collection", "search":
            return .green
        // Vision (blue)
        case "transcribe", "describe", "analyze":
            return .blue
        // Transform (pink)
        case "enhance", "crop", "rotate", "segment":
            return .pink
        // LLM (purple)
        case "summarize", "translate", "extract_entities", "classify", "custom_llm":
            return .purple
        // Logic (yellow)
        case "if", "switch", "loop", "filter", "merge":
            return .yellow
        // Convert (orange)
        case "to_pdf", "to_word", "to_excel", "to_json":
            return .orange
        // Sink (red)
        case "save_to_library", "export":
            return .red
        default:
            return .gray
        }
    }
}

// MARK: - Preview

#Preview {
    HStack(spacing: 40) {
        WorkflowNodeView(
            node: WorkflowNode(
                tool: "files",
                label: "Input Files",
                inputPorts: [],
                outputPorts: [PortInfo(id: "files", name: "Files", portType: "output", dataType: "files", required: true, description: "")],
                positionX: 0,
                positionY: 0
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
                inputPorts: [PortInfo(id: "input", name: "Files", portType: "input", dataType: "files", required: true, description: "")],
                outputPorts: [PortInfo(id: "text", name: "Text", portType: "output", dataType: "text", required: true, description: "")],
                positionX: 0,
                positionY: 0,
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
    .padding(40)
    .background(Color(.textBackgroundColor))
}
