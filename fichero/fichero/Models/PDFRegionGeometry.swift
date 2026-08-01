import CoreGraphics

/// Pure mapping between normalized bounding boxes (`[x, y, w, h]`, 0…1, TOP-left
/// origin — the app-wide convention shared with image regions) and PDFKit page
/// rects (bottom-left origin), given the page size (#2458).
///
/// PDFKit draws a page-coordinate `PDFAnnotation` correctly at any zoom/scroll,
/// so rendering only needs this conversion — no live view math. Kept SwiftUI/
/// PDFKit-free so it is unit-testable.
enum PDFRegionGeometry {
    /// PDF page rect (bottom-left origin) for a normalized top-left box.
    ///
    /// **The returned rect assumes a ZERO ORIGIN.** It takes a `CGSize`, so it
    /// can only flip and scale — it cannot know where the box it was measured
    /// against actually sits on the page. Callers working from a rect whose
    /// origin may be non-zero MUST re-add it:
    ///
    /// ```swift
    /// let cropBounds = page.bounds(for: .cropBox)
    /// let rect = PDFRegionGeometry.pageRect(normalized: box, pageSize: cropBounds.size)?
    ///     .offsetBy(dx: cropBounds.minX, dy: cropBounds.minY)
    /// ```
    ///
    /// That is safe to omit ONLY against the `.mediaBox`, whose origin is
    /// normally zero — which is why `applyRegions` gets away with it for
    /// user-drawn regions. It is wrong against an INSET `.cropBox`, and
    /// **scanned documents routinely have one**, so the error lands on exactly
    /// the archival material this app exists for: every box uniformly
    /// displaced, the page looking like the app cannot read it (#4418).
    ///
    /// The shipped precedent is the #2105/#3449 claim-source highlight, which
    /// re-adds `cropBounds.minX/minY` for this reason.
    static func pageRect(normalized box: [Double], pageSize: CGSize) -> CGRect? {
        guard box.count >= 4, pageSize.width > 0, pageSize.height > 0 else { return nil }
        let width = box[2] * pageSize.width
        let height = box[3] * pageSize.height
        let originX = box[0] * pageSize.width
        // Flip Y: top-left normalized → bottom-left page space.
        let originY = (1 - box[1] - box[3]) * pageSize.height
        return CGRect(x: originX, y: originY, width: width, height: height)
    }

    /// Normalized top-left box for a drag between two PDF page points
    /// (bottom-left origin), clamped to 0…1 with a positive size. `nil` for a
    /// degenerate (tap-sized) drag.
    static func normalizedBox(
        fromPagePoint start: CGPoint,
        toPagePoint end: CGPoint,
        pageSize: CGSize,
        minSpan: CGFloat = 2
    ) -> [Double]? {
        guard pageSize.width > 0, pageSize.height > 0 else { return nil }
        guard abs(end.x - start.x) >= minSpan || abs(end.y - start.y) >= minSpan else { return nil }

        func normalize(_ point: CGPoint) -> (Double, Double) {
            let normX = clamp(Double(point.x / pageSize.width))
            // Flip Y: page bottom-left → top-left normalized.
            let normY = clamp(1 - Double(point.y / pageSize.height))
            return (normX, normY)
        }
        let (startX, startY) = normalize(start)
        let (endX, endY) = normalize(end)
        let width = abs(endX - startX)
        let height = abs(endY - startY)
        guard width > 0, height > 0 else { return nil }
        return [min(startX, endX), min(startY, endY), width, height]
    }

    private static func clamp(_ value: Double) -> Double {
        min(1, max(0, value))
    }
}
