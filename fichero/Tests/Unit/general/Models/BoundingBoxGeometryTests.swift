import CoreGraphics
@testable import Fichero
import XCTest

/// Tests for the normalized-bbox ↔ view-rect mapping behind image annotations
/// (#2458). These prove the coordinate math independent of the live viewport.
final class BoundingBoxGeometryTests: XCTestCase {

    private let unitVisible = CGRect(x: 0, y: 0, width: 1, height: 1)
    private let size = CGSize(width: 200, height: 100)

    // MARK: - viewRect (render)

    func testViewRectAtFitScalesNormalizedToView() {
        let rect = BoundingBoxGeometry.viewRect(
            normalized: [0.25, 0.5, 0.5, 0.25], in: size, visible: unitVisible
        )
        XCTAssertEqual(rect, CGRect(x: 50, y: 50, width: 100, height: 25))
    }

    func testViewRectUnderZoomUsesVisibleWindow() {
        // Visible window = right half, bottom half of the image.
        let visible = CGRect(x: 0.5, y: 0.5, width: 0.5, height: 0.5)
        // A box at the very centre of the image (0.5,0.5) sits at the view origin.
        let rect = BoundingBoxGeometry.viewRect(
            normalized: [0.5, 0.5, 0.25, 0.25], in: size, visible: visible
        )
        XCTAssertEqual(rect?.minX ?? -1, 0, accuracy: 0.001)
        XCTAssertEqual(rect?.minY ?? -1, 0, accuracy: 0.001)
        // 0.25 of image / 0.5 visible = half the view.
        XCTAssertEqual(rect?.width ?? -1, 100, accuracy: 0.001)
        XCTAssertEqual(rect?.height ?? -1, 50, accuracy: 0.001)
    }

    func testViewRectRejectsMalformedBox() {
        XCTAssertNil(BoundingBoxGeometry.viewRect(normalized: [0.1, 0.2], in: size, visible: unitVisible))
        XCTAssertNil(BoundingBoxGeometry.viewRect(normalized: [0, 0, 1, 1], in: .zero, visible: unitVisible))
    }

    // MARK: - normalizedBox (create)

    func testNormalizedBoxFromDragAtFit() {
        let box = BoundingBoxGeometry.normalizedBox(
            from: CGPoint(x: 50, y: 25), to: CGPoint(x: 150, y: 75),
            in: size, visible: unitVisible
        )
        XCTAssertEqual(box?[0] ?? -1, 0.25, accuracy: 0.001)
        XCTAssertEqual(box?[1] ?? -1, 0.25, accuracy: 0.001)
        XCTAssertEqual(box?[2] ?? -1, 0.5, accuracy: 0.001)
        XCTAssertEqual(box?[3] ?? -1, 0.5, accuracy: 0.001)
    }

    func testNormalizedBoxNormalizesCornerOrder() {
        // Drag bottom-right → top-left still yields a positive-size rect.
        let box = BoundingBoxGeometry.normalizedBox(
            from: CGPoint(x: 150, y: 75), to: CGPoint(x: 50, y: 25),
            in: size, visible: unitVisible
        )
        XCTAssertEqual(box?[0] ?? -1, 0.25, accuracy: 0.001)
        XCTAssertEqual(box?[1] ?? -1, 0.25, accuracy: 0.001)
    }

    func testNormalizedBoxClampsOutOfBoundsDrag() {
        let box = BoundingBoxGeometry.normalizedBox(
            from: CGPoint(x: -40, y: -40), to: CGPoint(x: 400, y: 400),
            in: size, visible: unitVisible
        )
        XCTAssertEqual(box, [0, 0, 1, 1])
    }

    func testDegenerateTapReturnsNil() {
        XCTAssertNil(BoundingBoxGeometry.normalizedBox(
            from: CGPoint(x: 50, y: 50), to: CGPoint(x: 51, y: 51),
            in: size, visible: unitVisible
        ))
    }
}
