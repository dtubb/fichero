import Foundation

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
