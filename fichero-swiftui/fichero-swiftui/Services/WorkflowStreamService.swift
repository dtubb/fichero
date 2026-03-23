import Foundation
import Combine
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "WorkflowStreamService")

// MARK: - WorkflowStreamService

/// Service for streaming workflow execution events via SSE
///
/// This service is callback-only - it does NOT store events.
/// All event state is managed by WorkflowExecutionObserver (single source of truth).
@MainActor
class WorkflowStreamService: ObservableObject {
    private let api: APIClient

    /// Current streaming status
    @Published var isStreaming = false

    /// Current thread ID being streamed
    @Published var currentThreadId: String?

    /// Error message if stream fails
    @Published var error: String?

    /// Track if workflow had errors (for final status determination)
    private var hadError = false

    private var streamTask: Task<Void, Never>?

    init(apiClient: APIClient) {
        self.api = apiClient
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
        onEvent: ((WorkflowStreamEvent) -> Void)? = nil
    ) async throws -> ExecuteAcceptedResponse {
        // Cancel any existing stream
        streamTask?.cancel()
        error = nil
        hadError = false
        isStreaming = true

        // Step 1: POST to /execute to start the workflow
        let requestBody: [String: Any] = [
            "workflow_id": workflowId,
            "inputs": inputs,
            "checkpoint_ns": "",
            "interrupt_before": [] as [String],
            "interrupt_after": [] as [String]
        ]

        guard let executeUrl = URL(string: "\(api.baseURL)/workflow-execution/execute") else {
            throw WorkflowStreamError.invalidURL
        }

        var executeRequest = URLRequest(url: executeUrl)
        executeRequest.httpMethod = "POST"
        executeRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Add library path header (required by backend)
        if let libraryPath = api.currentLibraryPath {
            executeRequest.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let bodyData = try JSONSerialization.data(withJSONObject: requestBody, options: [])
        executeRequest.httpBody = bodyData

        logger.info("Starting workflow execution: \(workflowId)")

        let (responseData, executeResponse) = try await URLSession.shared.data(for: executeRequest)

        guard let httpResponse = executeResponse as? HTTPURLResponse else {
            throw WorkflowStreamError.invalidResponse
        }

        // Accept 202 (non-blocking) or 200 (legacy blocking)
        guard httpResponse.statusCode == 202 || httpResponse.statusCode == 200 else {
            throw WorkflowStreamError.httpError(statusCode: httpResponse.statusCode)
        }

        // Parse the response
        let decoder = JSONDecoder()
        let acceptedResponse = try decoder.decode(ExecuteAcceptedResponse.self, from: responseData)

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
        guard let streamUrl = URL(string: "\(api.baseURL)/workflow-execution/stream/\(threadId)") else {
            await MainActor.run {
                self.error = "Invalid stream URL"
                self.isStreaming = false
            }
            return
        }

        var request = URLRequest(url: streamUrl)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

        // Add library path header (required by backend)
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        logger.info("Subscribing to event stream: \(streamUrl)")

        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)

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

        // Then delete the thread on the backend
        guard let url = URL(string: "\(api.baseURL)/workflow-execution/threads/\(threadId)") else {
            throw WorkflowStreamError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"

        // Add library path header (required by backend)
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        logger.info("Stopping workflow thread: \(threadId)")

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowStreamError.invalidResponse
        }

        // 200 = deleted, 404 = already gone (both OK)
        if httpResponse.statusCode != 200 && httpResponse.statusCode != 404 {
            throw WorkflowStreamError.httpError(statusCode: httpResponse.statusCode)
        }

        logger.info("Workflow thread stopped: \(threadId)")
    }

    /// Resume a paused workflow
    /// - Parameter threadId: The thread ID to resume
    func resumeWorkflow(threadId: String, onEvent: ((WorkflowStreamEvent) -> Void)? = nil) async throws {
        guard let url = URL(string: "\(api.baseURL)/workflow-execution/threads/\(threadId)/resume") else {
            throw WorkflowStreamError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Add library path header (required by backend)
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        logger.info("Resuming workflow thread: \(threadId)")

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowStreamError.invalidResponse
        }

        if httpResponse.statusCode != 200 {
            throw WorkflowStreamError.httpError(statusCode: httpResponse.statusCode)
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
