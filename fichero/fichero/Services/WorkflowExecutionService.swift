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
    ///
    /// - Parameter selection: WHAT the user pointed at, declared (#4414). The
    ///   server has validated this since #4397, but every shipping call site
    ///   sent ids untyped inside `inputs["selected_doc_ids"]`, so the boundary
    ///   adapter re-derived them as `kind=documents` and a folder run was
    ///   indistinguishable from a 47-document run. An engine-side guarantee the
    ///   client routes around is not a guarantee.
    ///
    ///   `inputs` still carries `selected_doc_ids` alongside it, and that is
    ///   not belt-and-braces: `executor.py:318` and `runtime.py:159` build the
    ///   run's initial state from the untyped inputs, and NOTHING in the server
    ///   reads `request.selection` after the boundary validator. The typed
    ///   field is what makes a wrong request rejectable; the legacy key is
    ///   still what makes the run happen. Dropping it here would execute
    ///   against nothing.
    func executeAccepted(
        workflowId: String,
        inputs: [String: Any] = [:],
        threadId: String? = nil,
        interruptBefore: [String] = [],
        interruptAfter: [String] = [],
        providerOverride: String? = nil,
        modelOverride: String? = nil,
        selection: Components.Schemas.WorkflowSelection? = nil
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
            modelOverride: (modelOverride?.isEmpty == false) ? modelOverride : nil,
            selection: selection
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

    /// Signal a pause. Returns WHAT THE ENGINE SAID (#4402).
    ///
    /// This used to return `Void`: the 200 body was decoded by the generated
    /// client and then dropped on the floor. That mattered because these two
    /// endpoints are *politely* 200 — a thread the engine has never heard of
    /// (a row left behind by a killed engine) answers `status="not_running"`
    /// with a 200, not a 404. Discarding the body made "I have no such run"
    /// indistinguishable from "pausing now", so the caller went on to poll the
    /// stale row's status, got `running` back from the database forever, and
    /// the spinner never stopped. The button looked dead because the ONLY
    /// signal that would have explained it was thrown away.
    ///
    /// pause/cancel are app-wide (they operate on a thread by id, with no
    /// library header in their OpenAPI signature) — unlike the other thread ops.
    @discardableResult
    func pauseWorkflow(threadId: String) async throws -> RunControlOutcome {
        let response = try await client.api.pauseWorkflowApiWorkflowExecutionThreadsThreadIdPausePost(
            path: .init(threadId: threadId)
        )

        switch response {
        case .ok(let okResponse):
            let raw = try okResponse.body.json.status
            let outcome = try Self.controlOutcome(fromRawStatus: raw)
            logger.info(
                "Pause for thread \(threadId): engine said '\(raw)' → \(String(describing: outcome))"
            )
            return outcome
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Pause workflow failed")
        default:
            throw WorkflowExecutionError.serverError(422, "Pause workflow failed")
        }
    }

    /// Signal a cancel. Returns WHAT THE ENGINE SAID — see `pauseWorkflow` for
    /// why the discarded body was the whole of #4402.
    @discardableResult
    func cancelWorkflow(threadId: String) async throws -> RunControlOutcome {
        let response = try await client.api.cancelWorkflowApiWorkflowExecutionThreadsThreadIdCancelPost(
            path: .init(threadId: threadId)
        )

        switch response {
        case .ok(let okResponse):
            let raw = try okResponse.body.json.status
            let outcome = try Self.controlOutcome(fromRawStatus: raw)
            logger.info(
                "Cancel for thread \(threadId): engine said '\(raw)' → \(String(describing: outcome))"
            )
            return outcome
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw WorkflowExecutionError.serverError(statusCode, detail ?? "Cancel workflow failed")
        default:
            throw WorkflowExecutionError.serverError(422, "Cancel workflow failed")
        }
    }

    @discardableResult
    func stopWorkflow(threadId: String) async throws -> RunControlOutcome {
        try await cancelWorkflow(threadId: threadId)
    }

    /// Parse the pause/cancel `status` string into a typed outcome.
    ///
    /// Deliberately tolerant of BOTH response vocabularies, because the engine
    /// is changing underneath this in parallel:
    ///
    /// * The shape shipping today answers only with the request verbs
    ///   (`pause_requested` / `cancel_requested`), `already_terminal`, or
    ///   `not_running`.
    /// * The shape landing alongside this settles stale rows in the database
    ///   itself and answers with the run's new lifecycle status (`cancelled`,
    ///   `paused`, `failed`, …).
    ///
    /// Both must work from the same build, so both are mapped here rather than
    /// gated on a version.
    ///
    /// An UNRECOGNISED status throws. It would be easy to fall through to
    /// `.requested` and let the poll sort it out — that is exactly the silent
    /// substitution that produced #4402, and a new engine verb must announce
    /// itself as a visible error rather than as a control that quietly does
    /// nothing. `nonisolated` so tests can exercise it off the main actor.
    nonisolated static func controlOutcome(fromRawStatus raw: String) throws -> RunControlOutcome {
        switch raw.lowercased() {
        case "pause_requested", "cancel_requested", "stop_requested":
            return .requested
        case "not_running":
            return .notRunning
        case "already_terminal":
            return .alreadyTerminal
        case "running", "accepted":
            return .settled(.running)
        case "paused":
            return .settled(.paused)
        case "completed", "complete", "success", "succeeded":
            return .settled(.completed)
        case "failed", "error":
            return .settled(.failed)
        case "cancelled", "canceled", "stopped", "deleted":
            return .settled(.cancelled)
        default:
            throw WorkflowExecutionError.unrecognizedControlStatus(raw)
        }
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

enum WorkflowExecutionError: LocalizedError, Equatable {
    case invalidResponse
    case serverError(Int, String)
    /// The engine answered a pause/cancel with a `status` this build does not
    /// know (#4402). Loud on purpose — see `controlOutcome(fromRawStatus:)`.
    case unrecognizedControlStatus(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from server"
        case let .serverError(code, message):
            return "Server error (\(code)): \(message)"
        case let .unrecognizedControlStatus(raw):
            return "The engine answered with an unrecognized run status: '\(raw)'"
        }
    }
}

// MARK: - Run-control outcome (#4402)

/// What a pause/cancel POST actually reported.
///
/// The engine answers these politely — a run it has never heard of comes back
/// **200** with `status="not_running"`, not 404. Until #4402 the Swift side
/// decoded that body and discarded it, which is why Stop and Pause looked dead:
/// the one signal that said "there is nothing here to stop" was the one signal
/// nobody read.
enum RunControlOutcome: Equatable, Sendable {
    /// The engine accepted the request and will act on it asynchronously
    /// (`pause_requested` / `cancel_requested`). The run's own stream or a
    /// status refresh carries the transition.
    case requested

    /// The engine settled the run there and then and reported its new
    /// lifecycle status. No poll needed — this IS the authoritative answer.
    case settled(WorkflowStatus)

    /// The run had already finished before the request arrived. The row is
    /// real, so its true terminal state is worth fetching.
    case alreadyTerminal

    /// **The engine has no such run.** Typically a row left behind by a killed
    /// engine: the database still says `running`, the process that would have
    /// answered for it is gone, and no event will ever settle it. Polling its
    /// status returns `running` forever, which is precisely how a row spins
    /// after its workflow has stopped (#4346). The client must settle it.
    case notRunning
}
