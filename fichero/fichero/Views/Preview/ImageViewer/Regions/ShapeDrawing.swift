#if os(macOS)
import AppKit

/// A segment's own shapes as paths in the image view's document space (`SegmentShapes.Drawn`): a
/// polygon closed and washed, a path open, a point a dot, the baseline a heavier line under the ink.
/// Every length is in SCREEN points, divided by the magnification, as the boxes' are.
enum ShapeDrawing {
    /// How the shapes are stroked and washed: a box's look, or the selection's.
    struct Look {
        let line: CGFloat
        let stroke: NSColor
        let wash: NSColor
        let dashed: Bool
    }

    static func draw(_ shapes: [SegmentShapes.Drawn], imageRect: CGRect, scale: CGFloat, look: Look) {
        let (line, stroke, wash, dashed) = (look.line, look.stroke, look.wash, look.dashed)
        for shape in shapes {
            let points = shape.points.compactMap { DocumentBoxMapping.point(normalized: $0, imageRect: imageRect) }
            switch shape {
            case .polygon, .area:
                guard let path = path(through: points, closed: true) else { continue }
                wash.setFill()
                path.fill()
                stroke.setStroke()
                path.lineWidth = line
                if dashed { path.setLineDash([3 / scale, 2 / scale], count: 2, phase: 0) }
                path.stroke()
            case .path:
                guard let path = path(through: points, closed: false) else { continue }
                stroke.setStroke()
                path.lineWidth = line
                path.stroke()
            case .baseline:
                guard let path = path(through: points, closed: false) else { continue }
                stroke.setStroke()
                path.lineWidth = line * 2
                path.lineCapStyle = .round
                path.stroke()
            case .point:
                guard let point = points.first else { continue }
                let radius = 3 / scale
                let dot = NSBezierPath(ovalIn: CGRect(x: point.x - radius, y: point.y - radius,
                                                      width: radius * 2, height: radius * 2))
                stroke.setFill()
                dot.fill()
            }
        }
    }

    /// Reshape's handles: a square on every point of every shape, as Preview draws a shape's handles, and
    /// a small round one on each side's midpoint, where a point can be added (a point shape has none).
    static func drawHandles(
        _ shapes: [SegmentShapes.Drawn], imageRect: CGRect, scale: CGFloat, line: CGFloat, stroke: NSColor
    ) {
        let side = SelectionStyle.handleSide / scale
        for shape in shapes {
            let target = shape.target
            for normalized in shape.points {
                guard let point = DocumentBoxMapping.point(normalized: normalized, imageRect: imageRect) else { continue }
                let square = NSBezierPath(rect: CGRect(x: point.x - side / 2, y: point.y - side / 2, width: side, height: side))
                SelectionStyle.handleFill.setFill()
                square.fill()
                stroke.setStroke()
                square.lineWidth = line
                square.stroke()
            }
            for normalized in SegmentShapes.sideMidpoints(shape.points, target) {
                guard let point = DocumentBoxMapping.point(normalized: normalized, imageRect: imageRect) else { continue }
                let radius = side / 3
                let dot = NSBezierPath(ovalIn: CGRect(x: point.x - radius, y: point.y - radius,
                                                      width: radius * 2, height: radius * 2))
                stroke.setFill()
                dot.fill()
            }
        }
    }

    private static func path(through points: [CGPoint], closed: Bool) -> NSBezierPath? {
        guard let first = points.first, points.count >= 2 else { return nil }
        let path = NSBezierPath()
        path.move(to: first)
        points.dropFirst().forEach { path.line(to: $0) }
        if closed { path.close() }
        return path
    }
}
#endif
