import CoreGraphics
@testable import Fichero
import XCTest

/// Tests for the preview's measurement rule (2026-08-20 bbox review, D3/D5).
///
/// The value exists to make one bug unrepresentable: an overlay rendered from
/// a fresh visible window paired with a stale drawn frame. These prove the
/// measurement gate that guards it, independent of a running view.
final class PreviewImageGeometryTests: XCTestCase {

    private let visible = CGRect(x: 0.25, y: 0.25, width: 0.5, height: 0.5)
    private let drawn = CGRect(x: 10, y: 20, width: 200, height: 100)

    // MARK: - isMeasured

    func testUnmeasuredIsNotMeasured() {
        XCTAssertFalse(PreviewImageGeometry.unmeasured.isMeasured)
    }

    func testBothRectsPresentIsMeasured() {
        XCTAssertTrue(PreviewImageGeometry(visible: visible, drawnFrame: drawn).isMeasured)
    }

    /// The D5 flash: before layout the drawn frame is zero, and the old code
    /// fell back to the unit rect and rendered anyway — across the whole pane.
    func testVisibleWithoutDrawnFrameIsNotMeasured() {
        XCTAssertFalse(PreviewImageGeometry(visible: visible, drawnFrame: .zero).isMeasured)
    }

    /// The mirror case: a drawn frame with no visible window would give the
    /// box mapping a zero-width divisor.
    func testDrawnFrameWithoutVisibleIsNotMeasured() {
        XCTAssertFalse(PreviewImageGeometry(visible: .zero, drawnFrame: drawn).isMeasured)
    }

    /// A rect can be non-zero yet degenerate — an origin offset with no area
    /// is still nothing to draw into.
    func testZeroAreaRectsAreNotMeasured() {
        let flatDrawn = CGRect(x: 10, y: 20, width: 200, height: 0)
        XCTAssertFalse(PreviewImageGeometry(visible: visible, drawnFrame: flatDrawn).isMeasured)

        let flatVisible = CGRect(x: 0.25, y: 0.25, width: 0, height: 0.5)
        XCTAssertFalse(PreviewImageGeometry(visible: flatVisible, drawnFrame: drawn).isMeasured)
    }

    // MARK: - Equatable (the write-coalescing guard)

    /// The binding writes only when the value differs, so equality has to
    /// compare BOTH rects — comparing one would drop a real update in which
    /// only the other moved (panning a fitted image moves neither; zooming
    /// moves both; a pane resize can move the drawn frame alone).
    func testEqualityComparesBothRects() {
        let base = PreviewImageGeometry(visible: visible, drawnFrame: drawn)
        XCTAssertEqual(base, PreviewImageGeometry(visible: visible, drawnFrame: drawn))

        let movedVisible = CGRect(x: 0.3, y: 0.25, width: 0.5, height: 0.5)
        XCTAssertNotEqual(base, PreviewImageGeometry(visible: movedVisible, drawnFrame: drawn))

        let movedDrawn = CGRect(x: 10, y: 20, width: 200, height: 120)
        XCTAssertNotEqual(base, PreviewImageGeometry(visible: visible, drawnFrame: movedDrawn))
    }

    // MARK: - Round trip with the box mapping

    /// The whole point of pairing them: a box mapped through `visible` lands
    /// inside a frame sized to `drawnFrame`. At fit (visible == unit rect) a
    /// full-page box exactly covers the drawn image.
    func testFullPageBoxCoversDrawnFrameAtFit() {
        let fit = PreviewImageGeometry(
            visible: CGRect(x: 0, y: 0, width: 1, height: 1),
            drawnFrame: drawn
        )
        let rect = BoundingBoxGeometry.viewRect(
            normalized: [0, 0, 1, 1],
            in: CGSize(width: fit.drawnFrame.width, height: fit.drawnFrame.height),
            visible: fit.visible
        )
        XCTAssertEqual(rect?.width ?? -1, drawn.width, accuracy: 0.001)
        XCTAssertEqual(rect?.height ?? -1, drawn.height, accuracy: 0.001)
    }

    /// Zoomed to the centre quarter, a box at the visible origin maps to the
    /// overlay origin — the invariant that breaks when the two rects come
    /// from different measurement passes.
    func testZoomedBoxMapsToOverlayOrigin() {
        let zoomed = PreviewImageGeometry(visible: visible, drawnFrame: drawn)
        let rect = BoundingBoxGeometry.viewRect(
            normalized: [0.25, 0.25, 0.1, 0.1],
            in: CGSize(width: zoomed.drawnFrame.width, height: zoomed.drawnFrame.height),
            visible: zoomed.visible
        )
        XCTAssertEqual(rect?.minX ?? -1, 0, accuracy: 0.001)
        XCTAssertEqual(rect?.minY ?? -1, 0, accuracy: 0.001)
    }

    // MARK: - Zoom-out letterbox mapping (2026-08-21: "if I zoom out, it
    // doesn't work") — the drawn frame must be the image WITHIN the
    // letterboxing NSImageView, not the view bounds.

    /// A wide image in a viewport-sized view sits centered with vertical
    /// slack; the drawn rect must inset to it.
    func testAspectFitRectInsetsLetterbox() {
        let rect = DrawnImageFrame.aspectFitRect(
            of: CGSize(width: 200, height: 100),
            in: CGRect(x: 0, y: 0, width: 400, height: 400)
        )
        XCTAssertEqual(rect, CGRect(x: 0, y: 100, width: 400, height: 200))
    }

    /// A view already image-shaped (zoomed in / exact fit) is a no-op —
    /// the pre-fix behavior, preserved.
    func testAspectFitRectExactShapeIsNoop() {
        let bounds = CGRect(x: 0, y: 0, width: 300, height: 150)
        let rect = DrawnImageFrame.aspectFitRect(
            of: CGSize(width: 200, height: 100), in: bounds
        )
        XCTAssertEqual(rect, bounds)
    }

    /// Degenerate sizes never divide by zero — the bounds come back whole.
    func testAspectFitRectDegenerateFallsBackToBounds() {
        let bounds = CGRect(x: 0, y: 0, width: 300, height: 150)
        XCTAssertEqual(DrawnImageFrame.aspectFitRect(of: .zero, in: bounds), bounds)
    }

    // MARK: - `.scaleNone` mapping (2026-09-01: boxes spilled off the page at
    // 47%). The preview's image view draws at NATIVE size, centred — so when
    // the view is slack on BOTH axes the drawn rect is the image's own size,
    // never a proportional blow-up to the bounds.

    func testCenteredNativeRectKeepsNativeSizeWhenSlackOnBothAxes() {
        let rect = DrawnImageFrame.centeredNativeRect(
            of: CGSize(width: 200, height: 100),
            in: CGRect(x: 0, y: 0, width: 400, height: 400)
        )
        XCTAssertEqual(rect, CGRect(x: 100, y: 150, width: 200, height: 100))
        // The aspect-fit answer for the same inputs is the wrong one here.
        XCTAssertNotEqual(
            rect,
            DrawnImageFrame.aspectFitRect(of: CGSize(width: 200, height: 100),
                                          in: CGRect(x: 0, y: 0, width: 400, height: 400))
        )
    }

    /// Zoomed in, the view IS the image: the rect is the bounds.
    func testCenteredNativeRectClampsToBoundsWhenImageLarger() {
        let bounds = CGRect(x: 0, y: 0, width: 300, height: 150)
        XCTAssertEqual(
            DrawnImageFrame.centeredNativeRect(of: CGSize(width: 900, height: 450), in: bounds),
            bounds
        )
    }

    /// Fit on one axis (the common case): both rules agree, so the fix cannot
    /// have moved a single box in the state that already looked right.
    func testCenteredNativeRectAgreesWithAspectFitAtOneAxisFit() {
        let image = CGSize(width: 200, height: 100)
        let bounds = CGRect(x: 0, y: 0, width: 200, height: 400)
        XCTAssertEqual(
            DrawnImageFrame.centeredNativeRect(of: image, in: bounds),
            DrawnImageFrame.aspectFitRect(of: image, in: bounds)
        )
    }
}
