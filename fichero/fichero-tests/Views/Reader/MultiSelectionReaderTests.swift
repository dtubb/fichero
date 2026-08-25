@testable import Fichero
import Testing
import XCTest

// The multi-selection reader fetches ONLY what the listing snapshot lacks —
// text already in hand is rendered immediately and never re-fetched.
struct MultiSelectionReaderTests {
    @Test("only documents without text in hand are fetched")
    func missingTextIds() {
        let docs = [
            Document(id: "a", name: "A", pageContent: "some transcript"),
            Document(id: "b", name: "B", pageContent: ""),
            Document(id: "c", name: "C")
        ]
        #expect(multiReaderMissingTextIds(docs) == ["b", "c"])
    }

    @Test("a fully-loaded selection fetches nothing")
    func nothingMissing() {
        let docs = [
            Document(id: "a", name: "A", pageContent: "x"),
            Document(id: "b", name: "B", pageContent: "y")
        ]
        #expect(multiReaderMissingTextIds(docs).isEmpty)
    }
}

// The multi view renders INSIDE the reader pane's chrome (2026-08-25: it
// used to replace ReadingPaneView wholesale, erasing the head, the lens
// selector and the crumbs on any 2+ selection). Source pins because the
// wiring is view composition XCTest cannot instantiate.
final class MultiSelectionReaderWiringTests: XCTestCase {
    func testMultiSelectionRendersInsideTheReaderPane() throws {
        let detail = try String(contentsOf: AppSource.root()
            .appendingPathComponent("Views/Shell/ContentView/Layout/ContentView+DetailLayout.swift"))
        XCTAssertTrue(
            detail.contains("multiDocuments: readerStack"),
            "the reading pane hosts the multi-selection itself"
        )
        XCTAssertFalse(
            detail.contains("AnyView(MultiSelectionReaderView"),
            "the multi view must never replace ReadingPaneView wholesale"
        )
        let tabs = try String(contentsOf: AppSource.root()
            .appendingPathComponent("Views/Reader/Page/ReadingPaneView+Tabs.swift"))
        XCTAssertTrue(
            tabs.contains("multiDocuments.count > 1"),
            "the Page lens routes 2+ documents to the multi list under the pane head"
        )
    }
}
