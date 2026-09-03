@testable import Fichero
import Foundation
import SwiftUI
import XCTest

/// Daniel, live testing 2026-09-02: "result list rows should show the
/// matched/relevant text with the query terms highlighted, not just the
/// leading snippet."
///
/// Two claims, tested separately: the row shows the right WINDOW of text, and
/// it marks the right words inside it.
final class SearchSnippetHighlighterTests: XCTestCase {

    // MARK: - Which words are evidence

    func testTermsDropTheConnectivesAskModeSendsAlong() {
        // Ask mode (#4117) sends sentences. Without a stopword pass every
        // snippet would be half-bold and the emphasis would stop meaning
        // "this is why this row is here".
        let terms = SearchSnippetHighlighter.terms(in: "what did he say about the road to Bagadó")

        XCTAssertEqual(terms, ["say", "about", "road", "Bagadó"])
    }

    func testTermsAreDedupedAndPunctuationIsNotATerm() {
        let terms = SearchSnippetHighlighter.terms(in: "Bagadó, Bagadó — \"bagadó\"!")

        XCTAssertEqual(terms, ["Bagadó"])
    }

    func testSingleCharactersAreNotTermsButDigitPairsAre() {
        // "a" matches everywhere and explains nothing; "85" is a real
        // archival query.
        let terms = SearchSnippetHighlighter.terms(in: "a 85 x Quibdó")

        XCTAssertEqual(terms, ["85", "Quibdó"])
    }

    func testAStopwordOnlyQueryHighlightsNothingRatherThanEverything() {
        let terms = SearchSnippetHighlighter.terms(in: "the and of")

        XCTAssertTrue(terms.isEmpty)
        let attributed = SearchSnippetHighlighter.highlighted("the road and the river", terms: terms)
        XCTAssertEqual(String(attributed.characters), "the road and the river")
        XCTAssertEqual(attributed.runs.count, 1, "No terms must mean no emphasis, not one big run of it.")
    }

    // MARK: - Matching

    func testMatchingIsCaseAndDiacriticInsensitive() throws {
        // The exact query Daniel ran: "Bagado" must find "Bagadó".
        let text = "the road to BAGADÓ was impassable"
        let ranges = SearchSnippetHighlighter.matchRanges(in: text, terms: ["bagado"])

        XCTAssertEqual(ranges.count, 1)
        XCTAssertEqual(String(text[try XCTUnwrap(ranges.first)]), "BAGADÓ")
    }

    func testEveryOccurrenceIsMarkedNotJustTheFirst() {
        let text = "Quibdó, then Quibdó again"
        let ranges = SearchSnippetHighlighter.matchRanges(in: text, terms: ["Quibdó"])

        XCTAssertEqual(ranges.count, 2)
    }

    func testOverlappingTermsMergeIntoOneSpan() throws {
        // "road" is inside "roadside" — nested spans would double-emphasise
        // and produce a run boundary in the middle of a word.
        let text = "the roadside camp"
        let ranges = SearchSnippetHighlighter.matchRanges(in: text, terms: ["roadside", "road"])

        XCTAssertEqual(ranges.count, 1)
        XCTAssertEqual(String(text[try XCTUnwrap(ranges.first)]), "roadside")
    }

    // MARK: - Which window of the text

    func testTheSnippetCentresOnTheMatchInsteadOfTheTopOfThePage() {
        let lead = String(repeating: "preamble ", count: 60)   // ~540 characters
        let text = lead + "the mule track to Bagadó" + String(repeating: " tail", count: 40)

        let snippet = SearchSnippetHighlighter.snippet(text, terms: ["Bagadó"])

        XCTAssertTrue(snippet.contains("Bagadó"), "The row must show the text that matched.")
        XCTAssertTrue(snippet.hasPrefix("…"), "An elided opening must say so.")
        XCTAssertLessThanOrEqual(snippet.count, SearchSnippetHighlighter.rowSnippetLength + 2)
    }

    func testAMatchAlreadyNearTheStartIsNotReCentred() {
        // Re-centring here would cost the reader the run-up to the phrase and
        // gain nothing.
        let text = "Bagadó was reached at noon. " + String(repeating: "more text ", count: 60)

        let snippet = SearchSnippetHighlighter.snippet(text, terms: ["Bagadó"])

        XCTAssertTrue(snippet.hasPrefix("Bagadó was reached"))
    }

    func testShortTextIsReturnedWholeAndUnelided() {
        let snippet = SearchSnippetHighlighter.snippet("a short line", terms: ["short"])

        XCTAssertEqual(snippet, "a short line")
    }

    func testNewlinesCollapseSoTheRowStaysTwoLinesOfProse() {
        let snippet = SearchSnippetHighlighter.snippet("first\nsecond\r\nthird", terms: ["second"])

        XCTAssertEqual(snippet, "first second  third")
    }

    func testTextWithNoMatchStillShowsItsLeadingSnippet() {
        // A row can be here on an entity or claim leg whose excerpt does not
        // contain the query words at all — it must not render blank.
        let text = String(repeating: "unrelated prose ", count: 40)

        let snippet = SearchSnippetHighlighter.snippet(text, terms: ["Bagadó"])

        XCTAssertTrue(snippet.hasPrefix("unrelated prose"))
        XCTAssertTrue(snippet.hasSuffix("…"))
    }

    // MARK: - The emphasis itself

    func testMatchedTermsAreEmphasisedAndTheRestIsNot() {
        let attributed = SearchSnippetHighlighter.highlighted(
            "the road to Bagadó", terms: ["Bagadó"]
        )

        XCTAssertEqual(String(attributed.characters), "the road to Bagadó")
        let emphasised = attributed.runs
            .filter { $0.inlinePresentationIntent == .stronglyEmphasized }
            .map { String(attributed[$0.range].characters) }
        XCTAssertEqual(emphasised, ["Bagadó"])
    }

    /// Weight and colour only — never a point size. A highlight that pins a
    /// font would override whatever semantic font the row renders with.
    func testEmphasisDoesNotPinAFont() {
        let attributed = SearchSnippetHighlighter.highlighted("road to Bagadó", terms: ["Bagadó"])

        for run in attributed.runs {
            XCTAssertNil(run.font, "The row's own semantic font must survive the highlight.")
        }
    }

    func testRowTextWindowsAndHighlightsInOneStep() {
        let lead = String(repeating: "preamble ", count: 60)
        let text = lead + "the mule track to Bagadó"

        let attributed = SearchSnippetHighlighter.rowText(excerpt: text, query: "road to Bagado")

        let rendered = String(attributed.characters)
        XCTAssertTrue(rendered.contains("Bagadó"))
        let emphasised = attributed.runs
            .filter { $0.inlinePresentationIntent == .stronglyEmphasized }
            .map { String(attributed[$0.range].characters) }
        XCTAssertEqual(emphasised, ["Bagadó"], "\"to\" is a stopword; \"road\" is not in the window.")
    }

    // MARK: - Wiring

    func testTheHitCarriesTheQueryItMatched() throws {
        let hit = TransientSearchRowHit(excerpt: "the road to Bagadó", score: 0.9, query: "Bagado")

        let highlighted = try XCTUnwrap(hit.highlightedExcerpt)
        XCTAssertEqual(String(highlighted.characters), "the road to Bagadó")
        let emphasised = highlighted.runs
            .filter { $0.inlinePresentationIntent == .stronglyEmphasized }
            .map { String(highlighted[$0.range].characters) }
        XCTAssertEqual(emphasised, ["Bagadó"])
    }

    func testAHitWithNoExcerptFallsBackRatherThanRenderingEmpty() {
        let hit = TransientSearchRowHit(excerpt: nil, score: 0.9, query: "Bagado")

        XCTAssertNil(
            hit.highlightedExcerpt,
            "nil, not an empty AttributedString — the row falls back to the document's own text."
        )
    }

    func testTheQueryIsPartOfTheRowIdentitySoANewSearchRepaints() {
        // `.equatable()` compares this struct and nothing else; a query the
        // identity did not contain could not repaint the row.
        let first = TransientSearchRowHit(excerpt: "same text", score: 0.9, query: "Bagado")
        let second = TransientSearchRowHit(excerpt: "same text", score: 0.9, query: "Quibdo")

        XCTAssertNotEqual(first, second)
    }
}
