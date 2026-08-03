import FicheroAPIClient
import Foundation

extension WorkflowStore {
    func importWorkflow(
        name: String = "",
        description: String = "",
        workflowData: [String: Any]
    ) async throws -> WorkflowSidebarItem {
        isSaving = true
        defer { isSaving = false }

        do {
            // Convert dictionary to AnyCodable format for API
            let anyCodableData = workflowData.mapValues { AnyCodable($0) }
            let response = try await workflowService.importWorkflow(
                name: name,
                description: description,
                workflowData: anyCodableData
            )

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
                requiresVision: response.requiresVision
            )

            // Add to local array
            workflows.append(item)

            return item
        } catch {
            if error.isCancellationError { throw error }   // superseded — rethrow without error state
            self.error = error
            throw error
        }
    }

    func exportWorkflow(_ id: String) async throws -> [String: Any] {
        do {
            let response = try await workflowService.exportWorkflow(id)

            // Convert from AnyCodable back to regular types
            var result: [String: Any] = [:]
            for (key, value) in response {
                result[key] = value.value
            }

            return result
        } catch {
            if error.isCancellationError { throw error }   // superseded — rethrow without error state
            self.error = error
            throw error
        }
    }
}
