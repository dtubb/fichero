import Foundation

// MARK: - Batch Types

/// Batch information from the API
struct BatchInfo: Codable, Identifiable, Equatable, Hashable {
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

    /// Display name for sidebar (uses workflowId or truncated batchId)
    var name: String {
        "Batch \(batchId.prefix(8))..."
    }
}

/// Batch item information
struct BatchItemInfo: Codable, Identifiable, Equatable, Hashable {
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

// MARK: - Batch Request Types

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

}
