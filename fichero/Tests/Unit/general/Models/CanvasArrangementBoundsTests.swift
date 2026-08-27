@testable import Fichero
import Foundation
import simd
import Testing

/// #4411, second half: the zoom-OUT ceiling derives from the arrangement's
/// span, and until now nothing recomputed that span.
///
/// The first fix removed the fixed `2.2…16` clamp and derived both bounds from
/// content, which made zoom-IN reach a page. But `arrangementSpan` was assigned
/// in exactly one place — `fit()` — and `fit()` had no caller in the app. The
/// span therefore stayed at its initial value of one item's extent forever, so
/// `maxDistance` collapsed to `defaultDistance`, which is precisely the
/// distance the camera starts at. Zoom out did nothing whatsoever: a tighter
/// ceiling than the constant that was removed.
struct CanvasArrangementBoundsTests {

    private let item: Float = 1

    // MARK: - The defect, stated as a number

    /// Why a stale span is not a cosmetic imprecision but the whole bug.
    @Test("a span stuck at one item leaves no room to zoom out at all")
    func staleSpanRemovesAllZoomOutHeadroom() {
        let stale = CanvasZoomRange.maxDistance(arrangementSpan: item, itemExtent: item)

        #expect(stale == CanvasZoomRange.defaultDistance)
        #expect(
            stale < 16,
            "a ceiling at the starting distance is tighter than the 16 this fix replaced"
        )
    }

    /// And why refreshing it is the fix: the same arrangement, measured, opens
    /// the ceiling well past where the constant was.
    @Test("a measured span opens the ceiling past the old constant")
    func measuredSpanOpensTheCeiling() throws {
        let spread = (0..<5).map { SIMD3<Float>(Float($0) * 10, 0, 0) }
        let bounds = try #require(CanvasArrangementBounds.of(spread, itemExtent: item))

        #expect(bounds.span == 40)
        #expect(CanvasZoomRange.maxDistance(arrangementSpan: bounds.span, itemExtent: item) > 16)
    }

    // MARK: - Bounds themselves

    @Test("an empty arrangement has no bounds, rather than bounds around the origin")
    func emptyHasNoBounds() {
        #expect(CanvasArrangementBounds.of([], itemExtent: item) == nil)
    }

    @Test("the centre is the midpoint of the extremes on every axis")
    func centreIsTheMidpoint() throws {
        let bounds = try #require(
            CanvasArrangementBounds.of(
                [SIMD3<Float>(-4, 2, 10), SIMD3<Float>(6, -6, 0)],
                itemExtent: item
            )
        )

        #expect(bounds.center == SIMD3<Float>(1, -2, 5))
    }

    /// z is a real axis in the 3D view — an arrangement arranged in depth must
    /// frame like one arranged across.
    @Test("depth counts toward the span, not only width and height")
    func depthCountsTowardTheSpan() throws {
        let bounds = try #require(
            CanvasArrangementBounds.of(
                [SIMD3<Float>(0, 0, 0), SIMD3<Float>(1, 1, 30)],
                itemExtent: item
            )
        )

        #expect(bounds.span == 30)
    }

    /// Spans are centre-to-centre, so one card spans zero. A zoom range derived
    /// from zero clamps every distance to one value, which reads on screen as a
    /// pinch gesture that does nothing.
    @Test("a lone item still has a usable span")
    func loneItemHasAUsableSpan() throws {
        let bounds = try #require(CanvasArrangementBounds.of([SIMD3<Float>(3, 3, 3)], itemExtent: item))

        #expect(bounds.span == item)
        #expect(bounds.center == SIMD3<Float>(3, 3, 3))
        #expect(CanvasZoomRange.range(arrangementSpan: bounds.span, itemExtent: item) > 1)
    }

    @Test("a degenerate item extent cannot produce a zero span")
    func degenerateExtentIsFloored() throws {
        let bounds = try #require(CanvasArrangementBounds.of([.zero, .zero], itemExtent: 0))

        #expect(bounds.span > 0)
    }

    /// Order of arrival must not change the frame — placeables come out of a
    /// dictionary, so the sequence is not stable between reconciles.
    @Test("the bounds do not depend on the order points arrive in")
    func orderIndependent() throws {
        let points = [SIMD3<Float>(5, -1, 2), SIMD3<Float>(-3, 8, -7), SIMD3<Float>(0, 0, 0)]
        let forward = try #require(CanvasArrangementBounds.of(points, itemExtent: item))
        let backward = try #require(CanvasArrangementBounds.of(points.reversed(), itemExtent: item))

        #expect(forward.center == backward.center)
        #expect(forward.span == backward.span)
    }

    // MARK: - The bounds and the clamp agree

    /// Whatever the arrangement, fitting it must be a distance the clamp
    /// actually allows — otherwise "zoom to fit" and "as far out as it goes"
    /// disagree and the view settles somewhere that frames nothing.
    @Test("the fit distance for any arrangement is inside the permitted range")
    func fitDistanceIsReachable() throws {
        for span in [Float(0), 1, 7, 40, 500, 5000] {
            let points = [SIMD3<Float>(0, 0, 0), SIMD3<Float>(span, 0, 0)]
            let bounds = try #require(CanvasArrangementBounds.of(points, itemExtent: item))
            let wanted = bounds.span * 1.4

            let clamped = CanvasZoomRange.clamp(wanted, arrangementSpan: bounds.span, itemExtent: item)
            #expect(clamped == wanted, "fitting a span of \(bounds.span) was clamped away")
        }
    }
}
