import SwiftUI

// MARK: - Tool Block View (for Built-in Tools)

struct ToolBlockView: View {
    let tool: ToolInfo
    var onTap: (() -> Void)? = nil

    @State private var isHovering: Bool = false

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: tool.icon)
                .font(.body)
                .foregroundColor(toolColor)

            Text(tool.displayName)
                .font(.caption2)
                .lineLimit(1)
                .foregroundColor(.primary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(isHovering ? Color(.selectedControlColor) : Color(.controlBackgroundColor))
        .cornerRadius(6)
        .onHover { hovering in
            isHovering = hovering
        }
        .onTapGesture {
            onTap?()
        }
        .help(tool.description)
    }

    /// Convert color string from API to SwiftUI Color
    private var toolColor: Color {
        switch tool.color.lowercased() {
        case "blue": return .blue
        case "green": return .green
        case "orange": return .orange
        case "purple": return .purple
        case "pink": return .pink
        case "red": return .red
        case "yellow": return .yellow
        case "teal": return .teal
        case "indigo": return .indigo
        case "cyan": return .cyan
        case "mint": return .mint
        case "brown": return .brown
        case "gray", "grey": return .gray
        default: return .accentColor
        }
    }
}

// MARK: - MCP Tool Block View (for MCP Tools)

struct MCPToolBlockView: View {
    let tool: MCPToolInfo

    @State private var isHovering: Bool = false

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: "cube.box")
                .font(.body)
                .foregroundColor(.accentColor)

            Text(tool.name)
                .font(.caption2)
                .lineLimit(1)
                .foregroundColor(.primary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(isHovering ? Color(.selectedControlColor) : Color(.controlBackgroundColor))
        .cornerRadius(6)
        .onHover { hovering in
            isHovering = hovering
        }
        .help(tool.description)
    }
}

// MARK: - Preview

#Preview("Tool Block") {
    ToolBlockView(
        tool: ToolInfo(
            name: "test",
            displayName: "Test Tool",
            description: "A test tool",
            category: "test",
            icon: "gear",
            color: "blue",
            inputPorts: [],
            outputPorts: [],
            configSchema: [:],
            usesLLM: false,
            supportsBatch: false,
            supportsStreaming: false,
            supportsStructuredOutput: false,
            sortOrder: 0
        )
    )
    .frame(width: 100)
}
