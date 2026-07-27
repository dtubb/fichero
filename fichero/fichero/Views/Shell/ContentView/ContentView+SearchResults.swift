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

    /// Navigate to the document that owns a matched artifact (#4118).
    @MainActor
    func openArtifactHit(_ hit: Components.Schemas.SearchArtifactHit) {
        Task { @MainActor in
            guard let library = LibraryManager.shared.getLibrary(id: windowState.libraryId)
                ?? LibraryManager.shared.globalLibrary else { return }
            do {
                let doc = try await library.documentService.getDocument(hit.documentId)
                navigateToDocument(doc)
            } catch {
                searchResultsLogger.error(
                    "artifact hit \(hit.documentId, privacy: .public) failed to open: \(error.localizedDescription)"
                )
            }
        }
    }

    /// Human summary of a compiled query's structured filters (#4116).
    static func compiledFiltersSummary(_ compiled: Components.Schemas.CompiledQuery) -> String {
        var parts: [String] = []
        if let from = compiled.dateFrom, let to = compiled.dateTo {
            parts.append("\(from) – \(to)")
        } else if let from = compiled.dateFrom {
            parts.append("from \(from)")
        } else if let to = compiled.dateTo {
            parts.append("until \(to)")
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
        transientSearchLimit = Self.transientSearchPageSize
        transientSearchContextFolder = nil
        transientSearchScopeIsFolder = false
    }

    // MARK: - Results bar (S5/S9 UI halves)

    /// Header above the Library view while a transient search is active:
    /// honest result count (#4113), Load More when the engine reports more
    /// pages, the explicit Save Search action, and the engine's failure
    /// detail (#4109) — never a silent empty grid.
    @ViewBuilder
    var transientSearchResultsBar: some View {
        if let query = activeSearchQuery, let store = transientSearchStore {
            VStack(spacing: 0) {
                HStack(spacing: 12) {
                    if let error = store.searchError {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.callout)
                            .foregroundStyle(.red)
                            .lineLimit(2)
                    } else if store.isSearching {
                        ProgressView()
                            .controlSize(.small)
                        Text("Searching for “\(query)”…")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    } else {
                        let total = store.searchStats?.totalResults ?? store.results.count
                        Text("\(total) result\(total == 1 ? "" : "s") for “\(query)”")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    // Scope control (#4107/S3): whole library vs the folder
                    // that was being browsed when the search ran. No "All
                    // libraries" until cross-library fan-out lands (#4110).
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

                    if store.searchStats?.hasMore == true {
                        Button("Load More") {
                            loadMoreTransientResults()
                        }
                        .controlSize(.small)
                    }

                    if !store.results.isEmpty && store.searchError == nil {
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

                // What the AI actually searched (#4116) — always visible so
                // the compiled query is inspectable; edit the toolbar field
                // to override. Compilation failure shows too, never hidden.
                if let compiled = store.searchStats?.compiledQuery {
                    HStack(spacing: 6) {
                        Image(systemName: "sparkles")
                            .foregroundStyle(.secondary)
                        Text("Searched: “\(compiled.semanticQuery)”\(Self.compiledFiltersSummary(compiled))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 4)
                    .background(.bar)
                } else if let compileError = store.searchStats?.compilationError {
                    HStack(spacing: 6) {
                        Image(systemName: "sparkles")
                            .foregroundStyle(.secondary)
                        Text("AI couldn't refine this search (\(compileError)) — searched your words as typed.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 4)
                    .background(.bar)
                }

                // Typed artifact hits (#4118): workflow outputs that matched —
                // type-badged, snippeted, click navigates to the owning doc.
                if let artifactHits = store.searchStats?.artifactHits, !artifactHits.isEmpty {
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 4) {
                            ForEach(Array(artifactHits.prefix(5).enumerated()), id: \.offset) { _, hit in
                                Button {
                                    openArtifactHit(hit)
                                } label: {
                                    HStack(spacing: 6) {
                                        Text(hit.artifactType)
                                            .font(.caption2.weight(.medium))
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 1)
                                            .background(Capsule().fill(Color.secondary.opacity(0.12)))
                                        Text(hit.snippet ?? hit.documentName ?? hit.documentId)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .lineLimit(1)
                                        Spacer()
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                            if artifactHits.count > 5 {
                                Text("…and \(artifactHits.count - 5) more")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.leading, 4)
                    } label: {
                        Label("Artifacts (\(artifactHits.count))", systemImage: "shippingbox")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 4)
                    .background(.bar)
                }

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
    }
}
