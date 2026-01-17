import Foundation
import Combine
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowStreamService")

// MARK: - SSE Event Types

/// Events received from workflow execution SSE stream
enum WorkflowStreamEvent: Equatable {
    case start(threadId: String, workflowName: String)
    case nodeBegin(threadId: String, nodeId: String, nodeName: String)
    case nodeEnd(threadId: String, nodeId: String, durationMs: Double, output: [String: Any]?)
    // Parallel execution events
    case parallelStart(threadId: String, nodeId: String, fileTotal: Int)
    case fileStart(threadId: String, nodeId: String, filePath: String, fileIndex: Int, fileTotal: Int, progress: Double)
    case fileComplete(threadId: String, nodeId: String, filePath: String, fileIndex: Int, fileTotal: Int, progress: Double)
    case fileError(threadId: String, nodeId: String, filePath: String, error: String, progress: Double)
    case parallelComplete(threadId: String, nodeId: String, successCount: Int, errorCount: Int, total: Int)
    case complete(threadId: String, checkpointId: String?, finalState: [String: Any]?)
    case pause(threadId: String, checkpointId: String?, currentState: [String: Any]?)
    case error(threadId: String, error: String)
    case systemicError(threadId: String, error: String, errorCount: Int, totalCount: Int)

    // Equatable for testing - simplified comparison
    static func == (lhs: WorkflowStreamEvent, rhs: WorkflowStreamEvent) -> Bool {
        switch (lhs, rhs) {
        case (.start(let lhsThread, _), .start(let rhsThread, _)):
            return lhsThread == rhsThread
        case (.nodeBegin(let lhsThread, let lhsNode, _), .nodeBegin(let rhsThread, let rhsNode, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.nodeEnd(let lhsThread, let lhsNode, _, _), .nodeEnd(let rhsThread, let rhsNode, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.parallelStart(let lhsThread, let lhsNode, _), .parallelStart(let rhsThread, let rhsNode, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.fileStart(let lhsThread, let lhsNode, _, _, _, _), .fileStart(let rhsThread, let rhsNode, _, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.fileComplete(let lhsThread, let lhsNode, _, _, _, _), .fileComplete(let rhsThread, let rhsNode, _, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.fileError(let lhsThread, let lhsNode, _, _, _), .fileError(let rhsThread, let rhsNode, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.parallelComplete(let lhsThread, let lhsNode, _, _, _), .parallelComplete(let rhsThread, let rhsNode, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.complete(let lhsThread, _, _), .complete(let rhsThread, _, _)):
            return lhsThread == rhsThread
        case (.pause(let lhsThread, _, _), .pause(let rhsThread, _, _)):
            return lhsThread == rhsThread
        case (.error(let lhsThread, let lhsError), .error(let rhsThread, let rhsError)):
            return lhsThread == rhsThread && lhsError == rhsError
        case (.systemicError(let lhsThread, _, _, _), .systemicError(let rhsThread, _, _, _)):
            return lhsThread == rhsThread
        default:
            return false
        }
    }
}

/// Response from POST /execute (202 Accepted)
struct ExecuteAcceptedResponse: Codable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: String
    let streamUrl: String

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case status
        case streamUrl = "stream_url"
    }
}

/// SSE event data from backend
struct SSEEventData: Codable {
    let event: String
    let threadId: String
    let workflowId: String
    let data: [String: AnyCodableValue]
    let timestamp: String
    // Parallel execution fields (top-level, not nested in data)
    let nodeId: String?
    let filePath: String?
    let fileIndex: Int?
    let fileTotal: Int?
    let progress: Double?

    enum CodingKeys: String, CodingKey {
        case event
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case data
        case timestamp
        case nodeId = "node_id"
        case filePath = "file_path"
        case fileIndex = "file_index"
        case fileTotal = "file_total"
        case progress
    }
}

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

    /// Subscribe to SSE events for a running workflow thread
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

    // MARK: - Private Methods

    private func parseEvent(_ jsonString: String) -> WorkflowStreamEvent? {
        guard let data = jsonString.data(using: .utf8) else {
            logger.error("[SSE-PARSE] Failed to convert string to data")
            return nil
        }

        do {
            let decoder = JSONDecoder()
            let eventData = try decoder.decode(SSEEventData.self, from: data)
            logger.info("[SSE-PARSE] Event type: \(eventData.event), threadId: \(eventData.threadId)")

            switch eventData.event {
            case "start":
                let workflowName = (eventData.data["workflow_name"]?.stringValue) ?? "Unknown"
                return .start(threadId: eventData.threadId, workflowName: workflowName)

            case "node_begin":
                // node_id can be top-level or in data dict
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let nodeName = (eventData.data["node_name"]?.stringValue) ?? nodeId
                return .nodeBegin(threadId: eventData.threadId, nodeId: nodeId, nodeName: nodeName)

            case "node_end":
                // node_id can be top-level or in data dict
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let durationMs = (eventData.data["duration_ms"]?.doubleValue) ?? 0
                return .nodeEnd(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    durationMs: durationMs,
                    output: nil // Simplified - full output parsing would require more work
                )

            case "complete":
                let checkpointId = eventData.data["checkpoint_id"]?.stringValue
                return .complete(threadId: eventData.threadId, checkpointId: checkpointId, finalState: nil)

            case "pause":
                let checkpointId = eventData.data["checkpoint_id"]?.stringValue
                return .pause(threadId: eventData.threadId, checkpointId: checkpointId, currentState: nil)

            case "error":
                let errorMsg = (eventData.data["error"]?.stringValue) ?? "Unknown error"
                return .error(threadId: eventData.threadId, error: errorMsg)

            case "parallel_start":
                // Parallel processing has begun for a node
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let fileTotal = eventData.fileTotal ?? eventData.data["total"]?.intValue ?? 0
                return .parallelStart(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    fileTotal: fileTotal
                )

            case "file_start":
                // A single file has started processing in parallel
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
                let fileIndex = eventData.fileIndex ?? eventData.data["file_index"]?.intValue ?? 0
                let fileTotal = eventData.fileTotal ?? eventData.data["file_total"]?.intValue ?? 0
                let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
                return .fileStart(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    filePath: filePath,
                    fileIndex: fileIndex,
                    fileTotal: fileTotal,
                    progress: progress
                )

            case "file_complete":
                // A single file has completed processing in parallel
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
                let fileIndex = eventData.fileIndex ?? eventData.data["file_index"]?.intValue ?? 0
                let fileTotal = eventData.fileTotal ?? eventData.data["file_total"]?.intValue ?? 0
                let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
                return .fileComplete(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    filePath: filePath,
                    fileIndex: fileIndex,
                    fileTotal: fileTotal,
                    progress: progress
                )

            case "file_error":
                // A single file failed processing in parallel
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
                let errorMsg = eventData.data["error"]?.stringValue ?? "Unknown error"
                let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
                return .fileError(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    filePath: filePath,
                    error: errorMsg,
                    progress: progress
                )

            case "parallel_complete":
                // node_id is top-level for parallel events
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let successCount = eventData.data["success_count"]?.intValue ?? 0
                let errorCount = eventData.data["error_count"]?.intValue ?? 0
                let total = eventData.fileTotal ?? eventData.data["total"]?.intValue ?? 0
                return .parallelComplete(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    successCount: successCount,
                    errorCount: errorCount,
                    total: total
                )

            case "systemic_error":
                let errorMsg = (eventData.data["error"]?.stringValue) ?? "Unknown error"
                let errorCount = eventData.data["error_count"]?.intValue ?? 0
                let totalCount = eventData.data["total_count"]?.intValue ?? 0
                return .systemicError(
                    threadId: eventData.threadId,
                    error: errorMsg,
                    errorCount: errorCount,
                    totalCount: totalCount
                )

            default:
                logger.warning("Unknown SSE event type: \(eventData.event)")
                return nil
            }
        } catch {
            logger.error("Failed to parse SSE event: \(error.localizedDescription)")
            return nil
        }
    }
}

// MARK: - Errors

enum WorkflowStreamError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int)
    case parseError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL for workflow stream"
        case .invalidResponse:
            return "Invalid response from workflow stream"
        case .httpError(let statusCode):
            return "HTTP error: \(statusCode)"
        case .parseError(let message):
            return "Parse error: \(message)"
        }
    }
}

// MARK: - AnyCodableValue Extensions

extension AnyCodableValue {
    var stringValue: String? {
        switch self {
        case .string(let value):
            return value
        default:
            return nil
        }
    }

    var doubleValue: Double? {
        switch self {
        case .int(let value):
            return Double(value)
        case .double(let value):
            return value
        default:
            return nil
        }
    }

    var intValue: Int? {
        switch self {
        case .int(let value):
            return value
        case .double(let value):
            return Int(value)
        default:
            return nil
        }
    }
}
