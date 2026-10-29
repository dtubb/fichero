import Foundation

/// One audited action from a verb, with ⌘Z: the verbs' shape over the one helper (`UndoableChange`,
/// #5658). It invokes the action, registers its row as one step on the window's stack, and calls
/// `afterChange` (re-read what the verb changed) after it and after each undo / redo.
enum AuditedAction {
    @MainActor
    @discardableResult
    static func run<Params: Encodable>(
        _ name: String, params: Params, actionName: String, actionsService: ActionsService,
        steps: WindowSteps?, afterChange: @escaping @MainActor () async -> Void = {}
    ) async throws -> ActionInvokeResult {
        let result = try await UndoableChange.invoke(
            name, params: params, named: actionName, service: actionsService, steps: steps,
            afterEach: afterChange
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

/// `image.square`: the page warped to a rectangle from a person's four corners (fractions of the upright image, top-left clockwise).
struct ImageSquareRequest: Encodable, Equatable {
    let documentId: String
    let quad: [[Double]]
    var page: Int = 1

    enum CodingKeys: String, CodingKey { case documentId = "document_id", quad, page }
}

/// `image.mark_blank`: hide a page as blank, or show it again (`blank: false`).
struct ImageMarkBlankRequest: Encodable, Equatable {
    let documentId: String
    let blank: Bool
    var page: Int = 1

    enum CodingKeys: String, CodingKey { case documentId = "document_id", blank, page }
}
