import SwiftUI

/// Search results display supporting four view modes
struct SearchResultsDisplay: View {
    let searchResults: [SearchResult]
    let displayMode: ViewDisplayMode
    @Binding var selection: Set<String>
    let onLoadDocument: (String) -> Void
    var onOpenExcerpt: ((SearchResult) -> Void)?
    /// Current query text — drives the empty-state copy.
    /// Empty (whitespace-only) → "Type to search" placeholder.
    /// Non-empty + no results → "No matches for X" guidance. (#481)
    var currentQuery: String = ""
    var isSearching: Bool = false
    /// Indexed-document count (from /api/search/stats). When 0 + the
    /// user hasn't typed anything yet, the empty state surfaces a
    /// "Re-index this library" CTA rather than the generic placeholder.
    var indexedCount: Int?
    var isReindexing: Bool = false
    var onReindex: (() -> Void)?
    /// Did-you-mean suggestions surfaced by the backend when results=0
    /// and the query looks substantive. Each is clickable — taps run a
    /// fresh search for that suggested term via onSuggestionTap.
    var suggestions: [String] = []
    var onSuggestionTap: ((String) -> Void)?
    /// User's recent successful queries (most recent first). Surfaced
    /// in the empty state when no query is typed so the user can re-run
    /// past searches with one click. Persisted in @SceneStorage by the
    /// caller (SearchView).
    var recentSearches: [String] = []
    var onRecentSearchTap: ((String) -> Void)?

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    /// Top-N keywords for browse-by-tag. Each pill click runs a search
    /// for that keyword. Sized by frequency for visual hierarchy.
    var keywordCloud: [KeywordCloudEntryDTO] = []
    var onKeywordTap: ((String) -> Void)?
    /// Size keyword-cloud pill text by its document-frequency rank. The
    /// most-used tag in the cloud renders biggest; rare tags stay small.
    /// Linear interpolation between 11pt and 17pt over the count range
    /// for any given cloud snapshot.
    static func fontSize(
        for entry: KeywordCloudEntryDTO, cloud: [KeywordCloudEntryDTO]
    ) -> CGFloat {
        let counts = cloud.map(\.count)
        guard let lowerBound = counts.min(),
              let upperBound = counts.max(),
              upperBound > lowerBound else { return 12 }
        let interpolation = CGFloat(entry.count - lowerBound) / CGFloat(upperBound - lowerBound)
        return 11 + interpolation * 6
    }
    var body: some View {
        if searchResults.isEmpty {
            emptyState
        } else {
            VStack(spacing: 0) {
                resultCountHeader
                switch displayMode {
                case .icon:
                    iconView
                case .list:
                    listView
                case .table:
                    tableView
                case .canvas, .space, .workspace:
                    mapView
                }
            }
        }
    }

    /// Lightweight header that shows "N results" + the index-health
    /// hint so the user always knows whether they're seeing everything
    /// the index has. Hidden when there are no results (the empty state
    /// already covers that case).
    @ViewBuilder
    private var resultCountHeader: some View {
        let count = searchResults.count
        let suffix = count == 1 ? "result" : "results"
        HStack(spacing: 8) {
            Text("\(count) \(suffix)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if let indexedCount, indexedCount > 0 {
                Text("·")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                Text("\(indexedCount) indexed")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Empty State (#481)

    private var trimmedQuery: String {
        currentQuery.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var emptyState: some View {
        SearchResultsEmptyState(
            currentQuery: currentQuery,
            isSearching: isSearching,
            isReindexing: isReindexing,
            indexedCount: indexedCount,
            onReindex: onReindex,
            suggestions: suggestions,
            onSuggestionTap: onSuggestionTap,
            recentSearches: recentSearches,
            onRecentSearchTap: onRecentSearchTap,
            keywordCloud: keywordCloud,
            onKeywordTap: onKeywordTap
        )
    }

    // MARK: - List View

    private var listView: some View {
        List(selection: $selection) {
            ForEach(searchResults) { result in
                SearchResultRowFromAPI(
                    result: result,
                    onOpenExcerpt: {
                        onOpenExcerpt?(result)
                    }
                )
                    .tag(result.documentId)
                    .draggable(result.documentId)
            }
        }
        .listStyle(.inset)
    }

    // MARK: - Icon View

    private var iconView: some View {
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
                        activate(result)
                    }
                }
            }
            .padding()
        }
    }

    /// Open a result at its matched page/passage when possible (#1476), falling
    /// back to loading the whole document. The list rows already route through
    /// `onOpenExcerpt`; this makes the grid + map cards consistent instead of
    /// always loading the whole PDF and losing the matched page.
    private func activate(_ result: SearchResult) {
        if let onOpenExcerpt {
            onOpenExcerpt(result)
        } else {
            onLoadDocument(result.documentId)
        }
    }

    // MARK: - Table View

    @ViewBuilder
    private var tableView: some View {
        // A multi-column Table has no room to breathe on a compact iPhone; fall
        // back to the existing list rows there, mirroring the library table
        // (#2806). Mac/iPad-regular keep the columns.
        if horizontalSizeClass == .compact {
            listView
        } else {
            resultsTable
        }
    }

    private var resultsTable: some View {
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
                if let preview = SearchResultRowFromAPI(result: result).preferredExcerptText {
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

    // MARK: - Map View

    private var mapView: some View {
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
                            activate(result)
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
