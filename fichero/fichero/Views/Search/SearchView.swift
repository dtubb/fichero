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

    @EnvironmentObject var searchService: SearchServiceGenerated
    @EnvironmentObject var apiClient: APIClient

    var body: some View {
        resultsPanel
            // Search input wired via the standard macOS .searchable
            // modifier so users get ⌘F focus, the system clear button,
            // and the toolbar-integrated search field for free (#481).
            // Submitting (Return) fires the query; live re-querying as
            // the user types is left to the saved-search auto-trigger
            // path so we don't hammer the backend on each keystroke.
            .searchable(text: $queryText, placement: .toolbar, prompt: "Search documents…")
            .onSubmit(of: .search) { performSearch() }
            .onAppear {
                if let search = savedSearch {
                    queryText = search.query
                    performSearch()
                }
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
            onLoadDocument: loadDocument
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
