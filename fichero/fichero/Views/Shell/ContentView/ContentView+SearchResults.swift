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
        transientSearchRowHits = Dictionary(
            store.results.map { ($0.documentId, $0.rowHit) },
            uniquingKeysWith: { first, _ in first }
        )
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
    }

    // MARK: - Results bar (S5/S9 UI halves)

    /// Header above the Library view while a transient search is active:
    /// honest result count (#4113), Load More when the engine reports more
    /// pages, the explicit Save Search action, and the engine's failure
    /// detail (#4109) — never a silent empty grid.
    ///
    /// Structural invariant (crash, 2026-07-27): this view is mounted through
    /// `AnyView(...)` inside `.safeAreaInset` at the content-router boundary
    /// (#4188). The inset's erased content must keep ONE concrete root across
    /// the active/inactive flip — a bare `if let` here makes the erased view
    /// list alternate between empty and populated, which the attribute graph
    /// resolves by re-typing live attributes mid-update and dies with a
    /// precondition failure when a query starts or clears. The conditional
    /// therefore lives INSIDE a constant outer container: mounting or
    /// dismissing the bar only inserts/removes children of a stable root.
    /// An empty VStack lays out at zero size, so the inactive state still
    /// reserves no inset space.
    var transientSearchResultsBar: some View {
        VStack(spacing: 0) {
            if let query = activeSearchQuery, let store = transientSearchStore {
                activeSearchResultsContent(query: query, store: store)
            }
        }
    }

    @ViewBuilder
    private func activeSearchResultsContent(query: String, store: SearchStore) -> some View {
        VStack(spacing: 0) {
            searchResultsHeaderRow(query: query, store: store)

            // What the AI actually searched (#4116) — always visible so
            // the compiled query is inspectable; edit the toolbar field
            // to override. Compilation failure shows too, never hidden.
            compilationDetailRow(store: store)

            // Every non-document leg the engine searched (#4118, #4403).
            // Entities and claims were returned and counted but never
            // rendered, which is why searching a person surfaced only
            // Artifacts. All three now share one section type.
            nonDocumentHitSections(store: store)

            Divider()
        }
        // A document.* change on this (or another window's) library bumps
        // SearchStore.changeToken (#3249) — re-run the active query so
        // renamed / deleted / re-OCR'd docs don't linger stale in the
        // results. Lives on the bar because the bar is mounted exactly
        // while a transient search is presented.
        .onChange(of: store.changeToken) { _, _ in
            Task { @MainActor in
                await runTransientSearch(query)
            }
        }
        // Changing type/sort re-runs the active query with a fresh page
        // (#4112/S8) — the values are Strings, so one observed tuple
        // keeps the modifier count down.
        .onChange(of: [transientSearchType, transientSearchSortBy, transientSearchSortDirection]) { _, _ in
            transientSearchLimit = Self.transientSearchPageSize
            Task { @MainActor in
                await runTransientSearch(query)
            }
        }
    }

    @ViewBuilder
    private func searchResultsHeaderRow(query: String, store: SearchStore) -> some View {
        HStack(spacing: 12) {
            searchStatusLabel(query: query, store: store)

            Spacer()

            searchScopePicker(query: query)

            searchOptionsMenu

            if store.searchStats?.hasMore == true {
                Button("Load More") {
                    loadMoreTransientResults()
                }
                .controlSize(.small)
            }

            searchResultActions(store: store)

            Button {
                toolbarSearchText = ""
                clearTransientSearch()
            } label: {
                Label("Done", systemImage: "xmark.circle.fill")
                    .labelStyle(.titleOnly)
            }
            .controlSize(.small)
            .help("Clear the search and return to browsing")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.bar)
        .accessibilityIdentifier("library.search.resultsBar")
    }

    /// The leading half of the bar: what the search is doing, or what it
    /// found. Exactly one of failure / in-flight / count is ever shown.
    @ViewBuilder
    private func searchStatusLabel(query: String, store: SearchStore) -> some View {
        if let failure = store.searchFailure {
            // Typed failure: stable message inline, raw detail only on
            // demand (error-presentation convention — never dump error
            // text in chrome).
            Label(failure.message, systemImage: "exclamationmark.triangle")
                .font(.callout)
                .foregroundStyle(.red)
                .help(failure.detail)
        } else if store.isSearching {
            ProgressView()
                .controlSize(.small)
            Text("Searching for “\(query)”…")
                .font(.callout)
                .foregroundStyle(.secondary)
        } else {
            // #4403: this read `searchStats.totalResults`, which is the
            // DOCUMENT leg alone — so a query matching six artifacts and no
            // documents said "3 results" above a section headed "Artifacts (6)".
            //
            // It now reads the SAME `SearchHitCounts` the body renders from:
            // `transientSearchHitCounts` counts `searchResultDocuments`,
            // `artifactHits`, `entityHits` and `claimHits` — the four arrays the
            // sections below are built out of. Header and body are therefore one
            // value from one source, and cannot disagree by construction.
            //
            // Deliberately NOT the server's new `rendered_total`, which is also
            // correct arithmetic but is a SECOND source of truth for one number:
            // it would have to be kept in step with whatever the client actually
            // renders, and "two places compute the same thing" is the defect
            // class this issue belongs to. rendered_total remains available and
            // is worth using as a server/client AGREEMENT check — a different
            // job from deciding what the header says.
            let total = transientSearchHitCounts.total
            Text("\(total) result\(total == 1 ? "" : "s") for “\(query)”")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
    }

    /// Scope control (#4107/S3): whole library vs the folder that was being
    /// browsed when the search ran. Absent when there was no browsing folder.
    /// No "All libraries" until cross-library fan-out lands (#4110).
    @ViewBuilder
    private func searchScopePicker(query: String) -> some View {
        if let folder = transientSearchContextFolder {
            Picker("Search scope", selection: $transientSearchScopeIsFolder) {
                Text("Library").tag(false)
                Text("“\(folder.name)”").tag(true)
            }
            .pickerStyle(.segmented)
            .fixedSize()
            .labelsHidden()
            .controlSize(.small)
            .onChange(of: transientSearchScopeIsFolder) { _, _ in
                transientSearchLimit = Self.transientSearchPageSize
                Task { @MainActor in
                    await runTransientSearch(query)
                }
            }
        }
    }

    /// What you can do with a result set: chat it, or save it. Both require
    /// results that actually loaded, so a failed search offers neither.
    @ViewBuilder
    private func searchResultActions(store: SearchStore) -> some View {
        if !store.results.isEmpty && store.searchFailure == nil {
            // Chat the search (#4117): the result set becomes the
            // conversation's document scope.
            Button {
                openChatWithSearchResults()
            } label: {
                Label("Chat", systemImage: "bubble.left.and.text.bubble.right")
            }
            .controlSize(.small)
            .help("Chat about these results — the search scope becomes the conversation's context")

            Button {
                Task { await saveTransientSearch() }
            } label: {
                Label("Save Search", systemImage: "square.and.arrow.down")
            }
            .controlSize(.small)
            .help("Save this search to the sidebar")
        }
    }

    @ViewBuilder
    private func compilationDetailRow(store: SearchStore) -> some View {
        if let compiled = store.searchStats?.compiledQuery {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .foregroundStyle(.secondary)
                Text("Searched: “\(compiled.semanticQuery)”\(Self.compiledFiltersSummary(compiled))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .help("Searched: “\(compiled.semanticQuery)”\(Self.compiledFiltersSummary(compiled))")
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 4)
            .background(.bar)
        } else if let compileError = store.searchStats?.compilationError {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .foregroundStyle(.secondary)
                // Readable failure (the user, live 2026-07-27): one
                // truncated line hid the actual error. Wrap up to
                // four lines + full text on hover — a failure detail
                // the user can't read is a silent failure.
                Text("AI couldn't refine this search (\(compileError)) — searched your words as typed.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
                    .textSelection(.enabled)
                    .help(compileError)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 4)
            .background(.bar)
        }
    }

    /// Artifacts, entities and claims — the three legs the engine searches
    /// besides documents (#4403).
    ///
    /// Each renders through the same `SearchHitSection`, so a leg cannot be
    /// silently unrepresented again: adding one here is the whole change.
    @ViewBuilder
    private func nonDocumentHitSections(store: SearchStore) -> some View {
        if let stats = store.searchStats {
            SearchHitSection(
                title: "Artifacts",
                systemImage: "shippingbox",
                rows: SearchHitPresentation.artifactRows(stats.artifactHits),
                open: openHitDocument
            )
            SearchHitSection(
                title: "People & Places",
                systemImage: "person.2",
                rows: SearchHitPresentation.entityRows(stats.entityHits),
                open: openHitDocument
            )
            SearchHitSection(
                title: "Claims",
                systemImage: "quote.opening",
                rows: SearchHitPresentation.claimRows(stats.claimHits),
                open: openHitDocument
            )
        }
    }

    /// Search type and sort order (#4112/S8), lifted out of
    /// `searchResultsHeaderRow` (#4353).
    ///
    /// That function was at 95 of the 100-line ERROR threshold — five lines of
    /// headroom, in a file #4403 had just added to. Extracted by cohesion: this
    /// is one self-contained control, not a slice taken to reach a number.
    @ViewBuilder
    private var searchOptionsMenu: some View {
                // Real parameters (#4112/S8): search type + sort, the
                // knobs the deleted mode surface used to own. One compact
                // menu, not a pile of chrome.
                Menu {
                    Picker("Search Type", selection: $transientSearchType) {
                        Text("Hybrid").tag("hybrid")
                        Text("Semantic").tag("semantic")
                        Text("Full Text").tag("fulltext")
                    }
                    Divider()
                    Picker("Sort By", selection: $transientSearchSortBy) {
                        Text("Relevance").tag("relevance")
                        Text("Date").tag("date")
                        Text("Name").tag("name")
                        Text("Size").tag("size")
                    }
                    Picker("Order", selection: $transientSearchSortDirection) {
                        Text("Descending").tag("desc")
                        Text("Ascending").tag("asc")
                    }
                } label: {
                    Label("Search Options", systemImage: "slider.horizontal.3")
                        .labelStyle(.iconOnly)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Search type and sort order")
    }

}
