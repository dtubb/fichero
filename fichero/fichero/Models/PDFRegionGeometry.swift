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

    /// Undo a page's `/Rotate` so a DISPLAY-space normalized box can be drawn
    /// as a PDFKit annotation.
    ///
    /// Two coordinate systems meet on a rotated page and neither announces
    /// itself. The engine normalizes PDF text-layer geometry in DISPLAY space
    /// — the picture the reader is looking at, and the one every server-
    /// rendered rendition shares. PDFKit's `bounds(for:)` and every
    /// `PDFAnnotation` live in the page's UNROTATED space; `PDFView` applies
    /// the rotation itself when it draws. Handing a display-space box straight
    /// to an annotation therefore lands it ninety degrees out of true —
    /// boxes sideways across the page.
    ///
    /// Returns the box re-expressed as normalized top-left coordinates of the
    /// UNROTATED page, ready for `pageRect(normalized:pageSize:)`. `rotation`
    /// is `PDFPage.rotation` (a multiple of 90; anything else is treated as 0
    /// because PDFKit has already normalized it).
    static func unrotated(normalized box: [Double], rotation: Int) -> [Double] {
        guard box.count >= 4 else { return box }
        let boxX = box[0], boxY = box[1], boxW = box[2], boxH = box[3]
        switch ((rotation % 360) + 360) % 360 {
        case 90:
            // display (x, y) came from unrotated (y, 1 - x - w) — invert it.
            return [boxY, 1 - boxX - boxW, boxH, boxW]
        case 180:
            return [1 - boxX - boxW, 1 - boxY - boxH, boxW, boxH]
        case 270:
            return [1 - boxY - boxH, boxX, boxH, boxW]
        default:
            return box
        }
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
