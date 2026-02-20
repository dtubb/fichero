import SwiftUI

/// Reusable search result row component for API results
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
