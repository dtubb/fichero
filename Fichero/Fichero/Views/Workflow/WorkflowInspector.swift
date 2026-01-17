import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowInspector")

/// Inspector panel for workflow editor - shows available blocks to drag onto canvas
struct WorkflowInspector: View {
    @Binding var workflow: Workflow
    let onAddNode: (ToolInfo, CGPoint) -> Void

    @State private var selectedTab: InspectorTab = .builtin
    @State private var blocksExpanded: Bool = true

    // Built-in tools loaded from workflow registry (grouped by category)
    @State private var toolCategories: [CategoryTools] = []
    @State private var isLoadingTools: Bool = false

    // MCP tools loaded from MCP servers
    @State private var mcpTools: [MCPToolInfo] = []
    @State private var isLoadingMCPTools: Bool = false
    @State private var mcpToolsGrouped: [String: [MCPToolInfo]] = [:]

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

    // MARK: - MCP Tools Section

    private var mcpToolsSection: some View {
        VStack(spacing: 16) {
            // Header with load button
            HStack {
                Label("MCP Tools", systemImage: "server.rack")
                    .font(.headline)
                Spacer()
                Button(action: { Task { await loadIntoRegistry() } }) {
                    HStack(spacing: 4) {
                        Image(systemName: "square.and.arrow.down")
                        Text("Load into Registry")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(mcpTools.isEmpty)
                .help("Make MCP tools available for drag and drop")
            }

            if isLoadingMCPTools {
                ProgressView()
                    .frame(maxWidth: .infinity, minHeight: 100)
            } else if mcpTools.isEmpty {
                // No MCP tools available
                VStack(spacing: 12) {
                    Image(systemName: "server.rack")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("No MCP Tools")
                        .font(.headline)
                    Text("Configure MCP servers to load tools")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Open MCP Servers") {
                        appState.showMCPServers = true
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
            } else {
                // Show MCP tools grouped by server
                ForEach(Array(mcpToolsGrouped.keys.sorted()), id: \.self) { serverName in
                    if let tools = mcpToolsGrouped[serverName] {
                        mcpServerToolsView(serverName: serverName, tools: tools)
                    }
                }
            }
        }
    }

    // MARK: - Agents Section

    private var agentsSection: some View {
        VStack(spacing: 16) {
            // Header
            HStack {
                Label("Agent Nodes", systemImage: "person.2.wave.2")
                    .font(.headline)
                Spacer()
            }

            // Agent types
            VStack(spacing: 8) {
                ForEach(AgentType.allCases, id: \.self) { agentType in
                    AgentNodeBlockView(agentType: agentType) {
                        // Create agent node at smart position
                        let tool = ToolInfo(
                            name: "agent",
                            displayName: agentType.displayName,
                            description: agentType.description,
                            category: "agent",
                            icon: agentType.icon,
                            color: "purple",
                            inputPorts: [
                                PortInfo(
                                    id: "input",
                                    name: "Input",
                                    portType: "input",
                                    dataType: "any",
                                    required: true,
                                    description: "Agent input"
                                )
                            ],
                            outputPorts: [
                                PortInfo(
                                    id: "output",
                                    name: "Output",
                                    portType: "output",
                                    dataType: "any",
                                    required: false,
                                    description: "Agent output"
                                )
                            ],
                            configSchema: [:],
                            usesLLM: true,
                            supportsBatch: false,
                            supportsStreaming: true,
                            supportsStructuredOutput: true,
                            sortOrder: 0
                        )
                        onAddNode(tool, nextNodePosition)
                    }
                    .onDrag {
                        // Drag as agent tool - use proper JSON encoding
                        let tool = ToolInfo(
                            name: "agent",
                            displayName: agentType.displayName,
                            description: agentType.description,
                            category: "agent",
                            icon: agentType.icon,
                            color: "purple",
                            inputPorts: [
                                PortInfo(id: "input", name: "Input", portType: "input", dataType: "any", required: true, description: "Agent input")
                            ],
                            outputPorts: [
                                PortInfo(id: "output", name: "Output", portType: "output", dataType: "any", required: false, description: "Agent output")
                            ],
                            configSchema: [:],
                            usesLLM: true,
                            supportsBatch: false,
                            supportsStreaming: true,
                            supportsStructuredOutput: true,
                            sortOrder: 0
                        )
                        if let data = try? JSONEncoder().encode(tool),
                           let json = String(data: data, encoding: .utf8) {
                            return NSItemProvider(object: json as NSString)
                        }
                        return NSItemProvider(object: "agent" as NSString)
                    }
                }
            }

            Divider()

            // Info
            VStack(alignment: .leading, spacing: 8) {
                Text("About Agent Nodes")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Text("Agent nodes use AI to reason and select tools dynamically. They can handle complex multi-step tasks by breaking them down and executing appropriate actions.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .padding()
            .background(Color.secondary.opacity(0.1))
            .cornerRadius(8)
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

    // MARK: - MCP Server Tools View

    @ViewBuilder
    private func mcpServerToolsView(serverName: String, tools: [MCPToolInfo]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: "server.rack")
                    .font(.caption)
                    .foregroundColor(.accentColor)
                Text(serverName)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Spacer()
                Text("\(tools.count)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                    .background(Color(.controlBackgroundColor))
                    .cornerRadius(3)
            }
            .padding(.leading, 4)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 4) {
                ForEach(tools) { tool in
                    MCPToolBlockView(tool: tool)
                }
            }
        }
    }

    // MARK: - Data Loading

    private func loadBuiltinTools() async {
        guard toolCategories.isEmpty && !isLoadingTools else { return }
        isLoadingTools = true
        defer { isLoadingTools = false }

        do {
            let response = try await workflowServiceGenerated.listToolsGrouped()
            toolCategories = response.categories
            let totalTools = response.categories.reduce(0) { $0 + $1.tools.count }
            logger.info("Loaded \(totalTools) built-in tools in \(response.categories.count) categories")
        } catch {
            logger.error("Failed to load built-in tools: \(String(describing: error))")
            // Fall back to empty - UI will show placeholder
        }
    }

    private func loadMCPTools() async {
        isLoadingMCPTools = true
        defer { isLoadingMCPTools = false }

        do {
            let response = try await mcpService.getAllTools()
            mcpTools = response.tools

            // Group by server
            mcpToolsGrouped = Dictionary(grouping: response.tools) { $0.serverName }

            logger.info("Loaded \(response.tools.count) MCP tools from \(mcpToolsGrouped.keys.count) servers")
        } catch {
            logger.error("Failed to load MCP tools: \(String(describing: error))")
        }
    }

    private func loadIntoRegistry() async {
        do {
            let response = try await mcpService.loadToolsIntoWorkflowRegistry()
            logger.info("Loaded \(response.toolCount) MCP tools into workflow registry")

            // Refresh built-in tools to show newly loaded tools
            toolCategories = []
            await loadBuiltinTools()

            // Switch to built-in tab to show the newly loaded tools
            selectedTab = .builtin
        } catch {
            logger.error("Failed to load tools into registry: \(String(describing: error))")
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
