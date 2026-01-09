import Foundation
import SwiftUI
import OSLog

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
    private let workflowService: WorkflowService

    init(apiClient: APIClient) {
        self.workflowService = WorkflowService(apiClient: apiClient)
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
        do {
            try await workflowService.deleteWorkflow(id)
            workflows.removeAll { $0.id == id }
        } catch {
            self.error = error
            throw error
        }
    }
    
    func runWorkflow(
        _ workflow: WorkflowDefinition,
        inputs: [String: Any] = [:],
        inputFiles: [String] = []
    ) async throws -> WorkflowRunResult {
        do {
            return try await workflowService.runWorkflow(workflow, inputs: inputs, inputFiles: inputFiles)
        } catch {
            self.error = error
            throw error
        }
    }
    
    func getWorkflow(_ id: String) async throws -> WorkflowDefinition {
        do {
            return try await workflowService.getWorkflow(id)
        } catch {
            self.error = error
            throw error
        }
    }

    func importWorkflow(name: String = "", description: String = "", workflowData: [String: Any]) async throws -> WorkflowSidebarItem {
        isSaving = true
        defer { isSaving = false }

        do {
            // Convert dictionary to AnyCodable format for API
            let anyCodableData = workflowData.mapValues { AnyCodable($0) }
            let response = try await workflowService.importWorkflow(name: name, description: description, workflowData: anyCodableData)

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

    /// Rename a workflow
    func renameWorkflow(_ id: String, to newName: String) async throws -> WorkflowSidebarItem {
        // Get the current workflow
        let currentWorkflow = try await getWorkflow(id)

        // Update the workflow with new name
        let updatedWorkflow = WorkflowDefinition(
            id: currentWorkflow.id,
            name: newName,
            description: currentWorkflow.description,
            provider: currentWorkflow.provider,
            model: currentWorkflow.model,
            nodes: currentWorkflow.nodes,
            edges: currentWorkflow.edges,
            folderPath: currentWorkflow.folderPath,
            sortOrder: currentWorkflow.sortOrder
        )

        // Update using the service
        return try await updateWorkflow(updatedWorkflow)
    }

    /// Duplicate a workflow
    func duplicateWorkflow(_ id: String) async throws -> WorkflowSidebarItem {
        // Get the current workflow
        let currentWorkflow = try await getWorkflow(id)

        // Create a new workflow with a new name
        let newWorkflow = WorkflowDefinition(
            id: UUID().uuidString, // This will be overridden by the backend
            name: "\(currentWorkflow.name) Copy",
            description: currentWorkflow.description,
            provider: currentWorkflow.provider,
            model: currentWorkflow.model,
            nodes: currentWorkflow.nodes,
            edges: currentWorkflow.edges,
            folderPath: currentWorkflow.folderPath,
            sortOrder: currentWorkflow.sortOrder + 1  // Place after original
        )

        // Save the new workflow
        return try await saveWorkflow(newWorkflow)
    }
}