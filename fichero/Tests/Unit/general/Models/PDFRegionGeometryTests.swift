import CoreGraphics
@testable import Fichero
import XCTest

/// Tests for the normalized-bbox ↔ PDF page-rect conversion behind PDF region
/// annotations (#2458). PDF page space is bottom-left origin; the app stores
/// boxes top-left, so the Y flip is the thing worth proving.
final class PDFRegionGeometryTests: XCTestCase {

    private let pageSize = CGSize(width: 100, height: 200)

    // MARK: - pageRect (render)

    func testPageRectFlipsYToBottomLeft() {
        // Top-left box at the very top of the page → high Y in PDF space.
        let rect = PDFRegionGeometry.pageRect(normalized: [0.1, 0.0, 0.2, 0.25], pageSize: pageSize)
        XCTAssertEqual(rect?.minX ?? -1, 10, accuracy: 0.001)
        XCTAssertEqual(rect?.width ?? -1, 20, accuracy: 0.001)
        XCTAssertEqual(rect?.height ?? -1, 50, accuracy: 0.001)
        // y = (1 - 0 - 0.25) * 200 = 150
        XCTAssertEqual(rect?.minY ?? -1, 150, accuracy: 0.001)
    }

    func testPageRectBottomBoxMapsToYZero() {
        let rect = PDFRegionGeometry.pageRect(normalized: [0, 0.75, 1, 0.25], pageSize: pageSize)
        XCTAssertEqual(rect?.minY ?? -1, 0, accuracy: 0.001)
    }

    func testPageRectRejectsMalformed() {
        XCTAssertNil(PDFRegionGeometry.pageRect(normalized: [0, 0], pageSize: pageSize))
        XCTAssertNil(PDFRegionGeometry.pageRect(normalized: [0, 0, 1, 1], pageSize: .zero))
    }

    // MARK: - normalizedBox (create)

    func testNormalizedBoxRoundTripsThroughPageRect() {
        let box: [Double] = [0.2, 0.3, 0.4, 0.25]
        guard let rect = PDFRegionGeometry.pageRect(normalized: box, pageSize: pageSize) else {
            return XCTFail("pageRect failed")
        }
        // Page-space corners of that rect, fed back through normalizedBox.
        let result = PDFRegionGeometry.normalizedBox(
            fromPagePoint: CGPoint(x: rect.minX, y: rect.minY),
            toPagePoint: CGPoint(x: rect.maxX, y: rect.maxY),
            pageSize: pageSize
        )
        XCTAssertEqual(result?[0] ?? -1, 0.2, accuracy: 0.001)
        XCTAssertEqual(result?[1] ?? -1, 0.3, accuracy: 0.001)
        XCTAssertEqual(result?[2] ?? -1, 0.4, accuracy: 0.001)
        XCTAssertEqual(result?[3] ?? -1, 0.25, accuracy: 0.001)
    }

    func testNormalizedBoxClampsAndOrders() {
        let result = PDFRegionGeometry.normalizedBox(
            fromPagePoint: CGPoint(x: 200, y: -50),
            toPagePoint: CGPoint(x: -10, y: 250),
            pageSize: pageSize
        )
        XCTAssertEqual(result, [0, 0, 1, 1])
    }

    func testDegenerateDragReturnsNil() {
        XCTAssertNil(PDFRegionGeometry.normalizedBox(
            fromPagePoint: CGPoint(x: 50, y: 50),
            toPagePoint: CGPoint(x: 51, y: 51),
            pageSize: pageSize
        ))
    }
}
