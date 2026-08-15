#if os(macOS)
import AppKit

/// Where the image is actually DRAWN inside a scroll view's bounds, in SwiftUI
/// top-left coordinates (2026-08-12 bbox repro): the box overlays must frame
/// to THIS rect, not the whole pane, or fit-with-letterbox renders normalized
/// geometry into the gray margins below the image.
enum DrawnImageFrame {
    /// The visible part of the image's on-screen rect. AppKit's `convert`
    /// carries magnification and nested flippedness; only the scroll view's
    /// own unflipped bounds need the final y-flip.
    @MainActor
    static func compute(scrollView: NSScrollView, imageView: NSView) -> CGRect? {
        let visible = scrollView.convert(imageView.bounds, from: imageView)
            .intersection(scrollView.bounds)
        guard !visible.isNull, visible.width > 0, visible.height > 0 else { return nil }
        let topLeftY = scrollView.isFlipped
            ? visible.minY
            : scrollView.bounds.height - visible.maxY
        return CGRect(
            x: visible.minX, y: topLeftY,
            width: visible.width, height: visible.height
        )
    }
}
#endif
