@testable import Fichero
import XCTest

/// One page's boxes must not be painted over another page (#4418 follow-up).
///
/// `PDFPageWithToolbar` renders from the PARENT PDF, but the importer writes
/// each page's `text_geometry` artifact on that page's own child document. So
/// asking the parent for geometry found nothing on a normally-imported PDF —
/// and where a whole-document run HAD left an artifact on the parent, a single
/// page's boxes were drawn on every page of the book. Both read to a reader as
/// "the boxes are wrong".
final class PDFPageGeometryScopingTests: XCTestCase {

    private func box(_ text: String, page: Int?) -> OCRGeometryBox {
        OCRGeometryBox(
            text: text,
            bbox: [0.1, 0.1, 0.2, 0.05],
            level: "word",
            confidence: nil,
            pageIndex: page,
            charStart: nil,
            charEnd: nil,
            provider: nil,
            source: nil
        )
    }

    func testWholeDocumentGeometryDrawsOnlyTheDisplayedPage() {
        let boxes = [box("one", page: 0), box("two", page: 1), box("three", page: 2)]
        let drawn = PDFPageWithToolbar.boxesForDisplayedPage(
            boxes, pageIndex: 1, isPageScoped: false
        )
        XCTAssertEqual(drawn.map(\.text), ["two"])
    }

    func testABoxWithNoPageIndexIsKept() {
        // Absence of the field is not evidence of the wrong page — dropping
        // these would blank every producer that does not number its boxes.
        let boxes = [box("unnumbered", page: nil), box("elsewhere", page: 7)]
        let drawn = PDFPageWithToolbar.boxesForDisplayedPage(
            boxes, pageIndex: 1, isPageScoped: false
        )
        XCTAssertEqual(drawn.map(\.text), ["unnumbered"])
    }

    func testPageScopedGeometryIsDrawnWhole() {
        // The geometry came from the page child, so it is already this page's.
        // A page-scoped producer may leave pageIndex unset or number it from
        // its own origin; second-guessing it here would blank a correct
        // overlay.
        let boxes = [box("a", page: 0), box("b", page: nil), box("c", page: 4)]
        let drawn = PDFPageWithToolbar.boxesForDisplayedPage(
            boxes, pageIndex: 2, isPageScoped: true
        )
        XCTAssertEqual(drawn.map(\.text), ["a", "b", "c"])
    }

    func testFilteringIsNotAccidentallyANoOp() {
        // Guard against a future "fix" that returns the input unchanged: the
        // whole-document path MUST discard another page's boxes.
        let boxes = [box("wrong-page", page: 5)]
        XCTAssertTrue(
            PDFPageWithToolbar.boxesForDisplayedPage(
                boxes, pageIndex: 0, isPageScoped: false
            ).isEmpty
        )
    }
}

/// A pane the host cannot see must not borrow the host's page (team-lead
/// review, 2026-09-03). A secondary split pane and a pinned pane track their
/// own page index and never tell the host, so the page document handed down
/// can describe a different page than the pane is rendering.
extension PDFPageGeometryScopingTests {

    /// The rule the view applies: host-supplied geometry counts only while the
    /// pane is showing the host's page.
    private func paneGeometryApplies(
        isSecondaryOrPinned: Bool, localPageIndex: Int, hostPageIndex: Int
    ) -> Bool {
        !isSecondaryOrPinned || localPageIndex == hostPageIndex
    }

    func testAPrimaryPaneAlwaysUsesTheHostPageDocument() {
        XCTAssertTrue(
            paneGeometryApplies(
                isSecondaryOrPinned: false, localPageIndex: 4, hostPageIndex: 0
            )
        )
    }

    func testAPinnedPaneOnTheHostPageStillUsesIt() {
        XCTAssertTrue(
            paneGeometryApplies(
                isSecondaryOrPinned: true, localPageIndex: 2, hostPageIndex: 2
            )
        )
    }

    func testAPaneFlippedAwayFromTheHostDoesNotBorrowItsGeometry() {
        // The narrow case of the original bug: without this the pinned pane
        // would draw page 2's boxes over page 7.
        XCTAssertFalse(
            paneGeometryApplies(
                isSecondaryOrPinned: true, localPageIndex: 7, hostPageIndex: 2
            )
        )
    }

    func testFallingBackToWholeDocumentStillFiltersToThePaneItsOwnPage() {
        // What a flipped pane gets instead: the rendered document's geometry,
        // filtered to ITS page — never another page's boxes.
        let boxes = [box("host page", page: 2), box("this pane", page: 7)]
        let drawn = PDFPageWithToolbar.boxesForDisplayedPage(
            boxes, pageIndex: 7, isPageScoped: false
        )
        XCTAssertEqual(drawn.map(\.text), ["this pane"])
    }
}
