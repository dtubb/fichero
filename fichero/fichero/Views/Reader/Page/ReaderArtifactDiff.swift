import Foundation

// MARK: - Comparing artifact results in the Reader (Daniel, 2026-09-04)
//
// "A 2–5-way diff of artifact results — three transcription reviews side by
// side with the differences highlighted, HTML-style." The reader is WebKit, so
// an HTML diff is at home in it; what did not exist was the DIFF itself.
//
// Everything here is pure: tokenizing, the longest-common-subsequence, and the
// HTML rendering. That is deliberate — a diff that is only exercised through a
// WKWebView is a diff nobody can test, and "the highlighting is subtly wrong"
// is precisely the failure a manuscript reader cannot afford to discover by
// eye.

/// One run of text in a comparison, and what the comparison says about it.
enum ReaderDiffSegment: Equatable {
    /// Present in both texts.
    case same(String)
    /// Present only in the variant — an addition.
    case inserted(String)
    /// Present only in the baseline — a deletion.
    case removed(String)

    var text: String {
        switch self {
        case .same(let text), .inserted(let text), .removed(let text): return text
        }
    }

    var isChange: Bool { self != .same(text) }
}

/// A word-level diff of two artifact readings, rendered as HTML.
enum ReaderArtifactDiff {

    /// The granularity a comparison was actually computed at.
    ///
    /// Named in the output rather than hidden: a page-long transcription
    /// diffed word by word and a 400-page book compared line by line are not
    /// the same claim, and a reader who is told "words" has a right to expect
    /// word precision.
    enum Granularity: String, Equatable {
        case word
        case line

        var caption: String {
            switch self {
            case .word: return "word-level"
            case .line: return "line-level"
            }
        }
    }

    /// Above this many tokens per side the word-level table stops being worth
    /// its memory (the LCS table is tokens × tokens), and the comparison drops
    /// to lines — which is coarser, and SAYS it is, rather than silently
    /// truncating the text or hanging the reader.
    static let wordDiffTokenLimit = 2000

    /// The result of comparing one variant against the baseline.
    struct Comparison: Equatable {
        let granularity: Granularity
        let segments: [ReaderDiffSegment]

        /// How many tokens differ — what the header prints so a reviewer can
        /// see at a glance which of three reviews is the outlier.
        var changeCount: Int {
            segments.filter(\.isChange).count
        }

        var isIdentical: Bool { changeCount == 0 }
    }

    // MARK: - Diffing

    /// Compare `variant` against `baseline`, word by word where the texts are
    /// small enough and line by line where they are not.
    static func compare(baseline: String, variant: String) -> Comparison {
        let baseWords = tokens(baseline)
        let variantWords = tokens(variant)
        if baseWords.count <= wordDiffTokenLimit, variantWords.count <= wordDiffTokenLimit {
            return Comparison(
                granularity: .word,
                segments: merge(diff(baseWords, variantWords), joinedBy: " ")
            )
        }
        return Comparison(
            granularity: .line,
            segments: merge(
                diff(lines(baseline), lines(variant)),
                joinedBy: "\n"
            )
        )
    }

    /// Whitespace-separated words. Punctuation stays attached to its word: a
    /// transcription review that changes "quales" to "quales," has changed the
    /// word, and splitting the comma off would report two changes for one.
    static func tokens(_ text: String) -> [String] {
        text.split(whereSeparator: \.isWhitespace).map(String.init)
    }

    static func lines(_ text: String) -> [String] {
        text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    }

    /// Classic LCS diff over any equatable tokens, emitting one segment per
    /// token. Deletions are emitted before insertions at the same position, so
    /// a replacement always reads "was X, now Y".
    static func diff<Token: Equatable>(_ base: [Token], _ variant: [Token]) -> [ReaderDiffSegment]
    where Token: CustomStringConvertible {
        let table = lcsTable(base, variant)
        var segments: [ReaderDiffSegment] = []
        var i = 0
        var j = 0
        while i < base.count && j < variant.count {
            if base[i] == variant[j] {
                segments.append(.same(base[i].description))
                i += 1
                j += 1
            } else if table[i + 1][j] >= table[i][j + 1] {
                segments.append(.removed(base[i].description))
                i += 1
            } else {
                segments.append(.inserted(variant[j].description))
                j += 1
            }
        }
        while i < base.count {
            segments.append(.removed(base[i].description))
            i += 1
        }
        while j < variant.count {
            segments.append(.inserted(variant[j].description))
            j += 1
        }
        return segments
    }

    /// `table[i][j]` = length of the longest common subsequence of the
    /// suffixes `base[i...]` and `variant[j...]`.
    private static func lcsTable<Token: Equatable>(
        _ base: [Token], _ variant: [Token]
    ) -> [[Int]] {
        var table = Array(
            repeating: Array(repeating: 0, count: variant.count + 1),
            count: base.count + 1
        )
        guard !base.isEmpty, !variant.isEmpty else { return table }
        for i in stride(from: base.count - 1, through: 0, by: -1) {
            for j in stride(from: variant.count - 1, through: 0, by: -1) {
                table[i][j] = base[i] == variant[j]
                    ? table[i + 1][j + 1] + 1
                    : max(table[i + 1][j], table[i][j + 1])
            }
        }
        return table
    }

    /// Collapse consecutive segments of the same kind into one run, so the
    /// rendered HTML marks a changed PHRASE once instead of wrapping every
    /// word in its own tag.
    static func merge(_ segments: [ReaderDiffSegment], joinedBy separator: String) -> [ReaderDiffSegment] {
        var merged: [ReaderDiffSegment] = []
        for segment in segments {
            guard let last = merged.last else {
                merged.append(segment)
                continue
            }
            switch (last, segment) {
            case (.same(let a), .same(let b)):
                merged[merged.count - 1] = .same(a + separator + b)
            case (.inserted(let a), .inserted(let b)):
                merged[merged.count - 1] = .inserted(a + separator + b)
            case (.removed(let a), .removed(let b)):
                merged[merged.count - 1] = .removed(a + separator + b)
            default:
                merged.append(segment)
            }
        }
        return merged
    }

    // MARK: - Rendering

    /// One artifact in the comparison, named the way the reader's "Showing"
    /// submenu names it.
    struct Column: Equatable {
        let title: String
        let text: String
    }

    /// The comparison page: the FIRST column is the baseline every other
    /// column is measured against, which is why the picker's order matters and
    /// the page says which one it is.
    ///
    /// Two columns render inline (one reading, changes marked in place); three
    /// or more render as columns, each against the same baseline — the shape
    /// that answers "which of my three reviews disagrees with the others".
    static func html(columns: [Column], granularityNote: Bool = true) -> String {
        guard columns.count >= 2 else {
            return page(body: """
            <p class="empty">Pick two or more artifacts to compare.</p>
            """)
        }
        let baseline = columns[0]
        let comparisons = columns.dropFirst().map { column in
            (column: column, comparison: compare(baseline: baseline.text, variant: column.text))
        }
        var body = """
        <p class="baseline">Compared against <strong>\(escape(baseline.title))</strong></p>
        """
        for entry in comparisons {
            let comparison = entry.comparison
            let summary = comparison.isIdentical
                ? "identical"
                : "\(comparison.changeCount) "
                    + (comparison.granularity == .word ? "word" : "line")
                    + (comparison.changeCount == 1 ? " differs" : "s differ")
            let note = granularityNote ? " · \(comparison.granularity.caption)" : ""
            body += """
            <section>
              <h2>\(escape(entry.column.title)) <span class="summary">\(escape(summary))\(escape(note))</span></h2>
              <div class="text">\(marked(comparison.segments))</div>
            </section>
            """
        }
        return page(body: body)
    }

    /// The segments as marked-up HTML: `<ins>` for what the variant added,
    /// `<del>` for what it dropped. Semantic tags, not styled spans — a reader
    /// with a screen reader hears "insertion" without any CSS.
    static func marked(_ segments: [ReaderDiffSegment]) -> String {
        segments.map { segment in
            switch segment {
            case .same(let text): return escape(text)
            case .inserted(let text): return "<ins>\(escape(text))</ins>"
            case .removed(let text): return "<del>\(escape(text))</del>"
            }
        }
        .joined(separator: " ")
    }

    /// HTML-escaped. The texts being compared are transcriptions of
    /// manuscripts — `<`, `>` and `&` occur in real editorial markup, and an
    /// unescaped one would silently eat the rest of the page.
    static func escape(_ text: String) -> String {
        text
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }

    /// The document shell. System fonts and system colors only, and both
    /// appearances declared, so the comparison matches every other reader
    /// surface rather than announcing itself as a web page.
    static func page(body: String) -> String {
        """
        <!DOCTYPE html>
        <html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
        :root { color-scheme: light dark; }
        body {
          font: -apple-system-body;
          font-family: -apple-system, system-ui, serif;
          margin: 0; padding: 16px; line-height: 1.6;
        }
        .baseline, .summary, .empty { color: color-mix(in srgb, currentColor 55%, transparent); }
        .summary { font-size: 0.85em; font-weight: normal; }
        h2 { font-size: 1.05em; margin: 1.4em 0 0.4em; }
        section + section { border-top: 1px solid color-mix(in srgb, currentColor 15%, transparent); }
        ins { background: rgba(52, 199, 89, 0.22); text-decoration: none; }
        del { background: rgba(255, 69, 58, 0.20); }
        .text { white-space: pre-wrap; }
        </style></head>
        <body>\(body)</body></html>
        """
    }
}
