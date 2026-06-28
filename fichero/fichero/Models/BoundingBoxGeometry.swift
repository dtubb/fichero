import CoreGraphics

/// Pure mapping between normalized image-space bounding boxes (`[x, y, w, h]`
/// in 0…1 of the full image) and view-space rects, accounting for the portion
/// of the image currently visible in a zoom/pan viewport (#2458).
///
/// Kept free of SwiftUI/AppKit so the coordinate math is unit-testable without
/// a running view — pixel alignment is the one thing worth proving by test.
enum BoundingBoxGeometry {
    /// Where a normalized image rect lands in the view, given the normalized
    /// `visible` window (the sub-rect of the image currently on screen) and the
    /// view `size`. At fit (visible == unit rect) this is a plain scale.
    static func viewRect(
        normalized box: [Double],
        in size: CGSize,
        visible: CGRect
    ) -> CGRect? {
        guard box.count >= 4, visible.width > 0, visible.height > 0,
              size.width > 0, size.height > 0 else { return nil }
        let originX = (box[0] - visible.minX) / visible.width * size.width
        let originY = (box[1] - visible.minY) / visible.height * size.height
        let width = box[2] / visible.width * size.width
        let height = box[3] / visible.height * size.height
        return CGRect(x: originX, y: originY, width: width, height: height)
    }

    /// Normalized image rect for a drag between two view points, given the
    /// visible window and view size. Returns `[x, y, w, h]` clamped to 0…1 with
    /// a positive size, or `nil` if the drag is degenerate (a tap).
    static func normalizedBox(
        from start: CGPoint,
        to end: CGPoint,
        in size: CGSize,
        visible: CGRect,
        minSpan: CGFloat = 4
    ) -> [Double]? {
        guard size.width > 0, size.height > 0 else { return nil }
        guard abs(end.x - start.x) >= minSpan || abs(end.y - start.y) >= minSpan else { return nil }

        func normalize(_ point: CGPoint) -> (Double, Double) {
            let normX = visible.minX + Double(point.x / size.width) * visible.width
            let normY = visible.minY + Double(point.y / size.height) * visible.height
            return (clamp(normX), clamp(normY))
        }
        let (startX, startY) = normalize(start)
        let (endX, endY) = normalize(end)
        let minX = min(startX, endX)
        let minY = min(startY, endY)
        let width = abs(endX - startX)
        let height = abs(endY - startY)
        guard width > 0, height > 0 else { return nil }
        return [minX, minY, width, height]
    }

    private static func clamp(_ value: Double) -> Double {
        min(1, max(0, value))
    }
}
