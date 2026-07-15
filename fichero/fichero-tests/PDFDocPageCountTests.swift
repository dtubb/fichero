@testable import Fichero
import XCTest

/// Covers the sort-free page-child count `ContentView.pdfDocPageCount(in:)`
/// introduced by #3866. The reading pane only needs the count, so this replaced
/// the old `pdfDocPages` accessor whose filter+sort ran twice per render.
final class PDFDocPageCountTests: XCTestCase {
    func testCountsOnlyPageChildren() {
        let docs = [
            Document(name: "folder", docType: .folder),
            Document(name: "p1", docType: .page),
            Document(name: "file", docType: .file),
            Document(name: "p2", docType: .page),
            Document(name: "p3", docType: .page)
        ]
        XCTAssertEqual(ContentView.pdfDocPageCount(in: docs), 3)
    }

    func testEmptyAndNoPagesAreZero() {
        XCTAssertEqual(ContentView.pdfDocPageCount(in: []), 0)
        XCTAssertEqual(
            ContentView.pdfDocPageCount(in: [Document(name: "x", docType: .file)]),
            0
        )
    }
}
