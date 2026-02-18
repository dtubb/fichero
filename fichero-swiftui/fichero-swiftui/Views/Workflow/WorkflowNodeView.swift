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
    var executionState: NodeExecutionState?  // Optional execution state for progress display

    private let width: CGFloat = 140
    private let height: CGFloat = 100

    var body: some View {
        ZStack(alignment: .topTrailing) {
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

            // Progress badge overlay
            if let state = executionState {
                NodeProgressBadge(state: state)
                    .offset(x: -8, y: -8)
            }
        }
    }

    private var nodeBody: some View {
        VStack(spacing: 6) {
            // Icon with status indicator
            ZStack {
                // Pulsing animation when running
                if isRunning {
                    Circle()
                        .fill(nodeColor.opacity(0.3))
                        .frame(width: 50, height: 50)
                        .scaleEffect(pulseScale)
                        .animation(
                            .easeInOut(duration: 0.8).repeatForever(autoreverses: true),
                            value: pulseScale
                        )
                        .onAppear { pulseScale = 1.2 }
                }

                Circle()
                    .fill(iconBackgroundColor)
                    .frame(width: 40, height: 40)

                Image(systemName: statusIcon)
                    .font(.system(size: 18))
                    .foregroundColor(.white)
            }

            // Label
            Text(node.label ?? node.tool)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            // Provider/model subtitle or progress
            if let progress = executionState?.progressText {
                Text(progress)
                    .font(.caption2)
                    .foregroundColor(nodeColor)
                    .fontWeight(.medium)
            } else if let subtitle = nodeSubtitle {
                Text(subtitle)
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
                    color: shadowColor,
                    radius: isSelected ? 8 : 4
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(borderColor, lineWidth: 2)
        )
        .opacity(node.enabled ? 1.0 : 0.5)
    }

    @State private var pulseScale: CGFloat = 1.0

    /// Whether node is currently running
    private var isRunning: Bool {
        guard let state = executionState else { return false }
        return state.status == .running || state.status == .parallelRunning
    }

    /// Subtitle showing model/engine configuration
    private var nodeSubtitle: String? {
        // Check for vision_mode config (transcribe, describe tools)
        if let visionMode = node.config?["vision_mode"]?.stringValue {
            if visionMode == "apple" {
                return "Apple Vision"
            }
            // For "llm" mode, fall through to show model name
        }
        // Show model name if set
        return node.modelName
    }

    /// Background color for icon based on status
    private var iconBackgroundColor: Color {
        guard let state = executionState else { return nodeColor }
        switch state.status {
        case .completed:
            return state.errorCount > 0 ? .orange : .green
        case .failed:
            return .red
        case .running, .parallelRunning:
            return nodeColor
        case .idle:
            return nodeColor
        }
    }

    /// Icon to show based on status
    private var statusIcon: String {
        guard let state = executionState else { return iconForTool }
        switch state.status {
        case .completed:
            return state.errorCount > 0 ? "exclamationmark.triangle.fill" : "checkmark"
        case .failed:
            return "xmark"
        case .running, .parallelRunning:
            return iconForTool
        case .idle:
            return iconForTool
        }
    }

    /// Shadow color based on status
    private var shadowColor: Color {
        if isSelected {
            return nodeColor.opacity(0.5)
        }
        guard let state = executionState else { return .black.opacity(0.1) }
        switch state.status {
        case .running, .parallelRunning:
            return nodeColor.opacity(0.5)
        case .completed:
            return state.errorCount > 0 ? .orange.opacity(0.3) : .green.opacity(0.3)
        case .failed:
            return .red.opacity(0.3)
        case .idle:
            return .black.opacity(0.1)
        }
    }

    /// Border color based on selection and status
    private var borderColor: Color {
        if isSelected {
            return nodeColor
        }
        guard let state = executionState else { return .clear }
        switch state.status {
        case .running, .parallelRunning:
            return nodeColor.opacity(0.5)
        case .completed:
            return state.errorCount > 0 ? .orange.opacity(0.5) : .green.opacity(0.5)
        case .failed:
            return .red.opacity(0.5)
        case .idle:
            return .clear
        }
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

// MARK: - Progress Badge

/// Badge showing parallel processing progress on a node
struct NodeProgressBadge: View {
    let state: NodeExecutionState

    var body: some View {
        HStack(spacing: 2) {
            // Progress or status indicator
            if state.isParallelProcessing {
                // Show file progress
                Text("\(state.successCount + state.errorCount)/\(state.fileTotal)")
                    .font(.system(size: 10, weight: .bold, design: .rounded))
            } else if state.status == .running {
                // Spinning indicator for non-parallel running
                ProgressView()
                    .scaleEffect(0.5)
                    .frame(width: 12, height: 12)
            } else if state.status == .completed {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
            } else if state.status == .failed {
                Image(systemName: "xmark")
                    .font(.system(size: 10, weight: .bold))
            } else {
                EmptyView()
            }

            // Error indicator
            if state.errorCount > 0 {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 8))
                    .foregroundColor(.orange)
            }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(badgeBackground)
        .foregroundColor(badgeForeground)
        .clipShape(Capsule())
        .shadow(color: .black.opacity(0.2), radius: 2, x: 0, y: 1)
    }

    private var badgeBackground: Color {
        switch state.status {
        case .running, .parallelRunning:
            return .blue
        case .completed:
            return state.errorCount > 0 ? .orange : .green
        case .failed:
            return .red
        case .idle:
            return .gray
        }
    }

    private var badgeForeground: Color {
        .white
    }
}

// MARK: - Preview

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

        // Preview with execution states
        HStack(spacing: 40) {
            // Parallel running
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

            // Completed with errors
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
