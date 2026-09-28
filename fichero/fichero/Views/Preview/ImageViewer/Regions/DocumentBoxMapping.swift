import CoreGraphics

/// A normalized box as a rect in the IMAGE VIEW's own coordinates -- the scroll view's document
/// view (#5020, #5142).
///
/// The page's pixels are scrolled and magnified by AppKit: the image view is the `NSScrollView`'s
/// document view, and one transform (the clip view's origin and the magnification) moves it in the
/// gesture's own pass. A box drawn IN that view, at the rect this returns, is moved by the same
/// transform in the same pass, so it cannot lag the pixels or drift from them. That is the fix for
/// both defects: the overlays drawn today are SwiftUI views laid out from a geometry handed over
/// AFTER the scroll, through an async hop, and re-mapped box by box on every tick.
///
/// Pure, so the mapping is tested as arithmetic: `documentSize` is the image view's bounds (the
/// image's size in points), and the view is NOT flipped -- AppKit's y grows upward, while a
/// normalized box's y grows downward from the top of the page.
enum DocumentBoxMapping {
    /// `imageRect` is where the image sits in the image view (`DrawnImageFrame.drawnRect(in:)`):
    /// its native size, centred when the view is enlarged below fit. `normalized` is `[x, y, w, h]`,
    /// top-left origin, fractions of the page. Nil when it is not
    /// four numbers or has no area -- a zero-size placeholder (an unstated shape, an unset rect) is
    /// never drawn.
    static func rect(normalized: [Double], imageRect: CGRect) -> CGRect? {
        guard normalized.count >= 4, normalized[2] > 0, normalized[3] > 0,
              imageRect.width > 0, imageRect.height > 0 else { return nil }
        let (left, top, width, height) = (normalized[0], normalized[1], normalized[2], normalized[3])
        return CGRect(
            x: imageRect.minX + left * imageRect.width,
            y: imageRect.minY + (1 - top - height) * imageRect.height,
            width: width * imageRect.width,
            height: height * imageRect.height
        )
    }

    /// Where a document rect appears in the scroll view's clip view, top-left origin -- what a
    /// person sees -- for a clip showing `documentVisibleRect` at `magnification`. Used by the tests
    /// to prove the document path and the pointer path agree; the drawing never needs it, because
    /// AppKit applies this transform itself.
    /// A normalized `[x, y]` point (top-left origin) in the image view's document space (y grows up).
    static func point(normalized: [Double], imageRect: CGRect) -> CGPoint? {
        guard normalized.count >= 2, imageRect.width > 0, imageRect.height > 0 else { return nil }
        return CGPoint(
            x: imageRect.minX + normalized[0] * imageRect.width,
            y: imageRect.minY + (1 - normalized[1]) * imageRect.height
        )
    }

    static func onScreen(
        documentRect: CGRect, documentVisibleRect: CGRect, magnification: CGFloat
    ) -> CGRect {
        let left = (documentRect.minX - documentVisibleRect.minX) * magnification
        // Flip once, for the top-left screen space: the distance from the TOP of the visible window.
        let top = (documentVisibleRect.maxY - documentRect.maxY) * magnification
        return CGRect(x: left, y: top, width: documentRect.width * magnification,
                      height: documentRect.height * magnification)
    }
}
