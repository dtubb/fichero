import Observation
import SwiftUI

/// Browser-style back/forward navigation stack for the KG entity browser.
/// Owned as @State at the OntologyBrowser level (one per window scene).
/// (#1186)
@Observable
final class NavigationHistoryManager {

    enum Entry: Equatable {
        case entityList
        case entityProfile(entityId: String)
        case claimJump(claimId: String, pageLabel: String?)
        case pdfPage(pageLabel: String)
    }

    private(set) var stack: [Entry] = []
    private(set) var cursor: Int = -1

    static let maxDepth = 50

    var canGoBack: Bool { cursor > 0 }
    var canGoForward: Bool { cursor < stack.count - 1 }

    /// Push a new entry, clearing any forward history.
    /// Consecutive duplicate entries are ignored.
    func push(_ entry: Entry) {
        if cursor >= 0 && stack[cursor] == entry { return }
        if cursor < stack.count - 1 {
            stack.removeSubrange((cursor + 1)...)
        }
        stack.append(entry)
        if stack.count > Self.maxDepth { stack.removeFirst() }
        cursor = stack.count - 1
    }

    @discardableResult
    func goBack() -> Entry? {
        guard canGoBack else { return nil }
        cursor -= 1
        return stack[cursor]
    }

    @discardableResult
    func goForward() -> Entry? {
        guard canGoForward else { return nil }
        cursor += 1
        return stack[cursor]
    }
}
