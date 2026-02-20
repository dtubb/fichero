import SwiftUI

/// Search view with query input, filters, and results
struct SearchView: View {
    let savedSearch: SavedSearch?
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    var onSearchSaved: (() -> Void)?
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State var queryText: String = ""
    @State var isSmartSearch: Bool = true  // Default to smart search (semantic)
    @State var searchType: String = "hybrid"  // "semantic", "fulltext", "hybrid"
    @State var sortBy: String = "relevance"  // "relevance", "date", "name"
    @State var sortOrder: String = "desc"    // "asc", "desc"
    @State var filters = SearchFilters()
    @State var searchResults: [SearchResult] = []
    @State var searchStats: SearchResponse?
    @State var isSearching: Bool = false
    @State var searchError: String?
    @State var isSaving: Bool = false

    @EnvironmentObject var searchService: SearchServiceGenerated
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
    @EnvironmentObject var apiClient: APIClient

    var body: some View {
        HSplitView {
            // Left: Filters panel
            SearchFiltersPanel(
                queryText: $queryText,
                isSmartSearch: $isSmartSearch,
                searchType: $searchType,
                sortBy: $sortBy,
                sortOrder: $sortOrder,
                filters: $filters,
                onSearch: performSearch,
                onClear: clearFilters
            )
            .frame(minWidth: 200, maxWidth: 250)

            // Right: Results
            resultsPanel
        }
        .onAppear {
            if let search = savedSearch {
                queryText = search.query
                filters = search.filters
                isSmartSearch = search.isSmartSearch
                // Note: searchType, sortBy, sortOrder would need to be added to SavedSearch model
                // For now, use defaults
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
        VStack(spacing: 0) {
            // View-specific toolbar at top
            SearchViewToolbar(
                isSearching: isSearching,
                searchError: searchError,
                resultsCount: searchResults.count,
                hasQuery: !queryText.isEmpty,
                hasActiveFilters: hasActiveFilters,
                onSaveSearch: saveSearch
            )

            Divider()

            // Results display (adapts to displayMode)
            SearchResultsDisplay(
                searchResults: searchResults,
                displayMode: displayMode,
                selection: $selection,
                onLoadDocument: loadDocument
            )
        }
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
