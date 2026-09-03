import SwiftUI

// MARK: - What a result row shows, and why it matched (Daniel, 2026-09-02)
//
// "Result list rows should show the matched/relevant text with the query
// terms highlighted, not just the leading snippet."
//
// Two defects in one sentence, and they are separable:
//
//   1. The row showed the LEADING text of whatever the engine returned. For a
//      transcript excerpt that is usually the match; for a content preview it
//      is the top of the page, which answers "what is this document" when the
//      question was "why is this document here".
//   2. Nothing marked the terms. A two-line snippet with the answer in the
//      middle of the second line is a paragraph, not an explanation.
//
// Everything here is pure and string-in/string-out so it can be tested
// without a window, and so the SAME decision serves any view mode that later
// wants to show why a row matched.
enum SearchSnippetHighlighter {

    /// Roughly how many characters a two-line row can show. Not a hard cut:
    /// `snippet` trims on a word boundary near it.
    static let rowSnippetLength = 220

    /// Words too common to be evidence of anything.
    ///
    /// Ask mode (#4117) sends whole sentences, so without this a query like
    /// "what did he say about the road to Bagadó" would embolden half of
    /// every snippet and the highlight would stop meaning "this is why".
    /// Bilingual because the corpus is (Spanish-language archival material
    /// searched in English and Spanish alike); deliberately short — a
    /// stopword list that grows becomes a list of words the user is not
    /// allowed to search for.
    static let stopwords: Set<String> = [
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "did",
        "do", "does", "for", "from", "had", "has", "have", "he", "her", "his",
        "how", "i", "if", "in", "is", "it", "its", "of", "on", "or", "she",
        "that", "the", "their", "them", "then", "there", "they", "this", "to",
        "was", "were", "what", "when", "where", "which", "who", "why", "with",
        "you", "your",
        "al", "como", "con", "de", "del", "el", "en", "es", "la", "las", "lo",
        "los", "para", "por", "que", "se", "su", "sus", "un", "una", "y"
    ]

    /// The words worth lighting up in a snippet.
    ///
    /// Order is preserved and duplicates are dropped, so a repeated word does
    /// not cost a second scan of the text.
    static func terms(in query: String) -> [String] {
        var seen = Set<String>()
        var out: [String] = []
        for raw in query.split(whereSeparator: { !$0.isLetter && !$0.isNumber }) {
            let term = String(raw)
            let folded = term.lowercased()
            // One-character terms match everywhere and explain nothing; a
            // digit pair ("85") is still a real archival query.
            guard term.count > 1, !Self.stopwords.contains(folded) else { continue }
            guard seen.insert(folded).inserted else { continue }
            out.append(term)
        }
        return out
    }

    /// Where each term occurs, merged and in reading order.
    ///
    /// Case- AND diacritic-insensitive: "Bagado" must find "Bagadó", which is
    /// the exact query Daniel ran. Overlapping matches (one term inside
    /// another) merge rather than producing nested spans.
    static func matchRanges(in text: String, terms: [String]) -> [Range<String.Index>] {
        var found: [Range<String.Index>] = []
        for term in terms {
            var searchStart = text.startIndex
            while searchStart < text.endIndex,
                  let range = text.range(
                      of: term,
                      options: [.caseInsensitive, .diacriticInsensitive],
                      range: searchStart..<text.endIndex
                  ) {
                found.append(range)
                // `range` is non-empty (terms are ≥2 characters), so this
                // always advances.
                searchStart = range.upperBound
            }
        }
        guard !found.isEmpty else { return [] }
        found.sort { $0.lowerBound < $1.lowerBound }
        var merged: [Range<String.Index>] = [found[0]]
        for range in found.dropFirst() {
            let last = merged[merged.count - 1]
            if range.lowerBound <= last.upperBound {
                merged[merged.count - 1] = last.lowerBound..<max(last.upperBound, range.upperBound)
            } else {
                merged.append(range)
            }
        }
        return merged
    }

    /// The window of `text` a row should show: centred on the FIRST match
    /// rather than starting at the top of the page.
    ///
    /// An elision is marked with a leading "…" so the row never implies the
    /// document begins here.
    static func snippet(
        _ text: String, terms: [String], length: Int = rowSnippetLength
    ) -> String {
        let cleaned = text
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard cleaned.count > length else { return cleaned }

        guard let first = matchRanges(in: cleaned, terms: terms).first else {
            // No match to centre on — the leading text is the only honest
            // choice, and it is what the row showed before.
            return String(cleaned.prefix(length)).trimmingCharacters(in: .whitespaces) + "…"
        }

        let matchOffset = cleaned.distance(from: cleaned.startIndex, to: first.lowerBound)
        // A match already inside the first window needs no re-centring:
        // starting the snippet mid-sentence to gain nothing costs the reader
        // the run-up to the phrase.
        let lead = length / 4
        guard matchOffset > lead else {
            return String(cleaned.prefix(length)).trimmingCharacters(in: .whitespaces) + "…"
        }

        let start = cleaned.index(cleaned.startIndex, offsetBy: matchOffset - lead)
        let window = cleaned[start...].prefix(length)
        // Start on a word boundary so the snippet does not open mid-word.
        let trimmedStart = window.drop(while: { !$0.isWhitespace }).drop(while: { $0.isWhitespace })
        let body = trimmedStart.isEmpty ? window : trimmedStart
        let suffix = cleaned.index(start, offsetBy: window.count) < cleaned.endIndex ? "…" : ""
        return "…" + body.trimmingCharacters(in: .whitespaces) + suffix
    }

    /// `text` with every matched term emphasised.
    ///
    /// Built by appending runs rather than by mutating ranges on an
    /// `AttributedString`: the matches are found on the `String` and the two
    /// index spaces are not interchangeable, so composing is both simpler and
    /// impossible to get subtly wrong.
    ///
    /// `inlinePresentationIntent` rather than an explicit font: the row keeps
    /// whatever semantic font it renders with, and only the WEIGHT changes
    /// (semantic-fonts rule — a highlight must never pin a point size).
    static func highlighted(_ text: String, terms: [String]) -> AttributedString {
        let ranges = matchRanges(in: text, terms: terms)
        guard !ranges.isEmpty else { return AttributedString(text) }

        var out = AttributedString()
        var cursor = text.startIndex
        for range in ranges {
            if cursor < range.lowerBound {
                out += AttributedString(String(text[cursor..<range.lowerBound]))
            }
            var hit = AttributedString(String(text[range]))
            hit.inlinePresentationIntent = .stronglyEmphasized
            hit.foregroundColor = .accentColor
            out += hit
            cursor = range.upperBound
        }
        if cursor < text.endIndex {
            out += AttributedString(String(text[cursor...]))
        }
        return out
    }

    /// The whole decision for one row: window the excerpt on the match, then
    /// light the terms up.
    static func rowText(excerpt: String, query: String) -> AttributedString {
        let terms = terms(in: query)
        return highlighted(snippet(excerpt, terms: terms), terms: terms)
    }
}
