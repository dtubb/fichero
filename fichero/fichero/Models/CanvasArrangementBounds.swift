import Foundation
import simd

/// The centre and extent of a spatial arrangement, in scene units (#4411).
///
/// Split out of the 3D renderer because it is the input the zoom-OUT bound is
/// derived from, and a bound derived from a number nothing recomputes is not
/// derived from anything. Keeping it pure means the arrangement's span can be
/// tested without a RealityKit scene — which is the layer the defect lived in,
/// not the rendering.
enum CanvasArrangementBounds {

    /// Centre and span of `points`, or nil when there is nothing to frame.
    ///
    /// Span is measured CENTRE-to-centre, so a single item spans zero and a
    /// tight cluster spans almost nothing. Both are floored at one item's own
    /// extent: a zoom range derived from zero collapses to a single distance,
    /// which reads on screen as a pinch gesture that does nothing.
    ///
    /// Nil rather than a zero default, so the caller decides what an empty
    /// arrangement means. A renderer wants its default camera distance there,
    /// not a frame around the origin.
    static func of(_ points: [SIMD3<Float>], itemExtent: Float) -> (center: SIMD3<Float>, span: Float)? {
        guard let first = points.first else { return nil }

        var lower = first, upper = first
        for point in points.dropFirst() {
            lower = simd_min(lower, point)
            upper = simd_max(upper, point)
        }

        let extent = upper - lower
        return (
            center: (lower + upper) / 2,
            span: max(extent.x, extent.y, extent.z, max(itemExtent, 0.0001))
        )
    }
}
