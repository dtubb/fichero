import SwiftUI

/// Reusable search result row component for API results
struct SearchResultRowFromAPI: View {
    let result: SearchResult

    var body: some View {
        HStack(spacing: 12) {
            // Thumbnail — shows page thumbnail when available,
            // falls back to generic icon (LibraryImageView returns
            // Color.clear when no image is loaded).
            ZStack {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.windowBackgroundColor))

                Image(systemName: "doc.text.magnifyingglass")
                    .foregroundColor(.accentColor)

                LibraryImageView(documentId: result.documentId, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .clipped()
            }
            .frame(width: 40, height: 40)
            .clipShape(RoundedRectangle(cornerRadius: 4))

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

                // Score badge + match-source pill
                HStack(spacing: 6) {
                    Text(String(format: "%.0f%%", result.score * 100))
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .cornerRadius(4)

                    if let label = matchSourceLabel {
                        Text(label)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.12))
                            .cornerRadius(4)
                    }
                }

                // Content preview or highlights — render `**term**`
                // markers (added by the backend) as colored highlights.
                // Entity matches (#1052) get accent color + background;
                // search-term matches get bold + primary foreground (#481).
                if let highlights = result.highlights, !highlights.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(highlights.prefix(2), id: \.self) { highlight in
                            Text(SearchResultRowFromAPI.attributedHighlight(
                                highlight,
                                matchSource: matchSourceLabel
                            ))
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(2)
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

    /// "fulltext", "semantic", "entity", "fulltext + semantic", etc.
    /// Returns nil when the backend didn't provide match_sources (older
    /// engines or pure-mode searches). Read from result.metadata so the
    /// generated SearchResult model doesn't need a schema bump.
    private var matchSourceLabel: String? {
        let raw = (result.metadata["match_sources"]?.value as? [Any])?
            .compactMap { $0 as? String } ?? []
        if !raw.isEmpty {
            return raw.sorted().joined(separator: " + ")
        }
        if let single = result.metadata["match_source"]?.value as? String {
            return single
        }
        return nil
    }

    /// Build an AttributedString with `**...**` spans highlighted.
    /// Styling depends on matchSource: entity matches get accent color with
    /// background (#1052); search-term matches (fulltext, semantic) get
    /// bold with primary foreground (#481).
    static func attributedHighlight(
        _ raw: String,
        matchSource: String? = nil
    ) -> AttributedString {
        let isEntityMatch = matchSource?.localizedCaseInsensitiveContains("entity") ?? false

        var attributed = AttributedString()
        var remaining = raw[...]
        while let openRange = remaining.range(of: "**") {
            let prefix = remaining[..<openRange.lowerBound]
            attributed += AttributedString(prefix)
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "**") {
                let highlighted = afterOpen[..<closeRange.lowerBound]
                var span = AttributedString(highlighted)

                if isEntityMatch {
                    // KG entity match: accent color text with background
                    span.foregroundColor = .accentColor
                    span.backgroundColor = .accentColor.opacity(0.15)
                } else {
                    // Search-term match: bold with primary foreground
                    span.font = .caption.bold()
                    span.foregroundColor = .primary
                }

                attributed += span
                remaining = afterOpen[closeRange.upperBound...]
            } else {
                attributed += AttributedString(afterOpen)
                return attributed
            }
        }
        attributed += AttributedString(remaining)
        return attributed
    }
}
