import Foundation

/// A direction stated on a SOURCE -- a folder, a document or a page (`source_setting.set`, level
/// `node`): every page below it reads that way unless a page or a line says otherwise. Set from the
/// Library's right-click and the Inspector's Language section, ⌘Z by its own audit id. Before this only
/// MCP or the command line could state it.
enum SourceDirection {
    /// Posted (object: the node's id) after the set, its ⌘Z and its ⇧⌘Z, once each: the Reader re-reads
    /// the pages it shows (`SegmentChangeObserver`), the Inspector re-reads what it resolves.
    static let didChange = Notification.Name("SourceDirection.didChange")

    /// `source_setting.set` of `direction` on the node, or `source_setting.clear` for nil ("Not Stated":
    /// never determined again, so the level below answers).
    static func call(_ direction: String?, on nodeId: String) -> (action: String, params: SourceDirectionRequest) {
        (direction == nil ? "source_setting.clear" : "source_setting.set",
         SourceDirectionRequest(value: direction, targetId: nodeId))
    }

    /// Sends it through the audited choke point, ⌘Z registered, `didChange` after each step.
    @MainActor
    static func apply(
        _ direction: String?, on nodeId: String, actionsService: ActionsService, undoManager: UndoManager?
    ) async throws {
        let planned = call(direction, on: nodeId)
        try await AuditedAction.run(
            planned.action, params: planned.params,
            actionName: direction == nil ? "Clear Direction" : "Set Direction",
            actionsService: actionsService, undoManager: undoManager,
            afterChange: { NotificationCenter.default.post(name: didChange, object: nodeId) }
        )
    }
}

/// `source_setting.set` / `.clear` for a node's direction. `value` is absent for a clear, which refuses
/// one (`extra="forbid"`).
struct SourceDirectionRequest: Encodable, Equatable {
    var level = "node"
    var key = "direction"
    let value: String?
    let targetId: String

    enum CodingKeys: String, CodingKey { case level, key, value, targetId = "target_id" }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(level, forKey: .level)
        try container.encode(key, forKey: .key)
        try container.encodeIfPresent(value, forKey: .value)
        try container.encode(targetId, forKey: .targetId)
    }
}
