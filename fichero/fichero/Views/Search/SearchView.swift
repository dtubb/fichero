import SwiftUI

/// Search view with query input, filters, and results
struct SearchView: View {
    let savedSearch: SavedSearch?
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State var queryText: String = ""
    @State var searchResults: [SearchResult] = []
    @State var searchStats: SearchResponse?
    @State var isSearching: Bool = false
    @State var searchError: String?
    @State var indexedCount: Int?
    @State var isReindexing: Bool = false

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

    @EnvironmentObject var searchService: SearchServiceGenerated
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var windowState: WindowState

    var body: some View {
        resultsPanel
            // SearchView owns its own toolbar search field via .searchable
            // (#481). Each mode-specific view in this app owns the toolbar
            // search slot for that mode; SwiftUI/AppKit only allows one
            // search item per toolbar at a time, so we never stack them.
            .searchable(text: $queryText, placement: .toolbar, prompt: "Search documents…")
            .onSubmit(of: .search) { performSearch() }
            // Save-Search action only when results exist and we're not
            // already viewing a saved search (#481). The button persists
            // the current query as a SavedSearch and routes the sidebar
            // to it so the user can return to the same query later.
            .toolbar {
                if savedSearch == nil
                    && !searchResults.isEmpty
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
                if !searchResults.isEmpty {
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
                Task { await loadIndexStats() }
            }
            .onChange(of: savedSearch?.id) { _, _ in
                guard let search = savedSearch else {
                    return
                }
                queryText = search.query
                performSearch()
            }
            .onChange(of: queryText) { _, newValue in
                // Empty query resets results so the previous-run state
                // doesn't linger when the user clears the field.
                if newValue.trimmingCharacters(in: .whitespaces).isEmpty {
                    searchResults = []
                    searchStats = nil
                    searchError = nil
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
    var resultsPanel: some View {
        // Search uses the window toolbar search field, so avoid duplicate in-view toolbar chrome.
        SearchResultsDisplay(
            searchResults: searchResults,
            displayMode: displayMode,
            selection: $selection,
            onLoadDocument: loadDocument,
            currentQuery: queryText,
            isSearching: isSearching,
            indexedCount: indexedCount,
            isReindexing: isReindexing,
            onReindex: { Task { await reindexLibrary() } }
        )
    }
}

// MARK: - Preview

#Preview {
    SearchView(
        savedSearch: nil,
        selection: .constant([]),
        detailDocument: .constant(nil),
        displayMode: .icon
    )
    .frame(width: 800, height: 600)
}
