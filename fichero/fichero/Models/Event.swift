import Foundation

// MARK: - Event Model

/// Audit log entry for tracking changes.
/// Matches Python Event model in fichero/models.py
///
/// Records what changed, before/after state, and context.
/// Enables undo/redo and audit trails.
struct Event: Identifiable, Codable, Hashable {
    let id: String
    var timestamp: Date

    // What changed
    var eventType: String
    var targetType: String
    var targetId: String

    // For undo
    var before: [String: AnyCodable]?
    var after: [String: AnyCodable]?

    // Context
    var source: String
    var runId: String?

    var metadata: [String: AnyCodable]

    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case eventType = "event_type"
        case targetType = "target_type"
        case targetId = "target_id"
        case before
        case after
        case source
        case runId = "run_id"
        case metadata
    }

    init(
        id: String = UUID().uuidString,
        timestamp: Date = Date(),
        eventType: String,
        targetType: String,
        targetId: String,
        before: [String: AnyCodable]? = nil,
        after: [String: AnyCodable]? = nil,
        source: String = "user",
        runId: String? = nil,
        metadata: [String: AnyCodable] = [:]
    ) {
        self.id = id
        self.timestamp = timestamp
        self.eventType = eventType
        self.targetType = targetType
        self.targetId = targetId
        self.before = before
        self.after = after
        self.source = source
        self.runId = runId
        self.metadata = metadata
    }
}

// MARK: - Event Type Helpers

extension Event {
    /// Common event types
    enum EventType: String {
        case documentCreate = "document.create"
        case documentUpdate = "document.update"
        case documentDelete = "document.delete"
        case documentMove = "document.move"
        case artifactCreate = "artifact.create"
        case artifactUpdate = "artifact.update"
        case artifactDelete = "artifact.delete"
        case workflowCreate = "workflow.create"
        case workflowUpdate = "workflow.update"
        case workflowDelete = "workflow.delete"
        case runCreate = "run.create"
        case runUpdate = "run.update"
        case noteCreate = "note.create"
        case noteUpdate = "note.update"
        case noteDelete = "note.delete"

        var action: String {
            let parts = rawValue.split(separator: ".")
            return parts.last.map(String.init) ?? rawValue
        }

        var entity: String {
            let parts = rawValue.split(separator: ".")
            return parts.first.map(String.init) ?? rawValue
        }
    }

    /// Event source types
    enum EventSource: String {
        case user
        case system
        case workflow
    }

    /// Extract action from event type (e.g., "create" from "document.create")
    var action: String {
        let parts = eventType.split(separator: ".")
        return parts.last.map(String.init) ?? eventType
    }

    /// Extract entity from event type (e.g., "document" from "document.create")
    var entity: String {
        let parts = eventType.split(separator: ".")
        return parts.first.map(String.init) ?? eventType
    }

    /// Display name for the event type
    var eventTypeDisplayName: String {
        let entityName = entity.capitalized
        let actionName = action.capitalized
        return "\(entityName) \(actionName)"
    }

    /// Icon for the event type
    var eventTypeIcon: String {
        switch action {
        case "create": return "plus.circle"
        case "update": return "pencil.circle"
        case "delete": return "trash.circle"
        case "move": return "arrow.right.circle"
        default: return "info.circle"
        }
    }

    /// Color for the event type
    var eventTypeColor: String {
        switch action {
        case "create": return "green"
        case "update": return "blue"
        case "delete": return "red"
        case "move": return "orange"
        default: return "gray"
        }
    }

    /// Whether this event can be undone
    var canUndo: Bool {
        before != nil && (action == "update" || action == "delete")
    }

    /// Whether this event was triggered by a user
    var isUserEvent: Bool {
        source == EventSource.user.rawValue
    }

    /// Whether this event was triggered by a workflow
    var isWorkflowEvent: Bool {
        source == EventSource.workflow.rawValue
    }
}
