import Foundation

/// How far the 3D camera may travel, derived from the arrangement rather than
/// fixed (#4411).
///
/// The camera was clamped to 2.2…16 — under one order of magnitude, about 7×.
/// Neither number knew how large the arrangement was or how big an item is, so
/// two things were impossible at once: zooming IN until a page is legible, and
/// zooming OUT until the whole arrangement fits. The pinch gesture was wired
/// correctly; the clamp was the bug.
///
/// Spatial arrangement only becomes *work* — read it, decide, file it — at the
/// point a page can actually be read. A limit that stops short of legibility
/// makes the view a picture of documents rather than a way to handle them.
enum CanvasZoomRange {

    /// Closest approach, in scene units.
    ///
    /// Derived from item size: an item is legible when it fills a good part of
    /// the view, so the floor is a small multiple of the item's own extent
    /// rather than a constant. Not zero — the camera must not enter or pass
    /// through the thing it is looking at.
    static func minDistance(itemExtent: Float) -> Float {
        max(0.05, itemExtent * 0.6)
    }

    /// Furthest retreat, in scene units.
    ///
    /// Derived from the arrangement's own span, so "as far out as it goes" and
    /// "everything is visible" are the same place. The margin leaves the
    /// outermost items inside the frame rather than exactly on its edge.
    ///
    /// An empty or single-item arrangement has no span, so it falls back to a
    /// usable default instead of collapsing to the minimum.
    static func maxDistance(arrangementSpan: Float, itemExtent: Float) -> Float {
        let span = max(arrangementSpan, itemExtent)
        return max(defaultDistance, span * 1.6)
    }

    /// Where the camera sits before the user has done anything.
    static let defaultDistance: Float = 6

    /// Clamp a requested distance into the range this arrangement supports.
    ///
    /// The bounds are ordered defensively: a degenerate arrangement could
    /// otherwise produce `min > max` and clamp every value to a single
    /// distance, which reads as a frozen pinch gesture.
    static func clamp(
        _ value: Float,
        arrangementSpan: Float,
        itemExtent: Float
    ) -> Float {
        let low = minDistance(itemExtent: itemExtent)
        let high = max(low, maxDistance(arrangementSpan: arrangementSpan, itemExtent: itemExtent))
        guard value.isFinite else { return defaultDistance }
        return min(max(value, low), high)
    }

    /// How much zoom range this arrangement affords, as a ratio.
    ///
    /// Recorded because the reported defect is exactly this number being too
    /// small: 16 / 2.2 ≈ 7.3×, which is not enough to go from "the whole
    /// arrangement" to "this word".
    static func range(arrangementSpan: Float, itemExtent: Float) -> Float {
        let low = minDistance(itemExtent: itemExtent)
        let high = max(low, maxDistance(arrangementSpan: arrangementSpan, itemExtent: itemExtent))
        return low > 0 ? high / low : 1
    }
}
