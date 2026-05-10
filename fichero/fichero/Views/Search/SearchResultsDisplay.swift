import SwiftUI

/// Search results display supporting four view modes
struct SearchResultsDisplay: View {
    let searchResults: [SearchResult]
    let displayMode: ViewDisplayMode
    @Binding var selection: Set<String>
    let onLoadDocument: (String) -> Void
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
                case .map:
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
        VStack(spacing: 12) {
            if isSearching {
                ProgressView()
                Text("Searching…")
                    .font(.headline)
                    .foregroundStyle(.secondary)
            } else if isReindexing {
                ProgressView()
                Text("Indexing library…")
                    .font(.headline)
                    .foregroundStyle(.secondary)
                Text("This runs in the background; you can keep using\nthe rest of the app. Search will return results\nonce indexing completes.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            } else if trimmedQuery.isEmpty {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                Text("Search Documents")
                    .font(.headline)
                if let indexedCount, indexedCount == 0, let onReindex {
                    // Library has docs but no embeddings — most likely
                    // failure mode for first-time use of search. (#481)
                    Text("This library has no search index yet.\nIndex it once to enable search.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button(action: onReindex) {
                        Label("Index Library", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Text("Type a query in the toolbar (⌘F) to search across\nall transcribed documents in this library.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    if let indexedCount, indexedCount > 0 {
                        Text("\(indexedCount) document\(indexedCount == 1 ? "" : "s") indexed")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
            } else {
                Image(systemName: "doc.text.magnifyingglass")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                Text("No Matches")
                    .font(.headline)
                Text("Nothing matched “\(trimmedQuery)”.\nTry a shorter query or different terms.")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                // Did-you-mean: clickable backend-supplied suggestions
                // when the query is substantive but found nothing.
                if !suggestions.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Did you mean…")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                        FlowLayout(spacing: 6) {
                            ForEach(suggestions, id: \.self) { suggestion in
                                Button {
                                    onSuggestionTap?(suggestion)
                                } label: {
                                    Text(suggestion)
                                        .font(.caption)
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 4)
                                        .background(
                                            Capsule().fill(Color.accentColor.opacity(0.12))
                                        )
                                        .overlay(
                                            Capsule().stroke(Color.accentColor.opacity(0.25), lineWidth: 0.5)
                                        )
                                        .foregroundStyle(Color.accentColor)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .frame(maxWidth: 360)
                    .padding(.top, 8)
                }
                if let onReindex {
                    Button(action: onReindex) {
                        Label("Re-index Library", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .padding(.top, 4)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - List View

    private var listView: some View {
        List(selection: $selection) {
            ForEach(searchResults) { result in
                SearchResultRowFromAPI(result: result)
                    .tag(result.documentId)
                    .draggable(result.documentId)
                    .onTapGesture(count: 2) {
                        onLoadDocument(result.documentId)
                    }
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
                        onLoadDocument(result.documentId)
                    }
                }
            }
            .padding()
        }
    }

    // MARK: - Table View

    private var tableView: some View {
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
                            onLoadDocument(result.documentId)
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
