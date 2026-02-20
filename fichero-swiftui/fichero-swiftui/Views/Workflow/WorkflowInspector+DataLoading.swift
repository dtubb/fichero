import SwiftUI

extension WorkflowInspector {

    // MARK: - Data Loading

    func loadBuiltinTools() async {
        guard toolCategories.isEmpty && !isLoadingTools else { return }
        isLoadingTools = true
        defer { isLoadingTools = false }

        do {
            let response = try await workflowServiceGenerated.listToolsGrouped()
            toolCategories = response.categories
            let totalTools = response.categories.reduce(0) { $0 + $1.tools.count }
            workflowInspectorLogger.info("Loaded \(totalTools) built-in tools in \(response.categories.count) categories")
        } catch {
            workflowInspectorLogger.error("Failed to load built-in tools: \(String(describing: error))")
            // Fall back to empty - UI will show placeholder
        }
    }

    func loadMCPTools() async {
        isLoadingMCPTools = true
        defer { isLoadingMCPTools = false }

        do {
            let response = try await mcpService.getAllTools()
            mcpTools = response.tools

            // Group by server
            mcpToolsGrouped = Dictionary(grouping: response.tools) { $0.serverName }

            workflowInspectorLogger.info("Loaded \(response.tools.count) MCP tools from \(mcpToolsGrouped.keys.count) servers")
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

    /// Calculate a smart position for the next node
    var nextNodePosition: CGPoint {
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
