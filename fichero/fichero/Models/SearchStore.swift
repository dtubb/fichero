import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for semantic search (#1903, mirrors `NoteStore`).
///
/// The single endpoint accessor for search-result data. A view never holds
/// raw `@State` result arrays or calls `SearchService` directly: it
/// observes `results`, `isSearching`, and the other state below, and
/// dispatches the named actions. `apply(_:)` invalidates stale results when
/// documents change so the next query always reflects the current index.
///
/// UI-local state (query text, sort preferences, debounce tokens,
/// `@SceneStorage`) remains in the view layer.
///
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows.
@MainActor
@Observable
final class SearchStore: ChangeEventConsumer {
    // ─── Published domain state (views read these directly) ───
    private(set) var results: [SearchResult] = []
    private(set) var searchStats: SearchResponse?
    private(set) var isSearching = false
    private(set) var searchError: String?
    private(set) var indexedCount: Int?
    private(set) var isReindexing = false
    private(set) var keywordCloud: [KeywordCloudEntryDTO] = []

    /// Bumped when a `document.*` change event arrives so views know their
    /// cached results may be stale and should re-run the current query.
    private(set) var changeToken: Int = 0

    // ─── Transport: the EXISTING SearchService wrapper, unchanged ───
    private let searchService: SearchService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "SearchStore")

    init(searchService: SearchService) {
        self.searchService = searchService
    }

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    /// Run a semantic / hybrid search and update `results`.
    func performSearch(
        query: String,
        limit: Int = 50,
        include: [Components.Schemas.SearchInclude] = [],
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortOrder: String = "desc"
    ) async {
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            results = []
            searchStats = nil
            searchError = nil
            return
        }
        isSearching = true
        searchError = nil
        defer { isSearching = false }
        do {
            let response = try await searchService.searchCompatible(
                query: trimmed,
                limit: limit,
                include: include,
                minScore: 0.0,
                searchType: searchType,
                filters: nil,
                sortBy: sortBy,
                sortOrder: sortOrder,
                offset: 0,
                useFuzzyMatch: false,
                highlightResults: true
            )
            results = response.results
            searchStats = response
            log.info("Search '\(trimmed, privacy: .public)' → \(response.count, privacy: .public) results")
        } catch {
            searchError = error.localizedDescription
            results = []
            searchStats = nil
            log.error("Search failed: \(error.localizedDescription)")
        }
    }

    /// Fetch index statistics (indexed doc count). Cheap; call on appear.
    func loadIndexStats() async {
        do {
            let stats = try await searchService.stats()
            indexedCount = stats.indexedCount
        } catch {
            log.debug("Search stats fetch failed: \(error.localizedDescription)")
        }
    }

    /// Kick off a background reindex and poll until the count stabilises.
    func reindexLibrary() async {
        guard !isReindexing else { return }
        isReindexing = true
        defer { isReindexing = false }
        do {
            _ = try await searchService.reindexAll()
        } catch {
            log.error("Reindex kickoff failed: \(error.localizedDescription)")
            return
        }
        var previous = -1
        var stableTicks = 0
        for _ in 0..<100 {
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
                log.debug("Index poll failed: \(error.localizedDescription)")
            }
        }
    }

    /// Fetch top-N keyword cloud entries for the library.
    func loadKeywordCloud(limit: Int = 30) async {
        keywordCloud = (try? await searchService.keywordCloud(limit: limit)) ?? []
    }

    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    /// React to document mutations by bumping the token so views know their
    /// last result set may be stale.
    nonisolated var changeDomains: Set<String> { ["document"] }

    func apply(_ event: ChangeEvent) {
        changeToken &+= 1
        // No automatic re-search: query context lives in the view. The view
        // observes `changeToken` and can re-run the active query if desired.
    }

    func resync() async {
        await loadIndexStats()
    }
}
