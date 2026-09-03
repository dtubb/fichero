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

    // MARK: - unrotated (display space → PDFKit page space)
    //
    // The engine normalises PDF text geometry in DISPLAY space; PDFKit
    // annotations live in UNROTATED page space. On a /Rotate page the two
    // disagree by ninety degrees, which is why boxes rendered sideways.

    /// The forward transform the ENGINE applies (unrotated → display), stated
    /// here so the round trip is proved against the real contract rather than
    /// against this file's own idea of it.
    private func engineDisplayBox(_ box: [Double], rotation: Int) -> [Double] {
        let x = box[0], y = box[1], w = box[2], h = box[3]
        switch rotation {
        case 90: return [1 - y - h, x, h, w]
        case 180: return [1 - x - w, 1 - y - h, w, h]
        case 270: return [y, 1 - x - w, h, w]
        default: return box
        }
    }

    func testUnrotatedIsTheInverseOfTheEngineTransform() {
        let source = [0.1, 0.2, 0.3, 0.05]
        for rotation in [0, 90, 180, 270] {
            let display = engineDisplayBox(source, rotation: rotation)
            let recovered = PDFRegionGeometry.unrotated(normalized: display, rotation: rotation)
            for (index, expected) in source.enumerated() {
                XCTAssertEqual(
                    recovered[index], expected, accuracy: 0.000_001,
                    "rotation \(rotation) component \(index)"
                )
            }
        }
    }

    func testUnrotatedIsNotANoOpOnARotatedPage() {
        let box = [0.1, 0.2, 0.3, 0.05]
        XCTAssertEqual(PDFRegionGeometry.unrotated(normalized: box, rotation: 0), box)
        XCTAssertNotEqual(PDFRegionGeometry.unrotated(normalized: box, rotation: 90), box)
        XCTAssertNotEqual(PDFRegionGeometry.unrotated(normalized: box, rotation: 270), box)
    }

    func testUnrotatedSwapsTheAspectOnAQuarterTurn() {
        // A WIDE display box on a 90° page came from a TALL unrotated one.
        let wide = [0.1, 0.4, 0.6, 0.05]
        let recovered = PDFRegionGeometry.unrotated(normalized: wide, rotation: 90)
        XCTAssertEqual(recovered[2], 0.05, accuracy: 0.000_001)
        XCTAssertEqual(recovered[3], 0.6, accuracy: 0.000_001)
    }

    func testUnrotatedKeepsBoxesInsideThePage() {
        for rotation in [90, 180, 270] {
            let corner = PDFRegionGeometry.unrotated(normalized: [0, 0, 0.2, 0.1], rotation: rotation)
            XCTAssertGreaterThanOrEqual(corner[0], -0.000_001)
            XCTAssertGreaterThanOrEqual(corner[1], -0.000_001)
            XCTAssertLessThanOrEqual(corner[0] + corner[2], 1.000_001)
            XCTAssertLessThanOrEqual(corner[1] + corner[3], 1.000_001)
        }
    }

    func testUnrotatedPassesMalformedBoxesThrough() {
        XCTAssertEqual(PDFRegionGeometry.unrotated(normalized: [0, 0], rotation: 90), [0, 0])
    }
}
