import PDFKit

#if canImport(AppKit)
import AppKit

/// A segment drawn on a PDF page AS ITSELF, the same as on an image (`ShapeDrawing`, #5163 residue): its
/// outline and any area as a closed ink path, an open path and the baseline as open ink paths (the
/// baseline heavier), a point as a small circle -- and a segment with no reading dashed and unfilled.
/// `PDFView` draws in page space, so each is a `PDFAnnotation`; one function builds them for the
/// renderer (`applyOCRBoxes`) and its test alike.
enum PDFShapeAnnotations {
    /// The annotations one box draws as on `page`, or nil when it has no shapes of its own (a box is
    /// then drawn as the square it always was). `userName` marks them for the renderer's sweep.
    static func make(for box: OCRGeometryBox, on page: PDFPage, userName: String) -> [PDFAnnotation]? {
        guard !box.shapes.isEmpty else { return nil }
        let crop = page.bounds(for: .cropBox)
        let rotation = page.rotation
        let faint = box.noReading || OCRBoxConfidence.isUncertain(box)
        let color = faint ? NSColor.systemTeal.withAlphaComponent(0.35) : NSColor.systemTeal
        var out: [PDFAnnotation] = []
        for shape in box.shapes {
            let points = shape.points.compactMap { PDFRegionGeometry.pagePoint(normalized: $0, rotation: rotation, crop: crop) }
            let annotation: PDFAnnotation
            switch shape {
            case .point:
                guard let point = points.first else { continue }
                annotation = PDFAnnotation(
                    bounds: CGRect(x: point.x - 2, y: point.y - 2, width: 4, height: 4), forType: .circle, withProperties: nil
                )
                annotation.interiorColor = color
            case .polygon, .area, .path, .baseline:
                guard points.count >= 2 else { continue }
                let closed = shape.target.isClosed
                let width: CGFloat = shape.target == .baseline ? 2 : 1
                let bounds = boundingRect(points).insetBy(dx: -width, dy: -width)
                annotation = PDFAnnotation(bounds: bounds, forType: .ink, withProperties: nil)
                // Ink paths are in the annotation's own space: relative to its bounds' origin.
                let path = NSBezierPath()
                path.move(to: relative(points[0], to: bounds))
                points.dropFirst().forEach { path.line(to: relative($0, to: bounds)) }
                if closed { path.close() }
                annotation.add(path)
                let border = PDFBorder()
                border.lineWidth = width
                annotation.border = border
            }
            annotation.color = color
            if box.noReading {
                // No reading yet: dashed, never hidden, as on the image.
                let border = annotation.border ?? PDFBorder()
                border.style = .dashed
                border.dashPattern = [4, 3]
                annotation.border = border
            }
            annotation.userName = userName
            out.append(annotation)
        }
        return out
    }

    private static func boundingRect(_ points: [CGPoint]) -> CGRect {
        let xValues = points.map(\.x), yValues = points.map(\.y)
        let minX = xValues.min() ?? 0, minY = yValues.min() ?? 0
        return CGRect(x: minX, y: minY, width: (xValues.max() ?? 0) - minX, height: (yValues.max() ?? 0) - minY)
    }

    private static func relative(_ point: CGPoint, to bounds: CGRect) -> CGPoint {
        CGPoint(x: point.x - bounds.minX, y: point.y - bounds.minY)
    }
}
#endif
