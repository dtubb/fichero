import Foundation
import SwiftUI
import OSLog
import FicheroAPIClient

/// Store for managing workflows with backend persistence
@MainActor
class WorkflowStore: ObservableObject {
    @Published var workflows: [WorkflowSidebarItem] = []
    @Published var selectedWorkflow: WorkflowSidebarItem?
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var isConnected = false
    @Published var error: Error?

    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowStore")
    private let workflowService: WorkflowServiceGenerated
    private let ficheroClient: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.ficheroClient = ficheroClient
        self.workflowService = WorkflowServiceGenerated(ficheroClient: ficheroClient)
    }

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
                createdAt: Date(),
                updatedAt: Date()
            )

            // Update in local array
            if let index = workflows.firstIndex(where: { $0.id == response.id }) {
                workflows[index] = item
            }

            return item
        } catch {
            self.error = error
            throw error
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
                createdAt: Date(),
                updatedAt: Date()
            )

            // Add to local array
            workflows.append(item)

            return item
        } catch {
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
            self.error = error
            throw error
        }
    }

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
            createdAt: workflows[index].createdAt,  // Preserve original dates
            updatedAt: Date()
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
            createdAt: Date(),
            updatedAt: Date()
        )

        // Add to local array
        workflows.append(item)

        return item
    }

    // MARK: - Workflow Execution

    private lazy var executionService: WorkflowExecutionService = {
        WorkflowExecutionService(libraryPath: ficheroClient.currentLibraryPath)
    }()

    /// Execute a saved workflow by ID
    func executeWorkflow(
        _ workflowId: String,
        inputs: [String: Any] = [:],
        interruptBefore: [String] = [],
        interruptAfter: [String] = []
    ) async throws -> ExecutionThread {
        do {
            let thread = try await executionService.executeWorkflow(
                workflowId: workflowId,
                inputs: inputs,
                interruptBefore: interruptBefore,
                interruptAfter: interruptAfter
            )
            logger.info("Started execution of workflow \(workflowId), thread: \(thread.threadId)")
            return thread
        } catch {
            self.error = error
            logger.error("Failed to execute workflow \(workflowId): \(String(describing: error))")
            throw error
        }
    }

    /// Get the status of an execution thread
    func getExecutionStatus(_ threadId: String) async throws -> ExecutionThread {
        do {
            return try await executionService.getThreadStatus(threadId: threadId)
        } catch {
            self.error = error
            throw error
        }
    }

    /// Resume a paused workflow
    func resumeExecution(_ threadId: String, inputs: [String: Any]? = nil) async throws -> ExecutionThread {
        do {
            let thread = try await executionService.resumeWorkflow(threadId: threadId, inputs: inputs)
            logger.info("Resumed workflow thread: \(threadId)")
            return thread
        } catch {
            self.error = error
            logger.error("Failed to resume workflow thread \(threadId): \(String(describing: error))")
            throw error
        }
    }

    /// List all execution threads
    func listExecutionThreads(limit: Int = 100) async throws -> [ExecutionThread] {
        do {
            return try await executionService.listThreads(limit: limit)
        } catch {
            self.error = error
            throw error
        }
    }

    /// Delete an execution thread
    func deleteExecutionThread(_ threadId: String) async throws {
        do {
            try await executionService.deleteThread(threadId: threadId)
            logger.info("Deleted execution thread: \(threadId)")
        } catch {
            self.error = error
            throw error
        }
    }
}

// MARK: - Error Types

enum WorkflowStoreError: Error, LocalizedError {
    case notFound(String)
    case saveFailed(String)
    case executionFailed(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let message):
            return "Not found: \(message)"
        case .saveFailed(let message):
            return "Save failed: \(message)"
        case .executionFailed(let message):
            return "Execution failed: \(message)"
        }
    }
}
