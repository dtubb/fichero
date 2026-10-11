import CoreGraphics
import simd

/// Where the canvas camera looks when a board opens: every card in view, by the cards' own extents (Daniel,
/// 2026-10-11: a folder of 92 pages showed nothing but two stray dots). Pure, so 1, 12 and 92 cards are tested
/// without a screen. The ortho scale is HALF the visible height, as RealityKit's orthographic camera has it.
enum CanvasCameraFit {
    struct Card: Equatable {
        let center: SIMD2<Float>
        let size: SIMD2<Float>
    }

    struct Pose: Equatable {
        let center: SIMD2<Float>
        let orthoScale: Float
    }

    /// The pose that frames every card with `margin` around them, for a viewport of this shape; nil with no cards.
    static func fit(_ cards: [Card], viewport: CGSize, margin: Float) -> Pose? {
        guard let bounds = bounds(of: cards) else { return nil }
        let aspect = aspect(of: viewport)
        let spanX = bounds.max.x - bounds.min.x + 2 * margin
        let spanY = bounds.max.y - bounds.min.y + 2 * margin
        // Frame whichever axis is tighter for this pane's shape, so a narrow pane shows every column.
        return Pose(center: (bounds.min + bounds.max) / 2, orthoScale: max(spanY / 2, spanX / 2 / aspect))
    }

    /// Whether a camera shows the board: some card is in view, and the cards are not lost as specks (the board
    /// fills at least a tenth of the view's height or width). A remembered camera that fails this is replaced by
    /// the fit: a board that changed since, or a camera saved in a different pane, showed only stray dots.
    static func shows(_ pose: Pose, _ cards: [Card], viewport: CGSize) -> Bool {
        guard let bounds = bounds(of: cards), pose.orthoScale > 0 else { return false }
        let halfHeight = pose.orthoScale
        let halfWidth = pose.orthoScale * aspect(of: viewport)
        let viewMin = pose.center - SIMD2(halfWidth, halfHeight)
        let viewMax = pose.center + SIMD2(halfWidth, halfHeight)
        let overlaps = bounds.min.x < viewMax.x && bounds.max.x > viewMin.x
            && bounds.min.y < viewMax.y && bounds.max.y > viewMin.y
        let boardFraction = max((bounds.max.y - bounds.min.y) / (2 * halfHeight),
                                (bounds.max.x - bounds.min.x) / (2 * halfWidth))
        return overlaps && boardFraction >= 0.1
    }

    private static func bounds(of cards: [Card]) -> (min: SIMD2<Float>, max: SIMD2<Float>)? {
        guard let first = cards.first else { return nil }
        return cards.dropFirst().reduce((first.center - first.size / 2, first.center + first.size / 2)) { acc, card in
            (simd_min(acc.0, card.center - card.size / 2), simd_max(acc.1, card.center + card.size / 2))
        }
    }

    private static func aspect(of viewport: CGSize) -> Float {
        viewport.height > 0 && viewport.width > 0 ? max(Float(viewport.width / viewport.height), 0.1) : 1
    }
}
