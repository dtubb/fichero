import FicheroAPIClient
import Foundation
import OSLog
import SwiftUI

// swiftlint:disable file_length

// Store for managing workflows with backend persistence
@MainActor
// swiftlint:disable:next type_body_length
class WorkflowStore: ObservableObject {
    @Published var workflows: [WorkflowSidebarItem] = []
    @Published var selectedWorkflow: WorkflowSidebarItem?
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var isConnected = false
    @Published var error: Error?

    private let logger = Logger(subsystem: "com.tubb.Fichero", category: "WorkflowStore")
    private let workflowService: WorkflowServiceGenerated
    private let ficheroClient: FicheroClient
    private let defaultWorkflowTemplates: [DefaultWorkflowTemplate] = [
        .filesToTranscribe,
        .collectionToTranscribe
    ]

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
            // Re-seed defaults first so updated presets reach the library
            try? await workflowService.reinstallDefaults()

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
            self.error = error
            throw error
        }
    }

    /// Move a workflow into a different folder path.
    ///
    /// Thin wrapper over `WorkflowServiceGenerated.moveToFolder` which
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
                isSystem: response.isSystem,
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
            isSystem: workflows[index].isSystem,  // Preserve system flag
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
            isSystem: response.isSystem,
            createdAt: Date(),
            updatedAt: Date()
        )

        // Add to local array
        workflows.append(item)

        return item
    }

    // MARK: - Default Templates

    /// Install built-in default workflows if they are missing.
    @discardableResult
    func installDefaultWorkflowTemplates() async throws -> [WorkflowSidebarItem] {
        try await syncDefaultWorkflowTemplates(resetExisting: false)
    }

    /// Remove and recreate built-in default workflows.
    @discardableResult
    func resetDefaultWorkflowTemplates() async throws -> [WorkflowSidebarItem] {
        try await syncDefaultWorkflowTemplates(resetExisting: true)
    }

    @discardableResult
    private func syncDefaultWorkflowTemplates(resetExisting: Bool) async throws -> [WorkflowSidebarItem] {
        let toolsByName = try await loadToolRegistry()
        let workflowResponses = try await workflowService.listWorkflows()
        let existingByName = Dictionary(
            uniqueKeysWithValues: workflowResponses.map { ($0.name, $0) }
        )

        if resetExisting {
            for template in defaultWorkflowTemplates {
                if let existing = existingByName[template.name] {
                    try await workflowService.deleteWorkflow(existing.id)
                }
            }
        }

        var created: [WorkflowSidebarItem] = []
        for template in defaultWorkflowTemplates {
            if !resetExisting, existingByName[template.name] != nil {
                continue
            }

            let definition = try template.makeDefinition(toolsByName: toolsByName)
            let response = try await workflowService.createWorkflow(definition)
            created.append(
                WorkflowSidebarItem(
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
            )
        }

        await loadWorkflows()
        return created
    }

    private func loadToolRegistry() async throws -> [String: ToolInfo] {
        let tools = try await workflowService.listTools()
        return Dictionary(uniqueKeysWithValues: tools.map { ($0.name.lowercased(), $0) })
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
    case templateInstallFailed(String)

    var errorDescription: String? {
        switch self {
        case .notFound(let message):
            return "Not found: \(message)"
        case .saveFailed(let message):
            return "Save failed: \(message)"
        case .executionFailed(let message):
            return "Execution failed: \(message)"
        case .templateInstallFailed(let message):
            return "Template install failed: \(message)"
        }
    }
}

// MARK: - Default Workflow Templates

private enum DefaultWorkflowTemplate {
    case filesToTranscribe
    case collectionToTranscribe

    var name: String {
        switch self {
        case .filesToTranscribe:
            return "Default · Transcribe Files"
        case .collectionToTranscribe:
            return "Default · Transcribe Collection"
        }
    }

    var description: String {
        switch self {
        case .filesToTranscribe:
            return "Run transcription over selected files."
        case .collectionToTranscribe:
            return "Run transcription over a collection source."
        }
    }

    func makeDefinition(toolsByName: [String: ToolInfo]) throws -> WorkflowDefinition {
        let sourceToolName = switch self {
        case .filesToTranscribe: "files"
        case .collectionToTranscribe: "collection"
        }

        guard let sourceTool = toolsByName[sourceToolName] else {
            throw WorkflowStoreError.templateInstallFailed("Missing source tool '\(sourceToolName)'")
        }
        guard let transcribeTool = toolsByName["transcribe"] else {
            throw WorkflowStoreError.templateInstallFailed("Missing tool 'transcribe'")
        }

        let sourceNode = WorkflowNode(
            from: sourceTool,
            positionX: 220,
            positionY: 220
        )
        let transcribeNode = WorkflowNode(
            from: transcribeTool,
            positionX: 540,
            positionY: 220
        )

        let sourcePort = sourceNode.outputPorts.first?.id ?? "output"
        let targetPort = transcribeNode.inputPorts.first?.id ?? "input"

        return WorkflowDefinition(
            name: name,
            description: description,
            nodes: [sourceNode, transcribeNode],
            edges: [
                WorkflowEdge(
                    sourceNodeId: sourceNode.id,
                    targetNodeId: transcribeNode.id,
                    sourcePortId: sourcePort,
                    targetPortId: targetPort
                )
            ]
        )
    }
}
