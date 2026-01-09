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
    var onInputPortDetach: ((PortInfo, String) -> Void)?  // Detach from connected input

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
            Text(node.label ?? node.tool)
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

    private static let toolIcons: [String: String] = [
        "files": "doc.on.doc",
        "collection": "folder",
        "search": "magnifyingglass",
        "transcribe": "text.viewfinder",
        "describe": "eye",
        "analyze": "doc.text.magnifyingglass",
        "enhance": "wand.and.stars",
        "crop": "crop",
        "rotate": "rotate.right",
        "segment": "rectangle.split.3x1",
        "summarize": "text.quote",
        "translate": "globe",
        "extract_entities": "person.text.rectangle",
        "classify": "tag",
        "custom_llm": "text.bubble",
        "if": "arrow.triangle.branch",
        "switch": "arrow.triangle.swap",
        "loop": "repeat",
        "filter": "line.3.horizontal.decrease.circle",
        "merge": "arrow.triangle.merge",
        "to_pdf": "doc.richtext",
        "to_word": "doc.text",
        "to_excel": "tablecells",
        "to_json": "curlybraces",
        "save_to_library": "square.and.arrow.down",
        "export": "folder.badge.plus"
    ]

    private static let toolColors: [String: Color] = [
        // Sources (green)
        "files": .green,
        "collection": .green,
        "search": .green,
        // Vision (blue)
        "transcribe": .blue,
        "describe": .blue,
        "analyze": .blue,
        // Transform (pink)
        "enhance": .pink,
        "crop": .pink,
        "rotate": .pink,
        "segment": .pink,
        // LLM (purple)
        "summarize": .purple,
        "translate": .purple,
        "extract_entities": .purple,
        "classify": .purple,
        "custom_llm": .purple,
        // Logic (yellow)
        "if": .yellow,
        "switch": .yellow,
        "loop": .yellow,
        "filter": .yellow,
        "merge": .yellow,
        // Convert (orange)
        "to_pdf": .orange,
        "to_word": .orange,
        "to_excel": .orange,
        "to_json": .orange,
        // Sink (red)
        "save_to_library": .red,
        "export": .red
    ]

    static func iconForTool(_ tool: String) -> String {
        return toolIcons[tool] ?? "gearshape"
    }

    static func colorForTool(_ tool: String) -> Color {
        return toolColors[tool] ?? .gray
    }
}

// MARK: - Preview

#Preview {
    HStack(spacing: 40) {
        WorkflowNodeView(
            node: WorkflowNode(
                tool: "files",
                label: "Input Files",
                positionX: 0,
                positionY: 0,
                inputPorts: [],
                outputPorts: [PortInfo(id: "files", name: "Files", portType: "output", dataType: "files", required: true, description: "")]
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
                inputPorts: [PortInfo(id: "input", name: "Files", portType: "input", dataType: "files", required: true, description: "")],
                outputPorts: [PortInfo(id: "text", name: "Text", portType: "output", dataType: "text", required: true, description: "")],
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
