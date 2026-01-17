import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "SearchView")

/// Search view with query input, filters, and results
struct SearchView: View {
    let savedSearch: SavedSearch?
    @Binding var selection: Set<String>
    @Binding var detailDocument: Document?
    var onSearchSaved: (() -> Void)?
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

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

    @EnvironmentObject var searchService: SearchService
    @EnvironmentObject var savedSearchService: SavedSearchServiceGenerated
    @EnvironmentObject var apiClient: APIClient

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

            // Results display (adapts to displayMode)
            if searchResults.isEmpty && !isSearching {
                emptyState
            } else {
                switch displayMode {
                case .icon:
                    searchResultsIconView
                case .list:
                    searchResultsListView
                case .table:
                    searchResultsTableView
                case .map:
                    searchResultsMapView
                }
            }
        }
    }

    private func loadDocument(_ id: String) {
        Task {
            do {
                let doc: Document = try await apiClient.get("/documents/\(id)")
                await MainActor.run {
                    detailDocument = doc
                }
            } catch {
                logger.error("Failed to load document: \(error.localizedDescription)")
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

    // MARK: - Search Results Views

    private var searchResultsListView: some View {
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

    private var searchResultsIconView: some View {
        ScrollView {
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 100, maximum: 140))],
                spacing: 16
            ) {
                ForEach(searchResults) { result in
                    VStack(spacing: 8) {
                        Image(systemName: "doc.text.magnifyingglass")
                            .font(.system(size: 48))
                            .foregroundColor(.accentColor)

                        if let name = result.metadata["name"]?.value as? String {
                            Text(name)
                                .font(.caption)
                                .lineLimit(2)
                                .multilineTextAlignment(.center)
                        } else {
                            Text(result.documentId)
                                .font(.caption)
                                .lineLimit(1)
                        }

                        Text(String(format: "%.1f%%", result.score * 100))
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    .frame(width: 120, height: 120)
                    .background(selection.contains(result.documentId) ? Color.accentColor.opacity(0.1) : Color.clear)
                    .cornerRadius(8)
                    .onTapGesture {
                        selection = [result.documentId]
                    }
                    .onTapGesture(count: 2) {
                        loadDocument(result.documentId)
                    }
                }
            }
            .padding()
        }
    }

    private var searchResultsTableView: some View {
        Table(searchResults, selection: $selection) {
            TableColumn("Name") { result in
                if let name = result.metadata["name"]?.value as? String {
                    Text(name)
                } else {
                    Text(result.documentId)
                        .foregroundColor(.secondary)
                }
            }

            TableColumn("Score") { result in
                Text(String(format: "%.1f%%", result.score * 100))
            }
            .width(min: 60, ideal: 80)

            TableColumn("Preview") { result in
                if let preview = result.contentPreview {
                    Text(preview)
                        .lineLimit(2)
                        .foregroundColor(.secondary)
                } else {
                    Text("—")
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    private var searchResultsMapView: some View {
        GeometryReader { geometry in
            ScrollView([.horizontal, .vertical]) {
                ZStack {
                    // Grid background
                    SearchMapGrid()
                        .stroke(Color.gray.opacity(0.2), lineWidth: 0.5)
                        .allowsHitTesting(false)

                    // Search result cards positioned by relevance
                    ForEach(Array(searchResults.enumerated()), id: \.element.id) { index, result in
                        SearchResultCard(
                            result: result,
                            isSelected: selection.contains(result.documentId)
                        )
                        .position(cardPosition(for: index, score: result.score, in: geometry.size))
                        .onTapGesture {
                            selection = [result.documentId]
                        }
                        .onTapGesture(count: 2) {
                            loadDocument(result.documentId)
                        }
                    }
                }
                .frame(width: max(geometry.size.width, 1200), height: max(geometry.size.height, 800))
            }
        }
        .background(Color(.textBackgroundColor))
    }

    /// Calculate card position based on relevance score and index
    private func cardPosition(for index: Int, score: Double, in size: CGSize) -> CGPoint {
        let columns = max(4, Int(size.width / 180))
        let row = index / columns
        let col = index % columns
        let xPos = CGFloat(col) * 170 + 100
        let yPos = CGFloat(row) * 140 + 80
        return CGPoint(x: xPos, y: yPos)
    }
}

// MARK: - Search Map Grid

private struct SearchMapGrid: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let spacing: CGFloat = 40

        // Vertical lines
        var xPos = spacing
        while xPos < rect.width {
            path.move(to: CGPoint(x: xPos, y: 0))
            path.addLine(to: CGPoint(x: xPos, y: rect.height))
            xPos += spacing
        }

        // Horizontal lines
        var yPos = spacing
        while yPos < rect.height {
            path.move(to: CGPoint(x: 0, y: yPos))
            path.addLine(to: CGPoint(x: rect.width, y: yPos))
            yPos += spacing
        }

        return path
    }
}

// MARK: - Search Result Card (for Map View)

private struct SearchResultCard: View {
    let result: SearchResult
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 8) {
            // Icon
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 28))
                .foregroundColor(.accentColor)
                .frame(width: 44, height: 44)
                .background(Color.accentColor.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 8))

            // Name
            if let name = result.metadata["name"]?.value as? String {
                Text(name)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
            } else {
                Text(result.documentId.prefix(12) + "...")
                    .font(.caption)
                    .lineLimit(1)
            }

            // Score badge
            Text(String(format: "%.0f%%", result.score * 100))
                .font(.caption2)
                .foregroundColor(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(scoreColor(for: result.score))
                .clipShape(Capsule())
        }
        .frame(width: 140, height: 110)
        .padding(8)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? Color.accentColor : Color(.separatorColor), lineWidth: isSelected ? 2 : 1)
        )
        .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
    }

    private func scoreColor(for score: Double) -> Color {
        if score >= 0.8 { return .green }
        if score >= 0.5 { return .orange }
        return .gray
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

        logger.info("Starting enhanced search for: \(queryText)")
        isSearching = true
        searchError = nil

        Task {
            do {
                logger.info("Calling searchService.search with enhanced parameters...")
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

                logger.info("Got \(response.count) results (total: \(response.totalResults))")
                await MainActor.run {
                    searchResults = response.results
                    searchStats = response
                    isSearching = false
                }
            } catch {
                logger.error("Search error: \(String(describing: error))")
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
                    sortDirection: sortOrder
                )
                await MainActor.run {
                    isSaving = false
                    onSearchSaved?()
                }
            } catch {
                logger.error("Failed to save search: \(error.localizedDescription)")
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
        detailDocument: .constant(nil),
        displayMode: .icon
    )
    .frame(width: 800, height: 600)
}
