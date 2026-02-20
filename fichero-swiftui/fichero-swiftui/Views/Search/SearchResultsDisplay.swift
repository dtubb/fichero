import SwiftUI

/// Search results display supporting four view modes
struct SearchResultsDisplay: View {
    let searchResults: [SearchResult]
    let displayMode: ViewDisplayMode
    @Binding var selection: Set<String>
    let onLoadDocument: (String) -> Void
    
    var body: some View {
        if searchResults.isEmpty {
            emptyState
        } else {
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
