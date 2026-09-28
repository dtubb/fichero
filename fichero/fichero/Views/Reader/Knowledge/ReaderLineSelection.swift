import Foundation

/// One selection across the Source view, the Reader and the Inspector (#5155). The Reader's caret
/// line becomes the focused Source view's selection (`lineFocused` from the page), and the Source
/// view's selection is shown in the Reader's text (`window.fichero.showLines` on the page). The
/// page's half is the served page's (the bugs lane); this is the app's.
enum ReaderLineSelection {
    struct Focus: Equatable {
        /// The page the line is on: the document whose Source view selection it becomes.
        let pageId: String
        let segmentId: String
    }

    /// The page's `lineFocused` message, or nil when it is not a whole one.
    static func focus(from body: [String: Any]) -> Focus? {
        guard let pageId = body["pageId"] as? String, !pageId.isEmpty,
              let segmentId = body["segmentId"] as? String, !segmentId.isEmpty else { return nil }
        return Focus(pageId: pageId, segmentId: segmentId)
    }

    /// The call that shows `segmentIds` as selected in the Reader's text; an empty list clears it.
    /// Optional-chained, so a page that does not have it yet ignores it rather than throwing.
    static func showLinesScript(_ segmentIds: [String]) -> String {
        let data = (try? JSONSerialization.data(withJSONObject: segmentIds)) ?? Data()
        let json = String(bytes: data, encoding: .utf8) ?? "[]"
        return "window.fichero?.showLines?.(\(json));"
    }
}
