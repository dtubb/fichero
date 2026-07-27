import OSLog
import SwiftUI

// MARK: - Transient search → Library view results (#4106 / S2)
//
// The global toolbar search renders its hits INTO the Library view: the
// library column's `documents` input swaps to `searchResultDocuments` while
// `activeSearchQuery` is non-nil, so every existing view mode (icons / list /
// columns / table) presents the results. Nothing is persisted (#4086) and the
// view mode never leaves `.library`.

private let searchResultsLogger = Logger(
    subsystem: "app.fichero.fichero", category: "TransientSearch"
)

extension ContentView {
    /// Run the library's search store for `query` and resolve the hits into
    /// `Document` rows, preserving the engine's relevance order.
    ///
    /// Resolution prefers documents already loaded by the DocumentStore (zero
    /// fetches for the common case of hits inside the browsed library) and
    /// fetches the rest individually — a search page is ≤50 rows, so per-id
    /// gets are fine here.
    @MainActor
    func runTransientSearch(_ query: String) async {
        guard let library = LibraryManager.shared.getLibrary(id: windowState.libraryId)
            ?? LibraryManager.shared.globalLibrary else { return }
        let store = library.searchStore
        await store.performSearch(query: query)

        // A newer query superseded this one while the request was in flight —
        // its own resolution pass owns the result state.
        guard activeSearchQuery == query else { return }

        var resolved: [Document] = []
        for result in store.results {
            if let known = documentStore.currentDocuments.first(where: { $0.id == result.documentId })
                ?? documentStore.collections.first(where: { $0.id == result.documentId }) {
                resolved.append(known)
                continue
            }
            do {
                resolved.append(try await library.documentService.getDocument(result.documentId))
            } catch {
                // A hit whose document can't load is dropped from the grid —
                // the engine already 500s on real failures (#4109), so this is
                // a per-row race (deleted since indexing), not a silent state.
                searchResultsLogger.warning(
                    "search hit \(result.documentId, privacy: .public) failed to resolve: \(error.localizedDescription)"
                )
            }
        }
        guard activeSearchQuery == query else { return }
        searchResultDocuments = resolved
    }

    /// Leave transient-search presentation and return to folder browsing.
    @MainActor
    func clearTransientSearch() {
        activeSearchQuery = nil
        searchResultDocuments = []
    }
}
