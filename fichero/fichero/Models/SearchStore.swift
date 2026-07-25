import FicheroAPIClient
import Foundation
import Observation
import OSLog

enum SearchFailure: Equatable {
    /// The search request itself failed. `detail` is diagnostic text for the
    /// disclosure affordance (tooltip/log) — the UI never renders it inline
    /// (error-presentation convention: icon + generic message, detail on
    /// demand).
    case requestFailed(detail: String)

    /// The stable user-facing message for this failure.
    var message: String {
        switch self {
        case .requestFailed: "Search failed"
        }
    }

    var detail: String {
        switch self {
        case .requestFailed(let detail): detail
        }
    }
}

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
    private(set) var searchFailure: SearchFailure?
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

    /// The engine's default relevance floor (SearchRequest.min_score).
    static let defaultMinScore = 0.55

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    /// Run a semantic / hybrid search and update `results`.
    func performSearch(
        query: String,
        limit: Int = 50,
        include: [Components.Schemas.SearchInclude] = [],
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortOrder: String = "desc",
        folderId: String? = nil,
        compile: Bool = false
    ) async {
        // #4024: trim newlines/tabs too — `.whitespaces` excludes newlines, so a query of
        // only whitespace (e.g. " \n\t") stayed non-empty and reached the backend as a blank
        // search → HTTP 400. `.whitespacesAndNewlines` makes it the intended local no-op.
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            results = []
            searchStats = nil
            searchFailure = nil
            return
        }
        isSearching = true
        searchFailure = nil
        defer { isSearching = false }
        do {
            let response = try await searchService.searchCompatible(
                query: trimmed,
                limit: limit,
                include: include,
                // 0.55 mirrors the engine's noise floor: unthresholded
                // semantic search returns EVERY page at 42-50% cosine
                // similarity, so 0.0 buried real hits in noise (#1054
                // regression, fixed by #4112/S8).
                minScore: Self.defaultMinScore,
                searchType: searchType,
                // Folder scope (#4107/S3): the engine expands folder_id to the
                // folder's whole descendant set server-side.
                filters: folderId.map { ["folder_id": $0] },
                sortBy: sortBy,
                sortOrder: sortOrder,
                offset: 0,
                useFuzzyMatch: false,
                highlightResults: true,
                // LLM query compilation (#4116): explicit submits only —
                // re-runs and live paths never pay the latency.
                compile: compile
            )
            results = response.results
            searchStats = response
            log.info("Search '\(trimmed, privacy: .public)' → \(response.count, privacy: .public) results")
        } catch {
            if error.isCancellationError { return }   // superseded search — keep results, no log
            searchFailure = .requestFailed(detail: error.localizedDescription)
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
            if error.isCancellationError { return }   // superseded — not a failure
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
