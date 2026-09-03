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
        let imageRect = drawnRect(in: imageView)
        // The CLIP VIEW, not `scrollView.bounds` (Daniel, 2026-09-03:
        // "marquee still offset down and to the right … disconnected from
        // the mouse"). With legacy scrollers — the system's "Show scroll
        // bars: Always", which overrides `scrollerStyle` — the clip view is
        // the scroll view minus ~17pt of gutter on the right and bottom.
        // `updateVisibleRect` already derives the normalized window from
        // `documentVisibleRect`, which IS clipped to the clip view; framing
        // the overlay to the wider `bounds` stretched that window across an
        // extra 17pt on each axis. Not a constant offset but a ~2% SCALE
        // error, so the band ran away from the pointer the further it got
        // from the top-left corner — measured +2pt at 100pt out, +15pt at
        // 700pt out. Both halves must name the same viewport.
        let viewport = scrollView.convert(scrollView.contentView.bounds, from: scrollView.contentView)
        let visible = scrollView.convert(imageRect, from: imageView)
            .intersection(viewport)
        guard !visible.isNull, visible.width > 0, visible.height > 0 else { return nil }
        let topLeftY = scrollView.isFlipped
            ? visible.minY
            : scrollView.bounds.height - visible.maxY
        return CGRect(
            x: visible.minX, y: topLeftY,
            width: visible.width, height: visible.height
        )
    }

    /// Where the image lands inside `imageView`'s OWN bounds — the one rule
    /// both halves of the pointer round-trip must use. The overlay maps
    /// normalized boxes out through it; `ImageWithCursorTracking` maps mouse
    /// points in through it. It lived in two places until 2026-09-03, and a
    /// second copy of a coordinate rule is a second chance to disagree.
    @MainActor
    static func drawnRect(in imageView: NSView) -> CGRect {
        guard let hostView = imageView as? NSImageView, let img = hostView.image else {
            return imageView.bounds
        }
        // The preview's image view uses `.scaleNone`: the image is drawn
        // at its NATIVE size, centred in the (letterbox-expanded) bounds
        // — never fitted to them. Aspect-fitting here inflated the frame
        // whenever the view was slack on BOTH axes (zoomed out past fit),
        // so every box grew with it and spilled off the page (Daniel,
        // 2026-09-01: "text regions don't update" at 47%). Proportional
        // scaling modes keep the fit maths.
        return hostView.imageScaling == .scaleNone
            ? centeredNativeRect(of: img.size, in: imageView.bounds)
            : aspectFitRect(of: img.size, in: imageView.bounds)
    }

    /// Where `.scaleNone` + `.alignCenter` draws the image: native size,
    /// centred; when the bounds are SMALLER than the image (zoomed in, the
    /// frame equals the image) the rect is the bounds themselves.
    static func centeredNativeRect(of size: CGSize, in bounds: CGRect) -> CGRect {
        guard size.width > 0, size.height > 0,
              bounds.width > 0, bounds.height > 0 else { return bounds }
        let width = min(size.width, bounds.width)
        let height = min(size.height, bounds.height)
        return CGRect(
            x: bounds.midX - width / 2,
            y: bounds.midY - height / 2,
            width: width,
            height: height
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
