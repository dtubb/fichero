import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExecutionService")

/// Service for executing workflows via the backend API.
///
/// Routes through the generated OpenAPI client (FicheroClient → AuthTokenMiddleware
/// + LibraryPathMiddleware) instead of hand-written URLSession requests (#1666/#1712).
/// These endpoints are **library-scoped** (a workflow run lives in a library), so the
/// library header is passed explicitly on every call — matching SavedSearch/Chat/Note.
/// (#1710 will later fold this into middleware and drop the manual header arg.)
@MainActor
@Observable
class WorkflowExecutionService {
    private let client: FicheroClient

    var isExecuting: Bool = false
    var threads: [ExecutionThread] = []
    var currentThreadStatus: ExecutionThread?
    var error: String?

    init(baseURL: URL = EngineConfig.apiBaseURL, libraryPath: String? = nil) {
        // FicheroClient expects the host root (paths in openapi.json already carry the
        // `/api` prefix). Legacy call sites pass `…:8765/api`, so strip any path here.
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        components?.path = ""
        let host = components?.url ?? baseURL
        self.client = FicheroClient(baseURL: host, libraryPath: libraryPath, transportMode: EngineConfig.transportMode)
    }

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Update the library path (called when library changes)
    func setLibraryPath(_ path: String?) {
        client.currentLibraryPath = path
    }

    /// Map a generated execution-status payload onto the app model (1:1 fields).
    private func mapThread(_ response: Components.Schemas.ExecutionStatusResponse) -> ExecutionThread {
        ExecutionThread(
            threadId: response.threadId,
            workflowId: response.workflowId,
            workflowName: response.workflowName,
            // Typed end-to-end (#4316/#4321): the generated RunStatus enum maps
            // case-for-case — no string round-trip, so a new backend state is a
            // compile error here instead of a silent `.running` fallback.
            status: Self.mapStatus(response.status),
            checkpointId: response.checkpointId,
            error: response.error
        )
    }

    /// Map the generated `RunStatus` enum (#4316) onto the app status enum.
    /// Exhaustive by construction — regenerating the client with a new
    /// lifecycle state fails compilation here rather than misrendering.
    static func mapStatus(_ status: Components.Schemas.RunStatus) -> ExecutionStatus {
        switch status {
        case .accepted, .running:
            return .running
        case .paused:
            return .paused
        case .completed:
            return .completed
        case .failed:
            return .failed
        case .cancelled:
            return .cancelled
        case .deleted:
            return .deleted
        }
    }

    /// Map the backend status string onto the app status enum. Unknown values
    /// (e.g. the 202 "accepted" handshake state) collapse to `.running`, which
    /// preserves a valid case rather than failing — the prior URLSession path
    /// decoded the same field straight into this enum.
    static func mapStatus(_ raw: String?) -> ExecutionStatus {
        switch raw?.lowercased() {
        case "paused":
            return .paused
        case "completed", "complete", "success", "succeeded":
            return .completed
        case "failed":
            return .failed
        case "error":
            return .error
        case "cancelled", "canceled":
            return .cancelled
        case "stopped", "stop_requested":
            return .stopped
        case "deleted":
            return .deleted
        default:
            return .running
        }
    }

    private func mapStatus(_ raw: String?) -> ExecutionStatus {
        Self.mapStatus(raw)
    }

    /// Build the OpenAPI free-form object container from a JSON-compatible dict,
    /// round-tripping through JSONSerialization to match the previous encoding.
    private func objectContainer(fromJSON dict: [String: Any]) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(OpenAPIRuntime.OpenAPIObjectContainer.self, from: data)
    }

    // MARK: - Execute Workflow

    /// Execute a workflow with optional interrupt points
    func executeAccepted(
        workflowId: String,
        inputs: [String: Any] = [:],
        threadId: String? = nil,
        interruptBefore: [String] = [],
        interruptAfter: [String] = [],
        providerOverride: String? = nil,
        modelOverride: String? = nil
    ) async throws -> ExecuteAcceptedResponse {
        let inputsPayload = Components.Schemas.ExecuteWorkflowRequest.InputsPayload(
            additionalProperties: try objectContainer(fromJSON: inputs)
        )
        let request = Components.Schemas.ExecuteWorkflowRequest(
            workflowId: workflowId,
            inputs: inputsPayload,
            threadId: threadId,
            interruptBefore: interruptBefore,
            interruptAfter: interruptAfter,
            providerOverride: (providerOverride?.isEmpty == false) ? providerOverride : nil,
            modelOverride: (modelOverride?.isEmpty == false) ? modelOverride : nil
        )

        isExecuting = true
        defer { isExecuting = false }

        let response = try await client.api.executeWorkflowApiWorkflowExecutionExecutePost(
            body: .json(request)
        )

        switch response {
        case .accepted(let accepted):
            let payload = try accepted.body.json
            logger.info("Executed workflow \(workflowId), thread: \(payload.threadId)")
            return ExecuteAcceptedResponse(
                threadId: payload.threadId,
                workflowId: payload.workflowId,
                workflowName: payload.workflowName,
                status: (payload.status ?? .accepted).rawValue,
                streamUrl: payload.streamUrl
            )
        case .unprocessableContent:
            logger.error("Execute workflow failed: validation error")
            throw WorkflowExecutionError.serverError(422, "Validation error")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            logger.error("Execute workflow failed: \(statusCode)")
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Execute workflow failed")
        }
    }

    func executeWorkflow(
        workflowId: String,
        inputs: [String: Any] = [:],
        threadId: String? = nil,
        interruptBefore: [String] = [],
        interruptAfter: [String] = []
    ) async throws -> ExecutionThread {
        let payload = try await executeAccepted(
            workflowId: workflowId,
            inputs: inputs,
            threadId: threadId,
            interruptBefore: interruptBefore,
            interruptAfter: interruptAfter
        )
        let thread = ExecutionThread(
            threadId: payload.threadId,
            workflowId: payload.workflowId,
            workflowName: payload.workflowName,
            status: mapStatus(payload.status),
            checkpointId: nil,
            error: nil
        )
        currentThreadStatus = thread
        return thread
    }

    // MARK: - Resume Workflow

    /// Resume a paused workflow
    func resumeWorkflow(threadId: String, inputs: [String: Any]? = nil) async throws -> ExecutionThread {
        let body: Operations.ResumeWorkflowApiWorkflowExecutionThreadsThreadIdResumePost.Input.Body?
        if let inputs = inputs {
            let inputsPayload = Components.Schemas.ResumeWorkflowRequest.InputsPayload(
                additionalProperties: try objectContainer(fromJSON: inputs)
            )
            body = .json(.init(inputs: inputsPayload))
        } else {
            body = nil
        }

        isExecuting = true
        defer { isExecuting = false }

        let response = try await client.api.resumeWorkflowApiWorkflowExecutionThreadsThreadIdResumePost(
            path: .init(threadId: threadId),
            body: body
        )

        switch response {
        case .ok(let okResponse):
            let thread = mapThread(try okResponse.body.json)
            currentThreadStatus = thread
            logger.info("Resumed workflow thread: \(threadId)")
            return thread
        case .unprocessableContent:
            logger.error("Resume workflow failed: validation error")
            throw WorkflowExecutionError.serverError(422, "Validation error")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            logger.error("Resume workflow failed: \(statusCode)")
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Resume workflow failed")
        }
    }

    // MARK: - Get Thread Status

    /// Get the current status of an execution thread
    func getThreadStatus(threadId: String) async throws -> ExecutionThread {
        let response = try await client.api.getThreadStatusApiWorkflowExecutionThreadsThreadIdStatusGet(
            path: .init(threadId: threadId),
        )

        switch response {
        case .ok(let okResponse):
            let thread = mapThread(try okResponse.body.json)
            currentThreadStatus = thread
            return thread
        case .unprocessableContent:
            logger.error("Get thread status failed: validation error")
            throw WorkflowExecutionError.serverError(422, "Validation error")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            logger.error("Get thread status failed: \(statusCode)")
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Get thread status failed")
        }
    }

    // MARK: - List Threads

    /// List all execution threads
    func listThreads(limit: Int = 100) async throws -> [ExecutionThread] {
        let response = try await client.api.listThreadsApiWorkflowExecutionThreadsGet(
            query: .init(limit: limit),
        )

        switch response {
        case .ok(let okResponse):
            let responseBody = try okResponse.body.json
            threads = responseBody.threads.map { mapThread($0) }
            logger.info("Listed \(self.threads.count) threads")
            return threads
        case .unprocessableContent:
            logger.error("List threads failed: validation error")
            throw WorkflowExecutionError.serverError(422, "Validation error")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            logger.error("List threads failed: \(statusCode)")
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "List threads failed")
        }
    }

    // MARK: - Delete Thread

    /// Delete an execution thread and its checkpoints
    func deleteThread(threadId: String) async throws {
        let response = try await client.api.deleteThreadApiWorkflowExecutionThreadsThreadIdDelete(
            path: .init(threadId: threadId),
        )

        switch response {
        case .ok:
            // Remove from local list
            threads.removeAll { $0.threadId == threadId }
            if currentThreadStatus?.threadId == threadId {
                currentThreadStatus = nil
            }
            logger.info("Deleted thread: \(threadId)")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            logger.error("Delete thread failed: \(statusCode)")
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Delete thread failed")
        default:
            throw WorkflowExecutionError.serverError(422, "Delete thread failed")
        }
    }

    // MARK: - Pause / Cancel

    func pauseWorkflow(threadId: String) async throws {
        // pause/cancel are app-wide (operate on a thread by id, no library
        // header in their OpenAPI signature) — unlike the other thread ops.
        let response = try await client.api.pauseWorkflowApiWorkflowExecutionThreadsThreadIdPausePost(
            path: .init(threadId: threadId)
        )

        switch response {
        case .ok:
            logger.info("Pause requested for workflow thread: \(threadId)")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Pause workflow failed")
        default:
            throw WorkflowExecutionError.serverError(422, "Pause workflow failed")
        }
    }

    func cancelWorkflow(threadId: String) async throws {
        let response = try await client.api.cancelWorkflowApiWorkflowExecutionThreadsThreadIdCancelPost(
            path: .init(threadId: threadId)
        )

        switch response {
        case .ok:
            logger.info("Cancel requested for workflow thread: \(threadId)")
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Cancel workflow failed")
        default:
            throw WorkflowExecutionError.serverError(422, "Cancel workflow failed")
        }
    }

    func stopWorkflow(threadId: String) async throws {
        try await cancelWorkflow(threadId: threadId)
    }
}

// MARK: - Models

/// Execution thread status
struct ExecutionThread: Identifiable, Hashable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: ExecutionStatus
    let checkpointId: String?
    let error: String?

    var id: String { threadId }
}

extension ExecutionThread: Codable {
    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case status
        case checkpointId = "checkpoint_id"
        case error
    }
}

/// Workflow execution status
enum ExecutionStatus: String, Codable {
    case running
    case paused
    case completed
    case error
    case failed
    case cancelled
    case stopped
    case deleted

    /// Whether the persisted run has stopped for good (#4457).
    ///
    /// `running` and `paused` are the two states a run can still leave on its
    /// own — a paused run resumes and streams again — so everything else is
    /// terminal. That is deliberately the SAME split
    /// `WorkflowExecutionStore.shouldSubscribe(status:)` makes on
    /// `WorkflowStatus`; the two enums are separate, but "can this run still
    /// move?" must not get two different answers. Anything that needs the
    /// split should read it from here rather than re-listing the cases.
    var isTerminal: Bool {
        switch self {
        case .running, .paused:
            return false
        case .completed, .error, .failed, .cancelled, .stopped, .deleted:
            return true
        }
    }
}

// The thread-list response is now the generated `Components.Schemas.ThreadListResponse`
// (mapped in `listThreads`); the hand-written struct was retired in #1712.

// Note: AnyCodable is defined in Document.swift

// MARK: - Errors

enum WorkflowExecutionError: LocalizedError {
    case invalidResponse
    case serverError(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from server"
        case let .serverError(code, message):
            return "Server error (\(code)): \(message)"
        }
    }
}
