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
    case complete(threadId: String, checkpointId: String?, finalState: [String: Any]?)
    case pause(threadId: String, checkpointId: String?, currentState: [String: Any]?)
    case error(threadId: String, error: String)

    // Equatable for testing - simplified comparison
    static func == (lhs: WorkflowStreamEvent, rhs: WorkflowStreamEvent) -> Bool {
        switch (lhs, rhs) {
        case (.start(let lhsThread, _), .start(let rhsThread, _)):
            return lhsThread == rhsThread
        case (.nodeBegin(let lhsThread, let lhsNode, _), .nodeBegin(let rhsThread, let rhsNode, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.nodeEnd(let lhsThread, let lhsNode, _, _), .nodeEnd(let rhsThread, let rhsNode, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.complete(let lhsThread, _, _), .complete(let rhsThread, _, _)):
            return lhsThread == rhsThread
        case (.pause(let lhsThread, _, _), .pause(let rhsThread, _, _)):
            return lhsThread == rhsThread
        case (.error(let lhsThread, let lhsError), .error(let rhsThread, let rhsError)):
            return lhsThread == rhsThread && lhsError == rhsError
        default:
            return false
        }
    }
}

/// SSE event data from backend
struct SSEEventData: Codable {
    let event: String
    let threadId: String
    let workflowId: String
    let data: [String: AnyCodableValue]
    let timestamp: String

    enum CodingKeys: String, CodingKey {
        case event
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case data
        case timestamp
    }
}

// MARK: - WorkflowStreamService

/// Service for streaming workflow execution events via SSE
@MainActor
class WorkflowStreamService: ObservableObject {
    private let api: APIClient

    /// Current events from active stream
    @Published var events: [WorkflowStreamEvent] = []

    /// Current streaming status
    @Published var isStreaming = false

    /// Current thread ID being streamed
    @Published var currentThreadId: String?

    /// Error message if stream fails
    @Published var error: String?

    private var streamTask: Task<Void, Never>?

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    deinit {
        streamTask?.cancel()
    }

    // MARK: - Public Methods

    /// Execute a workflow with SSE streaming
    func executeWithStream(
        workflowId: String,
        inputs: [String: Any] = [:],
        threadId: String? = nil,
        onEvent: ((WorkflowStreamEvent) -> Void)? = nil
    ) async throws {
        // Cancel any existing stream
        streamTask?.cancel()
        events = []
        error = nil
        isStreaming = true

        let requestBody: [String: Any] = [
            "workflow_id": workflowId,
            "inputs": inputs,
            "thread_id": threadId as Any,
            "checkpoint_ns": "",
            "interrupt_before": [] as [String],
            "interrupt_after": [] as [String],
        ]

        guard let url = URL(string: "\(api.baseURL)/workflows/execution/execute/stream") else {
            throw WorkflowStreamError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

        // Serialize body
        let bodyData = try JSONSerialization.data(withJSONObject: requestBody, options: [])
        request.httpBody = bodyData

        logger.info("Starting SSE stream for workflow: \(workflowId)")

        // Start stream
        let (bytes, response) = try await URLSession.shared.bytes(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowStreamError.invalidResponse
        }

        if httpResponse.statusCode != 200 {
            throw WorkflowStreamError.httpError(statusCode: httpResponse.statusCode)
        }

        // Process stream
        var eventBuffer = ""

        for try await line in bytes.lines {
            // Parse SSE format
            if line.hasPrefix("event:") {
                // Event type line - we get it from the data JSON
                continue
            } else if line.hasPrefix("data:") {
                let jsonString = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                eventBuffer = jsonString
            } else if line.isEmpty && !eventBuffer.isEmpty {
                // End of event - process it
                if let event = parseEvent(eventBuffer) {
                    events.append(event)
                    onEvent?(event)

                    // Update current thread ID
                    switch event {
                    case .start(let threadId, _):
                        currentThreadId = threadId
                    default:
                        break
                    }

                    // Check for terminal events
                    switch event {
                    case .complete, .error, .pause:
                        isStreaming = false
                    default:
                        break
                    }
                }
                eventBuffer = ""
            }
        }

        isStreaming = false
        logger.info("SSE stream completed for workflow: \(workflowId)")
    }

    /// Cancel the current stream
    func cancelStream() {
        streamTask?.cancel()
        streamTask = nil
        isStreaming = false
        logger.info("SSE stream cancelled")
    }

    // MARK: - Private Methods

    private func parseEvent(_ jsonString: String) -> WorkflowStreamEvent? {
        guard let data = jsonString.data(using: .utf8) else { return nil }

        do {
            let decoder = JSONDecoder()
            let eventData = try decoder.decode(SSEEventData.self, from: data)

            switch eventData.event {
            case "start":
                let workflowName = (eventData.data["workflow_name"]?.stringValue) ?? "Unknown"
                return .start(threadId: eventData.threadId, workflowName: workflowName)

            case "node_begin":
                let nodeId = (eventData.data["node_id"]?.stringValue) ?? ""
                let nodeName = (eventData.data["node_name"]?.stringValue) ?? nodeId
                return .nodeBegin(threadId: eventData.threadId, nodeId: nodeId, nodeName: nodeName)

            case "node_end":
                let nodeId = (eventData.data["node_id"]?.stringValue) ?? ""
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
}
