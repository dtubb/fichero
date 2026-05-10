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

    @EnvironmentObject var searchService: SearchServiceGenerated
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var libraryManager: LibraryManager
    @EnvironmentObject var windowState: WindowState

    var body: some View {
        resultsPanel
            // The single root-level .searchable on ContentView is now the
            // toolbar entry point — SearchView no longer owns one of its
            // own (avoids a stacked / duplicated search field on macOS).
            // queryText still drives this view's results display + the
            // empty-state copy; it gets seeded from savedSearch on appear
            // and on saved-search changes (see .onAppear / .onChange below)
            // and from the toolbar's runToolbarSearch flow when a new
            // search is submitted.
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
