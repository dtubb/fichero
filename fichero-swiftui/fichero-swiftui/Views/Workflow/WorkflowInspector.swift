import SwiftUI
import OSLog

let workflowInspectorLogger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowInspector")

/// Inspector panel for workflow editor - shows available blocks to drag onto canvas
struct WorkflowInspector: View {
    @Binding var workflow: Workflow
    let onAddNode: (ToolInfo, CGPoint) -> Void

    @State var selectedTab: InspectorTab = .builtin
    @State var blocksExpanded: Bool = true

    // Built-in tools loaded from workflow registry (grouped by category)
    @State var toolCategories: [CategoryTools] = []
    @State var isLoadingTools: Bool = false

    // MCP tools loaded from MCP servers
    @State var mcpTools: [MCPToolInfo] = []
    @State var isLoadingMCPTools: Bool = false
    @State var mcpToolsGrouped: [String: [MCPToolInfo]] = [:]

    @EnvironmentObject var workflowServiceGenerated: WorkflowServiceGenerated
    @EnvironmentObject var mcpService: MCPService
    @EnvironmentObject var appState: AppState

    enum InspectorTab: String, CaseIterable {
        case builtin = "Built-in"
        case mcp = "MCP"
        case agents = "Agents"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Tab picker
            Picker("Tool Source", selection: $selectedTab) {
                ForEach(InspectorTab.allCases, id: \.self) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 12)
            .padding(.bottom, 8)

            Divider()

            // Content based on selected tab
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    switch selectedTab {
                    case .builtin:
                        builtinToolsSection
                    case .mcp:
                        mcpToolsSection
                    case .agents:
                        agentsSection
                    }

                    Spacer()
                }
                .padding()
            }
            .background(Color(.windowBackgroundColor))
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadBuiltinTools()
        }
        .onChange(of: selectedTab) { _, newTab in
            if newTab == .mcp && mcpTools.isEmpty {
                Task {
                    await loadMCPTools()
                }
            }
        }
    }

    // MARK: - Built-in Tools Section

    private var builtinToolsSection: some View {
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
                            Task { await loadBuiltinTools() }
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
                Label("Registry Tools", systemImage: "square.grid.2x2")
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

    // MARK: - Tool Category View (Built-in)

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

}

// ToolBlockView and MCPToolBlockView are in WorkflowToolBlocks.swift

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
