import SwiftUI

// MARK: - Tool Block View (for Built-in Tools)

struct ToolBlockView: View {
    let tool: ToolInfo
    var onTap: (() -> Void)?

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

            if !tool.tested {
                untestedBadge
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(isHovering ? Color(platformColor: .platformSelectedControl) : Color(.controlBackgroundColor))
        .cornerRadius(6)
        .onHover { hovering in
            isHovering = hovering
        }
        .onTapGesture {
            onTap?()
        }
        .help(
            tool.tested
                ? tool.description
                : "\(tool.description)\n\nUntested — this tool has not been validated end-to-end."
        )
    }

    /// Small "Untested" tag shown on tools that haven't been validated end-to-end.
    private var untestedBadge: some View {
        Label("Untested", systemImage: "exclamationmark.triangle")
            .font(.caption2)
            .labelStyle(.titleAndIcon)
            .foregroundColor(.secondary)
            .lineLimit(1)
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
        .background(isHovering ? Color(platformColor: .platformSelectedControl) : Color(.controlBackgroundColor))
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
