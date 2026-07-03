@testable import Fichero
import XCTest

/// Pure logic behind the compact PDF reading path (#3013): page-index ↔ page
/// resolution (the `sequence - 1 == index` sync) and PDF leaf resolution.
@MainActor
final class PDFCompactReadingTests: XCTestCase {

    private func page(id: String, sequence: Int?) -> Document {
        Document(id: id, parentId: "pdf-1", docType: .page, fileType: nil, name: id, path: nil, sequence: sequence)
    }

    // MARK: - page-index sync

    /// 1-based `sequence` maps to PDFKit's 0-based index, clamped at 0.
    func testPdfPageIndexFromSequence() {
        XCTAssertEqual(ContentView.pdfPageIndex(for: page(id: "p1", sequence: 1)), 0)
        XCTAssertEqual(ContentView.pdfPageIndex(for: page(id: "p7", sequence: 7)), 6)
        // Missing sequence falls back to the first page, never a negative index.
        XCTAssertEqual(ContentView.pdfPageIndex(for: page(id: "p0", sequence: nil)), 0)
        XCTAssertEqual(ContentView.pdfPageIndex(for: page(id: "pNeg", sequence: 0)), 0)
    }

    /// Non-page docs (and nil) resolve to the first page.
    func testPdfPageIndexNonPageIsZero() {
        let file = Document(id: "f", docType: .file, fileType: .pdf, name: "Doc.pdf")
        XCTAssertEqual(ContentView.pdfPageIndex(for: file), 0)
        XCTAssertEqual(ContentView.pdfPageIndex(for: nil), 0)
    }

    /// The reverse direction: a 0-based index resolves to the page whose
    /// `sequence` is `index + 1` — and only among page documents.
    func testPageDocumentAtPDFIndex() {
        let docs = [
            page(id: "p1", sequence: 1),
            page(id: "p2", sequence: 2),
            Document(id: "note", docType: .file, fileType: nil, name: "note"),
            page(id: "p3", sequence: 3)
        ]
        XCTAssertEqual(ContentView.pageDocument(atPDFIndex: 0, in: docs)?.id, "p1")
        XCTAssertEqual(ContentView.pageDocument(atPDFIndex: 2, in: docs)?.id, "p3")
        XCTAssertNil(ContentView.pageDocument(atPDFIndex: 9, in: docs))
    }

    /// Round-trip: index → page → index is stable.
    func testPageIndexRoundTrip() {
        let docs = (1...5).map { page(id: "p\($0)", sequence: $0) }
        for index in 0..<5 {
            let resolved = ContentView.pageDocument(atPDFIndex: index, in: docs)
            XCTAssertEqual(ContentView.pdfPageIndex(for: resolved), index)
        }
    }

    // MARK: - PDF leaf resolution

    func testShouldUsePDFCanvasLeafResolution() {
        let pdf = Document(id: "pdf", docType: .file, fileType: .pdf, name: "Doc.pdf")
        let pdfPage = Document(id: "pg", parentId: "pdf", docType: .page, fileType: nil, name: "Page")
        let imagePage = Document(id: "img", parentId: "f", docType: .page, fileType: .image, name: "Scan")
        let plainImage = Document(id: "i", docType: .file, fileType: .image, name: "Photo")

        XCTAssertTrue(CanvasDocumentPolicy.shouldUsePDFCanvas(for: pdf))
        XCTAssertTrue(CanvasDocumentPolicy.shouldUsePDFCanvas(for: pdfPage))
        // An image-backed page is NOT a PDF leaf — it uses the image display.
        XCTAssertFalse(CanvasDocumentPolicy.shouldUsePDFCanvas(for: imagePage))
        XCTAssertFalse(CanvasDocumentPolicy.shouldUsePDFCanvas(for: plainImage))
    }
}
