import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "SearchView")

/// Helper methods for SearchView
extension SearchView {
    func clearFilters() {
        queryText = ""
        searchResults = []
        searchError = nil
    }

    func loadDocument(_ id: String) {
        Task {
            do {
                let doc: Document = try await apiClient.get("/documents/\(id)")
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
        guard !query.isEmpty,
              let libraryId = windowState.libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else {
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

    func performSearch() {
        guard !queryText.trimmingCharacters(in: .whitespaces).isEmpty else {
            searchResults = []
            searchStats = nil
            searchError = nil
            return
        }

        logger.info("Starting enhanced search for: \(queryText)")
        isSearching = true
        searchError = nil

        Task {
            do {
                logger.info("Calling searchService.search with enhanced parameters...")

                let response = try await searchService.searchCompatible(
                    query: queryText,
                    limit: 50,
                    minScore: 0.0,
                    searchType: "hybrid",
                    filters: nil,
                    sortBy: "relevance",
                    sortOrder: "desc",
                    offset: 0,
                    useFuzzyMatch: false,
                    highlightResults: true
                )

                logger.info("Got \(response.count) results (total: \(response.totalResults))")
                await MainActor.run {
                    searchResults = response.results
                    searchStats = response
                    isSearching = false
                }
            } catch {
                logger.error("Search error: \(String(describing: error))")
                await MainActor.run {
                    searchError = error.localizedDescription
                    searchResults = []
                    searchStats = nil
                    isSearching = false
                }
            }
        }
    }

}
