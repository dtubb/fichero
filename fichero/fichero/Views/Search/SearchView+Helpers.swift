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

    /// Refresh the indexed-doc count from /api/search/stats so the empty
    /// state can surface "Index Library" / "X indexed" messaging. Cheap;
    /// runs on appear and after reindex completion. (#481)
    @MainActor
    func loadIndexStats() async {
        do {
            let stats = try await searchService.stats()
            indexedCount = stats.indexedCount
        } catch {
            logger.debug("Search stats fetch failed: \(error.localizedDescription)")
        }
    }

    /// Trigger a background reindex of the active library. The backend
    /// endpoint returns immediately; we poll /stats every 3 s while
    /// indexedCount climbs, until two consecutive polls return the same
    /// value (settled). (#481)
    @MainActor
    func reindexLibrary() async {
        guard !isReindexing else { return }
        isReindexing = true
        defer { isReindexing = false }
        do {
            _ = try await searchService.reindexAll()
        } catch {
            logger.error("Reindex kickoff failed: \(error.localizedDescription)")
            return
        }
        // Poll stats. Stop when count stops climbing for two consecutive
        // polls (i.e. it's settled), or after a generous 5-min cap.
        var previous: Int = -1
        var stableTicks = 0
        let maxTicks = 100  // 5 minutes at 3 s
        for _ in 0..<maxTicks {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            do {
                let stats = try await searchService.stats()
                indexedCount = stats.indexedCount
                if stats.indexedCount == previous {
                    stableTicks += 1
                    if stableTicks >= 2 { break }
                } else {
                    stableTicks = 0
                    previous = stats.indexedCount
                }
            } catch {
                logger.debug("Index poll failed: \(error.localizedDescription)")
            }
        }
        // Re-run the user's query if they have one — search now has data.
        if !queryText.trimmingCharacters(in: .whitespaces).isEmpty {
            performSearch()
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
                    minScore: 0.0,  // Backend defaults; UI shows everything ≥ floor.
                    searchType: "hybrid",
                    filters: nil,
                    sortBy: sortBy,
                    sortOrder: sortDirection,
                    offset: 0,
                    useFuzzyMatch: false,
                    highlightResults: true
                )

                logger.info("Got \(response.count) results (total: \(response.totalResults))")
                await MainActor.run {
                    searchResults = response.results
                    searchStats = response
                    isSearching = false
                    // Record the query in @SceneStorage history once it
                    // returned a real result set; suppress 'recents'
                    // pollution when the user is just typing fragments.
                    if response.count > 0 {
                        recordRecentSearch(queryText)
                    }
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
