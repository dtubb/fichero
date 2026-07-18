@testable import Fichero
import XCTest

/// Covers the sort-free page-child count `ContentView.pdfDocPageCount(in:)`
/// introduced by #3866. The reading pane only needs the count, so this replaced
/// the old `pdfDocPages` accessor whose filter+sort ran twice per render.
final class PDFDocPageCountTests: XCTestCase {
    func testCountsOnlyPageChildren() {
        let docs = [
            Document(docType: .folder, name: "folder"),
            Document(docType: .page, name: "p1"),
            Document(docType: .file, name: "file"),
            Document(docType: .page, name: "p2"),
            Document(docType: .page, name: "p3")
        ]
        XCTAssertEqual(ContentView.pdfDocPageCount(in: docs), 3)
    }

    func testEmptyAndNoPagesAreZero() {
        XCTAssertEqual(ContentView.pdfDocPageCount(in: []), 0)
        XCTAssertEqual(
            ContentView.pdfDocPageCount(in: [Document(docType: .file, name: "x")]),
            0
        )
    }
}
