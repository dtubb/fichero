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
        // What stays: the count (now also the pager), the scope control, the
        // retrieval-type menu, and Save — the one explicit persistence path
        // (#4086), which has no bottom-bar home to move to yet.
        HStack(spacing: 12) {
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

            searchScopePicker(query: query)

            searchOptionsMenu

            searchResultActions(store: store)
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
        HStack(spacing: 6) {
            // The header must say WHERE it looked (Daniel, 2026-09-01: the
            // bar read as though the search were scoped to the open folder,
            // and once named the wrong library). The scope comes from the
            // same state the request is built from, so the sentence and the
            // query cannot drift apart.
            Text("\(total) result\(total == 1 ? "" : "s") for “\(query)” in \(searchScopeName)")
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
            return "“\(folder.name)”"
        }
        // The library the RESULTS came from — the same value the toolbar
        // island shows, so the two cannot disagree.
        return searchChromeLibraryName
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

    /// What you can do with a result set that the SEARCH owns: save it.
    ///
    /// Chat left this bar (Daniel, 2026-09-01) — the toolbar's chat button is
    /// the one chat affordance, and `openChatWithSearchResults()` stays as the
    /// action it calls when a search is showing. Save has no bottom-bar home
    /// yet and is the only explicit persistence path (#4086), so it stays here
    /// rather than being deleted with nowhere to land.
    @ViewBuilder
    private func searchResultActions(store: SearchStore) -> some View {
        if !store.results.isEmpty && store.searchFailure == nil {
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

    /// Search type (#4112/S8), lifted out of
    /// `searchResultsHeaderRow` (#4353).
    ///
    /// That function was at 95 of the 100-line ERROR threshold — five lines of
    /// headroom, in a file #4403 had just added to. Extracted by cohesion: this
    /// is one self-contained control, not a slice taken to reach a number.
    @ViewBuilder
    private var searchOptionsMenu: some View {
                // The one real retrieval parameter (#4112/S8) the deleted
                // mode surface used to own. Sort moved to the bottom bar
                // (2026-09-01); what is left is a single picker.
                Menu {
                    Picker("Search Type", selection: $transientSearchType) {
                        Text("Hybrid").tag("hybrid")
                        Text("Semantic").tag("semantic")
                        Text("Full Text").tag("fulltext")
                    }
                    // Sort left this menu (Daniel, 2026-09-01): the library
                    // BOTTOM bar's sort menu already owns the order of these
                    // rows — it sets `userChoseSortDuringSearch` and overrides
                    // the engine's relevance default (#11). Two sort controls
                    // over one list is the thing being fixed. The request
                    // still asks the engine for relevance/desc, which is the
                    // order the grid shows until the bottom bar says otherwise.
                } label: {
                    Label("Search Type", systemImage: "slider.horizontal.3")
                        .labelStyle(.iconOnly)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("How the engine retrieves: hybrid, semantic, or full text")
    }

}
