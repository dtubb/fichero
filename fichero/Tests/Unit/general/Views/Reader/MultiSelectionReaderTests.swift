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

// Same-parent page selections ride the shared WebKit transcript via its
// `?pages=` filter; everything else keeps the native list (2026-08-25).
struct MultiReaderCommonParentTests {
    @Test("pages of one parent resolve to that parent")
    func samePagesResolve() {
        let docs = [
            Document(id: "p1", parentId: "pdf", docType: .page, name: "Page 1"),
            Document(id: "p2", parentId: "pdf", docType: .page, name: "Page 2")
        ]
        #expect(multiReaderCommonPageParent(docs) == "pdf")
    }

    @Test("pages of different parents fall back to the native list")
    func mixedParentsFallBack() {
        let docs = [
            Document(id: "p1", parentId: "pdf-a", docType: .page, name: "Page 1"),
            Document(id: "p2", parentId: "pdf-b", docType: .page, name: "Page 2")
        ]
        #expect(multiReaderCommonPageParent(docs) == nil)
    }

    @Test("a non-page in the selection falls back to the native list")
    func nonPageFallsBack() {
        let docs = [
            Document(id: "p1", parentId: "pdf", docType: .page, name: "Page 1"),
            Document(id: "f1", parentId: "pdf", docType: .file, name: "Other.jpg")
        ]
        #expect(multiReaderCommonPageParent(docs) == nil)
    }

    @Test("an orphan page has no common parent")
    func orphanPage() {
        let docs = [Document(id: "p1", docType: .page, name: "Page 1")]
        #expect(multiReaderCommonPageParent(docs) == nil)
    }

    @Test("regions of one parent resolve to that parent (2026-08-29)")
    func sameParentRegionsResolve() {
        let region = DocumentRegion(rect: [0, 0, 1, 0.5], space: "normalized")
        let docs = [
            Document(id: "e1", parentId: "sheet", docType: .file, name: "1933-01-10", regionInParent: region),
            Document(id: "e2", parentId: "sheet", docType: .file, name: "1933-01-11", regionInParent: region)
        ]
        #expect(multiReaderCommonPageParent(docs) == "sheet")
    }

    @Test("a region-less file among regions falls back to the native list")
    func regionlessFileFallsBack() {
        let region = DocumentRegion(rect: [0, 0, 1, 0.5], space: "normalized")
        let docs = [
            Document(id: "e1", parentId: "sheet", docType: .file, name: "Entry", regionInParent: region),
            Document(id: "f1", parentId: "sheet", docType: .file, name: "Other.jpg")
        ]
        #expect(multiReaderCommonPageParent(docs) == nil)
    }
}
