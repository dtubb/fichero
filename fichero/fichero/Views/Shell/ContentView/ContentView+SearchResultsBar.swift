import FicheroAPIClient
import SwiftUI

// MARK: - Transient-search results bar (split from ContentView+SearchResults
// for file_length, 2026-08-20 — same members, only the file moved)

extension ContentView {
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

            // WHAT RAN (Daniel, 2026-09-02: "the user must SEE what ran").
            // One quiet line under the headline — visibility is the point,
            // so it is always there while a search is presented, and it is
            // never a control.
            retrievalLegsRow(store: store)

            // What the AI actually searched (#4116) — always visible so
            // the compiled query is inspectable; edit the toolbar field
            // to override. Compilation failure shows too, never hidden.
            compilationDetailRow(store: store)

            // Expanded search notice (Daniel, 2026-08-31): one-time
            // explanation that the results include meaning-based matches.
            // Gated on the response's OWN `search_type` — the mode the
            // engine reports it ran — so a full-text search, a failed
            // search (stats nil) or an empty result set never claims it.
            expandedSearchNotice(store: store)

            // Non-document legs are NOT listed here (#4118, ruling
            // 2026-08-19): entity/claim/artifact hits resolve into the grid
            // as nodes; the bar stays a slim two-row header.
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
        // Changing the retrieval type re-runs the active query with a fresh
        // page (#4112/S8).
        // Sort no longer lives in this bar, so only the retrieval type can
        // change here; the bottom bar's sort re-orders the rows client-side
        // and needs no round trip.
        .onChange(of: transientSearchType) { _, _ in
            transientSearchLimit = Self.transientSearchPageSize
            Task { @MainActor in
                await runTransientSearch(query)
            }
        }
        // Scope changed in the options menu (#4107/S3). This handler used to
        // live on the segmented picker itself; the picker is gone, so it sits
        // beside the retrieval-type handler on the container that is mounted
        // for exactly as long as a search is presented. Changing WHERE a
        // search looks is a new request, not a client-side filter.
        .onChange(of: transientSearchScopeIsFolder) { _, _ in
            transientSearchLimit = Self.transientSearchPageSize
            Task { @MainActor in
                await runTransientSearch(query)
            }
        }
    }

    /// The "Expanded Search Results" banner, above the results the grid is
    /// about to show.
    ///
    /// Three conditions, all required, and the notice owns the fourth
    /// (its persisted dismissal):
    ///   1. a search actually completed — `searchStats` is non-nil, so a
    ///      failure or an in-flight query says nothing;
    ///   2. it returned rows, so the sentence describes results on screen;
    ///   3. the mode the ENGINE reports (`search_type`) includes the
    ///      embeddings leg — `"semantic"` or `"hybrid"`. `"fulltext"` is
    ///      keyword-only and the claim would be untrue.
    @ViewBuilder
    private func expandedSearchNotice(store: SearchStore) -> some View {
        if let stats = store.searchStats,
           store.searchFailure == nil,
           !searchResultDocuments.isEmpty {
            ExpandedSearchNotice(searchType: stats.searchType)
        }
    }

    @ViewBuilder
    private func searchResultsHeaderRow(query: String, store: SearchStore) -> some View {
        // CONSOLIDATION (Daniel, 2026-09-01: "too many controls"). What left
        // this row and where it went — each control has ONE home now:
        //  * Ask / Keyword — already a scope inside the search FIELD
        //    (`ContentView+ToolbarSearch.swift`); it was never duplicated here.
        //  * Sort By / Order — the library BOTTOM bar's sort menu, which
        //    already overrides relevance mid-search (`userChoseSortDuringSearch`,
        //    #11). Two sort controls disagreeing about one list is the defect.
        //  * Chat — the toolbar's chat button. Chatting a result set is not a
        //    search-specific verb.
        //  * Done — Esc in the search field (`SearchEscapeDismiss` in ContentView+ToolbarSearch.swift), the
        //    same gesture that dismisses every other transient state.
        //  * Load More — folded into the count, which is the thing that
        //    made you want more.
        //
        // 2026-09-02 finished the job (Daniel: "fold it into a submenu
        // attached to the search field"). The scope pills, the retrieval-type
        // button and Save Search left the row too — they are rows of
        // `SearchFieldOptionsMenu` now, behind the one loupe control below.
        //
        // What stays is not a control at all: the count, and the pager that
        // count justifies. A row above a result set should say what the
        // result set IS; everything that CHANGES it is one gesture away at
        // the loupe, which is where a search's settings are looked for.
        HStack(spacing: 12) {
            // ONE control, at the loupe, holding everything the row used to
            // spread across it (Daniel, 2026-09-02): Ask/Keyword, the scope,
            // the retrieval type and Save Search. The row that is left says
            // only what the results say.
            searchFieldOptionsMenu(store: store)

            searchStatusLabel(query: query, store: store)
                // The flexible element must be the one that gives way, and it
                // must be ALLOWED to (Daniel, 2026-09-01: the bar "rendered
                // off-layout"). Every trailing control is `.fixedSize()`, so
                // with no priority and no minimum the HStack's ideal width
                // exceeded a narrow pane and the trailing buttons were pushed
                // out of it — an HStack clips, it does not collapse.
                .layoutPriority(1)
                .frame(minWidth: 0, alignment: .leading)

            Spacer(minLength: 8)
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
            searchCountLabel(query: query, store: store)
        }
    }

    /// The count, and the pager it justifies.
    ///
    /// #4403: this read `searchStats.totalResults`, which is the DOCUMENT leg
    /// alone — so a query matching six artifacts and no documents said "3
    /// results" above a section headed "Artifacts (6)". The grid IS the
    /// result set now (#4118): every leg's hits resolve into it as nodes, so
    /// the honest count is the rows on screen. Deliberately NOT the server's
    /// `rendered_total`, which is correct arithmetic but a SECOND source of
    /// truth for one number; it stays available as an AGREEMENT check.
    @ViewBuilder
    private func searchCountLabel(query: String, store: SearchStore) -> some View {
        let total = searchResultDocuments.count
        // HONESTY (Daniel, 2026-09-02): when the engine reports
        // `weak_semantic_only` it found no literal and no graph evidence and
        // every vector neighbour is far away. "45 results" over that state
        // claims 45 matches the search did not make. The header says what
        // actually happened instead, and names the best similarity so the
        // weakness is stated, not left to be inferred from the row badges.
        let headline: String = {
            guard let stats = store.searchStats, stats.weakSemanticOnly else {
                return SearchHonestySummary.countHeadline(
                    total: total, query: query, scopeName: searchScopeName
                )
            }
            return SearchHonestySummary.weakHeadline(
                total: total, bestSimilarity: stats.bestSemanticSimilarity
            )
        }()
        HStack(spacing: 6) {
            // The header must say WHERE it looked (Daniel, 2026-09-01: the
            // bar read as though the search were scoped to the open folder,
            // and once named the wrong library). The scope comes from the
            // same state the request is built from, so the sentence and the
            // query cannot drift apart.
            Text(headline)
                .font(.callout)
                .foregroundStyle(.secondary)
                // ONE line, truncating — in a narrow pane this wrapped into a
                // one-character vertical column ("9 1 r e s u l t s…", Daniel
                // 2026-08-22), same class as the editor's "S h".
                .lineLimit(1)
                .truncationMode(.tail)

            // Paging belongs to the count, not to a button three controls
            // away from it: the number you are reading is the reason you want
            // more of them. `.borderless`, not `.link` — LinkButtonStyle is
            // macOS-only and this bar is multiplatform chrome.
            if store.searchStats?.hasMore == true {
                Button("Load more") { loadMoreTransientResults() }
                    .buttonStyle(.borderless)
                    .font(.callout)
                    .fixedSize()
            }
        }
    }

    /// What the results header names as the place searched: the browsed
    /// folder when the scope control says so, otherwise THIS window's
    /// library by its display name — never a name carried over from
    /// whichever library was open before.
    private var searchScopeName: String {
        if transientSearchScopeIsFolder, let folder = transientSearchContextFolder {
            return "“\(folder.shortLabel)”"
        }
        // The library the RESULTS came from — the same value the toolbar
        // island shows, so the two cannot disagree.
        return searchChromeLibraryName
    }

    /// Every control the row used to carry, behind one loupe.
    ///
    /// The bindings are the SAME state the request is built from
    /// (`runTransientSearch` reads `transientSearchScopeIsFolder` and
    /// `transientSearchType`; `runToolbarSearch` reads `searchFieldMode`), so
    /// the menu cannot show a setting the next search will not honour. The
    /// menu body itself is `SearchFieldOptionsMenu` in
    /// `Views/Library/Search/` — a plain view over bindings, so the same rows
    /// can be mounted inside the toolbar search item without a second copy of
    /// the scope logic.
    @ViewBuilder
    private func searchFieldOptionsMenu(store: SearchStore) -> some View {
        SearchFieldOptionsMenuButton(
            mode: searchFieldModeBinding,
            scopeIsFolder: $transientSearchScopeIsFolder,
            searchType: $transientSearchType,
            libraryName: searchChromeLibraryName,
            contextFolder: transientSearchContextFolder,
            // What the knowledge graph actually has (Daniel, 2026-09-02:
            // "with no graph or garbage entities the graph must be OFF").
            // `nil` when no response has reported it — the rung stays
            // enabled rather than being disabled on an unasked question.
            reviewedEntityCount: store.searchStats?.reviewedEntityCount,
            // Save is offered for a result set worth saving, and never over a
            // failure — saving a query that just errored would persist a
            // question the library could not answer.
            canSave: !store.results.isEmpty && store.searchFailure == nil,
            onSave: { Task { await saveTransientSearch() } }
        )
    }

    /// The legs line: how many rows each retrieval leg contributed, and
    /// whether the graph leg ran at all.
    ///
    /// Absent over a failure, an in-flight query, and an engine that reports
    /// no legs — the line describes a completed retrieval or it says nothing.
    @ViewBuilder
    private func retrievalLegsRow(store: SearchStore) -> some View {
        if let stats = store.searchStats,
           store.searchFailure == nil,
           !store.isSearching,
           let legs = SearchHonestySummary.legsLine(
               legs: stats.legs, graphLegEnabled: stats.graphLegEnabled
           ) {
            HStack(spacing: 6) {
                Text(legs)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
                    .help("Which retrieval legs produced these results")
                    .accessibilityIdentifier("library.search.legs")
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 4)
            .background(.bar)
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
}
