import Foundation

/// A line moved from the Reader's text (Q5, 3c part d; `source.textedit.lines-move-in-the-order`).
///
/// The page resolves the caret's line from its line map and posts `lineMove` with the line's
/// segment id, its page and the step. This turns that message into the SAME store call the
/// Inspector's keys make -- `ReadingOrderStore.move(_:step:)` -- so a key in either place is one
/// `reading_order.place`, in the line's own level, undoable with ⌘Z. Never a second rule.
enum ReaderLineMove {
    struct Request: Equatable {
        /// The line; its PAGE is the document whose order holds it.
        let segmentId: String
        let pageId: String
        let step: ReadingOrderMove.Step
    }

    /// The page's message, or nil when it is not a whole one -- a malformed message moves nothing.
    static func request(from body: [String: Any]) -> Request? {
        guard
            let segmentId = body["segmentId"] as? String, !segmentId.isEmpty,
            let pageId = body["pageId"] as? String, !pageId.isEmpty,
            let name = body["step"] as? String, let step = step(named: name)
        else { return nil }
        return Request(segmentId: segmentId, pageId: pageId, step: step)
    }

    /// The page's step names (`LINE_MOVE_STEPS` in `document_view.html`).
    static func step(named name: String) -> ReadingOrderMove.Step? {
        switch name {
        case "up": .upward
        case "down": .downward
        case "toStart": .toStart
        case "toEnd": .toEnd
        default: nil
        }
    }

    /// Move it: load the page's order when the store is on another page, then the one store call.
    @MainActor
    @discardableResult
    static func perform(_ request: Request, store: ReadingOrderStore) async -> String? {
        if store.documentId != request.pageId || store.orderId == nil {
            try? await store.load(documentId: request.pageId)
        }
        return await store.move(request.segmentId, step: request.step)
    }
}
