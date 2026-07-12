import OSLog
import SwiftUI

let workflowInspectorLogger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowInspector")

/// Inspector panel for workflow editor - shows available blocks to drag onto canvas
struct WorkflowInspector: View {
    @Binding var workflow: Workflow
    let onAddNode: (ToolInfo, CGPoint) -> Void

    @State var selectedTab: WorkflowInspectorTab = .builtin

    // Built-in tools loaded from workflow registry (grouped by category)
    @State var toolCategories: [CategoryTools] = []
    @State var isLoadingTools: Bool = false

    // MCP tools loaded from MCP servers
    @State var mcpTools: [MCPToolInfo] = []
    @State var isLoadingMCPTools: Bool = false
    @State var mcpToolsGrouped: [String: [MCPToolInfo]] = [:]

    @Environment(WorkflowServiceGenerated.self) var workflowServiceGenerated
    @Environment(MCPService.self) var mcpService
    @Environment(AppState.self) var appState
    @ObservedObject var featureManager = FeatureManager.shared

    /// Workflow tool-palette tabs. Renamed from the old private `InspectorTab`
    /// to avoid colliding with the Library inspector's `InspectorTab` and to
    /// adopt the shared `SurfaceTab` chrome (#3530).
    enum WorkflowInspectorTab: String, Hashable, CaseIterable, Identifiable, SurfaceTab {
        case builtin = "Built-in"
        case mcp = "MCP"
        case agents = "Agents"

        var id: String { rawValue }
        var title: String { rawValue }

        var icon: String {
            switch self {
            case .builtin: return "square.grid.2x2"
            case .mcp: return "externaldrive.connected.to.line.below"
            case .agents: return "person.2"
            }
        }

        var help: String {
            switch self {
            case .builtin: return "Built-in tools — the workflow's native tool palette"
            case .mcp: return "MCP tools — tools from connected Model Context Protocol servers"
            case .agents: return "Agents — sub-agent tools available to the workflow"
            }
        }
    }

    private var availableTabs: [WorkflowInspectorTab] {
        var tabs: [WorkflowInspectorTab] = [.builtin]
        if featureManager.isWorkflowToolsMCPEnabled {
            tabs.append(.mcp)
        }
        if featureManager.isWorkflowToolsAgentsEnabled {
            tabs.append(.agents)
        }
        return tabs
    }

    private var visibleBuiltinCategories: [CategoryTools] {
        toolCategories.compactMap(filteredCategoryIfEnabled)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Shared top-tab chrome (#3530) — the same SurfaceTabBar icon row the
            // Reader and Document Inspector use.
            SurfaceTabBar(
                tabs: availableTabs,
                selection: $selectedTab,
                accessibilityID: "workflowInspectorTabBar"
            )

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
        .onAppear {
            if !availableTabs.contains(selectedTab) {
                selectedTab = .builtin
            }
        }
    }

    // MARK: - Built-in Tools Section

    private var builtinToolsSection: some View {
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
            } else if visibleBuiltinCategories.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "lock.shield")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    Text("No built-in tools available")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("External workflow categories may still be gated.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 100)
            } else {
                if hiddenBuiltinToolCount > 0 {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "eye.slash")
                            .foregroundColor(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(hiddenBuiltinToolCount) tool\(hiddenBuiltinToolCount == 1 ? "" : "s") hidden by feature flags")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("Only separately gated external workflow categories are hidden.")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                    }
                    .padding(8)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.secondary.opacity(0.08))
                    )
                }
                // Show tools from API grouped by category
                ForEach(visibleBuiltinCategories) { category in
                    toolCategoryView(category)
                }
            }
        }
        .padding(.top, 8)
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
                        do {
                            let data = try JSONEncoder().encode(tool)
                            guard let json = String(data: data, encoding: .utf8) else {
                                assertionFailure("Failed to encode UTF-8 drag payload for tool \(tool.name)")
                                return NSItemProvider()
                            }
                            return NSItemProvider(object: json as NSString)
                        } catch {
                            assertionFailure("Failed to encode drag payload for tool \(tool.name): \(error)")
                            return NSItemProvider()
                        }
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
