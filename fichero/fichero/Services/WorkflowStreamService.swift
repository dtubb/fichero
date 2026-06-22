import Combine
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowStreamService")

// MARK: - WorkflowStreamService

/// Service for streaming workflow execution events via SSE
///
/// This service is callback-only - it does NOT store events.
/// All event state is managed by WorkflowExecutionObserver (single source of truth).
@MainActor
class WorkflowStreamService: ObservableObject {
    /// Single source for BOTH the generated REST calls (execute / stop / resume)
    /// AND the SSE byte-stream's host, library path, auth and certificate pinning.
    ///
    /// The stream stays on a raw byte sequence (not the generated
    /// `streamWorkflowEvents…` operation) because that operation buffers its body
    /// via `getResponseBodyAsJSON` — the OpenAPI schema declares the 200 as
    /// `application/json`, not a streaming `text/event-stream` body — so it can
    /// never surface an infinite SSE `HTTPBody` (#1714 / #1943 / #2538).
    ///
    /// But the raw path now derives its host (`client.baseURL`), library path
    /// (`client.currentLibraryPath`), auth (`addEngineAuth`, the same on-disk
    /// token `AuthTokenMiddleware` reads) and certificate pinning
    /// (`RemoteCertificatePinning.configuredSession()`, the same factory
    /// `FicheroClient.makeTransport` uses) from THIS one client — the same one the
    /// generated calls use. That removes the second `FicheroClient` instance the
    /// stream used to read from (via `APIClient`), so the streaming transport can
    /// no longer drift from the generated transport (the #2376 regression).
    private let client: FicheroClient

    /// Current streaming status
    @Published var isStreaming = false

    /// Current thread ID being streamed
    @Published var currentThreadId: String?

    /// Error message if stream fails
    @Published var error: String?

    /// Track if workflow had errors (for final status determination)
    private var hadError = false

    private var streamTask: Task<Void, Never>?

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    deinit {
        streamTask?.cancel()
    }

    /// Build the OpenAPI free-form object container from a JSON-compatible dict,
    /// round-tripping through JSONSerialization to match the previous encoding.
    private func objectContainer(fromJSON dict: [String: Any]) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(OpenAPIRuntime.OpenAPIObjectContainer.self, from: data)
    }

    // MARK: - Public Methods

    /// Execute a workflow using the non-blocking API
    ///
    /// This method:
    /// 1. POSTs to /execute → gets 202 Accepted with thread_id and stream_url
    /// 2. Connects to stream_url for SSE events
    /// 3. Returns immediately once execution has started
    ///
    /// - Parameters:
    ///   - workflowId: The workflow ID to execute
    ///   - inputs: Optional inputs for the workflow
    ///   - onEvent: Callback for each event received
    /// - Returns: The execution response with thread_id and stream_url
    func execute(
        workflowId: String,
        inputs: [String: Any] = [:],
        providerOverride: String? = nil,
        modelOverride: String? = nil,
        onEvent: ((WorkflowStreamEvent) -> Void)? = nil
    ) async throws -> ExecuteAcceptedResponse {
        // Cancel any existing stream
        streamTask?.cancel()
        error = nil
        hadError = false
        isStreaming = true

        // Step 1: POST to /execute to start the workflow (generated client, #1714).
        let request = Components.Schemas.ExecuteWorkflowRequest(
            workflowId: workflowId,
            inputs: .init(additionalProperties: try objectContainer(fromJSON: inputs)),
            checkpointNs: "",
            interruptBefore: [],
            interruptAfter: [],
            providerOverride: (providerOverride?.isEmpty == false) ? providerOverride : nil,
            modelOverride: (modelOverride?.isEmpty == false) ? modelOverride : nil
        )

        logger.info("Starting workflow execution: \(workflowId)")

        let executeResponse = try await client.api.executeWorkflowApiWorkflowExecutionExecutePost(.init(
            body: .json(request)
        ))

        // The backend contract is 202 Accepted; map the handshake payload onto the
        // app model (carries thread_id + stream_url). Other statuses surface as errors.
        let acceptedResponse: ExecuteAcceptedResponse
        switch executeResponse {
        case .accepted(let accepted):
            let payload = try accepted.body.json
            acceptedResponse = ExecuteAcceptedResponse(
                threadId: payload.threadId,
                workflowId: payload.workflowId,
                workflowName: payload.workflowName,
                status: payload.status ?? "accepted",
                streamUrl: payload.streamUrl
            )
        case .unprocessableContent:
            throw WorkflowStreamError.httpError(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw WorkflowStreamError.httpError(statusCode: statusCode)
        }

        currentThreadId = acceptedResponse.threadId
        logger.info("Workflow execution started, thread: \(acceptedResponse.threadId)")

        // Step 2: Connect to the stream URL in a separate task
        streamTask = Task { [weak self] in
            await self?.subscribeToStream(
                threadId: acceptedResponse.threadId,
                onEvent: onEvent
            )
        }

        return acceptedResponse
    }

    // Subscribe to SSE events for a running workflow thread
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    private func subscribeToStream(
        threadId: String,
        onEvent: ((WorkflowStreamEvent) -> Void)?
    ) async {
        // Build the stream URL from the SAME FicheroClient the execute/stop/resume
        // calls use. `client.baseURL` is the host root; the OpenAPI `/api` prefix
        // is appended here to match the generated operation paths. Deriving the
        // host, library path, auth and pinning from this one client keeps the raw
        // byte stream from drifting off the generated transport (#2376 / #2538).
        let streamUrl = client.baseURL
            .appendingPathComponent("api")
            .appendingPathComponent("workflow-execution")
            .appendingPathComponent("stream")
            .appendingPathComponent(threadId)

        var request = URLRequest(url: streamUrl)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.addEngineAuth(libraryPath: client.currentLibraryPath)

        logger.info("Subscribing to event stream: \(streamUrl)")

        do {
            let session = RemoteCertificatePinning.configuredSession()
            let (bytes, response) = try await session.bytes(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw WorkflowStreamError.invalidResponse
            }

            if httpResponse.statusCode != 200 {
                throw WorkflowStreamError.httpError(statusCode: httpResponse.statusCode)
            }

            // Process SSE stream - process data lines immediately
            // (don't wait for empty line separator as bytes.lines may not yield them reliably)
            for try await line in bytes.lines {
                guard !Task.isCancelled else { break }

                // Skip keepalive comments
                if line.hasPrefix(":") {
                    continue
                }

                // Skip event type lines - we get the type from the data JSON
                if line.hasPrefix("event:") {
                    continue
                }

                // Skip empty lines
                if line.isEmpty {
                    continue
                }

                // Process data lines immediately
                if line.hasPrefix("data:") {
                    let jsonString = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                    if let event = parseEvent(jsonString) {
                        await MainActor.run {
                            // Dispatch to callback
                            onEvent?(event)

                            // Track errors and check for terminal events
                            switch event {
                            case .error, .systemicError:
                                self.hadError = true
                                self.isStreaming = false
                            case .complete, .pause:
                                self.isStreaming = false
                            default:
                                break
                            }
                        }
                    }
                }
            }
        } catch {
            if !Task.isCancelled {
                logger.error("Stream error: \(error.localizedDescription)")
                await MainActor.run {
                    self.error = error.localizedDescription
                    self.isStreaming = false
                }
            }
        }

        await MainActor.run {
            self.isStreaming = false
        }
        logger.info("Stream completed for thread: \(threadId)")
    }

    /// Cancel the current stream
    func cancelStream() {
        streamTask?.cancel()
        streamTask = nil
        isStreaming = false
        logger.info("SSE stream cancelled")
    }

    /// Stop a running workflow by deleting its thread
    /// - Parameter threadId: The thread ID to stop
    func stopWorkflow(threadId: String) async throws {
        // First cancel the local stream
        cancelStream()

        logger.info("Stopping workflow thread: \(threadId)")

        // Then delete the thread on the backend (generated client, #1714).
        let response = try await client.api.deleteThreadApiWorkflowExecutionThreadsThreadIdDelete(.init(
            path: .init(threadId: threadId),
        ))

        // 200 = deleted, 404 = already gone (both OK). 404 arrives as `.undocumented`
        // since the generated contract only documents 200/422.
        switch response {
        case .ok:
            logger.info("Workflow thread stopped: \(threadId)")
        case .undocumented(let statusCode, _):
            if statusCode == 404 {
                logger.info("Workflow thread already gone: \(threadId)")
            } else {
                throw WorkflowStreamError.httpError(statusCode: statusCode)
            }
        case .unprocessableContent:
            throw WorkflowStreamError.httpError(statusCode: 422)
        }
    }

    /// Resume a paused workflow
    /// - Parameter threadId: The thread ID to resume
    func resumeWorkflow(threadId: String, onEvent: ((WorkflowStreamEvent) -> Void)? = nil) async throws {
        logger.info("Resuming workflow thread: \(threadId)")

        // Resume the thread (generated client, #1714). No inputs → no body, matching
        // the previous empty-body POST. The SSE resubscribe below stays raw URLSession.
        let response = try await client.api.resumeWorkflowApiWorkflowExecutionThreadsThreadIdResumePost(.init(
            path: .init(threadId: threadId),
        ))

        switch response {
        case .ok:
            break
        case .unprocessableContent:
            throw WorkflowStreamError.httpError(statusCode: 422)
        case .undocumented(let statusCode, _):
            throw WorkflowStreamError.httpError(statusCode: statusCode)
        }

        // Resubscribe to the stream
        isStreaming = true
        currentThreadId = threadId

        streamTask = Task { [weak self] in
            await self?.subscribeToStream(threadId: threadId, onEvent: onEvent)
        }

        logger.info("Workflow thread resumed: \(threadId)")
    }

}
