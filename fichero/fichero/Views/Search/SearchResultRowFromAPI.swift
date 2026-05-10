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
                // markers (added by the backend) as bold so the matched
                // span actually visually stands out (#481).
                if let highlights = result.highlights, !highlights.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(highlights.prefix(2), id: \.self) { highlight in
                            Text(SearchResultRowFromAPI.attributedHighlight(highlight))
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

    /// Build an AttributedString with `**...**` spans bolded. The
    /// backend wraps the matched query in `**` markers via simple
    /// regex replace; we render those as bold visual highlights instead
    /// of showing literal asterisks (#481).
    static func attributedHighlight(_ raw: String) -> AttributedString {
        var attributed = AttributedString()
        var remaining = raw[...]
        while let openRange = remaining.range(of: "**") {
            let prefix = remaining[..<openRange.lowerBound]
            attributed += AttributedString(prefix)
            let afterOpen = remaining[openRange.upperBound...]
            if let closeRange = afterOpen.range(of: "**") {
                let bolded = afterOpen[..<closeRange.lowerBound]
                var bold = AttributedString(bolded)
                bold.font = .caption.bold()
                bold.foregroundColor = .primary
                attributed += bold
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
