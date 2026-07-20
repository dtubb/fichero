import FicheroAPIClient
import Foundation
import OSLog

extension WorkflowStore {
    func checkConnection() async {
        do {
            // Try to list tools as a connection test
            _ = try await workflowService.listTools()
            isConnected = true
            error = nil
        } catch {
            isConnected = false
            self.error = error
        }
    }

    func loadWorkflows() async {
        isLoading = true
        error = nil

        do {
            // NEVER auto-reinstall defaults on loadWorkflows — that wiped
            // user edits to preset workflows (Transcribe provider/model)
            // on every navigation AND every app launch. (#780 root cause)
            // Updated presets after a Sparkle update reach old libraries
            // via the explicit "Reset Defaults" button (#722). The backend
            // also demotes is_template=False on user PUT so even if the
            // reinstall does fire, edited presets survive.

            // Hydrate the tool registry alongside workflows so the canvas
            // can render correct icons for non-hardcoded tools (#725).
            // Failures are non-fatal — fall back to hardcoded icon dict.
            if let registry = try? await loadToolRegistry() {
                toolRegistry = registry
            }

            let response = try await workflowService.listWorkflows()
            workflows = response.map { workflow in
                WorkflowSidebarItem(
                    id: workflow.id,
                    name: workflow.name,
                    description: workflow.description,
                    nodeCount: workflow.nodes.count,
                    isEnabled: true,
                    folderPath: workflow.folderPath,
                    sortOrder: workflow.sortOrder,
                    isSystem: workflow.isSystem,
                    isUntested: workflow.isUntested,
                    createdAt: Date(),  // Backend doesn't return these yet
                    updatedAt: Date()
                )
            }
            isConnected = true
        } catch {
            self.error = error
            isConnected = false
            logger.error("Failed to load workflows: \(String(describing: error))")
        }

        isLoading = false
    }

    func loadToolRegistry() async throws -> [String: ToolInfo] {
        let tools = try await workflowService.listTools()
        return Dictionary(uniqueKeysWithValues: tools.map { ($0.name.lowercased(), $0) })
    }
}
