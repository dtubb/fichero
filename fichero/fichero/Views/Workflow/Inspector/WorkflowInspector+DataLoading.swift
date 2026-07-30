import SwiftUI

@MainActor
enum WorkflowPaletteGate {
    static func isBuiltinCategoryEnabled(_ category: String, featureManager: FeatureManager) -> Bool {
        let normalized = category.lowercased()

        if normalized == "agent" {
            return featureManager.isWorkflowToolsAgentsEnabled
        }
        if normalized == "mcp" || normalized.hasPrefix("mcp_") {
            return featureManager.isWorkflowToolsMCPEnabled
        }

        return true
    }

    static func isBuiltinToolEnabled(_ tool: ToolInfo, featureManager: FeatureManager) -> Bool {
        isBuiltinCategoryEnabled(tool.category, featureManager: featureManager)
    }
}

extension WorkflowInspector {

    // MARK: - Data Loading

    func loadBuiltinTools() async {
        guard toolCategories.isEmpty && !isLoadingTools else { return }
        isLoadingTools = true
        defer { isLoadingTools = false }

        do {
            let response = try await workflowService.listToolsGrouped()
            toolCategories = response.categories
            let totalTools = response.categories.reduce(0) { $0 + $1.tools.count }
            let categoryCount = response.categories.count
            workflowInspectorLogger.info("Loaded \(totalTools) built-in tools in \(categoryCount) categories")
        } catch {
            workflowInspectorLogger.error("Failed to load built-in tools: \(String(describing: error))")
            // Fall back to empty - UI will show placeholder
        }
    }

    func filteredCategoryIfEnabled(_ category: CategoryTools) -> CategoryTools? {
        guard isWorkflowCategoryEnabled(category.category) else {
            return nil
        }

        let filteredTools = category.tools.filter(isWorkflowToolEnabled)
        guard !filteredTools.isEmpty else {
            return nil
        }

        return CategoryTools(
            category: category.category,
            displayName: category.displayName,
            tools: filteredTools
        )
    }

    /// Number of built-in tools currently hidden by feature flags.
    /// Surfaces gating explicitly in the inspector so missing tools do not
    /// look like broken wiring (#1220).
    var hiddenBuiltinToolCount: Int {
        var hidden = 0
        for category in toolCategories {
            if !isWorkflowCategoryEnabled(category.category) {
                hidden += category.tools.count
                continue
            }
            hidden += category.tools.filter { !isWorkflowToolEnabled($0) }.count
        }
        return hidden
    }

    private func isWorkflowCategoryEnabled(_ category: String) -> Bool {
        WorkflowPaletteGate.isBuiltinCategoryEnabled(category, featureManager: featureManager)
    }

    private func isWorkflowToolEnabled(_ tool: ToolInfo) -> Bool {
        WorkflowPaletteGate.isBuiltinToolEnabled(tool, featureManager: featureManager)
    }

    func loadMCPTools() async {
        isLoadingMCPTools = true
        defer { isLoadingMCPTools = false }

        do {
            let response = try await mcpService.getAllTools()
            mcpTools = response.tools

            // Group by server
            mcpToolsGrouped = Dictionary(grouping: response.tools) { $0.serverName }

            let toolCount = response.tools.count
            let serverCount = mcpToolsGrouped.keys.count
            workflowInspectorLogger.info("Loaded \(toolCount) MCP tools from \(serverCount) servers")
        } catch {
            workflowInspectorLogger.error("Failed to load MCP tools: \(String(describing: error))")
        }
    }

    func loadIntoRegistry() async {
        do {
            let response = try await mcpService.loadToolsIntoWorkflowRegistry()
            workflowInspectorLogger.info("Loaded \(response.toolCount) MCP tools into workflow registry")

            // Refresh built-in tools to show newly loaded tools
            toolCategories = []
            await loadBuiltinTools()

            // Switch to built-in tab to show the newly loaded tools
            selectedTab = .builtin
        } catch {
            workflowInspectorLogger.error("Failed to load tools into registry: \(String(describing: error))")
        }
    }

    /// Position for the next added node: after the node selected on the
    /// canvas when there is one, otherwise after the last node in execution
    /// order — never at the rightmost X of an arbitrary branch (#4323).
    var nextNodePosition: CGPoint {
        WorkflowNodePlacement.nextNodePosition(
            nodes: workflow.nodes,
            edges: workflow.edges,
            selectedNodeIds: workflowStore.canvasSelectedNodeIds
        )
    }

}
