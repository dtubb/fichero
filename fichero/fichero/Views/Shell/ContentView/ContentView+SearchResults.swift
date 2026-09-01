import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Transient search → Library view results (#4106 / S2)
//
// The global toolbar search renders its hits INTO the Library view: the
// library column's `documents` input swaps to `searchResultDocuments` while
// `activeSearchQuery` is non-nil, so every existing view mode (icons / list /
// columns / table) presents the results. Nothing is persisted (#4086) and the
// view mode never leaves `.library`. Saved searches run through this SAME
// path (slice B) — selecting one seeds the toolbar field and runs it.

private let searchResultsLogger = Logger(
    subsystem: "app.fichero.fichero", category: "TransientSearch"
)

/// The folder the user was browsing when a transient search ran — offered as
/// a search scope beside the whole library (#4107/S3).
struct TransientSearchFolder: Equatable {
    let id: String
    let name: String
}

extension ContentView {
    static let transientSearchPageSize = 50

    /// UserDefaults key for the Finder-style default search scope (#4108/S4):
    /// false = whole library (default), true = the folder being browsed.
    /// Written by Settings ▸ General ▸ "When performing a search".
    static let searchDefaultScopeIsFolderKey = "search.defaultScopeIsFolder"

    /// The search store for the library this window is showing — the same
    /// resolution `runTransientSearch` uses.
    /// The search field's mode (#4117); raw storage lives on ContentView.
    var searchFieldMode: SearchFieldMode {
        SearchFieldMode(rawValue: searchFieldModeRaw) ?? .ask
    }

    /// Chat the search (#4117): open the main chat scoped to the ACTIVE
    /// result set — the retrieval context is what the search found, and
    /// follow-ups refine through the same audited search.query tool that
    /// produced the grid. One retrieval backbone behind both surfaces.
    @MainActor
    func openChatWithSearchResults() {
        let ids = searchResultDocuments.map(\.id)
        guard !ids.isEmpty else { return }
        let route = ChatWithDocsRouter.mainChatRoute(documentIds: ids)
        chatSelectedDocuments = route.selectedDocumentIds
        sidebarMode = route.sidebarMode
        viewMode = route.viewMode
    }

    /// What the active search matched, per kind (#4403). The header already
    /// counts all of these; this is how the grid's empty state gets to explain
    /// a count it structurally cannot render.
    var transientSearchHitCounts: SearchHitCounts {
        guard let stats = transientSearchStore?.searchStats else {
            return SearchHitCounts(documents: searchResultDocuments.count)
        }
        return SearchHitCounts(
            documents: searchResultDocuments.count,
            artifacts: stats.artifactHits.count,
            entities: stats.entityHits.count,
            claims: stats.claimHits.count
        )
    }

    var transientSearchStore: SearchStore? {
        (LibraryManager.shared.getLibrary(id: windowState.libraryId)
            ?? LibraryManager.shared.globalLibrary)?.searchStore
    }

    /// Run a saved search through the transient path (#4106/S2 slice B):
    /// seed the toolbar field so the query is visible/editable, then search.
    @MainActor
    func runSavedSearch(_ search: SavedSearch) {
        let query = search.query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }
        toolbarSearchText = query
        activeSearchQuery = query
        transientSearchLimit = Self.transientSearchPageSize
        // Saved searches are library-wide; never inherit a stale folder scope.
        transientSearchContextFolder = nil
        transientSearchScopeIsFolder = false
        // Apply the search's stored parameters (#4112/S8).
        transientSearchType = search.searchType
        transientSearchSortBy = search.sortBy
        transientSearchSortDirection = search.sortDirection
        Task { @MainActor in
            await runTransientSearch(query, compile: true)
        }
    }

    /// Run the library's search store for `query` and resolve the hits into
    /// `Document` rows, preserving the engine's relevance order.
    ///
    /// Resolution prefers documents already loaded by the DocumentStore (zero
    /// fetches for the common case of hits inside the browsed library) and
    /// fetches the rest individually — a search page is ≤`transientSearchLimit`
    /// rows, so per-id gets are fine here.
    @MainActor
    func runTransientSearch(_ query: String, compile: Bool = false) async {
        guard let library = LibraryManager.shared.getLibrary(id: windowState.libraryId)
            ?? LibraryManager.shared.globalLibrary else { return }
        let store = library.searchStore
        // Name the library that is about to be QUERIED, not the one the
        // window nominally shows (Daniel, 2026-09-01). The `?? globalLibrary`
        // above is the divergence: when `windowState.libraryId` does not
        // resolve, this searches a different library than the chrome names.
        // Recording it here makes the chrome follow the request; the warning
        // makes the underlying id mismatch visible rather than silent.
        if LibraryManager.shared.getLibrary(id: windowState.libraryId) == nil {
            searchResultsLogger.warning(
                "search fell back to the global library — window libraryId did not resolve"
            )
        }
        chromeUX.resultsLibraryName = library.displayName
        let folderId = transientSearchScopeIsFolder ? transientSearchContextFolder?.id : nil
        await store.performSearch(
            query: query,
            limit: transientSearchLimit,
            // All four legs (#4118): documents + entities + claims +
            // workflow artifacts — the grid shows documents; the bar
            // presents the typed hits.
            include: [.content, .entities, .claims, .artifacts],
            searchType: transientSearchType,
            sortBy: transientSearchSortBy,
            sortOrder: transientSearchSortDirection,
            folderId: folderId,
            // #4116: compile on the explicit submit only; re-runs (options,
            // changeToken, Load More) search the raw query without LLM latency.
            compile: compile
        )

        // A newer query superseded this one while the request was in flight —
        // its own resolution pass owns the result state.
        guard activeSearchQuery == query else { return }

        let orderedIds = Self.hitDocumentIds(results: store.results, stats: store.searchStats)

        // Loaded rows first, then ONE batched fetch for the rest (perf audit
        // 2026-08-19: this was ~90 sequential per-id GETs after every
        // search). Engine order isn't relevance order, so re-order by the
        // hit list; a hit whose document can't load is simply absent — the
        // engine already 500s on real failures (#4109), so a missing row is
        // a per-row race (deleted since indexing), not a silent state.
        var byId: [String: Document] = [:]
        var missing: [String] = []
        for documentId in orderedIds {
            if let known = documentStore.currentDocuments.first(where: { $0.id == documentId })
                ?? documentStore.collections.first(where: { $0.id == documentId }) {
                byId[documentId] = known
            } else {
                missing.append(documentId)
            }
        }
        if !missing.isEmpty {
            do {
                for doc in try await library.documentService.getDocuments(ids: missing) {
                    byId[doc.id] = doc
                }
            } catch {
                searchResultsLogger.warning(
                    "search hit batch resolve failed for \(missing.count) id(s): \(error.localizedDescription)"
                )
            }
        }
        let resolved = orderedIds.compactMap { byId[$0] }
        guard activeSearchQuery == query else { return }
        searchResultDocuments = resolved
        // Scope the reading surface to the results (user, 2026-08-19): with
        // nothing selected, the reader kept showing the pre-search document.
        // A selection the user makes still wins, as everywhere else.
        if browserSelection.isEmpty, let first = resolved.first,
           detailDocument?.id != first.id,
           !resolved.contains(where: { $0.id == detailDocument?.id }) {
            detailDocument = first
        }
        // The reader shows the SELECTED result with the matched terms lit
        // (Daniel, 2026-09-01: the reader "shows something unrelated"). The
        // find-in-page machinery already exists — `ReaderSearchState` driving
        // the CSS Custom Highlight API through `WebPaneFindSync` (#4338) —
        // it was simply never told what the library search was looking for.
        // Seeding it here means one query string reaches both surfaces from
        // the same place the request was built, rather than a second copy of
        // "what are we searching for" living in the reader.
        chromeUX.readerFindQuery = query
        transientSearchRowHits = Self.rowHits(results: store.results, stats: store.searchStats)
    }

    /// Relevance for EVERY row the grid shows — not just the document leg.
    ///
    /// `hitDocumentIds` folds entity- and claim-leg hits into the result set
    /// as nodes (#4118), but the hit map was built from `store.results`
    /// alone, so those rows resolved to `nil` and rendered with no relevance
    /// number at all (Daniel, 2026-09-01: "some rows show no relevance
    /// number"). A row on screen because the engine ranked it can always say
    /// how well it ranked; the legs carry their own similarity score, so the
    /// number is real, not invented.
    ///
    /// The document leg wins on collision — a doc that matched text AND an
    /// entity is scored by the fused ranking, which already counted the
    /// entity evidence (`_kg_evidence_results`, RRF leg #1833 M1).
    static func rowHits(
        results: [SearchResult], stats: SearchResponse?
    ) -> [String: TransientSearchRowHit] {
        var hits = Dictionary(
            results.map { ($0.documentId, $0.rowHit) },
            uniquingKeysWith: { first, _ in first }
        )
        guard let stats else { return hits }
        for entity in stats.entityHits {
            guard let documentId = entity.sourceDocumentIds?.first,
                  hits[documentId] == nil else { continue }
            hits[documentId] = TransientSearchRowHit(
                excerpt: entity.canonicalName,
                score: entity.similarityScore ?? 0
            )
        }
        for claim in stats.claimHits {
            guard let documentId = claim.sourceDocumentId,
                  hits[documentId] == nil else { continue }
            hits[documentId] = TransientSearchRowHit(
                excerpt: claim.text,
                score: claim.similarityScore ?? 0
            )
        }
        return hits
    }

    /// Grow the page and re-run the active query (S9 UI half).
    @MainActor
    func loadMoreTransientResults() {
        guard let query = activeSearchQuery else { return }
        transientSearchLimit += Self.transientSearchPageSize
        Task { @MainActor in
            await runTransientSearch(query)
        }
    }

    /// Persist the active transient query as a SavedSearch — the ONE explicit
    /// save path (#4086); searching itself never persists anything.
    @MainActor
    func saveTransientSearch() async {
        guard let query = activeSearchQuery,
              let library = LibraryManager.shared.getLibrary(id: windowState.libraryId)
                  ?? LibraryManager.shared.globalLibrary else { return }
        do {
            _ = try await library.savedSearchService.saveSearch(
                query: query,
                isSmartSearch: true,
                searchType: transientSearchType,
                sortBy: transientSearchSortBy,
                sortDirection: transientSearchSortDirection
            )
            try await library.savedSearchService.loadSavedSearches()
        } catch {
            searchResultsLogger.error("Save search failed: \(error.localizedDescription)")
        }
    }

    /// Navigate to the document behind any search hit (#4118, #4403).
    ///
    /// Took a typed `SearchArtifactHit` while artifacts were the only rendered
    /// leg. Entities and claims resolve to a document too, so the parameter is
    /// the document id all three already carry.
    @MainActor
    func openHitDocument(_ documentId: String) {
        Task { @MainActor in
            guard let library = LibraryManager.shared.getLibrary(id: windowState.libraryId)
                ?? LibraryManager.shared.globalLibrary else { return }
            do {
                let doc = try await library.documentService.getDocument(documentId)
                navigateToDocument(doc)
            } catch {
                searchResultsLogger.error(
                    "search hit \(documentId, privacy: .public) failed to open: \(error.localizedDescription)"
                )
            }
        }
    }

    /// Human summary of a compiled query's structured filters (#4116).
    static func compiledFiltersSummary(_ compiled: Components.Schemas.CompiledQuery) -> String {
        var parts: [String] = []
        if let from = compiled.dateFrom, let until = compiled.dateTo {
            parts.append("\(from) – \(until)")
        } else if let from = compiled.dateFrom {
            parts.append("from \(from)")
        } else if let until = compiled.dateTo {
            parts.append("until \(until)")
        }
        if let entities = compiled.entities, !entities.isEmpty {
            parts.append(entities.joined(separator: ", "))
        }
        if let docType = compiled.docType {
            parts.append(docType)
        }
        return parts.isEmpty ? "" : " · \(parts.joined(separator: " · "))"
    }

    /// Drop the PREVIOUS query's rows the moment a new query starts.
    ///
    /// Daniel, 2026-09-01: old results lingered and the new ones appeared
    /// beneath them. `SearchStore.performSearch` replaces `results` only when
    /// the response lands, and `searchResultDocuments` is resolved a further
    /// round trip later — so for the whole in-flight window the grid showed
    /// the old query's rows under a bar that said "Searching for …", and the
    /// swap read as an append. Clearing at submit is the honest state: there
    /// are no results for this query yet.
    ///
    /// Deliberately NOT called from `loadMoreTransientResults` or the
    /// retrieval-type re-run — those refine the SAME query, and blanking the
    /// grid to grow a page would be a flash, not information.
    @MainActor
    func clearTransientSearchResults() {
        searchResultDocuments = []
        transientSearchRowHits = [:]
    }

    /// Leave transient-search presentation and return to folder browsing.
    @MainActor
    func clearTransientSearch() {
        activeSearchQuery = nil
        searchResultDocuments = []
        transientSearchRowHits = [:]
        libraryToolbarState.userChoseSortDuringSearch = false
        transientSearchLimit = Self.transientSearchPageSize
        transientSearchContextFolder = nil
        transientSearchScopeIsFolder = false
        chromeUX.readerFindQuery = ""
        chromeUX.resultsLibraryName = nil
    }

    /// What the chrome calls the library while results are showing: the one
    /// the request actually ran against, falling back to the window's own
    /// library when no search is up. ONE value, so the toolbar island and the
    /// results header cannot name different libraries (Daniel, 2026-09-01).
    var searchChromeLibraryName: String {
        chromeUX.resultsLibraryName ?? windowState.library?.displayName ?? "Library"
    }
}

extension ContentView {
    /// Every hit is a NODE in the grid (#4118, ruling 2026-08-19): entity,
    /// claim and artifact hits resolve to their parent documents and join
    /// the result set, so all legs are clickable, dataset-viewable,
    /// canvas-able and saveable like any other node — never a separate
    /// list stacked above the library. Deduped, relevance order preserved.
    static func hitDocumentIds(
        results: [SearchResult], stats: SearchResponse?
    ) -> [String] {
        var hitIds: [String] = results.map(\.documentId)
        if let stats {
            hitIds.append(contentsOf: stats.artifactHits.map(\.documentId))
            hitIds.append(contentsOf: stats.entityHits.compactMap(\.sourceDocumentIds?.first))
            hitIds.append(contentsOf: stats.claimHits.compactMap(\.sourceDocumentId))
        }
        var seen = Set<String>()
        return hitIds.filter { seen.insert($0).inserted }
    }
}
