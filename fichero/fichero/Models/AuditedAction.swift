import Foundation

/// One audited action from a verb, with ⌘Z: invoke it, register the undo by its own audit id, and call
/// `afterChange` (re-read what the verb changed) after it and after each undo / redo. The Hands
/// section's verbs use it; the older verbs (`ReadingChoice`, `WorkingPassChoice`) have the same shape.
enum AuditedAction {
    @MainActor
    @discardableResult
    static func run<Params: Encodable>(
        _ name: String, params: Params, actionName: String, actionsService: ActionsService,
        undoManager: UndoManager?, afterChange: @escaping @MainActor () async -> Void = {}
    ) async throws -> ActionInvokeResult {
        let result = try await actionsService.invokeAction(name: name, params: params)
        ActionUndo.register(
            auditId: result.auditId, actionName: actionName, undoManager: undoManager,
            performUndo: { auditId in
                let next = try await actionsService.undoAction(auditId: auditId).auditId
                await afterChange()
                return next
            }
        )
        await afterChange()
        return result
    }
}

/// `hand.attribute`: this segment's ink is this hand's.
struct HandAttributeRequest: Encodable, Equatable {
    let handId: String
    let segmentId: String

    enum CodingKeys: String, CodingKey { case handId = "hand_id", segmentId = "segment_id" }
}

/// `hand.unattribute`: withdraw one attribution (kept, never deleted).
struct HandUnattributeRequest: Encodable, Equatable {
    let attributionId: String

    enum CodingKeys: String, CodingKey { case attributionId = "attribution_id" }
}

/// `hand.create`: a new hand in the project's list.
struct HandCreateRequest: Encodable, Equatable {
    let label: String
}
