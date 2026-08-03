import FicheroAPIClient
import Foundation
import OSLog

extension WorkflowStore {
    /// Rename a workflow using backend PATCH endpoint.
    /// The backend handles the partial update - no need to fetch full workflow.
    func renameWorkflow(_ id: String, to newName: String) async throws -> WorkflowSidebarItem {
        logger.info("renameWorkflow: id=\(id), newName=\(newName)")

        // Find the workflow first to ensure it exists locally
        guard let index = workflows.firstIndex(where: { $0.id == id }) else {
            logger.error("renameWorkflow: workflow not found locally with id=\(id)")
            throw WorkflowStoreError.notFound("Workflow not found: \(id)")
        }

        let response = try await workflowService.renameWorkflow(id, newName: newName)
        logger.info("renameWorkflow response: id=\(response.id), name=\(response.name)")

        // Create updated item using response data but keep the original ID
        // (in case API returns different format)
        let item = WorkflowSidebarItem(
            id: id,  // Use original ID to ensure consistency
            name: response.name,
            description: response.description,
            nodeCount: response.nodes.count,
            isEnabled: true,
            folderPath: response.folderPath,
            sortOrder: response.sortOrder,
            isSystem: workflows[index].isSystem,  // Preserve system flag
            // A rename must not change what the workflow can DO. These came
            // back on the response and were being discarded, so renaming a
            // pinned workflow handed it an override submenu it ignores
            // (#4494); same shape as the move path.
            isUntested: response.isUntested,
            isDirectlyRunnable: response.directRunnable ?? true,
            acceptsModelOverride: response.acceptsModelOverride ?? true,
            createdAt: workflows[index].createdAt,  // Preserve original dates
            updatedAt: Date(),
            hasVisionNodes: WorkflowSidebarItem.requiresVisionModel(
                nodes: response.nodes,
                toolRegistry: toolRegistry
            )
        )

        // Update the local array
        workflows[index] = item
        logger.info("renameWorkflow: updated workflow at index \(index)")

        return item
    }

    /// Duplicate a workflow using backend duplicate endpoint.
    /// The backend handles ID generation, naming, and all logic.
    func duplicateWorkflow(_ id: String) async throws -> WorkflowSidebarItem {
        let response = try await workflowService.duplicateWorkflow(id)

        let item = WorkflowSidebarItem(
            id: response.id,
            name: response.name,
            description: response.description,
            nodeCount: response.nodes.count,
            isEnabled: true,
            folderPath: response.folderPath,
            sortOrder: response.sortOrder,
            isSystem: response.isSystem,
            isUntested: response.isUntested,
            isDirectlyRunnable: response.directRunnable ?? true,
            acceptsModelOverride: response.acceptsModelOverride ?? true,
            createdAt: Date(),
            updatedAt: Date(),
            hasVisionNodes: WorkflowSidebarItem.requiresVisionModel(
                nodes: response.nodes,
                toolRegistry: toolRegistry
            )
        )

        // Add to local array
        workflows.append(item)

        return item
    }
}
