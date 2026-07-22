import FicheroAPIClient
import Foundation

extension WorkflowStore {
    func fetchWorkflowDiagramMermaid(_ workflowId: String) async throws -> String? {
        try await workflowService.fetchDiagramMermaid(workflowId: workflowId)
    }

    func fetchWorkflowPythonCode(_ workflowId: String) async throws -> String? {
        let response = try await ficheroClient.api.getWorkflowCodeApiWorkflowExecutionWorkflowsWorkflowIdCodeGet(.init(
            path: .init(workflowId: workflowId),
        ))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.pythonCode
        case .unprocessableContent:
            throw WorkflowStoreError.executionFailed("Validation error")
        case .undocumented(let statusCode, _):
            throw WorkflowStoreError.executionFailed("Failed to load code (HTTP \(statusCode))")
        }
    }

    func saveWorkflow(_ workflow: WorkflowDefinition) async throws -> WorkflowSidebarItem {
        isSaving = true
        defer { isSaving = false }

        do {
            let response = try await workflowService.createWorkflow(workflow)

            let item = WorkflowSidebarItem(
                id: response.id,
                name: response.name,
                description: response.description,
                nodeCount: response.nodes.count,
                isEnabled: true,
                folderPath: response.folderPath,
                sortOrder: response.sortOrder,
                isSystem: response.isSystem,
                createdAt: Date(),
                updatedAt: Date()
            )

            // Update existing or add new
            if let index = workflows.firstIndex(where: { $0.id == response.id }) {
                workflows[index] = item
            } else {
                workflows.append(item)
            }

            return item
        } catch {
            if error.isCancellationError { throw error }   // superseded — rethrow without error state
            self.error = error
            throw error
        }
    }

    func updateWorkflow(_ workflow: WorkflowDefinition) async throws -> WorkflowSidebarItem {
        isSaving = true
        defer { isSaving = false }

        do {
            let response = try await workflowService.updateWorkflow(workflow.id, workflow: workflow)

            let item = WorkflowSidebarItem(
                id: response.id,
                name: response.name,
                description: response.description,
                nodeCount: response.nodes.count,
                isEnabled: true,
                folderPath: response.folderPath,
                sortOrder: response.sortOrder,
                isSystem: response.isSystem,
                createdAt: Date(),
                updatedAt: Date()
            )

            // Update in local array
            if let index = workflows.firstIndex(where: { $0.id == response.id }) {
                workflows[index] = item
            }

            return item
        } catch {
            if error.isCancellationError { throw error }   // superseded — rethrow without error state
            self.error = error
            throw error
        }
    }

    /// Move a workflow into a different folder path.
    ///
    /// Thin wrapper over `WorkflowService.moveToFolder` which
    /// patches the backend `folder_path` field (`PATCH /api/workflows/{id}`
    /// accepts a partial body with `folder_path` — see `workflows.py:649`).
    /// Updates the local `workflows` array on success so the sidebar
    /// rebuilds without waiting for the next `loadWorkflows` round-trip.
    /// Sidebar plan Step 9 (#585).
    func moveWorkflow(_ id: String, toFolder folderPath: String) async throws {
        guard isValidWorkflowId(id) else {
            throw WorkflowStoreError.notFound("Invalid workflow ID format")
        }
        let response = try await workflowService.moveToFolder(id, folderPath: folderPath)
        if let index = workflows.firstIndex(where: { $0.id == id }) {
            let old = workflows[index]
            workflows[index] = WorkflowSidebarItem(
                id: old.id,
                name: old.name,
                description: old.description,
                nodeCount: old.nodeCount,
                edgeCount: old.edgeCount,
                isEnabled: old.isEnabled,
                folderPath: response.folderPath,
                sortOrder: old.sortOrder,
                isSystem: old.isSystem,
                createdAt: old.createdAt,
                updatedAt: Date()
            )
        }
    }

    func deleteWorkflow(_ id: String) async throws {
        // Validate ID format
        guard isValidWorkflowId(id) else {
            throw WorkflowStoreError.notFound("Invalid workflow ID format")
        }

        do {
            try await workflowService.deleteWorkflow(id)
            workflows.removeAll { $0.id == id }
        } catch {
            if error.isCancellationError { throw error }   // superseded — rethrow without error state
            self.error = error
            throw error
        }
    }

    func getWorkflow(_ id: String) async throws -> WorkflowDefinition {
        // Validate ID format
        guard isValidWorkflowId(id) else {
            throw WorkflowStoreError.notFound("Invalid workflow ID format")
        }

        do {
            return try await workflowService.getWorkflow(id)
        } catch {
            if error.isCancellationError { throw error }   // superseded — rethrow without error state
            self.error = error
            throw error
        }
    }

    // MARK: - Input Validation

    /// Validate workflow ID format (UUID or reasonable identifier)
    private func isValidWorkflowId(_ id: String) -> Bool {
        // Must not be empty, must be reasonable length, must not contain dangerous chars
        guard !id.isEmpty,
              id.count <= 100,
              !id.contains("\n"),
              !id.contains("\r"),
              !id.contains(".."),
              !id.contains("/"),
              !id.contains("\\") else {
            return false
        }
        return true
    }
}
