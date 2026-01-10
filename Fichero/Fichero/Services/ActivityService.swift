import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ActivityService")

/// Service for interacting with the Activity API
@MainActor
class ActivityService {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Activity Queries

    /// Fetch recent activities
    func getRecentActivities(limit: Int = 50) async throws -> [ActivityItem] {
        let response: [ActivityItem] = try await apiClient.get(
            "/api/activity/recent?limit=\(limit)"
        )
        return response
    }

    /// Query activities with filters
    func queryActivities(
        types: [String]? = nil,
        levels: [String]? = nil,
        workflowId: String? = nil,
        batchId: String? = nil,
        since: Date? = nil,
        until: Date? = nil,
        search: String? = nil,
        limit: Int = 100,
        offset: Int = 0
    ) async throws -> [ActivityItem] {
        var queryParams: [String] = []

        if let types = types, !types.isEmpty {
            queryParams.append("types=\(types.joined(separator: ","))")
        }
        if let levels = levels, !levels.isEmpty {
            queryParams.append("levels=\(levels.joined(separator: ","))")
        }
        if let workflowId = workflowId {
            queryParams.append("workflow_id=\(workflowId)")
        }
        if let batchId = batchId {
            queryParams.append("batch_id=\(batchId)")
        }
        if let since = since {
            queryParams.append("since=\(ISO8601DateFormatter().string(from: since))")
        }
        if let until = until {
            queryParams.append("until=\(ISO8601DateFormatter().string(from: until))")
        }
        if let search = search {
            queryParams.append("search=\(search.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? search)")
        }
        queryParams.append("limit=\(limit)")
        queryParams.append("offset=\(offset)")

        let queryString = queryParams.isEmpty ? "" : "?\(queryParams.joined(separator: "&"))"
        let response: [ActivityItem] = try await apiClient.get("/api/activity\(queryString)")
        return response
    }

    /// Get activity statistics
    func getActivityStats(hours: Int = 24) async throws -> ActivityStats {
        let response: ActivityStats = try await apiClient.get(
            "/api/activity/stats?hours=\(hours)"
        )
        return response
    }

    /// Get activities for a specific workflow
    func getWorkflowActivities(workflowId: String, limit: Int = 100) async throws -> [ActivityItem] {
        let response: [ActivityItem] = try await apiClient.get(
            "/api/activity/workflow/\(workflowId)?limit=\(limit)"
        )
        return response
    }

    /// Get activities for a specific batch
    func getBatchActivities(batchId: String, limit: Int = 100) async throws -> [ActivityItem] {
        let response: [ActivityItem] = try await apiClient.get(
            "/api/activity/batch/\(batchId)?limit=\(limit)"
        )
        return response
    }

    // MARK: - Batch Operations

    /// Create a new batch
    func createBatch(workflowId: String, items: [BatchInputItem], maxConcurrent: Int = 5) async throws -> BatchInfo {
        let body = CreateBatchRequest(
            workflowId: workflowId,
            items: items,
            maxConcurrent: maxConcurrent
        )
        let response: BatchInfo = try await apiClient.post("/api/batches", body: body)
        return response
    }

    /// Get batch details
    func getBatch(batchId: String, includeItems: Bool = true) async throws -> BatchInfo {
        let response: BatchInfo = try await apiClient.get(
            "/api/batches/\(batchId)?include_items=\(includeItems)"
        )
        return response
    }

    /// List all batches
    func listBatches(status: String? = nil, limit: Int = 100) async throws -> [BatchInfo] {
        var queryString = "?limit=\(limit)"
        if let status = status {
            queryString += "&status=\(status)"
        }
        let response: [BatchInfo] = try await apiClient.get("/api/batches\(queryString)")
        return response
    }

    /// Get batch progress
    func getBatchProgress(batchId: String) async throws -> BatchProgress {
        let response: BatchProgress = try await apiClient.get(
            "/api/batches/\(batchId)/progress"
        )
        return response
    }

    /// Pause a batch
    func pauseBatch(batchId: String) async throws -> BatchInfo {
        let response: BatchInfo = try await apiClient.post(
            "/api/batches/\(batchId)/pause"
        )
        return response
    }

    /// Cancel a batch
    func cancelBatch(batchId: String) async throws -> BatchInfo {
        let response: BatchInfo = try await apiClient.post(
            "/api/batches/\(batchId)/cancel"
        )
        return response
    }

    /// Delete a batch
    func deleteBatch(batchId: String) async throws {
        try await apiClient.delete("/api/batches/\(batchId)")
    }
}

// MARK: - Request Models

/// Request body for creating a batch
struct CreateBatchRequest: Codable {
    let workflowId: String
    let items: [BatchInputItem]
    let maxConcurrent: Int

    enum CodingKeys: String, CodingKey {
        case workflowId = "workflow_id"
        case items
        case maxConcurrent = "max_concurrent"
    }
}

/// Input item for batch creation - represents inputs for a single workflow execution
struct BatchInputItem: Codable {
    /// Dictionary of input values keyed by input port name
    let inputs: [String: String]

    init(inputs: [String: String]) {
        self.inputs = inputs
    }
}

// MARK: - Response Models

/// Activity item from the API
struct ActivityItem: Codable, Identifiable {
    let id: String
    let type: String
    let level: String
    let timestamp: String
    let message: String
    let workflowId: String?
    let batchId: String?
    let threadId: String?
    let nodeId: String?
    let metadata: [String: String]?
    let durationMs: Double?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case id, type, level, timestamp, message
        case workflowId = "workflow_id"
        case batchId = "batch_id"
        case threadId = "thread_id"
        case nodeId = "node_id"
        case metadata
        case durationMs = "duration_ms"
        case error
    }

    var parsedTimestamp: Date? {
        ISO8601DateFormatter().date(from: timestamp)
    }

    var levelColor: String {
        switch level {
        case "error", "critical": return "red"
        case "warning": return "orange"
        case "info": return "blue"
        case "debug": return "gray"
        default: return "primary"
        }
    }

    var typeIcon: String {
        switch type {
        case "workflow_started": return "play.circle"
        case "workflow_completed": return "checkmark.circle"
        case "workflow_failed": return "xmark.circle"
        case "workflow_paused": return "pause.circle"
        case "workflow_resumed": return "play.circle"
        case "workflow_cancelled": return "stop.circle"
        case "node_started": return "circle.dashed"
        case "node_completed": return "circle.fill"
        case "node_failed": return "exclamationmark.circle"
        case "batch_started": return "square.stack.3d.up"
        case "batch_completed": return "square.stack.3d.up.fill"
        case "batch_item_completed": return "checkmark.square"
        case "batch_item_failed": return "xmark.square"
        default: return "circle"
        }
    }
}

/// Activity statistics from the API
struct ActivityStats: Codable {
    let totalActivities: Int
    let activitiesByType: [String: Int]
    let activitiesByLevel: [String: Int]
    let errorCount: Int
    let warningCount: Int
    let avgWorkflowDurationMs: Double?
    let successRate: Double
    let periodStart: String
    let periodEnd: String

    enum CodingKeys: String, CodingKey {
        case totalActivities = "total_activities"
        case activitiesByType = "activities_by_type"
        case activitiesByLevel = "activities_by_level"
        case errorCount = "error_count"
        case warningCount = "warning_count"
        case avgWorkflowDurationMs = "avg_workflow_duration_ms"
        case successRate = "success_rate"
        case periodStart = "period_start"
        case periodEnd = "period_end"
    }
}

/// Batch information from the API
struct BatchInfo: Codable, Identifiable {
    let batchId: String
    let workflowId: String
    let status: String
    let totalItems: Int
    let completedItems: Int
    let failedItems: Int
    let maxConcurrent: Int
    let createdAt: String
    let startedAt: String?
    let completedAt: String?
    let errorMessage: String?
    let items: [BatchItemInfo]?

    var id: String { batchId }

    enum CodingKeys: String, CodingKey {
        case batchId = "batch_id"
        case workflowId = "workflow_id"
        case status
        case totalItems = "total_items"
        case completedItems = "completed_items"
        case failedItems = "failed_items"
        case maxConcurrent = "max_concurrent"
        case createdAt = "created_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case errorMessage = "error_message"
        case items
    }

    var progressPercent: Double {
        guard totalItems > 0 else { return 0 }
        return Double(completedItems) / Double(totalItems) * 100
    }

    var statusIcon: String {
        switch status {
        case "pending": return "clock"
        case "running": return "play.circle.fill"
        case "paused": return "pause.circle.fill"
        case "completed": return "checkmark.circle.fill"
        case "partial_failure": return "exclamationmark.triangle.fill"
        case "failed": return "xmark.circle.fill"
        case "cancelled": return "stop.circle.fill"
        default: return "questionmark.circle"
        }
    }

    var statusColor: String {
        switch status {
        case "pending": return "gray"
        case "running": return "blue"
        case "paused": return "yellow"
        case "completed": return "green"
        case "partial_failure": return "orange"
        case "failed": return "red"
        case "cancelled": return "gray"
        default: return "primary"
        }
    }
}

/// Batch item information
struct BatchItemInfo: Codable, Identifiable {
    let threadId: String
    let itemIndex: Int
    let inputs: [String: String]?
    let status: String
    let error: String?
    let startedAt: String?
    let completedAt: String?

    var id: String { threadId }

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case itemIndex = "item_index"
        case inputs
        case status
        case error
        case startedAt = "started_at"
        case completedAt = "completed_at"
    }
}

/// Batch progress information
struct BatchProgress: Codable {
    let batchId: String
    let totalItems: Int
    let completedItems: Int
    let failedItems: Int
    let runningItems: Int
    let pendingItems: Int
    let progressPercent: Double
    let estimatedRemainingSeconds: Double?
    let avgItemDurationSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case batchId = "batch_id"
        case totalItems = "total_items"
        case completedItems = "completed_items"
        case failedItems = "failed_items"
        case runningItems = "running_items"
        case pendingItems = "pending_items"
        case progressPercent = "progress_percent"
        case estimatedRemainingSeconds = "estimated_remaining_seconds"
        case avgItemDurationSeconds = "avg_item_duration_seconds"
    }
}
