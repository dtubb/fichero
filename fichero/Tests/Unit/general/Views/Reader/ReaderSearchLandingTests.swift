@testable import Fichero
import XCTest

/// The tie between a LIBRARY search hit and what the reader lights (Daniel:
/// "we want the reader to be able to show search results").
///
/// Selecting a result promotes it to `detailDocument`; the reader then seeds
/// its find-in-page (#4338) with the best description of WHY the document is on
/// screen — the matched passage when a search anchor names THIS document,
/// otherwise the library query's terms. `readerHighlightSeed` is that pure
/// decision, and it is the seam that makes the reader "show" the result. The
/// find machinery itself is covered by `ReaderFindInPageTests`; this pins the
/// choice of WHAT to find, which nothing else guarded.
@MainActor
final class ReaderSearchLandingTests: XCTestCase {

    private func anchor(
        documentId: String, text: String
    ) -> ReaderPassageAnchor {
        ReaderPassageAnchor(documentId: documentId, text: text, charStart: nil, charEnd: nil)
    }

    func testTheMatchedPassageWinsOverTheBareQuery() {
        // A passage anchor for the document on screen is more specific than the
        // query — it lands on the sentence, not every occurrence of a word.
        let seed = ReadingPaneView.readerHighlightSeed(
            anchor: anchor(documentId: "doc-1", text: "the road to Bagadó was long"),
            documentId: "doc-1",
            searchQuery: "road"
        )
        XCTAssertEqual(seed, "the road to Bagadó was long")
    }

    func testAnAnchorForAnotherDocumentIsIgnored() {
        // The anchor names a DIFFERENT document, so it does not describe this
        // one — fall back to the query rather than lighting a foreign passage.
        let seed = ReadingPaneView.readerHighlightSeed(
            anchor: anchor(documentId: "other-doc", text: "unrelated passage"),
            documentId: "doc-1",
            searchQuery: "bananas"
        )
        XCTAssertEqual(seed, "bananas")
    }

    func testNoAnchorFallsBackToTheQueryTerms() {
        let seed = ReadingPaneView.readerHighlightSeed(
            anchor: nil,
            documentId: "doc-1",
            searchQuery: "bananas"
        )
        XCTAssertEqual(seed, "bananas")
    }

    func testAnEmptyAnchorTextFallsBackToTheQuery() {
        // An anchor that resolved to no findable text must not blank the find —
        // the query is still a real description of the hit.
        let seed = ReadingPaneView.readerHighlightSeed(
            anchor: anchor(documentId: "doc-1", text: "   "),
            documentId: "doc-1",
            searchQuery: "bananas"
        )
        XCTAssertEqual(seed, "bananas")
    }

    func testNoAnchorAndNoQuerySeedsNothing() {
        // Nothing to say → empty seed, which the caller reads as "leave the
        // find bar alone" rather than an empty highlight over the whole page.
        let seed = ReadingPaneView.readerHighlightSeed(
            anchor: nil, documentId: "doc-1", searchQuery: ""
        )
        XCTAssertTrue(seed.isEmpty)
    }
}
