import Foundation

/// Where a toolbar search submit lands.
///
/// Deliberately carries no `SavedSearch`: a search is a transient view of the
/// library, not a stored object (#4086).
struct ToolbarSearchRoute: Equatable {
    let sidebarMode: SidebarMode
    let viewMode: AppViewMode
    /// The trimmed query the transient search runs (#4106/S2).
    let query: String
}

enum ToolbarSearchRouter {
    /// Returns the route for `rawQuery`, or nil when the query is blank.
    ///
    /// Search stays IN the library (#4106/S2): the sidebar keeps the library
    /// tree and the view mode keeps the Library view — only the library
    /// column's contents change, to the transient result set for `query`.
    static func route(for rawQuery: String) -> ToolbarSearchRoute? {
        let query = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return nil }
        return ToolbarSearchRoute(
            sidebarMode: .library,
            viewMode: .library(nil),
            query: query
        )
    }
}

struct ChatWithDocsRoute: Equatable {
    let selectedDocumentIds: Set<String>
    let sidebarMode: SidebarMode
    let viewMode: AppViewMode
}

enum ChatWithDocsRouter {
    static func mainChatRoute(documentIds: [String]) -> ChatWithDocsRoute {
        ChatWithDocsRoute(
            selectedDocumentIds: Set(documentIds),
            sidebarMode: .chat,
            viewMode: .chat(nil)
        )
    }
}
