import Foundation

/// The Inspector's statements (`build-notes-inspector.md` 5.7, second half; `source.statement.on-segment`,
/// `both-ways`): what is SAID about this segment -- the claims whose anchor, or a supporting source's,
/// names it, and the entities it mentions -- each opening its claim or entity in the knowledge views,
/// and each corrected from here (`source.extract.corrected-in-place`, #5602): a name re-pointed or its
/// words fixed, a statement dated or rejected. Pure: the words and the offsets live where a test can
/// reach them.
enum InspectorStatements {
    struct Claim: Equatable, Identifiable {
        let id: String
        let text: String
        let curationState: String
        let confidence: Double
        /// "anchor" (the claim's own anchor names the segment) or "support" (a supporting source does).
        let via: String
        var excerpt: String?
    }

    struct Mention: Equatable, Identifiable {
        /// The entity the mention names.
        let id: String
        let name: String
        let entityType: String
        var excerpt: String?
        /// The mention's span in the page text -- what `mentions/repoint` and `mentions/respan` name it by.
        var sourceCharStart: Int?
        var sourceCharEnd: Int?
        /// The same span on the line's own text.
        var charStart: Int?
        var charEnd: Int?
        /// A person placed this mark (re-pointed it or fixed its words); a re-run keeps it.
        var correctedByPerson = false

        /// The page-text span, when the engine sent one: without it the mark cannot be corrected.
        var pageSpan: (start: Int, end: Int)? {
            guard let start = sourceCharStart, let end = sourceCharEnd, end > start else { return nil }
            return (start, end)
        }
    }

    struct Answer: Equatable {
        var claims: [Claim] = []
        var mentions: [Mention] = []
    }

    struct Row: Equatable, Identifiable {
        /// The claim or entity id the row opens.
        let targetId: String
        let isClaim: Bool
        let title: String
        /// "unreviewed · confidence 50% · from this segment's own anchor · “ܐܒܪܗܡ ܐܘܠܕ”".
        let detail: String
        /// The mention the row shows (nil for a claim): what its corrections are sent about.
        var mention: Mention?
        /// "corrected by you": a person placed this mark.
        var corrected: Bool { mention?.correctedByPerson ?? false }
        /// Two marks of one entity on a line stay two rows.
        var id: String {
            if isClaim { return "claim:" + targetId }
            return "entity:" + targetId + (mention?.sourceCharStart.map { "@\($0)" } ?? "")
        }
    }

    static func rows(_ answer: Answer) -> [Row] {
        let claims = answer.claims.map { claim in
            var parts = [claim.curationState.replacingOccurrences(of: "_", with: " "),
                         "confidence \(Int((claim.confidence * 100).rounded()))%",
                         claim.via == "anchor" ? "anchored here" : "a supporting source is here"]
            if let excerpt = claim.excerpt, !excerpt.isEmpty { parts.append("“\(excerpt)”") }
            return Row(targetId: claim.id, isClaim: true, title: claim.text, detail: parts.joined(separator: " · "))
        }
        let mentions = answer.mentions.map { mention in
            var parts = [mention.entityType.replacingOccurrences(of: "_", with: " ")]
            if let excerpt = mention.excerpt, !excerpt.isEmpty { parts.append("“\(excerpt)”") }
            return Row(targetId: mention.id, isClaim: false, title: mention.name,
                       detail: parts.joined(separator: " · "), mention: mention)
        }
        return claims + mentions
    }

    /// Offsets as the engine counts them: Unicode scalars (a Python `str` index), not UTF-16.
    static func scalarOffset(of index: String.Index, in text: String) -> Int {
        text.unicodeScalars.distance(from: text.unicodeScalars.startIndex, to: index)
    }

    /// Whether `lineText` is the text the mention's line span counts in: the span fits it and, when the
    /// engine sent an excerpt, the words at the span are in that excerpt. When not, a selection on this
    /// text cannot be turned into page offsets, so "Fix the words" is not offered.
    static func lineTextMatches(_ mention: Mention, lineText: String) -> Bool {
        guard let start = mention.charStart, let end = mention.charEnd, end > start, mention.pageSpan != nil else {
            return false
        }
        let scalars = Array(lineText.unicodeScalars)
        guard end <= scalars.count else { return false }
        guard let excerpt = mention.excerpt, !excerpt.isEmpty else { return true }
        var words = String.UnicodeScalarView()
        words.append(contentsOf: scalars[start..<end])
        return excerpt.contains(String(words))
    }

    /// "Fix the words": the words selected on the line, as the page-text span `mentions/respan` takes.
    /// Nil when the line text does not match the mark, the selection is blank, or nothing moved.
    static func respanTarget(
        _ mention: Mention, lineText: String, selection: Range<String.Index>
    ) -> (start: Int, end: Int)? {
        guard lineTextMatches(mention, lineText: lineText),
              let lineStart = mention.charStart, let page = mention.pageSpan else { return nil }
        guard !lineText[selection].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        let lineOffsetInPage = page.start - lineStart
        let start = lineOffsetInPage + scalarOffset(of: selection.lowerBound, in: lineText)
        let end = lineOffsetInPage + scalarOffset(of: selection.upperBound, in: lineText)
        guard end > start, start != page.start || end != page.end else { return nil }
        return (start, end)
    }

    /// "Change date": a year, a year and month, or a full date (`1650`, `1650-03`, `1650-03-01`), sent as
    /// the claim's `time_start`. Nil for anything else, so a typo is never sent as a date.
    static func claimDate(_ typed: String) -> String? {
        let date = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        let pattern = #"^\d{1,4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$"#
        return date.range(of: pattern, options: .regularExpression) != nil ? date : nil
    }
}
