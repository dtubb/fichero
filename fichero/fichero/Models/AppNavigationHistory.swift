import Foundation

/// Browser/Finder-style navigation history for the main app window.
///
/// Entries are intentionally lightweight ids, not model objects, so restoring
/// can re-resolve against the current stores after a backend refresh.
struct AppNavigationHistory {
    struct Entry: Equatable {
        let viewType: String
        let viewItemId: String?
        let selectedSidebarItemId: String?
        let browserSelection: Set<String>
        let detailDocumentId: String?
    }

    private(set) var stack: [Entry] = []
    private(set) var cursor: Int = -1

    static let maxDepth = 80

    var canGoBack: Bool { cursor > 0 }
    var canGoForward: Bool { cursor >= 0 && cursor < stack.count - 1 }

    var current: Entry? {
        guard stack.indices.contains(cursor) else { return nil }
        return stack[cursor]
    }

    mutating func push(_ entry: Entry) {
        if current == entry { return }
        if cursor < stack.count - 1 {
            stack.removeSubrange((cursor + 1)...)
        }
        stack.append(entry)
        if stack.count > Self.maxDepth {
            stack.removeFirst()
        }
        cursor = stack.count - 1
    }

    mutating func goBack() -> Entry? {
        guard canGoBack else { return nil }
        cursor -= 1
        return current
    }

    mutating func goForward() -> Entry? {
        guard canGoForward else { return nil }
        cursor += 1
        return current
    }
}
