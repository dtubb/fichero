import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowInspector")

/// Inspector panel for workflow editor - shows available blocks to drag onto canvas
struct WorkflowInspector: View {
    @Binding var workflow: Workflow
    let onAddNode: (ToolInfo, CGPoint) -> Void

    @State private var blocksExpanded: Bool = true

    // Tools loaded from API (grouped by category)
    @State private var toolCategories: [CategoryTools] = []
    @State private var isLoadingTools: Bool = false

    @EnvironmentObject var workflowService: WorkflowService

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Blocks Section (collapsible)
                blocksSection

                Spacer()
            }
            .padding()
        }
        .background(Color(.windowBackgroundColor))
        .task {
            await loadTools()
        }
    }

    // MARK: - Data Loading

    private func loadTools() async {
        guard toolCategories.isEmpty && !isLoadingTools else { return }
        isLoadingTools = true
        defer { isLoadingTools = false }

        do {
            let response = try await workflowService.listToolsGrouped()
            toolCategories = response.categories
            let totalTools = response.categories.reduce(0) { $0 + $1.tools.count }
            logger.info("Loaded \(totalTools) tools in \(response.categories.count) categories")
        } catch {
            logger.error("Failed to load tools: \(String(describing: error))")
            // Fall back to empty - UI will show placeholder
        }
    }

    // MARK: - Blocks Section

    private var blocksSection: some View {
        DisclosureGroup(isExpanded: $blocksExpanded) {
            VStack(spacing: 12) {
                if isLoadingTools {
                    ProgressView()
                        .frame(maxWidth: .infinity, minHeight: 60)
                } else if toolCategories.isEmpty {
                    // API unavailable - show error message
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.title2)
                            .foregroundColor(.orange)
                        Text("Could not load tools")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Button("Retry") {
                            Task { await loadTools() }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    .frame(maxWidth: .infinity, minHeight: 100)
                } else {
                    // Show tools from API grouped by category
                    ForEach(toolCategories) { category in
                        toolCategoryView(category)
                    }
                }
            }
            .padding(.top, 8)
        } label: {
            HStack {
                Label("Tools", systemImage: "square.grid.2x2")
                    .font(.headline)
                Spacer()
                if !toolCategories.isEmpty {
                    let totalTools = toolCategories.reduce(0) { $0 + $1.tools.count }
                    Text("\(totalTools)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(.controlBackgroundColor))
                        .cornerRadius(4)
                }
            }
        }
    }

    /// Display tools for a category (from API response)
    @ViewBuilder
    private func toolCategoryView(_ category: CategoryTools) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(category.displayName)
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.leading, 4)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 4) {
                ForEach(category.tools) { tool in
                    ToolBlockView(tool: tool) {
                        // Add node at a smart position
                        onAddNode(tool, nextNodePosition)
                    }
                    .onDrag {
                        // Encode full ToolInfo as JSON for drag-drop
                        if let data = try? JSONEncoder().encode(tool),
                           let json = String(data: data, encoding: .utf8) {
                            return NSItemProvider(object: json as NSString)
                        }
                        return NSItemProvider(object: tool.name as NSString)
                    }
                }
            }
        }
    }

    /// Calculate a smart position for the next node
    private var nextNodePosition: CGPoint {
        if workflow.nodes.isEmpty {
            // First node goes near center-left
            return CGPoint(x: 150, y: 200)
        } else {
            // Find rightmost node and place new node to its right
            let rightmost = workflow.nodes.max(by: { $0.positionX < $1.positionX })!
            return CGPoint(x: rightmost.positionX + 200, y: rightmost.positionY)
        }
    }

}

// MARK: - Tool Block View (for API-loaded tools)

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

// MARK: - Preview

#Preview {
    WorkflowInspector(
        workflow: .constant(Workflow(name: "Test", description: "")),
        onAddNode: { tool, position in
            print("Add node: \(tool.name) at \(position)")
        }
    )
    .frame(width: 280, height: 600)
}
