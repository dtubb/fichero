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
