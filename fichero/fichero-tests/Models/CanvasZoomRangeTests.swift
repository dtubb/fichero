@testable import Fichero
import Foundation
import Testing

/// #4411: in the 3D view you cannot zoom in far enough to read a page, nor out
/// far enough to see the whole arrangement.
///
/// The camera was clamped to a fixed `2.2…16` — about 7x, under one order of
/// magnitude. Neither number knew how large the arrangement was or how big an
/// item is. The pinch gesture was wired correctly; the clamp was the bug.
struct CanvasZoomRangeTests {

    private let item: Float = 1

    // MARK: - The defect, stated directly

    /// The old ceiling was 16 regardless of content, so a large arrangement
    /// could not be seen whole. It must now grow with the span.
    @Test("a larger arrangement can be seen from further out")
    func largerArrangementsZoomOutFurther() {
        let small = CanvasZoomRange.maxDistance(arrangementSpan: 4, itemExtent: item)
        let large = CanvasZoomRange.maxDistance(arrangementSpan: 100, itemExtent: item)

        #expect(large > small)
        #expect(large > 16, "16 was the fixed ceiling that hid large arrangements")
    }

    /// The old floor was 2.2, which is why a page never became readable.
    @Test("the camera can approach far closer than the old floor")
    func cameraApproachesCloserThanBefore() {
        #expect(CanvasZoomRange.minDistance(itemExtent: item) < 2.2)
    }

    /// The reported symptom as one number: the affordable range was ~7x.
    @Test("the usable zoom range is far wider than it was")
    func rangeIsWiderThanBefore() {
        let old: Float = 16 / 2.2
        for span in [Float(1), 4, 20, 100] {
            let now = CanvasZoomRange.range(arrangementSpan: span, itemExtent: item)
            #expect(now > old, Comment(rawValue: "span \(span): \(now)x vs \(old)x"))
        }
    }

    /// Range grows with the arrangement rather than being fixed — the property
    /// the constants could not have.
    @Test("the range scales with the arrangement")
    func rangeScalesWithTheArrangement() {
        let tight = CanvasZoomRange.range(arrangementSpan: 1, itemExtent: item)
        let sprawling = CanvasZoomRange.range(arrangementSpan: 100, itemExtent: item)
        #expect(sprawling > tight * 5)
    }

    // MARK: - Bounds stay sane

    /// A degenerate arrangement must not produce `min > max`, which would
    /// clamp every value to one distance and read as a frozen pinch.
    @Test("the bounds never invert, for any arrangement")
    func boundsNeverInvert() {
        for span in [Float(0), 0.001, 1, 50, 10_000] {
            for extent in [Float(0.001), 1, 500] {
                let low = CanvasZoomRange.minDistance(itemExtent: extent)
                let high = CanvasZoomRange.maxDistance(arrangementSpan: span, itemExtent: extent)
                #expect(high >= low, Comment(rawValue: "span \(span) extent \(extent)"))
            }
        }
    }

    /// The camera must never reach zero: it would be inside the thing it is
    /// looking at.
    @Test("the camera never reaches the item it is looking at")
    func cameraNeverReachesTheItem() {
        for extent in [Float(0), 0.0001, 1, 100] {
            #expect(CanvasZoomRange.minDistance(itemExtent: extent) > 0,
                    Comment(rawValue: "extent \(extent)"))
        }
    }

    @Test("a requested distance is clamped into the supported range")
    func requestsAreClamped() {
        let low = CanvasZoomRange.minDistance(itemExtent: item)
        let high = CanvasZoomRange.maxDistance(arrangementSpan: 20, itemExtent: item)

        #expect(CanvasZoomRange.clamp(-5, arrangementSpan: 20, itemExtent: item) == low)
        #expect(CanvasZoomRange.clamp(9999, arrangementSpan: 20, itemExtent: item) == high)
        #expect(CanvasZoomRange.clamp(5, arrangementSpan: 20, itemExtent: item) == 5)
    }

    /// A non-finite distance would propagate NaN into the camera transform and
    /// blank the view — it falls back rather than clamping to nonsense.
    @Test("a non-finite request falls back instead of poisoning the camera")
    func nonFiniteRequestFallsBack() {
        for bad in [Float.nan, .infinity, -.infinity] {
            let clamped = CanvasZoomRange.clamp(bad, arrangementSpan: 20, itemExtent: item)
            #expect(clamped.isFinite, Comment(rawValue: "\(bad)"))
            #expect(clamped == CanvasZoomRange.defaultDistance)
        }
    }

    // MARK: - Structural: the constants are gone

    @Test("the renderer no longer clamps to fixed constants")
    func rendererUsesDerivedBounds() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(
                "fichero/Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        #expect(source.contains("CanvasZoomRange.clamp("))
        #expect(!source.contains("minDistance: Float = 2.2"))
        #expect(!source.contains("maxDistance: Float = 16"))
        // The span must actually be recorded, or the derived ceiling is stuck
        // at its fallback and nothing changes for a large arrangement.
        #expect(source.contains("arrangementSpan = span"))
    }
}
