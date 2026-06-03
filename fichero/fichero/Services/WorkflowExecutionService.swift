import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExecutionService")

/// Service for executing workflows via the backend API
@MainActor
class WorkflowExecutionService: ObservableObject {
    private let baseURL: URL
    private var libraryPath: String?
    private let decoder = JSONDecoder()

    private enum Endpoint {
        static let execute = "/api/workflow-execution/execute"
        static let threads = "/api/workflow-execution/threads"
        static let thread = "/api/workflow-execution/threads/{thread_id}"
        static let threadCancel = "/api/workflow-execution/threads/{thread_id}/cancel"
        static let threadDiagramPNG = "/api/workflow-execution/threads/{thread_id}/diagram.png"
        static let threadHistory = "/api/workflow-execution/threads/{thread_id}/history"
        static let threadPause = "/api/workflow-execution/threads/{thread_id}/pause"
        static let threadResume = "/api/workflow-execution/threads/{thread_id}/resume"
        static let threadRun = "/api/workflow-execution/threads/{thread_id}/run"
        static let threadStatus = "/api/workflow-execution/threads/{thread_id}/status"
        static let allCache = "/api/workflow-execution/cache"
        static let allCacheStats = "/api/workflow-execution/cache/stats"
        static let workflowCache = "/api/workflow-execution/workflows/{workflow_id}/cache"
        static let workflowCacheStats = "/api/workflow-execution/workflows/{workflow_id}/cache/stats"
    }

    @Published var isExecuting: Bool = false
    @Published var threads: [ExecutionThread] = []
    @Published var currentThreadStatus: ExecutionThread?
    @Published var error: String?

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765/api")!, libraryPath: String? = nil) {
        self.baseURL = baseURL
        self.libraryPath = libraryPath
    }

    /// Update the library path (called when library changes)
    func setLibraryPath(_ path: String?) {
        self.libraryPath = path
    }

    /// Create a URLRequest with common headers (auth + library path).
    private func createRequest(url: URL, method: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth(libraryPath: libraryPath)
        return request
    }

    private func url(for endpoint: String, replacements: [String: String] = [:]) -> URL {
        var path = endpoint
        for (placeholder, value) in replacements {
            path = path.replacingOccurrences(of: "{\(placeholder)}", with: value)
        }
        let relativePath = path.hasPrefix("/api/")
            ? String(path.dropFirst("/api/".count))
            : path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return baseURL.appendingPathComponent(relativePath)
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
        let url = url(for: Endpoint.execute)

        var body: [String: Any] = [
            "workflow_id": workflowId,
            "inputs": inputs,
            "interrupt_before": interruptBefore,
            "interrupt_after": interruptAfter
        ]
        if let threadId = threadId {
            body["thread_id"] = threadId
        }

        var request = createRequest(url: url, method: "POST")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        isExecuting = true
        defer { isExecuting = false }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }

        if httpResponse.statusCode >= 400 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            logger.error("Execute workflow failed: \(errorMessage)")
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, errorMessage)
        }

        let thread = try JSONDecoder().decode(ExecutionThread.self, from: data)
        currentThreadStatus = thread
        logger.info("Executed workflow \(workflowId), thread: \(thread.threadId)")
        return thread
    }

    // MARK: - Resume Workflow

    /// Resume a paused workflow
    func resumeWorkflow(threadId: String, inputs: [String: Any]? = nil) async throws -> ExecutionThread {
        let url = url(for: Endpoint.threadResume, replacements: ["thread_id": threadId])

        var request = createRequest(url: url, method: "POST")

        if let inputs = inputs {
            let body: [String: Any] = ["inputs": inputs]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        isExecuting = true
        defer { isExecuting = false }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }

        if httpResponse.statusCode >= 400 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            logger.error("Resume workflow failed: \(errorMessage)")
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, errorMessage)
        }

        let thread = try JSONDecoder().decode(ExecutionThread.self, from: data)
        currentThreadStatus = thread
        logger.info("Resumed workflow thread: \(threadId)")
        return thread
    }

    // MARK: - Get Thread Status

    /// Get the current status of an execution thread
    func getThreadStatus(threadId: String) async throws -> ExecutionThread {
        let url = url(for: Endpoint.threadStatus, replacements: ["thread_id": threadId])

        let request = createRequest(url: url, method: "GET")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }

        if httpResponse.statusCode >= 400 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            logger.error("Get thread status failed: \(errorMessage)")
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, errorMessage)
        }

        let thread = try JSONDecoder().decode(ExecutionThread.self, from: data)
        currentThreadStatus = thread
        return thread
    }

    // MARK: - List Threads

    /// List all execution threads
    func listThreads(limit: Int = 100) async throws -> [ExecutionThread] {
        let url = url(for: Endpoint.threads)
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "limit", value: String(limit))]

        let request = createRequest(url: components.url!, method: "GET")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }

        if httpResponse.statusCode >= 400 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            logger.error("List threads failed: \(errorMessage)")
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, errorMessage)
        }

        let responseBody = try JSONDecoder().decode(ThreadListResponse.self, from: data)
        threads = responseBody.threads
        logger.info("Listed \(self.threads.count) threads")
        return threads
    }

    // MARK: - Delete Thread

    /// Delete an execution thread and its checkpoints
    func deleteThread(threadId: String) async throws {
        let url = url(for: Endpoint.thread, replacements: ["thread_id": threadId])

        let request = createRequest(url: url, method: "DELETE")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }

        if httpResponse.statusCode >= 400 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            logger.error("Delete thread failed: \(errorMessage)")
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, errorMessage)
        }

        // Remove from local list
        threads.removeAll { $0.threadId == threadId }
        if currentThreadStatus?.threadId == threadId {
            currentThreadStatus = nil
        }
        logger.info("Deleted thread: \(threadId)")
    }

    // MARK: - Thread Artifacts

    func getThreadHistory(threadId: String, limit: Int = 100) async throws -> WorkflowExecutionPayload {
        let url = url(for: Endpoint.threadHistory, replacements: ["thread_id": threadId])
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "limit", value: String(limit))]

        let request = createRequest(url: components.url!, method: "GET")
        return try await sendJSONRequest(request)
    }

    func getWorkflowRun(threadId: String) async throws -> WorkflowExecutionPayload {
        let url = url(for: Endpoint.threadRun, replacements: ["thread_id": threadId])
        let request = createRequest(url: url, method: "GET")
        return try await sendJSONRequest(request)
    }

    func getThreadDiagramPNG(threadId: String) async throws -> Data {
        let url = url(for: Endpoint.threadDiagramPNG, replacements: ["thread_id": threadId])
        let request = createRequest(url: url, method: "GET")
        return try await sendDataRequest(request)
    }

    // MARK: - Cache

    func getAllCacheStats() async throws -> WorkflowExecutionPayload {
        let url = url(for: Endpoint.allCacheStats)
        let request = createRequest(url: url, method: "GET")
        return try await sendJSONRequest(request)
    }

    func clearAllCache() async throws {
        let url = url(for: Endpoint.allCache)
        let request = createRequest(url: url, method: "DELETE")
        _ = try await sendDataRequest(request)
    }

    func getWorkflowCacheStats(workflowId: String) async throws -> WorkflowExecutionPayload {
        let url = url(for: Endpoint.workflowCacheStats, replacements: ["workflow_id": workflowId])
        let request = createRequest(url: url, method: "GET")
        return try await sendJSONRequest(request)
    }

    func clearWorkflowCache(workflowId: String) async throws {
        let url = url(for: Endpoint.workflowCache, replacements: ["workflow_id": workflowId])
        let request = createRequest(url: url, method: "DELETE")
        _ = try await sendDataRequest(request)
    }

    // MARK: - Pause / Cancel

    func pauseWorkflow(threadId: String) async throws {
        let url = url(for: Endpoint.threadPause, replacements: ["thread_id": threadId])
        let request = createRequest(url: url, method: "POST")
        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }
        if httpResponse.statusCode >= 400 {
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, "Pause workflow failed")
        }
        logger.info("Pause requested for workflow thread: \(threadId)")
    }

    func cancelWorkflow(threadId: String) async throws {
        let url = url(for: Endpoint.threadCancel, replacements: ["thread_id": threadId])
        let request = createRequest(url: url, method: "POST")
        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }
        if httpResponse.statusCode >= 400 {
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, "Cancel workflow failed")
        }
        logger.info("Cancel requested for workflow thread: \(threadId)")
    }

    private func sendJSONRequest(_ request: URLRequest) async throws -> WorkflowExecutionPayload {
        let data = try await sendDataRequest(request)
        return try decoder.decode(WorkflowExecutionPayload.self, from: data)
    }

    private func sendDataRequest(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw WorkflowExecutionError.invalidResponse
        }

        if httpResponse.statusCode >= 400 {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw WorkflowExecutionError.serverError(httpResponse.statusCode, errorMessage)
        }

        return data
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
    case failed
}

/// Response containing list of threads
struct ThreadListResponse: Codable {
    let threads: [ExecutionThread]
}

struct WorkflowExecutionPayload: Codable, Hashable {
    let values: [String: AnyCodable]

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        values = try container.decode([String: AnyCodable].self)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(values)
    }
}

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
