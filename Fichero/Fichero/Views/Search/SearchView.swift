import SwiftUI

/// Search view with query input, filters, and results
struct SearchView: View {
    let savedSearch: SavedSearch?
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    var onSearchSaved: (() -> Void)?

    @State private var queryText: String = ""
    @State private var isSmartSearch: Bool = true  // Default to smart search (semantic)
    @State private var searchType: String = "hybrid"  // "semantic", "fulltext", "hybrid"
    @State private var sortBy: String = "relevance"  // "relevance", "date", "name"
    @State private var sortOrder: String = "desc"    // "asc", "desc"
    @State private var filters = SearchFilters()
    @State private var searchResults: [SearchResult] = []
    @State private var searchStats: SearchResponse?
    @State private var isSearching: Bool = false
    @State private var searchError: String?
    @State private var isSaving: Bool = false

    private let searchService = SearchService(apiClient: APIClient())
    private let savedSearchService = SavedSearchService(apiClient: APIClient())

    var body: some View {
        HSplitView {
            // Left: Filters panel
            filtersPanel
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
    // MARK: - Filters Panel

    var filtersPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Search query
                VStack(alignment: .leading, spacing: 8) {
                    Text("Query")
                        .font(.headline)

                    TextField("Search documents...", text: $queryText)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit {
                            performSearch()
                        }

                    Toggle("Smart Search (AI)", isOn: $isSmartSearch)
                        .font(.caption)
                }

                // Search Type
                VStack(alignment: .leading, spacing: 8) {
                    Text("Search Type")
                        .font(.headline)

                    Picker("Search Type", selection: $searchType) {
                        Text("Hybrid").tag("hybrid")
                        Text("Semantic").tag("semantic")
                        Text("Full-Text").tag("fulltext")
                    }
                    .pickerStyle(.segmented)
                }

                Divider()

                // Sort Options
                VStack(alignment: .leading, spacing: 8) {
                    Text("Sort By")
                        .font(.headline)

                    Picker("Sort Field", selection: $sortBy) {
                        Text("Relevance").tag("relevance")
                        Text("Date").tag("date")
                        Text("Name").tag("name")
                    }
                    .pickerStyle(.menu)

                    Picker("Order", selection: $sortOrder) {
                        Text("Descending").tag("desc")
                        Text("Ascending").tag("asc")
                    }
                    .pickerStyle(.segmented)
                }

                Divider()

                // Document Type filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("Document Type")
                        .font(.headline)

                    ForEach(DocType.allCases, id: \.self) { type in
                        Toggle(type.rawValue.capitalized, isOn: binding(for: type))
                            .font(.subheadline)
                    }
                }

                Divider()

                // File Type filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("File Type")
                        .font(.headline)

                    ForEach(FileType.allCases, id: \.self) { type in
                        Toggle(type.rawValue.capitalized, isOn: binding(for: type))
                            .font(.subheadline)
                    }
                }

                Divider()

                // Status filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("Status")
                        .font(.headline)

                    ForEach(Status.allCases, id: \.self) { status in
                        Toggle(status.rawValue.capitalized, isOn: binding(for: status))
                            .font(.subheadline)
                    }
                }

                Divider()

                // Content filter
                VStack(alignment: .leading, spacing: 8) {
                    Text("Content")
                        .font(.headline)

                    Picker("Has Content", selection: $filters.hasContent) {
                        Text("Any").tag(nil as Bool?)
                        Text("With Text").tag(true as Bool?)
                        Text("Without Text").tag(false as Bool?)
                    }
                    .pickerStyle(.segmented)
                }

                Spacer()

                // Actions
                HStack {
                    Button("Clear") {
                        clearFilters()
                    }

                    Spacer()

                    Button("Search") {
                        performSearch()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding()
        }
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Results Panel

    private var resultsPanel: some View {
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

            // Results list
            if searchResults.isEmpty && !isSearching {
                emptyState
            } else {
                List(selection: $selection) {
                    ForEach(searchResults) { result in
                        SearchResultRowFromAPI(result: result)
                            .tag(result.documentId)
                            .draggable(result.documentId)
                            .onTapGesture(count: 2) {
                                loadDocument(result.documentId)
                            }
                    }
                }
                .listStyle(.inset)
            }
        }
    }

    private func loadDocument(_ id: String) {
        Task {
            do {
                let doc: Document = try await APIClient().get("/documents/\(id)")
                await MainActor.run {
                    detailDocument = doc
                }
            } catch {
                NSLog("[SearchView] Failed to load document: %@", error.localizedDescription)
            }
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("No Results")
                .font(.headline)

            Text("Enter a query or adjust filters to search")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Helpers

extension SearchView {
    var hasActiveFilters: Bool {
        filters.docTypes != nil ||
        filters.fileTypes != nil ||
        filters.statuses != nil ||
        filters.hasContent != nil
    }

    private func binding(for docType: DocType) -> Binding<Bool> {
        Binding(
            get: { filters.docTypes?.contains(docType) ?? false },
            set: { isOn in
                var types = filters.docTypes ?? []
                if isOn {
                    types.append(docType)
                } else {
                    types.removeAll { $0 == docType }
                }
                filters.docTypes = types.isEmpty ? nil : types
            }
        )
    }

    private func binding(for fileType: FileType) -> Binding<Bool> {
        Binding(
            get: { filters.fileTypes?.contains(fileType) ?? false },
            set: { isOn in
                var types = filters.fileTypes ?? []
                if isOn {
                    types.append(fileType)
                } else {
                    types.removeAll { $0 == fileType }
                }
                filters.fileTypes = types.isEmpty ? nil : types
            }
        )
    }

    private func binding(for status: Status) -> Binding<Bool> {
        Binding(
            get: { filters.statuses?.contains(status) ?? false },
            set: { isOn in
                var statuses = filters.statuses ?? []
                if isOn {
                    statuses.append(status)
                } else {
                    statuses.removeAll { $0 == status }
                }
                filters.statuses = statuses.isEmpty ? nil : statuses
            }
        )
    }

    private func clearFilters() {
        queryText = ""
        filters = SearchFilters()
        searchResults = []
        searchError = nil
    }

    private func performSearch() {
        guard !queryText.trimmingCharacters(in: .whitespaces).isEmpty else {
            searchResults = []
            searchStats = nil
            searchError = nil
            return
        }

        NSLog("[SearchView] Starting enhanced search for: %@", queryText)
        isSearching = true
        searchError = nil

        Task {
            do {
                NSLog("[SearchView] Calling searchService.search with enhanced parameters...")
                let filterDict = buildFilterDictionary()

                let response = try await searchService.search(
                    query: queryText,
                    limit: 50,
                    minScore: 0.0,
                    searchType: searchType,
                    filters: filterDict.isEmpty ? nil : filterDict,
                    sortBy: sortBy,
                    sortOrder: sortOrder,
                    offset: 0,
                    useFuzzyMatch: false,
                    highlightResults: true
                )

                NSLog("[SearchView] Got %d results (total: %d)", response.count, response.totalResults)
                await MainActor.run {
                    searchResults = response.results
                    searchStats = response
                    isSearching = false
                }
            } catch {
                NSLog("[SearchView] Search error: %@", String(describing: error))
                await MainActor.run {
                    searchError = error.localizedDescription
                    searchResults = []
                    searchStats = nil
                    isSearching = false
                }
            }
        }
    }

    private func buildFilterDictionary() -> [String: String] {
        var filterDict: [String: String] = [:]
        if let docTypes = filters.docTypes, !docTypes.isEmpty {
            filterDict["doc_type"] = docTypes.map { $0.rawValue }.joined(separator: ",")
        }
        if let fileTypes = filters.fileTypes, !fileTypes.isEmpty {
            filterDict["file_type"] = fileTypes.map { $0.rawValue }.joined(separator: ",")
        }
        if let statuses = filters.statuses, !statuses.isEmpty {
            filterDict["status"] = statuses.map { $0.rawValue }.joined(separator: ",")
        }
        if let hasContent = filters.hasContent {
            filterDict["has_content"] = hasContent ? "true" : "false"
        }
        return filterDict
    }

    private func saveSearch() {
        guard !queryText.isEmpty else { return }
        isSaving = true

        Task {
            do {
                _ = try await savedSearchService.saveSearch(
                    query: queryText,
                    isSmartSearch: isSmartSearch,
                    searchType: searchType,
                    sortBy: sortBy,
                    sortOrder: sortOrder
                )
                await MainActor.run {
                    isSaving = false
                    onSearchSaved?()
                }
            } catch {
                NSLog("[SearchView] Failed to save search: %@", error.localizedDescription)
                await MainActor.run {
                    isSaving = false
                }
            }
        }
    }
}

// MARK: - Search Result Row (from API)

struct SearchResultRowFromAPI: View {
    let result: SearchResult

    var body: some View {
        HStack(spacing: 12) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.windowBackgroundColor))
                    .frame(width: 40, height: 40)

                Image(systemName: "doc.text.magnifyingglass")
                    .foregroundColor(.accentColor)
            }

            // Info
            VStack(alignment: .leading, spacing: 4) {
                // Document ID (would ideally show name from metadata)
                if let name = result.metadata["name"]?.value as? String {
                    Text(name)
                        .font(.body)
                        .lineLimit(1)
                } else {
                    Text(result.documentId)
                        .font(.body)
                        .lineLimit(1)
                }

                // Score badge
                HStack(spacing: 8) {
                    Text(String(format: "Score: %.1f%%", result.score * 100))
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .cornerRadius(4)
                }

                // Content preview or highlights
                if let highlights = result.highlights, !highlights.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(highlights.prefix(2), id: \.self) { highlight in
                            Text(highlight)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }
                } else if let contentPreview = result.contentPreview, !contentPreview.isEmpty {
                    Text(contentPreview)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Preview

#Preview {
    SearchView(
        savedSearch: nil,
        selection: .constant([]),
        detailDocument: .constant(nil)
    )
    .frame(width: 800, height: 600)
}
