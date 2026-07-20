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

    @Environment(WorkflowService.self) var workflowService
    @Environment(MCPService.self) var mcpService
    @Environment(AppState.self) var appState
    let featureManager = FeatureManager.shared

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

    /// Top-level workflow detail tabs (#3531): the tool palette, the workflow's
    /// step chain, and this workflow's runs. Shares the `SurfaceTab` chrome.
    enum WorkflowSurfaceTab: String, CaseIterable, Identifiable, SurfaceTab {
        case tools
        case chain
        case run

        var id: String { rawValue }
        var title: String {
            switch self {
            case .tools: return "Tools"
            case .chain: return "Chain"
            case .run: return "Run"
            }
        }
        var icon: String {
            switch self {
            case .tools: return "wrench.and.screwdriver"
            case .chain: return "arrow.triangle.branch"
            case .run: return "play.circle"
            }
        }
        var help: String {
            switch self {
            case .tools: return "Tools — the palette of built-in, MCP, and agent tools"
            case .chain: return "Chain — the workflow's ordered steps"
            case .run: return "Run — this workflow's executions"
            }
        }
    }

    @State private var surfaceTab: WorkflowSurfaceTab = .tools
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

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
            // Top-level workflow tabs (Tools / Chain / Run) in the shared chrome
            // (#3531) — the same SurfaceTabBar the Reader and Inspector use.
            SurfaceTabBar(
                tabs: WorkflowSurfaceTab.allCases,
                selection: $surfaceTab,
                accessibilityID: "workflowSurfaceTabBar"
            )

            Divider()

            switch surfaceTab {
            case .tools: toolsContent
            case .chain: chainContent
            case .run: runContent
            }

            Divider()
            bottomBar
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

    /// Tools tab — the tool palette, with Built-in / MCP / Agents as sub-tabs
    /// (the existing palette, now nested under the Tools top tab). (#3531)
    private var toolsContent: some View {
        VStack(spacing: 0) {
            SurfaceTabBar(
                tabs: availableTabs,
                selection: $selectedTab,
                accessibilityID: "workflowToolsTabBar"
            )
            Divider()
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
    }

    /// Chain tab — the workflow's ordered steps. Each node is a tool (#2441);
    /// this lists them in order (editing the node config stays in the editor).
    @ViewBuilder
    private var chainContent: some View {
        if workflow.nodes.isEmpty {
            ContentUnavailableView(
                "No steps",
                systemImage: "arrow.triangle.branch",
                description: Text("This workflow has no steps yet. Add tools from the Tools tab.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(Array(workflow.nodes.enumerated()), id: \.element.id) { index, node in
                HStack(spacing: 8) {
                    Text("\(index + 1)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .frame(width: 20, alignment: .trailing)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(node.label ?? node.tool).font(.body).lineLimit(1)
                        Text(node.tool).font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                }
            }
            .listStyle(.inset)
        }
    }

    /// Run tab — this workflow's executions (active + completed), newest first.
    @ViewBuilder
    private var runContent: some View {
        if workflowRuns.isEmpty {
            ContentUnavailableView(
                "No runs",
                systemImage: "play.slash",
                description: Text("This workflow hasn't been run yet.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(workflowRuns) { run in
                HStack(spacing: 8) {
                    Image(systemName: run.isRunning ? "play.circle.fill" : "checkmark.circle")
                        .foregroundStyle(run.isRunning ? Color.accentColor : .secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(run.name).font(.body).lineLimit(1)
                        Text("\(run.processedFiles)/\(run.totalFiles) · \(String(describing: run.status))")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                }
            }
            .listStyle(.inset)
        }
    }

    /// This workflow's executions from the shared observer, running first.
    private var workflowRuns: [WorkflowExecution] {
        let all = Array(executionObserver.activeExecutions.values)
            + Array(executionObserver.completedExecutions.values)
        return all
            .filter { $0.id == workflow.id }
            .sorted { $0.startTime > $1.startTime }
    }

    /// Shared bottom mini-toolbar (#3531) — a per-tab status line.
    private var bottomBar: some View {
        MiniToolbar {
            Text(bottomStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
        }
    }

    private var bottomStatus: String {
        switch surfaceTab {
        case .tools:
            return "Tools"
        case .chain:
            let count = workflow.nodes.count
            return "\(count) step\(count == 1 ? "" : "s")"
        case .run:
            let count = workflowRuns.count
            return count == 0 ? "No runs" : "\(count) run\(count == 1 ? "" : "s")"
        }
    }

}

// MARK: - Built-in Tools

extension WorkflowInspector {
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
