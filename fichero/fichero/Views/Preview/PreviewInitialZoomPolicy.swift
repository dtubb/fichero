import CoreGraphics

// MARK: - Content Kind

/// Whether the previewed item loses fidelity when scaled past its natural size.
enum PreviewContentKind {
    /// Bitmap content — fixed pixels, so scaling past 100% only blurs it.
    case raster
    /// Resolution-independent content (PDF / vector) — scaling past 100% is lossless.
    case vector
}

// MARK: - Initial Zoom Policy

/// Preview.app's opening-zoom rule, stated once so the image and PDF surfaces
/// can't drift apart (#4279).
///
/// A preview opens at *fit-to-view*: the largest scale at which the whole item
/// is visible in the pane. Raster content is additionally capped at 100% so a
/// small image opens crisp and centred rather than blown up and soft; vector
/// content has no cap because scaling it up costs nothing.
///
/// Every function here is pure — pane size and item size in, scale out — so the
/// rule is unit-testable without an AppKit/UIKit view. The live views measure
/// the geometry and delegate the arithmetic here.
enum PreviewInitialZoomPolicy {

    /// Scale used when the geometry isn't known yet or is degenerate (zero,
    /// negative, NaN). 1.0 shows the item at its natural size — never a blank
    /// or inverted view.
    static let neutralScale: CGFloat = 1.0

    /// Largest scale a freshly-opened preview may use, or `nil` for "no cap".
    static func upperBound(for kind: PreviewContentKind) -> CGFloat? {
        switch kind {
        case .raster: return 1.0
        case .vector: return nil
        }
    }

    /// The uncapped scale at which `contentSize` fits entirely inside `paneSize`.
    ///
    /// Returns `nil` when either size is degenerate — callers use that to mean
    /// "the pane hasn't been measured yet, don't commit to a zoom".
    static func fitScale(contentSize: CGSize, paneSize: CGSize) -> CGFloat? {
        guard contentSize.width > 0, contentSize.height > 0,
              paneSize.width > 0, paneSize.height > 0,
              contentSize.width.isFinite, contentSize.height.isFinite,
              paneSize.width.isFinite, paneSize.height.isFinite else {
            return nil
        }
        // The constraining axis is whichever runs out of room first, so the
        // whole item stays visible in both directions.
        return min(paneSize.width / contentSize.width, paneSize.height / contentSize.height)
    }

    /// Apply `kind`'s cap to an already-computed fit scale (e.g. PDFKit's
    /// `scaleFactorForSizeToFit`), falling back to `neutralScale` for a
    /// nonsensical input.
    static func clamped(_ scale: CGFloat, kind: PreviewContentKind) -> CGFloat {
        guard scale.isFinite, scale > 0 else { return neutralScale }
        guard let cap = upperBound(for: kind) else { return scale }
        return min(scale, cap)
    }

    /// The zoom a preview should open at: fit-to-view, capped per `kind`.
    static func initialScale(
        contentSize: CGSize,
        paneSize: CGSize,
        kind: PreviewContentKind
    ) -> CGFloat {
        guard let fit = fitScale(contentSize: contentSize, paneSize: paneSize) else {
            return neutralScale
        }
        return clamped(fit, kind: kind)
    }
}
