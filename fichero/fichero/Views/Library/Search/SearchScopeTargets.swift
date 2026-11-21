import Foundation

/// The nodes the page, document and folder scopes can point at, captured when a search is submitted.
struct SearchScopeTargets: Equatable {
    var page: TransientSearchFolder?
    var document: TransientSearchFolder?
    var folder: TransientSearchFolder?

    /// The scopes the menu offers, in menu order: a node scope only when there is a node, project and everywhere always.
    var offered: [SearchScope] {
        SearchScope.allCases.filter { scope in
            switch scope {
            case .page: page != nil
            case .document: document != nil
            case .folder: folder != nil
            case .project, .everywhere: true
            }
        }
    }

    /// The node a scope names, nil for the scopes that name none.
    func node(for scope: SearchScope) -> TransientSearchFolder? {
        switch scope {
        case .page: page
        case .document: document
        case .folder: folder
        case .project, .everywhere: nil
        }
    }

    /// The `folder_id` the engine call carries. A node scope whose node is gone sends nothing, so the search widens to
    /// the project rather than failing; the menu never offers such a scope.
    func engineFolderId(for scope: SearchScope) -> String? { node(for: scope)?.id }

    /// The scope a search starts with: the browsed folder when the Finder-style default asks for it and there is one.
    func defaultScope(folderByDefault: Bool) -> SearchScope { folder != nil && folderByDefault ? .folder : .project }

    /// The scope actually in force: a chosen node scope whose node is not there falls back to the project.
    func effective(_ scope: SearchScope) -> SearchScope { offered.contains(scope) ? scope : .project }
}
