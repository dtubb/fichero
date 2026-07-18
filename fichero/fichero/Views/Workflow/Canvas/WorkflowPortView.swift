import SwiftUI

/// Visual representation of a node port (input or output connection point)
struct WorkflowPortView: View {
    let port: PortInfo
    let isConnected: Bool
    let nodeColor: Color
    let showDataTypeIcon: Bool

    @State private var isHovered: Bool = false

    /// Port diameter
    private let portSize: CGFloat = 12

    var body: some View {
        ZStack {
            // Outer ring (shows on hover or when connected)
            Circle()
                .stroke(portColor.opacity(isHovered || isConnected ? 0.5 : 0), lineWidth: 2)
                .frame(width: portSize + 6, height: portSize + 6)

            // Main port circle
            Circle()
                .fill(isConnected ? portColor : Color(.controlBackgroundColor))
                .frame(width: portSize, height: portSize)

            // Data type icon is hidden in simple canvas mode.
            if showDataTypeIcon {
                Image(systemName: iconForDataType(port.dataType))
                    .font(.system(size: 7, weight: .semibold))
                    .foregroundColor(isConnected ? .white : portColor)
            }

            // Border
            Circle()
                .stroke(portColor, lineWidth: 1.5)
                .frame(width: portSize, height: portSize)
        }
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovered = hovering
            }
        }
        .help(portTooltip)
        #if !os(macOS)
        // The 12pt port dot is far below the 44pt touch minimum. Keep the small
        // visual but expand the tappable area to 44pt so a finger can grab the
        // connection point (#2806). Mac keeps the precise mouse-sized target.
        .frame(width: 44, height: 44)
        .contentShape(Circle())
        #endif
    }

    private var portColor: Color {
        colorForDataType(port.dataType)
    }

    private var portTooltip: String {
        var tooltip = "\(port.name) (\(port.dataType))"
        if !port.description.isEmpty {
            tooltip += "\n\(port.description)"
        }
        if port.isInput && !port.required {
            tooltip += "\n(Optional)"
        }
        return tooltip
    }

    /// Color based on data type for visual distinction
    private func colorForDataType(_ dataType: String) -> Color {
        switch dataType {
        case "files", "file":
            return .green
        case "text":
            return .blue
        case "json":
            return .orange
        case "array":
            return .purple
        case "image":
            return .pink
        case "number":
            return .yellow
        case "boolean":
            return .red
        case "any":
            return nodeColor
        default:
            return .gray
        }
    }

    /// SF Symbol icon based on data type
    private func iconForDataType(_ dataType: String) -> String {
        switch dataType {
        case "files", "file":
            return "folder.fill"
        case "text":
            return "text.alignleft"
        case "json":
            return "curlybraces"
        case "array":
            return "list.bullet"
        case "image":
            return "photo"
        case "number":
            return "number"
        case "boolean":
            return "switch.2"
        case "any":
            return "circle"
        default:
            return "circle"
        }
    }
}

/// Draggable port for creating new edges
struct DraggableWorkflowPortView: View {
    let port: PortInfo
    let nodeId: String
    let nodeColor: Color
    let isConnected: Bool
    let showDataTypeIcon: Bool
    let onDragStarted: (PortInfo, String) -> Void
    let onDragChanged: (CGSize) -> Void  // Report drag translation
    let onDragEnded: () -> Void

    @State private var isDragging: Bool = false

    var body: some View {
        WorkflowPortView(
            port: port,
            isConnected: isConnected,
            nodeColor: nodeColor,
            showDataTypeIcon: showDataTypeIcon
        )
        .frame(width: 18, height: 18)
        .contentShape(Circle())
        .highPriorityGesture(
            DragGesture(minimumDistance: 3)
                .onChanged { value in
                    if !isDragging {
                        isDragging = true
                        onDragStarted(port, nodeId)
                    }
                    onDragChanged(value.translation)
                }
                .onEnded { _ in
                    isDragging = false
                    onDragEnded()
                }
        )
        .opacity(isDragging ? 0.5 : 1.0)
    }
}

/// Input port that can receive edge connections and be dragged to detach
struct DroppableWorkflowPortView: View {
    let port: PortInfo
    let nodeId: String
    let nodeColor: Color
    let isConnected: Bool
    let showDataTypeIcon: Bool
    let canAcceptDrop: Bool
    let onDropReceived: (PortInfo, String) -> Void
    var onDetachDrag: ((PortInfo, String) -> Void)?  // Called when dragging from connected input

    @State private var isHovered: Bool = false
    @State private var isDragging: Bool = false

    var body: some View {
        WorkflowPortView(
            port: port,
            isConnected: isConnected,
            nodeColor: nodeColor,
            showDataTypeIcon: showDataTypeIcon
        )
        .frame(width: 18, height: 18)
        .contentShape(Circle())
        // Show hover state when edge drag is in progress
        .scaleEffect(isHovered && canAcceptDrop ? 1.2 : 1.0)
        .animation(.spring(response: 0.2), value: isHovered && canAcceptDrop)
        .onHover { hovering in
            isHovered = hovering
        }
        // Allow dragging from connected input to detach and reconnect
        .gesture(
            isConnected ?
                DragGesture(minimumDistance: 5)
                .onChanged { _ in
                    if !isDragging {
                        isDragging = true
                        onDetachDrag?(port, nodeId)
                    }
                }
                .onEnded { _ in
                    isDragging = false
                }
                : nil
        )
        .opacity(isDragging ? 0.5 : 1.0)
    }
}

/// Container for input ports (left side of node)
struct InputPortsView: View {
    let ports: [PortInfo]
    let nodeId: String
    let nodeColor: Color
    let showPortDetails: Bool
    let connectedPortIds: Set<String>
    let canAcceptDrop: Bool
    let onDropReceived: (PortInfo, String) -> Void
    var onDetachDrag: ((PortInfo, String) -> Void)?

    private var visiblePorts: [PortInfo] {
        guard !showPortDetails else { return ports }
        guard !ports.isEmpty else { return [] }
        return [ports[0]]
    }

    var body: some View {
        VStack(spacing: 8) {
            ForEach(visiblePorts) { port in
                HStack(spacing: 4) {
                    DroppableWorkflowPortView(
                        port: port,
                        nodeId: nodeId,
                        nodeColor: nodeColor,
                        isConnected: connectedPortIds.contains(port.id),
                        showDataTypeIcon: showPortDetails,
                        canAcceptDrop: canAcceptDrop,
                        onDropReceived: onDropReceived,
                        onDetachDrag: onDetachDrag
                    )

                    if showPortDetails {
                        Text(port.name)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
            }
        }
    }
}

/// Container for output ports (right side of node)
struct OutputPortsView: View {
    let ports: [PortInfo]
    let nodeId: String
    let nodeColor: Color
    let showPortDetails: Bool
    let connectedPortIds: Set<String>
    let onDragStarted: (PortInfo, String) -> Void
    let onDragChanged: (CGSize) -> Void  // Changed to CGSize for translation
    let onDragEnded: () -> Void

    private var visiblePorts: [PortInfo] {
        guard !showPortDetails else { return ports }
        guard !ports.isEmpty else { return [] }
        return [ports[0]]
    }

    var body: some View {
        VStack(spacing: 8) {
            ForEach(visiblePorts) { port in
                HStack(spacing: 4) {
                    if showPortDetails {
                        Text(port.name)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }

                    DraggableWorkflowPortView(
                        port: port,
                        nodeId: nodeId,
                        nodeColor: nodeColor,
                        isConnected: connectedPortIds.contains(port.id),
                        showDataTypeIcon: showPortDetails,
                        onDragStarted: onDragStarted,
                        onDragChanged: onDragChanged,
                        onDragEnded: onDragEnded
                    )
                }
            }
        }
    }
}

// MARK: - Preview

#Preview("Port Types") {
    HStack(spacing: 20) {
        VStack(spacing: 8) {
            Text("Input Ports").font(.caption).foregroundColor(.secondary)
            WorkflowPortView(
                port: PortInfo(
                    id: "files", name: "Files", portType: "input",
                    dataType: "files", required: true, description: "Input files"
                ),
                isConnected: false,
                nodeColor: .blue,
                showDataTypeIcon: true
            )
            WorkflowPortView(
                port: PortInfo(
                    id: "text", name: "Text", portType: "input",
                    dataType: "text", required: true, description: ""
                ),
                isConnected: true,
                nodeColor: .blue,
                showDataTypeIcon: true
            )
            WorkflowPortView(
                port: PortInfo(
                    id: "json", name: "Data", portType: "input",
                    dataType: "json", required: false, description: ""
                ),
                isConnected: false,
                nodeColor: .purple,
                showDataTypeIcon: true
            )
        }

        VStack(spacing: 8) {
            Text("Output Ports").font(.caption).foregroundColor(.secondary)
            WorkflowPortView(
                port: PortInfo(
                    id: "output", name: "Output", portType: "output",
                    dataType: "text", required: true, description: ""
                ),
                isConnected: true,
                nodeColor: .green,
                showDataTypeIcon: true
            )
            WorkflowPortView(
                port: PortInfo(
                    id: "any", name: "Any", portType: "output",
                    dataType: "any", required: true, description: ""
                ),
                isConnected: false,
                nodeColor: .orange,
                showDataTypeIcon: true
            )
        }
    }
    .padding()
    .background(Color(.windowBackgroundColor))
}
