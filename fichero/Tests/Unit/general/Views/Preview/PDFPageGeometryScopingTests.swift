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
