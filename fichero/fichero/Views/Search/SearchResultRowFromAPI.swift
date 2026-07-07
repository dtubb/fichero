import SwiftUI

/// Reusable search result row component for API results
struct SearchResultRowFromAPI: View {
    let result: SearchResult
    var onOpenExcerpt: (() -> Void)?

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
                // For page results: show parent document name with page badge.
                // For other results: show the document's own name.
                let parentName = result.metadata["parent_name"]?.value as? String
                let pageLabel = pageLabelText
                if let parentName {
                    HStack(spacing: 6) {
                        Text(parentName)
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        if let pageLabel {
                            Text(pageLabel)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.accentColor)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(Color.accentColor.opacity(0.12))
                                .clipShape(Capsule())
                        }
                    }
                } else if let name = result.metadata["name"]?.value as? String {
                    Text(name)
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                } else {
                    Text(result.documentId)
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                // Relevance + match-source badges moved to the row's trailing
                // edge so the matched snippet leads and the filename recedes
                // (#1784) — see the trailing VStack below.

                // Content preview or highlights — render `**term**`
                // markers (added by the backend) as colored highlights.
                // Entity matches (#1052) get accent color + background;
                // search-term matches get bold + primary foreground (#481).
                if let excerpt = preferredExcerptText, let onOpenExcerpt {
                    Button(action: onOpenExcerpt) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            if let pageLabel = pageLabelText {
                                Text(pageLabel)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundColor(.accentColor)
                            }

                            Text(attributedExcerpt(excerpt))
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(3)
                                .multilineTextAlignment(.leading)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                    .help("Open this matched passage")
                } else if let highlights = result.highlights, !highlights.isEmpty {
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

            // Relevance to the right (#1784): a trailing, de-emphasized column
            // so the row reads snippet-first, filename-second, relevance-aside.
            VStack(alignment: .trailing, spacing: 4) {
                relevanceBadge
                matchSourcePill
            }
        }
        .padding(.vertical, 4)
    }

    private var relevanceBadge: some View {
        Text(String(format: "relevance %.0f%%", result.score * 100))
            .font(.caption)
            .foregroundColor(.secondary)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.accentColor.opacity(0.15))
            .cornerRadius(4)
            .help("Semantic similarity — how closely this result's meaning matches your search (higher is closer).")
    }

    @ViewBuilder
    private var matchSourcePill: some View {
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

    var preferredExcerptText: String? {
        if let transcript = result.transcriptExcerpts.first {
            return Self.cleanedExcerptText(transcript.text)
        }
        if let sourceExcerpt = metadataString(keys: ["source_excerpt", "sourceExcerpt"]) {
            return Self.cleanedExcerptText(sourceExcerpt)
        }
        if let highlight = result.highlights?.first {
            return Self.cleanedExcerptText(highlight)
        }
        if let contentPreview = result.contentPreview {
            return Self.cleanedExcerptText(contentPreview)
        }
        return nil
    }

    var pageLabelText: String? {
        if let pageLabel = metadataString(keys: ["source_page_label", "page_label"]) {
            return "p. \(pageLabel)"
        }
        if let pageNum = Self.metadataInt(from: result, keys: ["page_number"]) {
            return "p. \(pageNum)"
        }
        return nil
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

    static func navigationUserInfo(for result: SearchResult) -> [String: Any]? {
        if let excerpt = result.transcriptExcerpts.first {
            return [
                "documentId": excerpt.anchor.documentId,
                "excerpt": excerpt.text,
                "charStart": excerpt.anchor.charStart,
                "charEnd": excerpt.anchor.charEnd
            ]
        }

        let excerpt = metadataString(
            from: result,
            keys: ["source_excerpt", "sourceExcerpt"]
        ) ?? result.contentPreview
        guard let cleaned = cleanedExcerptText(excerpt) else {
            return nil
        }

        var info: [String: Any] = [
            "documentId": result.documentId,
            "excerpt": cleaned
        ]

        if let pageLabel = metadataString(from: result, keys: ["source_page_label", "page_label"]) {
            info["pageLabel"] = pageLabel
        }
        if let charStart = metadataInt(from: result, keys: ["source_char_start", "char_start"]) {
            info["charStart"] = charStart
        }
        if let charEnd = metadataInt(from: result, keys: ["source_char_end", "char_end"]) {
            info["charEnd"] = charEnd
        }
        return info
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

    private func attributedExcerpt(_ text: String) -> AttributedString {
        SearchResultRowFromAPI.attributedHighlight(
            text,
            matchSource: matchSourceLabel
        )
    }

    private func metadataString(keys: [String]) -> String? {
        SearchResultRowFromAPI.metadataString(from: result, keys: keys)
    }

    private static func metadataString(from result: SearchResult, keys: [String]) -> String? {
        for key in keys {
            if let value = result.metadata[key]?.value as? String,
               let cleaned = cleanedExcerptText(value) {
                return cleaned
            }
        }
        return nil
    }

    private static func metadataInt(from result: SearchResult, keys: [String]) -> Int? {
        for key in keys {
            guard let raw = result.metadata[key]?.value else { continue }
            switch raw {
            case let value as Int:
                return value
            case let value as Double:
                return Int(value)
            case let value as NSNumber:
                return value.intValue
            case let value as String:
                return Int(value)
            default:
                continue
            }
        }
        return nil
    }

    private static func cleanedExcerptText(_ text: String?) -> String? {
        guard let text else { return nil }
        // Stored transcript/excerpt text can be RTF ({\rtf…}); a raw List row
        // would show the escape sequences (#2502). Decode to plain text first —
        // the codec passes non-RTF through unchanged, so this is a no-op for the
        // common plain-text case.
        let decoded = ArtifactRichTextCodec.decode(text).string
        let cleaned = decoded.trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? nil : cleaned
    }
}
