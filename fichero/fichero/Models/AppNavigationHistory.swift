import Foundation
import Observation

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
        /// The transient toolbar-search query active when this entry was
        /// recorded, or `nil` when the entry is plain folder browsing (#4106).
        /// Captured so Back/Forward can return to the search results a user
        /// stepped away from — e.g. after double-clicking a hit to reveal its
        /// source location — instead of silently dropping the query.
        let searchQuery: String?

        // Explicit init with a defaulted `searchQuery` so existing call sites
        // (and tests) that predate the field keep compiling; a `let` with a
        // default value is otherwise excluded from the synthesized memberwise
        // initializer, which would reject the query at the one site that sets it.
        init(
            viewType: String,
            viewItemId: String?,
            selectedSidebarItemId: String?,
            browserSelection: Set<String>,
            detailDocumentId: String?,
            searchQuery: String? = nil
        ) {
            self.viewType = viewType
            self.viewItemId = viewItemId
            self.selectedSidebarItemId = selectedSidebarItemId
            self.browserSelection = browserSelection
            self.detailDocumentId = detailDocumentId
            self.searchQuery = searchQuery
        }
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

/// The window's history as views see it (#4228): only whether Back and Forward are possible is
/// observable, and each changes only when it actually flips.
///
/// `AppNavigationHistory` was `@State` on `ContentView`, so every recorded entry re-evaluated the
/// whole window, and one sidebar click records three (the selection, then the view mode, then the
/// detail document once the folder loads). The stack itself is not observed: recording an entry
/// while Back was already possible changes nothing any view draws.
@MainActor
@Observable
final class NavigationHistoryModel {
    @ObservationIgnored private var history = AppNavigationHistory()
    private(set) var canGoBack = false
    private(set) var canGoForward = false

    func push(_ entry: AppNavigationHistory.Entry) {
        history.push(entry)
        publish()
    }

    func goBack() -> AppNavigationHistory.Entry? {
        defer { publish() }
        return history.goBack()
    }

    func goForward() -> AppNavigationHistory.Entry? {
        defer { publish() }
        return history.goForward()
    }

    /// An `@Observable` property notifies on every set, equal or not, so each is set only when it changed.
    private func publish() {
        if canGoBack != history.canGoBack { canGoBack = history.canGoBack }
        if canGoForward != history.canGoForward { canGoForward = history.canGoForward }
    }
}
