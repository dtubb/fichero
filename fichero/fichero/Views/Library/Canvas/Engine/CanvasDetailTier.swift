import Foundation

// MARK: - Shared level-of-detail rule (#3103, #2298 lineage)

/// How much of a card to draw at the renderer's current zoom — the shared rule
/// for smooth zoom-into-images across both renderers. The renderer reports its
/// zoom scale; this maps it to a tier. Thumbnails are fetched ONLY at
/// `.thumbnail` or above, and ONLY via `storageService.thumbnailData(for:)`
/// (never raw URLSession) — so a zoomed-out overview of thousands of nodes
/// issues zero image requests.
enum CanvasDetailTier: Equatable, Comparable {
    /// Zoomed out — cheap kind glyph, no image fetch.
    case glyph
    /// Mid zoom — the page thumbnail.
    case thumbnail
    /// Zoomed in far enough to read — the full-resolution texture.
    case fullTexture

    private var order: Int {
        switch self {
        case .glyph: 0
        case .thumbnail: 1
        case .fullTexture: 2
        }
    }

    static func < (lhs: CanvasDetailTier, rhs: CanvasDetailTier) -> Bool {
        lhs.order < rhs.order
    }

    /// Below this zoom the card is a glyph and issues no thumbnail request —
    /// the #2298 `thumbnailZoomThreshold`.
    static let thumbnailThreshold = 0.6
    /// At/above this zoom the card swaps the thumbnail for the full texture, so
    /// deep-zoom into a page stays crisp.
    static let fullTextureThreshold = 2.0

    /// The tier for a renderer-reported zoom `scale` (1.0 = fit).
    static func forZoomScale(_ scale: Double) -> CanvasDetailTier {
        if scale < thumbnailThreshold { return .glyph }
        if scale < fullTextureThreshold { return .thumbnail }
        return .fullTexture
    }
}
