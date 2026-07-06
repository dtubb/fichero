import FicheroAPIClient
import SwiftUI

/// Search view with query input, filters, and results
struct SearchView: View {
    let savedSearch: SavedSearch?
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    @Binding var displayMode: ViewDisplayMode  // Universal view mode from toolbar

    // ─── View-local state (UI scaffolding, debounce, persistence) ───
    @State var queryText: String = ""
    @State var searchScopeSelection: SearchScopeSelection = .all

    /// Token used to debounce live-as-you-type search. Each keystroke
    /// schedules a query and stamps a fresh UUID; the scheduled task only
    /// runs the search if its captured token matches the latest. Avoids
    /// hammering the backend on every key press while still feeling
    /// instant once the user pauses (Finder behaviour). 300 ms is the
    /// system's macOS-toolbar-search debounce sweet spot.
    @State private var liveSearchToken = UUID()
    private static let liveSearchDebounceMs: Int = 300

    /// Sort order chosen from the in-view sort menu. Matches backend
    /// `sort_by` values. Persisted via @SceneStorage so the user's pick
    /// survives window restoration.
    @SceneStorage("searchSortBy") var sortBy: String = "relevance"
    @SceneStorage("searchSortDirection") var sortDirection: String = "desc"

    /// JSON-encoded `[String]` of recent queries — most recent first,
    /// dedup'd, capped at 10. @SceneStorage persists across launches.
    /// Used by the empty-state to surface "Recent" pills.
    @SceneStorage("recentSearchQueries") var recentSearchQueriesJSON: String = "[]"

    var recentSearches: [String] {
        RecentSearchesStore.decode(recentSearchQueriesJSON)
    }

    func recordRecentSearch(_ query: String) {
        let updated = RecentSearchesStore.recording(query, into: recentSearches)
        if updated != recentSearches {
            recentSearchQueriesJSON = RecentSearchesStore.encode(updated)
        }
    }

    // ─── Observable data layer (#1903) ───
    // Not `private`: read from the SearchView+Helpers.swift extension (separate file).
    @Environment(SearchStore.self) var searchStore

    @Environment(LibraryManager.self) var libraryManager
    @Environment(WindowState.self) var windowState

    /// True for non-primary split-pane copies. A secondary copy must NOT register
    /// its own `.searchable(placement: .toolbar)` — two copies in one window's
    /// toolbar crash NSToolbar with a duplicate-identifier error (#1447/#2309).
    @Environment(\.isSecondarySplitPane) private var isSecondarySplitPane

    var body: some View {
        VStack(spacing: 0) {
            scopeSelectorBar
            Divider()
            resultsPanel
        }
            // SearchView owns its own toolbar search field via .searchable
            // (#481). Each mode-specific view in this app owns the toolbar
            // search slot for that mode; SwiftUI/AppKit only allows one
            // search item per toolbar at a time, so we never stack them.
            // A secondary split-pane copy must skip this registration or two
            // copies collide → NSToolbar duplicate-identifier crash (#1447/#2309),
            // mirroring LibraryView's guard.
            .conditionalSearchable(
                text: $queryText,
                placement: .toolbar,
                prompt: "Search documents…",
                isActive: ToolbarSearchRegistration.shouldRegister(isSecondarySplitPane: isSecondarySplitPane)
            )
            .onSubmit(of: .search) {
                guard !isSecondarySplitPane else { return }
                performSearch()
            }
            // Save-Search action only when results exist and we're not
            // already viewing a saved search (#481). The button persists
            // the current query as a SavedSearch and routes the sidebar
            // to it so the user can return to the same query later.
            .toolbar {
                if savedSearch == nil
                    && !searchStore.results.isEmpty
                    && !queryText.trimmingCharacters(in: .whitespaces).isEmpty {
                    ToolbarItem(placement: .primaryAction) {
                        Button {
                            Task { await saveCurrentQuery() }
                        } label: {
                            Label("Save Search", systemImage: "square.and.arrow.down")
                        }
                        .help("Save this search to the sidebar")
                    }
                }
                // Sort menu — visible when results exist. Pickers persist
                // via @SceneStorage in SearchView. Re-runs the query on
                // change (see .onChange(of: sortBy / sortDirection)).
                if !searchStore.results.isEmpty {
                    ToolbarItem(placement: .primaryAction) {
                        Menu {
                            Picker("Sort by", selection: $sortBy) {
                                Text("Relevance").tag("relevance")
                                Text("Date").tag("date")
                                Text("Name").tag("name")
                                Text("Size").tag("size")
                            }
                            Divider()
                            Picker("Order", selection: $sortDirection) {
                                Text("Descending").tag("desc")
                                Text("Ascending").tag("asc")
                            }
                        } label: {
                            Label("Sort", systemImage: "arrow.up.arrow.down")
                        }
                        .help("Sort results by relevance, date, name, or size")
                    }
                }
            }
            .onAppear {
                if let search = savedSearch {
                    queryText = search.query
                    performSearch()
                }
                // Pull index health so the empty state can surface
                // "Index Library" when there are no embeddings yet (#481).
                Task { await searchStore.loadIndexStats() }
                // Keyword cloud — top-N tags across the library, rendered
                // in the empty-state as clickable pills.
                Task { await searchStore.loadKeywordCloud(limit: 30) }
            }
            // Spotlight-standard: ↑/↓ move the result selection while the user
            // keeps typing in the search field (#1843). macOS-only bridge; no-op
            // elsewhere.
            .arrowKeyResultNavigation(
                itemIds: searchStore.results.map(\.documentId),
                selection: $selection,
                onActivate: activateSelectedResult
            )
            .onChange(of: savedSearch?.id) { _, _ in
                guard let search = savedSearch else { return }
                queryText = search.query
                performSearch()
            }
            .onChange(of: queryText) { _, newValue in
                // Empty query resets results so the previous-run state
                // doesn't linger when the user clears the field.
                if newValue.trimmingCharacters(in: .whitespaces).isEmpty {
                    Task { await searchStore.performSearch(query: "") }
                    return
                }
                // Live re-search as you type, debounced by 300 ms. Each
                // keystroke updates the token; only the most recent
                // scheduled task actually runs.
                let token = UUID()
                liveSearchToken = token
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: UInt64(Self.liveSearchDebounceMs) * 1_000_000)
                    if liveSearchToken == token {
                        performSearch()
                    }
                }
            }
            .onChange(of: sortBy) { _, _ in
                if !queryText.trimmingCharacters(in: .whitespaces).isEmpty {
                    performSearch()
                }
            }
            .onChange(of: sortDirection) { _, _ in
                if !queryText.trimmingCharacters(in: .whitespaces).isEmpty {
                    performSearch()
                }
            }
            // A document.* change on this (or another window's) library bumps
            // SearchStore.changeToken (#3249) — re-run the active query so
            // renamed / deleted / re-OCR'd docs don't linger stale in the
            // results. Wires the last hop the sibling stores already observe.
            .onChange(of: searchStore.changeToken) { _, _ in
                if !queryText.trimmingCharacters(in: .whitespaces).isEmpty {
                    performSearch()
                }
            }
            .onChange(of: selection) { _, newSelection in
                // Load document when selection changes (single click)
                if let selectedId = newSelection.first {
                    loadDocument(selectedId)
                } else {
                    detailDocument = nil
                }
            }
    }
}

// MARK: - View Components

extension SearchView {
    var scopeSelectorBar: some View {
        HStack(spacing: 8) {
            Text("Search")
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(SearchScope.allCases) { scope in
                let isSelected = searchScopeSelection.contains(scope)
                Button {
                    searchScopeSelection.toggle(scope)
                    if !queryText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        performSearch()
                    }
                } label: {
                    Text(scope.label)
                        .font(.caption.weight(.medium))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .foregroundStyle(isSelected ? Color.accentColor : Color.primary)
                        .background(
                            Capsule().fill(
                                isSelected
                                    ? Color.accentColor.opacity(0.14)
                                    : Color.secondary.opacity(0.10)
                            )
                        )
                        .overlay(
                            Capsule()
                                .stroke(
                                    isSelected
                                        ? Color.accentColor.opacity(0.25)
                                        : Color.secondary.opacity(0.12),
                                    lineWidth: 0.5
                                )
                        )
                }
                .buttonStyle(.plain)
                .help(scope.helpText)
            }

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    var resultsPanel: some View {
        // swiftlint:disable:next todo
        // TODO(#1766): render entity/claim hit rows once SearchResultsDisplay has a mixed-result section layout.
        // Search uses the window toolbar search field, so avoid duplicate in-view toolbar chrome.
        SearchResultsDisplay(
            searchResults: searchStore.results,
            displayMode: displayMode,
            selection: $selection,
            onLoadDocument: loadDocument,
            onOpenExcerpt: { result in
                openExcerpt(result)
            },
            currentQuery: queryText,
            isSearching: searchStore.isSearching,
            indexedCount: searchStore.indexedCount,
            isReindexing: searchStore.isReindexing,
            onReindex: { Task { await reindexLibrary() } },
            suggestions: searchStore.searchStats?.suggestions ?? [],
            onSuggestionTap: { suggestion in
                queryText = suggestion
                performSearch()
            },
            recentSearches: recentSearches,
            onRecentSearchTap: { recent in
                queryText = recent
                performSearch()
            },
            keywordCloud: searchStore.keywordCloud,
            onKeywordTap: { keyword in
                // Keyword cloud taps fire a scoped query — the cloud
                // lives over the 'keywords' artifact type, so a tap on
                // 'social license' should search keywords:"social license"
                // instead of free-text. (#481 follow-up: Daniel hit
                // 95%-on-blank-doc issue without this scoping.)
                let needsQuoting = keyword.contains(" ")
                queryText = needsQuoting
                    ? "keywords:\"\(keyword)\""
                    : "keywords:\(keyword)"
                performSearch()
            }
        )
    }
}

// MARK: - Preview

#Preview {
    SearchView(
        savedSearch: nil,
        selection: .constant([]),
        detailDocument: .constant(nil),
        displayMode: .constant(.icon)
    )
    .environment(SearchStore(searchService: SearchServiceGenerated(ficheroClient: FicheroClient(libraryPath: ""))))
    .frame(width: 800, height: 600)
}
