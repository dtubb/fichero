import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime
import OpenAPIURLSession

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowExecutionServiceGenerated")

/// WorkflowExecutionService using the generated OpenAPI client.
/// Handles workflow execution, thread management, and status tracking.
@MainActor
class WorkflowExecutionServiceGenerated: ObservableObject {
    private let client: FicheroClient

    @Published var isExecuting: Bool = false
    @Published var threads: [ExecutionThread] = []
    @Published var currentThreadStatus: ExecutionThread?
    @Published var error: String?

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient)
    }

    /// Update the library path (called when library changes)
    func setLibraryPath(_ path: String?) {
        // Library path is managed by FicheroClient
    }

    // MARK: - Execute Workflow

    /// Execute a workflow with optional interrupt points
    func executeWorkflow(
        workflowId: String,
        inputs: [String: Any] = [:],
        threadId: String? = nil,
        interruptBefore: [String] = [],
        interruptAfter: [String] = []
    ) async throws -> ExecutionThread {
        isExecuting = true
        defer { isExecuting = false }

        // Convert inputs to OpenAPI container
        let inputsContainer = OpenAPIObjectContainer(unvalidatedValue: inputs.mapValues { $0 as any Sendable })

        let response = try await client.api.executeWorkflowApiWorkflowExecutionExecutePost(.init(
            headers: .init(X_hyphen_Fichero_hyphen_Library_hyphen_Path: client.currentLibraryPath ?? ""),
            body: .json(.init(
                workflow_id: workflowId,
                inputs: inputsContainer,
                thread_id: threadId,
                interrupt_before: interruptBefore,
                interrupt_after: interruptAfter
            ))
        ))

        switch response {
        case .ok(let okResponse):
            let threadResponse = try okResponse.body.json
            let thread = convertToExecutionThread(threadResponse)
            currentThreadStatus = thread
            logger.info("Executed workflow \(workflowId), thread: \(thread.threadId)")
            return thread
        default:
            throw WorkflowExecutionServiceError.unexpectedResponse
        }
    }

    // MARK: - Resume Workflow

    /// Resume a paused workflow
    func resumeWorkflow(threadId: String, inputs: [String: Any]? = nil) async throws -> ExecutionThread {
        isExecuting = true
        defer { isExecuting = false }

        let inputsContainer = inputs.map {
            OpenAPIObjectContainer(unvalidatedValue: $0.mapValues { $0 as any Sendable })
        }

        let response = try await client.api.resumeThreadApiWorkflowExecutionThreadsThreadIdResumePost(.init(
            path: .init(thread_id: threadId),
            headers: .init(X_hyphen_Fichero_hyphen_Library_hyphen_Path: client.currentLibraryPath ?? ""),
            body: .json(.init(inputs: inputsContainer))
        ))

        switch response {
        case .ok(let okResponse):
            let threadResponse = try okResponse.body.json
            let thread = convertToExecutionThread(threadResponse)
            currentThreadStatus = thread
            logger.info("Resumed workflow thread: \(threadId)")
            return thread
        default:
            throw WorkflowExecutionServiceError.unexpectedResponse
        }
    }

    // MARK: - Get Thread Status

    /// Get the current status of an execution thread
    func getThreadStatus(threadId: String) async throws -> ExecutionThread {
        let response = try await client.api.getThreadStatusApiWorkflowExecutionThreadsThreadIdStatusGet(.init(
            path: .init(thread_id: threadId),
            headers: .init(X_hyphen_Fichero_hyphen_Library_hyphen_Path: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            let threadResponse = try okResponse.body.json
            let thread = convertToExecutionThread(threadResponse)
            currentThreadStatus = thread
            return thread
        default:
            throw WorkflowExecutionServiceError.unexpectedResponse
        }
    }

    // MARK: - List Threads

    /// List all execution threads
    func listThreads(limit: Int = 100) async throws -> [ExecutionThread] {
        let response = try await client.api.listThreadsApiWorkflowExecutionThreadsGet(.init(
            query: .init(limit: limit),
            headers: .init(X_hyphen_Fichero_hyphen_Library_hyphen_Path: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let okResponse):
            let listResponse = try okResponse.body.json
            threads = listResponse.threads.map { convertToExecutionThread($0) }
            logger.info("Listed \(self.threads.count) threads")
            return threads
        default:
            throw WorkflowExecutionServiceError.unexpectedResponse
        }
    }

    // MARK: - Delete Thread

    /// Delete an execution thread and its checkpoints
    func deleteThread(threadId: String) async throws {
        let response = try await client.api.deleteThreadApiWorkflowExecutionThreadsThreadIdDelete(.init(
            path: .init(thread_id: threadId),
            headers: .init(X_hyphen_Fichero_hyphen_Library_hyphen_Path: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok:
            // Remove from local list
            threads.removeAll { $0.threadId == threadId }
            if currentThreadStatus?.threadId == threadId {
                currentThreadStatus = nil
            }
            logger.info("Deleted thread: \(threadId)")
        default:
            throw WorkflowExecutionServiceError.unexpectedResponse
        }
    }

    // MARK: - Type Conversions

    private func convertToExecutionThread(_ generated: Components.Schemas.ThreadStatusResponse) -> ExecutionThread {
        ExecutionThread(
            threadId: generated.threadId,
            workflowId: generated.workflowId,
            workflowName: generated.workflowName,
            status: ExecutionStatus(rawValue: generated.status) ?? .failed,
            checkpointId: generated.checkpointId,
            error: generated.error
        )
    }
}

// MARK: - Error Types

enum WorkflowExecutionServiceError: Error, LocalizedError {
    case unexpectedResponse
    case invalidResponse
    case serverError(Int, String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from workflow execution service"
        case .invalidResponse:
            return "Invalid response from server"
        case let .serverError(code, message):
            return "Server error (\(code)): \(message)"
        }
    }
}
