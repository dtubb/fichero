import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - Activity Types
// Shared types used by ActivityService and views

/// Wrapper to decode any JSON value as String
struct AnyValueAsString: Codable, Hashable {
    let value: String

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

typealias ActivityItem = Components.Schemas.ActivityResponse

// The hand-rolled ActivityItem was Identifiable (id: String); the generated
// schema has the same `id`, so opt it into Identifiable for ForEach (#1702).
extension Components.Schemas.ActivityResponse: @retroactive Identifiable {}

extension Components.Schemas.ActivityResponse {
    var type: String { _type }

    /// Metadata with all values as strings. Named distinctly from the generated
    /// `metadata` (a `MetadataPayload?`) to avoid shadowing it (#1702).
    var metadataStrings: [String: String]? {
        guard let metadata else { return nil }
        let converted = metadata.additionalProperties.value.mapValues { value -> String in
            if let string = value as? String {
                return string
            }
            // #4024: Bool BEFORE NSNumber — a bridged Bool IS an NSNumber (__NSCFBoolean),
            // so testing NSNumber first rendered `true` as "1".
            if let bool = value as? Bool {
                return String(bool)
            }
            if let number = value as? NSNumber {
                return number.stringValue
            }
            return String(describing: value)
        }
        return converted.isEmpty ? nil : converted
    }

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
        let metadataPayload = metadataRaw.map { raw -> Components.Schemas.ActivityResponse.MetadataPayload in
            let object = (try? OpenAPIObjectContainer(unvalidatedValue: raw.mapValues(\.value))) ?? .init()
            return .init(additionalProperties: object)
        }
        self.init(
            id: id,
            _type: type,
            level: level,
            timestamp: timestamp,
            message: message,
            workflowId: workflowId,
            batchId: batchId,
            threadId: threadId,
            nodeId: nodeId,
            metadata: metadataPayload,
            durationMs: durationMs,
            error: error
        )
    }

    var parsedTimestamp: Date? {
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = isoFormatter.date(from: timestamp) {
            return date
        }
        isoFormatter.formatOptions = [.withInternetDateTime]
        if let date = isoFormatter.date(from: timestamp) {
            return date
        }

        let dateFormatter = DateFormatter()
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        dateFormatter.timeZone = .current

        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        if let date = dateFormatter.date(from: timestamp) {
            return date
        }

        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        if let date = dateFormatter.date(from: timestamp) {
            return date
        }

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

    var name: String {
        let displayMessage = message.prefix(40)
        return displayMessage.isEmpty ? type : String(displayMessage) + (message.count > 40 ? "..." : "")
    }

    var statusIcon: String { typeIcon }

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
