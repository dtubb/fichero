import Foundation

// MARK: - Activity Types
// Shared types used by ActivityServiceGenerated and views

/// Wrapper to decode any JSON value as String
struct AnyValueAsString: Codable, Hashable {
    let value: String

    /// Create with a string value directly
    init(_ stringValue: String) {
        self.value = stringValue
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = String(int)
        } else if let double = try? container.decode(Double.self) {
            value = String(double)
        } else if let bool = try? container.decode(Bool.self) {
            value = String(bool)
        } else {
            value = ""
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value)
    }
}

/// Activity item from the API
struct ActivityItem: Codable, Identifiable, Hashable {
    let id: String
    let type: String
    let level: String
    let timestamp: String
    let message: String
    let workflowId: String?
    let batchId: String?
    let threadId: String?
    let nodeId: String?
    private let metadataRaw: [String: AnyValueAsString]?
    let durationMs: Double?
    let error: String?

    /// Metadata with all values as strings
    var metadata: [String: String]? {
        metadataRaw?.mapValues { $0.value }
    }

    enum CodingKeys: String, CodingKey {
        case id, type, level, timestamp, message
        case workflowId = "workflow_id"
        case batchId = "batch_id"
        case threadId = "thread_id"
        case nodeId = "node_id"
        case metadataRaw = "metadata"
        case durationMs = "duration_ms"
        case error
    }

    /// Memberwise initializer for programmatic creation
    init(
        id: String,
        type: String,
        level: String,
        timestamp: String,
        message: String,
        workflowId: String? = nil,
        batchId: String? = nil,
        threadId: String? = nil,
        nodeId: String? = nil,
        metadataRaw: [String: AnyValueAsString]? = nil,
        durationMs: Double? = nil,
        error: String? = nil
    ) {
        self.id = id
        self.type = type
        self.level = level
        self.timestamp = timestamp
        self.message = message
        self.workflowId = workflowId
        self.batchId = batchId
        self.threadId = threadId
        self.nodeId = nodeId
        self.metadataRaw = metadataRaw
        self.durationMs = durationMs
        self.error = error
    }

    var parsedTimestamp: Date? {
        // First try ISO8601 with timezone info (Z or +HH:MM offset)
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = isoFormatter.date(from: timestamp) {
            return date
        }
        isoFormatter.formatOptions = [.withInternetDateTime]
        if let date = isoFormatter.date(from: timestamp) {
            return date
        }

        // Backend often uses datetime.now().isoformat() without timezone info
        // These timestamps are in the server's local time (assumed same as client)
        // Parse them in local timezone to display correctly
        let dateFormatter = DateFormatter()
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        dateFormatter.timeZone = .current  // Use local timezone for timestamps without TZ info

        // Try with microseconds
        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        if let date = dateFormatter.date(from: timestamp) {
            return date
        }

        // Try with milliseconds
        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        if let date = dateFormatter.date(from: timestamp) {
            return date
        }

        // Try without fractional seconds
        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return dateFormatter.date(from: timestamp)
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

    /// Display name for sidebar
    var name: String {
        // Use message truncated, or workflow type
        let displayMessage = message.prefix(40)
        return displayMessage.isEmpty ? type : String(displayMessage) + (message.count > 40 ? "..." : "")
    }

    /// Status icon for sidebar (alias for typeIcon)
    var statusIcon: String { typeIcon }

    /// Status derived from type
    var status: String {
        switch type {
        case "workflow_started", "node_started", "batch_started": return "running"
        case "workflow_completed", "node_completed", "batch_completed", "batch_item_completed": return "completed"
        case "workflow_failed", "node_failed", "batch_item_failed": return "failed"
        case "workflow_paused": return "paused"
        case "workflow_cancelled": return "cancelled"
        default: return level
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
