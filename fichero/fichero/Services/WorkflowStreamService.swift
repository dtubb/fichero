import Combine
import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowStreamService")

// MARK: - WorkflowStreamService

/// Service for streaming workflow execution events via SSE
///
/// This service is callback-only - it does NOT store events.
/// Live event state is reduced by the caller into the thread-keyed execution state.
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
    private let executionService: WorkflowExecutionService

    /// Certificate-pinned URLSession reused across stream subscriptions.
    /// URLSession.bytes(for:) only invokes the delegate challenge handler
    /// when the session is retained at the class level, not as a per-call local.
    private let urlSession: URLSession = RemoteCertificatePinning.configuredSession()

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
        self.executionService = WorkflowExecutionService(ficheroClient: ficheroClient)
    }

    deinit {
        streamTask?.cancel()
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
        onAccepted: ((ExecuteAcceptedResponse) -> Void)? = nil,
        onEvent: ((WorkflowStreamEvent) -> Void)? = nil
    ) async throws -> ExecuteAcceptedResponse {
        // Cancel any existing stream
        streamTask?.cancel()
        error = nil
        hadError = false
        isStreaming = true

        logger.info("Starting workflow execution: \(workflowId)")
        let acceptedResponse = try await executionService.executeAccepted(
            workflowId: workflowId,
            inputs: inputs,
            providerOverride: providerOverride,
            modelOverride: modelOverride
        )

        currentThreadId = acceptedResponse.threadId
        logger.info("Workflow execution started, thread: \(acceptedResponse.threadId)")

        onAccepted?(acceptedResponse)

        // Step 2: Connect to the stream URL in a separate task
        streamTask = Task { [weak self] in
            await self?.subscribeToStream(
                threadId: acceptedResponse.threadId,
                onEvent: onEvent
            )
        }

        return acceptedResponse
    }

    /// Subscribe to the live SSE stream for an already-running thread, without
    /// re-POSTing `/execute`. This is the entry point the Activity monitor uses
    /// (`WorkflowExecutionStore`, #2546): a run may have been started in another
    /// window / the Workflow editor, so the only handle we have is its
    /// `threadId`. The byte stream is built from the SAME `FicheroClient` and the
    /// SAME live endpoint (`/api/workflow-execution/stream/{threadId}`) that
    /// `execute(...)` connects to — there is one streaming code path, not two.
    func subscribe(threadId: String, onEvent: @escaping (WorkflowStreamEvent) -> Void) {
        streamTask?.cancel()
        error = nil
        hadError = false
        isStreaming = true
        currentThreadId = threadId

        streamTask = Task { [weak self] in
            await self?.subscribeToStream(threadId: threadId, onEvent: onEvent)
        }
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
        let request = engineEventStreamRequest(
            baseURL: client.apiBaseURL,
            pathComponents: ["workflow-execution", "stream", threadId],
            libraryPath: client.currentLibraryPath
        )
        let streamUrl = request.url!

        logger.info("Subscribing to event stream: \(streamUrl)")

        do {
            let (bytes, response) = try await urlSession.bytes(for: request)

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
                let message = WorkflowStreamError.streamFailureDescription(error: error, streamURL: streamUrl)
                logger.error("Stream error: \(message)")
                await MainActor.run {
                    self.error = message
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

    /// Stop a running workflow by requesting cancellation
    /// - Parameter threadId: The thread ID to stop
    func stopWorkflow(threadId: String) async throws {
        // First cancel the local stream
        cancelStream()

        logger.info("Stopping workflow thread: \(threadId)")
        try await executionService.stopWorkflow(threadId: threadId)
        logger.info("Workflow thread stopped: \(threadId)")
    }

    /// Resume a paused workflow
    /// - Parameter threadId: The thread ID to resume
    func resumeWorkflow(threadId: String, onEvent: ((WorkflowStreamEvent) -> Void)? = nil) async throws {
        logger.info("Resuming workflow thread: \(threadId)")

        try await executionService.resumeWorkflow(threadId: threadId)

        // Resubscribe to the stream
        isStreaming = true
        currentThreadId = threadId

        streamTask = Task { [weak self] in
            await self?.subscribeToStream(threadId: threadId, onEvent: onEvent)
        }

        logger.info("Workflow thread resumed: \(threadId)")
    }

}
