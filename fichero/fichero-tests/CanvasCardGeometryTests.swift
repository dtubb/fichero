@testable import Fichero
import Foundation
import XCTest

/// #4193 — page images were squeezed into one fixed card shape in the 2D
/// canvas and both 3D scenes. Cards must take their page's TRUE aspect,
/// normalized on AREA (not width) so every card carries equal visual weight,
/// with a stable fallback until the texture loads and a memo so synchronous
/// rebuilds (selection reskins) keep the true shape.
@MainActor
final class CanvasCardGeometryTests: XCTestCase {
    // The memo is process-wide and has no reset (none needed in the app), so
    // each test uses its own source ids to stay order-independent.

    // MARK: - Area normalization

    func testDimensionsPreserveAreaAcrossAspects() {
        let area: Float = 0.8 * (0.8 / 0.75)   // the legacy 3D card footprint
        for aspect: Float in [0.4, 0.75, 1.0, 1.6, 2.9] {
            let dims = CanvasCardGeometry.dimensions(area: area, aspect: aspect, fallback: 0.75)
            XCTAssertEqual(dims.width * dims.height, area, accuracy: 0.0001,
                           "area must be preserved for aspect \(aspect)")
            XCTAssertEqual(dims.width / dims.height, aspect, accuracy: 0.0001,
                           "aspect must be respected for \(aspect)")
        }
    }

    func testWideSpreadAndTallPageCarryEqualWeight() {
        // A 2:1 double-spread and a 1:2 tall page: same area, very different
        // shapes — width-normalizing would make the spread 4× the page's area.
        let spread = CanvasCardGeometry.dimensions(area: 1.0, aspect: 2.0, fallback: 0.75)
        let tall = CanvasCardGeometry.dimensions(area: 1.0, aspect: 0.5, fallback: 0.75)
        XCTAssertEqual(spread.width * spread.height, tall.width * tall.height, accuracy: 0.0001)
        XCTAssertGreaterThan(spread.width, tall.width)
        XCTAssertLessThan(spread.height, tall.height)
    }

    // MARK: - Fallback (pre-load stability)

    func testDegenerateAspectsFallBackToTheRendererRatio() {
        for bad: Float? in [nil, 0, -1, .infinity, .nan] {
            let dims = CanvasCardGeometry.dimensions(area: 0.6, aspect: bad, fallback: 0.75)
            XCTAssertEqual(dims.width / dims.height, 0.75, accuracy: 0.0001,
                           "degenerate aspect \(String(describing: bad)) must use the fallback")
            XCTAssertEqual(dims.width * dims.height, 0.6, accuracy: 0.0001)
        }
    }

    // MARK: - Memo (reskin stability + one-shot rebuild)

    func testRecordAspectMemoizesAndReportsChangeExactlyOnce() {
        // First record → change (the caller reskins once).
        XCTAssertTrue(CanvasCardGeometry.recordAspect(0.5, forSourceId: "memo-page"))
        XCTAssertEqual(CanvasCardGeometry.knownAspect(forSourceId: "memo-page"), 0.5)
        // The reskin's own cache-hit reload records no change — terminates.
        XCTAssertFalse(CanvasCardGeometry.recordAspect(0.5, forSourceId: "memo-page"))
        // A genuinely different texture (re-OCR, replaced page) re-cuts once.
        XCTAssertTrue(CanvasCardGeometry.recordAspect(2.0, forSourceId: "memo-page"))
    }

    func testRecordAspectRejectsDegenerateValues() {
        for bad: Float in [0, -0.5, .infinity, .nan] {
            XCTAssertFalse(CanvasCardGeometry.recordAspect(bad, forSourceId: "degenerate-page"),
                           "degenerate aspect \(bad) must not be memoized")
        }
        XCTAssertNil(CanvasCardGeometry.knownAspect(forSourceId: "degenerate-page"))
    }

    // MARK: - All three renderers consume the shared geometry

    func testAllThreeRenderersRouteCardShapeThroughTheSharedGeometry() throws {
        let base = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Library/ViewModes/Canvas")
        for relative in [
            "3D/SpaceSceneView.swift",
            "3D/CanvasScene3DRenderer.swift",
            "2D/CanvasOrtho2DRenderer.swift"
        ] {
            let source = try String(contentsOf: base.appendingPathComponent(relative), encoding: .utf8)
            XCTAssertTrue(source.contains("CanvasCardGeometry.dimensions("),
                          "\(relative) must build source cards through the shared geometry (#4193)")
            XCTAssertTrue(source.contains("CanvasCardGeometry.recordAspect(of:"),
                          "\(relative) must memoize the loaded texture aspect (#4193)")
        }
    }
}
