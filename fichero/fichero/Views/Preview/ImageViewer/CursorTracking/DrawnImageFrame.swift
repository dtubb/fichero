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
    ///
    /// `imageView.bounds` alone is NOT the drawn image (Daniel, 2026-08-21:
    /// "if I zoom out, it doesn't work"): whenever the view is larger than
    /// the image — zoomed out, or fit with slack on one axis — NSImageView
    /// letterboxes the image INSIDE its own bounds, so converting the bounds
    /// frames the overlay to the whole pane and every box scatters into the
    /// margins. Inset to the aspect-fit rect of the image within the view
    /// first; when the view is exactly image-shaped (fit and zoomed in) the
    /// inset is a no-op.
    @MainActor
    static func compute(scrollView: NSScrollView, imageView: NSView) -> CGRect? {
        var imageRect = imageView.bounds
        if let hostView = imageView as? NSImageView, let img = hostView.image {
            imageRect = aspectFitRect(of: img.size, in: imageRect)
        }
        let visible = scrollView.convert(imageRect, from: imageView)
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

    /// The centered aspect-fit rect of `size` inside `bounds` — where
    /// NSImageView (default `.alignCenter`, proportional scaling) actually
    /// draws the image. Pure, so the zoom-out mapping is unit-testable.
    static func aspectFitRect(of size: CGSize, in bounds: CGRect) -> CGRect {
        guard size.width > 0, size.height > 0,
              bounds.width > 0, bounds.height > 0 else { return bounds }
        let scale = min(bounds.width / size.width, bounds.height / size.height)
        let width = size.width * scale
        let height = size.height * scale
        return CGRect(
            x: bounds.midX - width / 2,
            y: bounds.midY - height / 2,
            width: width,
            height: height
        )
    }
}
#endif
