import FicheroAPIClient
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SearchView")

enum SearchScope: String, CaseIterable, Identifiable, Codable {
    case content
    case entities
    case claims

    var id: String { rawValue }

    var label: String {
        switch self {
        case .content:
            "Content"
        case .entities:
            "Entities"
        case .claims:
            "Claims"
        }
    }

    var helpText: String {
        switch self {
        case .content:
            "Search document text"
        case .entities:
            "Search extracted entities"
        case .claims:
            "Search extracted claims"
        }
    }
}

struct SearchScopeSelection: Equatable {
    private(set) var scopes: Set<SearchScope>

    static let all = SearchScopeSelection(scopes: Set(SearchScope.allCases))

    init(scopes: Set<SearchScope>) {
        self.scopes = scopes.isEmpty ? Set(SearchScope.allCases) : scopes
    }

    func contains(_ scope: SearchScope) -> Bool {
        scopes.contains(scope)
    }

    mutating func toggle(_ scope: SearchScope) {
        if scopes.contains(scope) {
            guard scopes.count > 1 else { return }
            scopes.remove(scope)
        } else {
            scopes.insert(scope)
        }
    }

    var apiIncludes: [Components.Schemas.SearchInclude] {
        SearchScope.allCases.compactMap { scope in
            guard scopes.contains(scope) else { return nil }
            return Components.Schemas.SearchInclude(rawValue: scope.rawValue)
        }
    }
}

/// Helper methods for SearchView
extension SearchView {
    func clearFilters() {
        queryText = ""
        // onChange(of: queryText) fires and delegates to store via performSearch(query:"")
    }

    func loadDocument(_ id: String) {
        Task {
            do {
                guard let library = libraryManager.getLibrary(id: windowState.libraryId) else {
                    logger.error("No active library while loading search result document")
                    return
                }

                var doc = try await library.documentServiceGenerated.getDocument(id)
                // Page-child docs have no path of their own — the preview
                // needs the parent PDF's on-disk path. EditorView resolves
                // it via documentStore.currentDocuments, but in the search
                // context that cache holds the browsed folder's docs, not
                // the parent. Inject the parent's path into metadata["pdf_path"]
                // so EditorView.resolvedParentPDFPath finds it immediately.
                if doc.docType == .page || (doc.path == nil && doc.parentId != nil) {
                    let parentId = doc.parentId ?? (doc.metadata["pdf_parent_id"]?.value as? String)
                    if let parentId {
                        if let parent = try? await library.documentServiceGenerated.getDocument(parentId),
                           let parentPath = parent.path, !parentPath.isEmpty {
                            doc.metadata["pdf_path"] = AnyCodable(parentPath)
                            doc.metadata["pdf_parent_id"] = AnyCodable(parentId)
                        }
                    }
                }
                await MainActor.run {
                    detailDocument = doc
                }
            } catch {
                logger.error("Failed to load document: \(error.localizedDescription)")
            }
        }
    }

    /// Persist the current query as a SavedSearch in the active library so
    /// it appears under "Saved Searches" in the sidebar (#481). After
    /// save, sidebar reload brings the new entry into view; user can
    /// click it to re-run.
    @MainActor
    func saveCurrentQuery() async {
        let query = queryText.trimmingCharacters(in: .whitespacesAndNewlines)
        // windowState.libraryId is a non-optional UUID; only the library
        // lookup can return nil (per-library state may not yet be wired
        // when this fires very early in window setup).
        guard !query.isEmpty,
              let library = libraryManager.getLibrary(id: windowState.libraryId) else {
            return
        }
        do {
            _ = try await library.savedSearchServiceGenerated.saveSearch(
                query: query,
                isSmartSearch: true,
                searchType: "hybrid",
                sortBy: "relevance",
                sortDirection: "desc"
            )
            try await library.savedSearchServiceGenerated.loadSavedSearches()
        } catch {
            logger.error("Save search failed: \(error.localizedDescription)")
        }
    }

    /// Trigger a background reindex and, once settled, re-run the active query.
    @MainActor
    func reindexLibrary() async {
        await searchStore.reindexLibrary()
        if !queryText.trimmingCharacters(in: .whitespaces).isEmpty {
            performSearch()
        }
    }

    /// Dispatch a search via the store. Keeps `displayMode` sync and
    /// records the query in @SceneStorage history.
    func performSearch() {
        guard !queryText.trimmingCharacters(in: .whitespaces).isEmpty else {
            Task { await searchStore.performSearch(query: "") }
            return
        }

        logger.info("Starting search for: \(queryText)")
        if displayMode != .list {
            displayMode = .list
        }

        Task {
            await searchStore.performSearch(
                query: queryText,
                include: searchScopeSelection.apiIncludes,
                sortBy: sortBy,
                sortOrder: sortDirection
            )
            if !searchStore.results.isEmpty {
                recordRecentSearch(queryText)
            }
        }
    }

    /// Open the arrow-selected result at its matched passage — the Return-key
    /// action for the arrow-through-results navigation (#1843).
    func activateSelectedResult() {
        guard let id = selection.first,
              let result = searchStore.results.first(where: { $0.documentId == id }) else { return }
        openExcerpt(result)
    }

    func openExcerpt(_ result: SearchResult) {
        guard let info = SearchResultRowFromAPI.navigationUserInfo(for: result) else {
            loadDocument(result.documentId)
            return
        }

        NotificationCenter.default.post(
            name: .ficheroOpenClaimSource,
            object: nil,
            userInfo: info
        )
    }
}
