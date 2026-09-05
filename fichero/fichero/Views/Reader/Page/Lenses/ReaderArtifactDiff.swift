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
        var basePos = 0
        var variantPos = 0
        while basePos < base.count && variantPos < variant.count {
            if base[basePos] == variant[variantPos] {
                segments.append(.same(base[basePos].description))
                basePos += 1
                variantPos += 1
            } else if table[basePos + 1][variantPos] >= table[basePos][variantPos + 1] {
                segments.append(.removed(base[basePos].description))
                basePos += 1
            } else {
                segments.append(.inserted(variant[variantPos].description))
                variantPos += 1
            }
        }
        while basePos < base.count {
            segments.append(.removed(base[basePos].description))
            basePos += 1
        }
        while variantPos < variant.count {
            segments.append(.inserted(variant[variantPos].description))
            variantPos += 1
        }
        return segments
    }

    /// `table[basePos][variantPos]` = length of the longest common subsequence
    /// of the suffixes `base[basePos...]` and `variant[variantPos...]`.
    private static func lcsTable<Token: Equatable>(
        _ base: [Token], _ variant: [Token]
    ) -> [[Int]] {
        var table = Array(
            repeating: Array(repeating: 0, count: variant.count + 1),
            count: base.count + 1
        )
        guard !base.isEmpty, !variant.isEmpty else { return table }
        for basePos in stride(from: base.count - 1, through: 0, by: -1) {
            for variantPos in stride(from: variant.count - 1, through: 0, by: -1) {
                table[basePos][variantPos] = base[basePos] == variant[variantPos]
                    ? table[basePos + 1][variantPos + 1] + 1
                    : max(table[basePos + 1][variantPos], table[basePos][variantPos + 1])
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
            case (.same(let lhs), .same(let rhs)):
                merged[merged.count - 1] = .same(lhs + separator + rhs)
            case (.inserted(let lhs), .inserted(let rhs)):
                merged[merged.count - 1] = .inserted(lhs + separator + rhs)
            case (.removed(let lhs), .removed(let rhs)):
                merged[merged.count - 1] = .removed(lhs + separator + rhs)
            default:
                merged.append(segment)
            }
        }
        return merged
    }

    // MARK: - N-way alignment (Daniel, 2026-09-05: "an html way to see
    // differences in results" — three reviews SIDE BY SIDE, not three
    // sections each measured separately against the first)

    /// One aligned band of the comparison: what the baseline says here, and
    /// what each other artifact says in the same place.
    struct AlignedRow: Equatable {
        /// The baseline's text for this band; empty where a variant inserted
        /// something the baseline has nothing for.
        let baseline: String
        /// One entry per variant, in column order. Empty means the variant
        /// DROPPED this text — which is a difference, and is why an empty cell
        /// is rendered as an absence rather than left blank.
        let cells: [String]
        /// True when any variant disagrees with the baseline here.
        let isChange: Bool
    }

    /// Align every artifact against the baseline so the columns line up.
    ///
    /// The baseline is the SPINE, which is what makes this n-way rather than n
    /// separate 2-way diffs: each variant is diffed against the same token
    /// stream, every segment is attributed to the baseline position it covers,
    /// and bands are cut wherever the agreement changes. Three reviews then
    /// read across a row — the question "which of these three disagrees" is
    /// answered by looking along one line instead of scrolling between three
    /// sections and remembering.
    ///
    /// Aligning all N against each other simultaneously is the other option
    /// and it is not worth it: multiple-sequence alignment is exponential,
    /// and for artifacts that are versions OF something there is a natural
    /// reference — the one the reader was already looking at.
    static func aligned(columns: [Column]) -> [AlignedRow] {
        guard columns.count >= 2 else { return [] }
        let baselineTokens = tokens(columns[0].text)
        let variants = columns.dropFirst().map { variantCells(baseline: baselineTokens, variant: $0.text) }

        var rows: [AlignedRow] = []
        // One band per baseline token, then merged below. `count + 1` because
        // a variant can append text past the baseline's last token, and text
        // nobody has a place for is still text somebody wrote.
        for index in 0...baselineTokens.count {
            let baselineToken = index < baselineTokens.count ? baselineTokens[index] : ""
            let cells = variants.map { $0[index] ?? "" }
            let changed = cells.contains { $0 != baselineToken }
            if baselineToken.isEmpty && cells.allSatisfy(\.isEmpty) { continue }
            rows.append(AlignedRow(baseline: baselineToken, cells: cells, isChange: changed))
        }
        return mergeRuns(rows)
    }

    /// What one variant says at each baseline position.
    ///
    /// `.same` and `.removed` each consume one baseline token; `.inserted`
    /// consumes none and is attached to the position it arrives at, so an
    /// addition lands beside the baseline text it was added before. Nothing
    /// here needs the LCS table again — the segment order already carries the
    /// alignment, and re-deriving it would be a second implementation free to
    /// disagree with the first.
    static func variantCells(baseline: [String], variant text: String) -> [Int: String] {
        var cells: [Int: String] = [:]
        var index = 0
        var previousWasRemoval = false
        for segment in diff(baseline, tokens(text)) {
            switch segment {
            case .same(let word):
                cells[index] = cells[index].map { $0 + " " + word } ?? word
                index += 1
                previousWasRemoval = false
            case .removed:
                // The variant does not have this baseline token. An absent
                // entry is the signal; the renderer draws it as a deletion.
                index += 1
                previousWasRemoval = true
            case .inserted(let word):
                // A REPLACEMENT — an insertion right after a removal — belongs
                // in the band it replaced, not the one after it. Without this,
                // "dos" → "DOS" put DOS beside the FOLLOWING word, which then
                // read as changed too: the band grew to "dos tres" vs "DOS
                // tres" and accused a word nobody had touched. An insertion
                // that follows no removal is a genuine addition and stays
                // where it arrives.
                let position = previousWasRemoval ? max(0, index - 1) : index
                cells[position] = cells[position].map { $0 + " " + word } ?? word
                previousWasRemoval = false
            }
        }
        return cells
    }

    /// Collapse consecutive rows that agree, and consecutive rows that differ,
    /// so a page of identical prose is one band rather than four hundred.
    static func mergeRuns(_ rows: [AlignedRow]) -> [AlignedRow] {
        var merged: [AlignedRow] = []
        for row in rows {
            guard let last = merged.last, last.isChange == row.isChange,
                  last.cells.count == row.cells.count else {
                merged.append(row)
                continue
            }
            merged[merged.count - 1] = AlignedRow(
                baseline: join(last.baseline, row.baseline),
                cells: zip(last.cells, row.cells).map(join),
                isChange: row.isChange
            )
        }
        return merged
    }

    private static func join(_ lhs: String, _ rhs: String) -> String {
        if lhs.isEmpty { return rhs }
        if rhs.isEmpty { return lhs }
        return lhs + " " + rhs
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
    /// EVERY comparison is columnar (Daniel, 2026-09-05: "an html way to see
    /// differences in results"). It used to render one section per variant,
    /// each measured separately against the first — which answers "how far is
    /// this one from the baseline" but not "which of these three disagrees
    /// HERE", the question three transcription reviews are opened to settle.
    /// Two columns get the same treatment as five: a two-column table IS the
    /// inline reading, with the second column beside the first instead of
    /// marked into it.
    static func html(columns: [Column], granularityNote: Bool = true) -> String {
        guard columns.count >= 2 else {
            return page(body: """
            <p class="empty">Pick two or more artifacts to compare.</p>
            """)
        }
        let baseline = columns[0]
        var body = """
        <p class="baseline">Compared against <strong>\(escape(baseline.title))</strong></p>
        """
        body += summaryLine(columns: columns, granularityNote: granularityNote)
        body += columnsTable(columns: columns)
        return page(body: body)
    }

    /// The per-artifact headline: how far each one is from the baseline, so
    /// the outlier is nameable before any reading happens.
    static func summaryLine(columns: [Column], granularityNote: Bool) -> String {
        let baseline = columns[0]
        let entries = columns.dropFirst().map { column -> String in
            let comparison = compare(baseline: baseline.text, variant: column.text)
            let summary = comparison.isIdentical
                ? "identical"
                : "\(comparison.changeCount) "
                    + (comparison.granularity == .word ? "word" : "line")
                    + (comparison.changeCount == 1 ? " differs" : "s differ")
            let note = granularityNote ? " · \(comparison.granularity.caption)" : ""
            return """
            <li><strong>\(escape(column.title))</strong> <span class="summary">\(escape(summary))\(escape(note))</span></li>
            """
        }
        return "<ul class=\"legend\">" + entries.joined() + "</ul>"
    }

    /// The comparison itself: ONE column per artifact, aligned on the
    /// baseline, differing bands marked.
    ///
    /// A `<table>` rather than flex columns, deliberately — a row IS the
    /// claim being made ("here is what each of them says in this place"), and
    /// table semantics are what a screen reader needs to read across it.
    /// Nothing is hidden: agreeing bands are shown too, greyed, because a
    /// comparison that elides agreement cannot be checked against the page.
    static func columnsTable(columns: [Column]) -> String {
        let rows = aligned(columns: columns)
        guard !rows.isEmpty else {
            return "<p class=\"empty\">These artifacts have no text to compare.</p>"
        }
        var markup = "<table class=\"cols\"><thead><tr>"
        markup += columns.map { "<th>\(escape($0.title))</th>" }.joined()
        markup += "</tr></thead><tbody>"
        for row in rows {
            markup += row.isChange ? "<tr class=\"changed\">" : "<tr>"
            markup += cell(row.baseline, isChange: false)
            for text in row.cells {
                markup += cell(text, isChange: row.isChange)
            }
            markup += "</tr>"
        }
        return markup + "</tbody></table>"
    }

    /// One cell. An EMPTY cell in a changed row is an absence the reader must
    /// see — the variant dropped what the baseline has — so it is drawn as a
    /// mark rather than left blank, which would read as "nothing to report".
    static func cell(_ text: String, isChange: Bool) -> String {
        guard !text.isEmpty else {
            return isChange ? "<td class=\"gone\">—</td>" : "<td></td>"
        }
        let body = isChange ? "<ins>\(escape(text))</ins>" : escape(text)
        return "<td>\(body)</td>"
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
        .legend { list-style: none; margin: 0 0 12px; padding: 0; }
        .legend li { display: inline-block; margin-right: 14px; }
        .cols { border-collapse: collapse; width: 100%; table-layout: fixed; }
        .cols th, .cols td {
          text-align: left; vertical-align: top; padding: 4px 10px;
          border-bottom: 1px solid color-mix(in srgb, currentColor 10%, transparent);
          overflow-wrap: anywhere;
        }
        .cols th { position: sticky; top: 0; background: Canvas; border-bottom-width: 2px; }
        .cols tr:not(.changed) td { color: color-mix(in srgb, currentColor 55%, transparent); }
        .cols tr.changed { background: color-mix(in srgb, currentColor 5%, transparent); }
        .gone { color: color-mix(in srgb, currentColor 45%, transparent); }
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
