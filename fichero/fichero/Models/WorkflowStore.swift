import FicheroAPIClient
import Foundation
import Observation
import OSLog

// swiftlint:disable file_length

// Store for managing workflows with backend persistence
@MainActor
@Observable
// swiftlint:disable:next type_body_length
final class WorkflowStore: ChangeEventConsumer {
    private(set) var workflows: [WorkflowSidebarItem] = []
    private(set) var selectedWorkflow: WorkflowSidebarItem?
    private(set) var isLoading = false
    private(set) var isSaving = false
    private(set) var isConnected = false
    private(set) var error: Error?

    /// Cached backend tool metadata, keyed by lowercased tool name. Populated
    /// by `loadWorkflows()` so the canvas's `WorkflowNodeView` can render the
    /// correct icon/color for any registered tool — palette and graph share
    /// one source of truth (#725). Empty until first successful load; views
    /// fall back to a hardcoded dictionary for unknown tools.
    private(set) var toolRegistry: [String: ToolInfo] = [:]

    /// Bumped when a `workflow.*` change event arrives so interested views can
    /// invalidate their cached workflow-dependent UI.
    private(set) var changeToken: Int = 0

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowStore")
    private let workflowService: WorkflowServiceGenerated
    private let ficheroClient: FicheroClient
    /// Per-process flag — true after the first reinstallDefaults() runs.
    /// Subsequent loadWorkflows() calls skip the reinstall so user edits to
    /// is_template preset workflows survive navigation. Without this, every
    /// view-mode change wiped the preset and re-seeded from JSON, blowing
    /// away the user's provider/model selection on the Transcribe (cloud)
    /// node etc. (#780 — root cause)
    private static var didReinstallDefaultsThisLaunch = false
    // Empty: backend ships the canonical default workflows (Transcribe,
    // Catalogue, Catalogue (composable)) via JSON in
    // fichero-engine/.../resources/default_workflows. The Swift-side
    // `Default · Transcribe Files` / `Default · Transcribe Collection`
    // duplicated backend's Transcribe — removed in #722.
    // Note: there used to be a Swift-defined `defaultWorkflowTemplates`
    // array of `DefaultWorkflowTemplate` here. Defaults now live in the
    // backend's JSON files and are re-seeded by `reinstallDefaults` on
    // every session start. Removed in #722 to stop creating duplicates.

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

    func fetchWorkflowDiagramImage(_ workflowId: String) async throws -> PlatformImage? {
        try await workflowService.fetchDiagramImage(workflowId: workflowId)
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
        // The Swift-side `DefaultWorkflowTemplate` enum used to define
        // a few simple Transcribe templates here, but those overlapped
        // with backend-shipped defaults (Catalogue, Transcribe,
        // Catalogue (composable), Apple variants) and just created
        // duplicates. Source of truth is now backend JSON in
        // fichero-engine/src/fichero/resources/default_workflows/. (#722 part 1)
        //
        // The reset path delegates to `reinstallDefaults` which deletes
        // existing presets server-side and re-seeds from the backend's
        // canonical JSON. Install is a no-op because `loadWorkflows`
        // already re-seeds defaults on every session start (see line 59).
        if resetExisting {
            try await workflowService.reinstallDefaults()
        }
        await loadWorkflows()

        // Return the system-default workflows that exist after the
        // operation so callers (e.g., the "Reset Defaults" button) can
        // surface a "Reinstalled N workflows" message.
        return workflows.filter(\.isSystem)
    }

    private func loadToolRegistry() async throws -> [String: ToolInfo] {
        let tools = try await workflowService.listTools()
        return Dictionary(uniqueKeysWithValues: tools.map { ($0.name.lowercased(), $0) })
    }

    // MARK: - Workflow Execution

    // @ObservationIgnored: a lazily-built transport, not observable UI state.
    // @Observable would otherwise try to wrap this `lazy var` in an init
    // accessor, which is illegal on a computed/lazy property.
    @ObservationIgnored
    private lazy var executionService: WorkflowExecutionService = {
        WorkflowExecutionService(ficheroClient: ficheroClient)
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

    // MARK: - ChangeEventConsumer

    nonisolated var changeDomains: Set<String> { ["workflow"] }

    func apply(_ event: ChangeEvent) {
        changeToken &+= 1
    }

    func resync() async {
        await loadWorkflows()
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

// Removed: `DefaultWorkflowTemplate` enum (Transcribe Files / Transcribe Collection)
// — replaced by backend-shipped JSON workflows. See #722.
