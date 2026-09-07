@testable import Fichero
import XCTest

/// The tie between a LIBRARY search hit and what the reader lights (Daniel:
/// "we want the reader to be able to show search results").
///
/// Selecting a result promotes it to `detailDocument`; the reader lights the
/// matched PASSAGE directly from the backend anchor
/// (`window.fichero.highlightMatchInPage`), and the find bar is seeded ONLY
/// with the library query's terms — no longer with a snippet of the excerpt
/// (Daniel, 2026-09-07: "highlight … by the html backend, not the swiftui
/// interface with a filter"). `readerHighlightSeed` is that pure decision. The
/// find machinery itself is covered by `ReaderFindInPageTests`; this pins the
/// choice of WHAT to find, which nothing else guarded.
@MainActor
final class ReaderSearchLandingTests: XCTestCase {

    private func anchor(
        documentId: String, text: String
    ) -> ReaderPassageAnchor {
        ReaderPassageAnchor(documentId: documentId, text: text, charStart: nil, charEnd: nil)
    }

    func testTheAnchorNoLongerSeedsTheFindBar() {
        // The matched passage is lit directly by the backend now
        // (highlightMatchInPage), so a passage anchor no longer pushes a snippet
        // into the SwiftUI find bar — the find bar holds the query terms, not
        // the excerpt. (Daniel, 2026-09-07.)
        let seed = ReadingPaneView.readerHighlightSeed(
            anchor: anchor(documentId: "doc-1", text: "the road to Bagadó was long"),
            documentId: "doc-1",
            searchQuery: "road"
        )
        XCTAssertEqual(seed, "road")
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
