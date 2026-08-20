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
            // The grid IS the result set now (#4118): every leg's hits resolve
            // into it as nodes, so the honest count is the rows on screen —
            // summing the legs would double-count a doc that also matched an
            // entity.
            let total = searchResultDocuments.count
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
