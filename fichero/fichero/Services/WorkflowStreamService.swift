import Combine
import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowStreamService")

// MARK: - WorkflowStreamService

/// Service for streaming workflow execution events via SSE
///
/// This service is callback-only - it does NOT store events.
/// Live event state is reduced by the caller into the thread-keyed execution state.
@MainActor
@Observable
class WorkflowStreamService {
    /// Single source for BOTH the generated REST calls (execute / stop / resume)
    /// AND the SSE stream's host, library path and auth.
    ///
    /// The stream is NOT the generated `streamWorkflowEvents…` operation because
    /// that operation buffers its body via `getResponseBodyAsJSON` — the OpenAPI
    /// schema declares the 200 as `application/json`, not a streaming
    /// `text/event-stream` body — so it can never surface an infinite SSE
    /// `HTTPBody` (#1714 / #1943 / #2538). Instead it uses `client.streamLines`,
    /// which issues the request through the SAME `ClientTransport` + middleware
    /// stack the generated calls use. That keeps host, library path and auth in
    /// lockstep with the generated transport (no drift — the #2376 regression) and
    /// lets the stream work over `.https` / `.uds` / an in-process engine, where a
    /// raw `URLSession` to `127.0.0.1:8765` would fail.
    private let client: FicheroClient
    private let executionService: WorkflowExecutionService

    /// Current streaming status
    var isStreaming = false

    /// Current thread ID being streamed
    var currentThreadId: String?

    /// Error message if stream fails
    var error: String?

    /// True once a running stream drops with an error and events are no longer
    /// arriving — the UI shows a "live updates paused" pill instead of leaving a
    /// half-finished run looking stalled (#2518 no-silent-fallback, F7). Set on
    /// the error path, cleared on (re)connect; a clean `.complete`/`.pause` leaves
    /// it false (the run ended normally, it isn't paused).
    private(set) var liveUpdatesUnavailable = false

    // Plumbing, not observed UI state — exclude from @Observable tracking, and
    // `nonisolated(unsafe)` so `deinit` (nonisolated in Swift 6) can cancel it
    // (only mutated on the main actor; `Task.cancel()` is safe from anywhere).
    @ObservationIgnored nonisolated(unsafe) private var streamTasks: [String: Task<Void, Never>] = [:]

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
        self.executionService = WorkflowExecutionService(ficheroClient: ficheroClient)
    }

    deinit {
        streamTasks.values.forEach { $0.cancel() }
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
        onEvent: ((WorkflowStreamEvent) -> Void)? = nil,
        // #4457: `subscribe()` has always forwarded this to `startStream`;
        // `execute()` silently dropped it. A caller that awaits a terminal
        // frame therefore had no way to learn the stream had died, and waited
        // forever. Defaulted, so the existing callers are unaffected.
        onStreamEnd: (@MainActor () -> Void)? = nil
    ) async throws -> ExecuteAcceptedResponse {
        error = nil
        liveUpdatesUnavailable = false  // fresh stream — clear any prior paused state (F7)
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
        startStream(
            threadId: acceptedResponse.threadId,
            onEvent: onEvent,
            onStreamEnd: onStreamEnd
        )

        return acceptedResponse
    }

    /// Subscribe to the live SSE stream for an already-running thread, without
    /// re-POSTing `/execute`. This is the entry point the Activity monitor uses
    /// (`WorkflowExecutionStore`, #2546): a run may have been started in another
    /// window / the Workflow editor, so the only handle we have is its
    /// `threadId`. The byte stream is built from the SAME `FicheroClient` and the
    /// SAME live endpoint (`/api/workflow-execution/stream/{threadId}`) that
    /// `execute(...)` connects to — there is one streaming code path, not two.
    func subscribe(
        threadId: String,
        onEvent: @escaping (WorkflowStreamEvent) -> Void,
        onStreamEnd: (@MainActor () -> Void)? = nil
    ) {
        error = nil
        liveUpdatesUnavailable = false  // fresh stream — clear any prior paused state (F7)
        isStreaming = true
        currentThreadId = threadId

        startStream(threadId: threadId, onEvent: onEvent, onStreamEnd: onStreamEnd)
    }

    /// Whether a live SSE task is currently open for this thread. Used by the
    /// terminal-reconciliation paths (#4346/#4349) to detect a dead stream.
    func isStreamingThread(_ threadId: String) -> Bool {
        streamTasks[threadId] != nil
    }

    /// Fetch the authoritative persisted status for a thread. Reconciliation
    /// seam (#4346/#4349): when the SSE stream dies without a terminal frame,
    /// the persisted run record is the only truth left about the run's state.
    func fetchThreadStatus(threadId: String) async throws -> ExecutionThread {
        try await executionService.getThreadStatus(threadId: threadId)
    }

    /// Poll the persisted run record until it reports a terminal status, for a
    /// run whose SSE stream ended without a terminal frame (#4457).
    ///
    /// When the transport dies mid-run no `complete`/`error`/`cancelled` frame
    /// can ever arrive, so a caller awaiting one waits forever. The persisted
    /// record is the only remaining truth about the run, and `fetchThreadStatus`
    /// is the seam that reads it (#4346/#4349).
    ///
    /// Returns the terminal record, or `nil` if the run was still live when the
    /// attempts ran out. **A `nil` means "unknown", not "still running"** — the
    /// caller must settle its UI anyway rather than keep waiting, because the
    /// whole point is that nothing else is coming.
    ///
    /// Bounded on the same 1s-then-5s / 12-attempt cadence as
    /// `WorkflowExecutionStore.reconcileAfterStreamEnd`, so a dead engine cannot
    /// be polled forever. Deliberately shared rather than reimplemented per
    /// surface: a second copy of this loop is how the Activity and editor paths
    /// came to disagree about the same run in the first place.
    func settleAfterStreamEnd(threadId: String) async -> ExecutionThread? {
        for attempt in 0..<12 {
            try? await Task.sleep(for: .seconds(attempt == 0 ? 1 : 5))
            if Task.isCancelled { return nil }
            do {
                let thread = try await fetchThreadStatus(threadId: threadId)
                if thread.status.isTerminal { return thread }
            } catch {
                let attemptNumber = attempt + 1
                logger.warning(
                    """
                    settleAfterStreamEnd: \(threadId, privacy: .public) \
                    attempt \(attemptNumber) failed: \
                    \(error.localizedDescription, privacy: .public)
                    """
                )
            }
        }
        logger.error(
            """
            settleAfterStreamEnd: giving up on \(threadId, privacy: .public) — \
            caller must settle its own UI rather than wait for a frame that \
            cannot arrive
            """
        )
        return nil
    }

    private func startStream(
        threadId: String,
        onEvent: ((WorkflowStreamEvent) -> Void)?,
        onStreamEnd: (@MainActor () -> Void)? = nil
    ) {
        streamTasks[threadId]?.cancel()
        streamTasks[threadId] = Task { [weak self] in
            await self?.subscribeToStream(threadId: threadId, onEvent: onEvent)
            guard !Task.isCancelled else { return }
            self?.streamTasks[threadId] = nil
            self?.isStreaming = self?.streamTasks.isEmpty == false
            // The stream ended on its own (terminal frame, server close, or
            // transport death) — NOT via cancelStream. Let the owner reconcile
            // run state against the persisted record (#4346/#4349).
            onStreamEnd?()
        }
    }

    // Subscribe to SSE events for a running workflow thread
    private func subscribeToStream(
        threadId: String,
        onEvent: ((WorkflowStreamEvent) -> Void)?
    ) async {
        // Route through the SAME FicheroClient the execute/stop/resume calls use.
        // `streamLines` issues the request through the shared ClientTransport +
        // middleware stack, so host, library path and auth stay in lockstep with
        // the generated transport (#2376 / #2538) and the stream works over
        // `.https` / `.uds` / in-process. A display URL is derived only for the
        // failure message — the fetch itself never touches a raw URL.
        let streamUrl = client.apiBaseURL
            .appendingPathComponent("workflow-execution")
            .appendingPathComponent("stream")
            .appendingPathComponent(threadId)

        logger.info("Subscribing to event stream: \(streamUrl)")

        do {
            let (status, lines) = try await client.streamLines(
                pathComponents: ["workflow-execution", "stream", threadId]
            )

            if status != 200 {
                throw WorkflowStreamError.httpError(statusCode: status)
            }

            liveUpdatesUnavailable = false  // connected — run events flowing (F7)

            try await consumeStreamLines(lines, onEvent: onEvent)
        } catch {
            if !Task.isCancelled {
                handleStreamFailure(
                    error,
                    streamUrl: streamUrl
                )
            }
        }

        logger.info("Stream completed for thread: \(threadId)")
    }

    /// Process SSE data lines immediately as they arrive (don't wait for the
    /// empty line separator, which the byte stream may not yield reliably).
    private func consumeStreamLines(
        _ lines: AsyncThrowingStream<String, any Error>,
        onEvent: ((WorkflowStreamEvent) -> Void)?
    ) async throws {
        for try await line in lines {
            guard !Task.isCancelled else { return }

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
                    await dispatchParsedEvent(event, onEvent: onEvent)
                }
            }
        }
    }

    /// Dispatch a parsed event to the caller's callback and track errors /
    /// terminal events for the service's own streaming state.
    private func dispatchParsedEvent(
        _ event: WorkflowStreamEvent,
        onEvent: ((WorkflowStreamEvent) -> Void)?
    ) async {
        await MainActor.run {
            // Dispatch to callback
            onEvent?(event)
        }
    }

    /// Handle a failure from the SSE byte stream (non-cancellation only).
    private func handleStreamFailure(
        _ error: Error,
        streamUrl: URL
    ) {
        let message = WorkflowStreamError.streamFailureDescription(error: error, streamURL: streamUrl)
        logger.error("Stream error: \(message)")
        self.error = message
        // Events stopped mid-run — surface a "live updates paused"
        // pill rather than leaving the run looking stalled (F7).
        self.liveUpdatesUnavailable = true
    }

    /// Cancel the current stream
    func cancelStream(threadId: String? = nil) {
        if let threadId {
            streamTasks.removeValue(forKey: threadId)?.cancel()
        } else {
            streamTasks.values.forEach { $0.cancel() }
            streamTasks.removeAll()
        }
        isStreaming = !streamTasks.isEmpty
        liveUpdatesUnavailable = false  // user-cancelled is not a paused stream (F7)
        logger.info("SSE stream cancelled")
    }

    /// Stop a running workflow by requesting cancellation
    /// - Parameter threadId: The thread ID to stop
    func stopWorkflow(threadId: String) async throws {
        // First cancel the local stream
        cancelStream(threadId: threadId)

        logger.info("Stopping workflow thread: \(threadId)")
        try await executionService.stopWorkflow(threadId: threadId)
        logger.info("Workflow thread stopped: \(threadId)")
    }

    /// Resume a paused workflow
    /// - Parameter threadId: The thread ID to resume
    func resumeWorkflow(threadId: String, onEvent: ((WorkflowStreamEvent) -> Void)? = nil) async throws {
        logger.info("Resuming workflow thread: \(threadId)")

        // Discard the returned ExecutionThread snapshot: only the side effect
        // (backend resumes the run) matters here — the stream resubscription
        // below drives live state. Failures still propagate via `try` (#3978).
        _ = try await executionService.resumeWorkflow(threadId: threadId)

        // Resubscribe to the stream
        isStreaming = true
        currentThreadId = threadId

        startStream(threadId: threadId, onEvent: onEvent)

        logger.info("Workflow thread resumed: \(threadId)")
    }

}
