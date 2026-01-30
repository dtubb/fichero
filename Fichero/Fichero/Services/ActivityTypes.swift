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

    init(
        totalActivities: Int,
        activitiesByType: [String: Int],
        activitiesByLevel: [String: Int],
        errorCount: Int,
        warningCount: Int,
        avgWorkflowDurationMs: Double?,
        successRate: Double,
        periodStart: String,
        periodEnd: String
    ) {
        self.totalActivities = totalActivities
        self.activitiesByType = activitiesByType
        self.activitiesByLevel = activitiesByLevel
        self.errorCount = errorCount
        self.warningCount = warningCount
        self.avgWorkflowDurationMs = avgWorkflowDurationMs
        self.successRate = successRate
        self.periodStart = periodStart
        self.periodEnd = periodEnd
    }
}

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

// MARK: - Checkpoint History Types

/// A single checkpoint snapshot in the execution history
struct CheckpointSnapshot: Codable, Identifiable {
    let checkpointId: String
    let parentCheckpointId: String?
    let step: Int
    let timestamp: String?
    let nodeName: String?
    let stateValues: [String: CheckpointValue]
    let writes: [String: CheckpointValue]
    let nextNodes: [String]

    var id: String { checkpointId }

    enum CodingKeys: String, CodingKey {
        case checkpointId = "checkpoint_id"
        case parentCheckpointId = "parent_checkpoint_id"
        case step
        case timestamp
        case nodeName = "node_name"
        case stateValues = "state_values"
        case writes
        case nextNodes = "next_nodes"
    }
}

/// Response with full checkpoint history for a thread
struct CheckpointHistoryResponse: Codable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let totalSteps: Int
    let checkpoints: [CheckpointSnapshot]

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case totalSteps = "total_steps"
        case checkpoints
    }
}

/// Type-erased Codable wrapper for checkpoint state values
struct CheckpointValue: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()

        if container.decodeNil() {
            self.value = NSNull()
        } else if let bool = try? container.decode(Bool.self) {
            self.value = bool
        } else if let int = try? container.decode(Int.self) {
            self.value = int
        } else if let double = try? container.decode(Double.self) {
            self.value = double
        } else if let string = try? container.decode(String.self) {
            self.value = string
        } else if let array = try? container.decode([CheckpointValue].self) {
            self.value = array.map { $0.value }
        } else if let dict = try? container.decode([String: CheckpointValue].self) {
            self.value = dict.mapValues { $0.value }
        } else {
            self.value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()

        switch value {
        case is NSNull:
            try container.encodeNil()
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { CheckpointValue($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { CheckpointValue($0) })
        default:
            try container.encodeNil()
        }
    }

    /// Get value as string for display
    var stringValue: String {
        switch value {
        case is NSNull:
            return "null"
        case let bool as Bool:
            return bool ? "true" : "false"
        case let int as Int:
            return String(int)
        case let double as Double:
            return String(format: "%.2f", double)
        case let string as String:
            return string
        case let array as [Any]:
            return "[\(array.count) items]"
        case let dict as [String: Any]:
            return "{\(dict.count) keys}"
        default:
            return String(describing: value)
        }
    }
}

// MARK: - Workflow Run Response

/// Response with workflow run data (code, logs, etc.)
struct WorkflowRunResponse: Codable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let pythonCode: String?
    let executionLog: String?
    let status: String
    let startedAt: String?
    let completedAt: String?
    let durationMs: Double?
    let error: String?
    let workflowSnapshot: [String: Any]?
    let nodeNameMap: [String: String]?
    let progressTimeline: [String: Any]?
    let diagramMermaid: String?

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case pythonCode = "python_code"
        case executionLog = "execution_log"
        case status
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationMs = "duration_ms"
        case error
        case workflowSnapshot = "workflow_snapshot"
        case nodeNameMap = "node_name_map"
        case progressTimeline = "progress_timeline"
        case diagramMermaid = "diagram_mermaid"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        threadId = try container.decode(String.self, forKey: .threadId)
        workflowId = try container.decode(String.self, forKey: .workflowId)
        workflowName = try container.decode(String.self, forKey: .workflowName)
        pythonCode = try container.decodeIfPresent(String.self, forKey: .pythonCode)
        executionLog = try container.decodeIfPresent(String.self, forKey: .executionLog)
        status = try container.decode(String.self, forKey: .status)
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        durationMs = try container.decodeIfPresent(Double.self, forKey: .durationMs)
        error = try container.decodeIfPresent(String.self, forKey: .error)

        // Decode JSON fields using CheckpointValue for type erasure
        if let snapshotData = try? container.decodeIfPresent(CheckpointValue.self, forKey: .workflowSnapshot) {
            workflowSnapshot = snapshotData.value as? [String: Any]
        } else {
            workflowSnapshot = nil
        }

        nodeNameMap = try container.decodeIfPresent([String: String].self, forKey: .nodeNameMap)

        if let timelineData = try? container.decodeIfPresent(CheckpointValue.self, forKey: .progressTimeline) {
            progressTimeline = timelineData.value as? [String: Any]
        } else {
            progressTimeline = nil
        }

        diagramMermaid = try container.decodeIfPresent(String.self, forKey: .diagramMermaid)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(threadId, forKey: .threadId)
        try container.encode(workflowId, forKey: .workflowId)
        try container.encode(workflowName, forKey: .workflowName)
        try container.encodeIfPresent(pythonCode, forKey: .pythonCode)
        try container.encodeIfPresent(executionLog, forKey: .executionLog)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(startedAt, forKey: .startedAt)
        try container.encodeIfPresent(completedAt, forKey: .completedAt)
        try container.encodeIfPresent(durationMs, forKey: .durationMs)
        try container.encodeIfPresent(error, forKey: .error)

        if let workflowSnapshot = workflowSnapshot {
            try container.encode(CheckpointValue(workflowSnapshot), forKey: .workflowSnapshot)
        }
        try container.encodeIfPresent(nodeNameMap, forKey: .nodeNameMap)
        if let progressTimeline = progressTimeline {
            try container.encode(CheckpointValue(progressTimeline), forKey: .progressTimeline)
        }
        try container.encodeIfPresent(diagramMermaid, forKey: .diagramMermaid)
    }

    init(
        threadId: String,
        workflowId: String,
        workflowName: String,
        pythonCode: String?,
        executionLog: String?,
        status: String,
        startedAt: String?,
        completedAt: String?,
        durationMs: Double?,
        error: String?,
        workflowSnapshot: [String: Any]? = nil,
        nodeNameMap: [String: String]? = nil,
        progressTimeline: [String: Any]? = nil,
        diagramMermaid: String? = nil
    ) {
        self.threadId = threadId
        self.workflowId = workflowId
        self.workflowName = workflowName
        self.pythonCode = pythonCode
        self.executionLog = executionLog
        self.status = status
        self.startedAt = startedAt
        self.completedAt = completedAt
        self.durationMs = durationMs
        self.error = error
        self.workflowSnapshot = workflowSnapshot
        self.nodeNameMap = nodeNameMap
        self.progressTimeline = progressTimeline
        self.diagramMermaid = diagramMermaid
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

    init(inputs: [String: String]) {
        self.inputs = inputs
    }
}
