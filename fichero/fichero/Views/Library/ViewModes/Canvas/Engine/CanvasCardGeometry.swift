import Foundation
#if canImport(RealityKit)
import RealityKit
#endif

/// Card geometry for page-image nodes across ALL canvas renderers (#4193):
/// the legacy 3D scene (`SpaceSceneView`), the engine 3D renderer
/// (`CanvasScene3DRenderer`), and the 2D ortho renderer
/// (`CanvasOrtho2DRenderer`) each built every source card at one fixed
/// aspect, so page images were squeezed into that shape regardless of the
/// page's true proportions.
///
/// Two rules, shared so the renderers can't drift apart:
/// 1. **Normalize on AREA, not width** — every card covers the same area
///    whatever its aspect, so a wide double-spread and a tall page carry
///    equal visual weight and the board stays even.
/// 2. **Fall back to the renderer's existing ratio until a texture loads**,
///    then memoize the loaded aspect — cards never jump shape mid-load, and
///    synchronous rebuilds (selection reskins, scene diffs) keep a card's
///    true shape instead of snapping back to the fallback.
@MainActor
enum CanvasCardGeometry {
    /// sourceId → texture aspect (width / height), memoized on first load.
    /// ponytail: keyed by sourceId only — the same id open in two libraries
    /// could collide, worst case a wrong-but-plausible card shape; key by
    /// library scope (like SpaceTextureCache) if that ever bites.
    private static var knownAspects: [String: Float] = [:]

    static func knownAspect(forSourceId sourceId: String) -> Float? {
        knownAspects[sourceId]
    }

    #if canImport(RealityKit)
    /// Memoize the aspect of a loaded page texture. Returns true when this
    /// CHANGES what's stored — the caller reskins the card exactly once and
    /// the reskin's own texture reload (cache hit) records no change, so the
    /// rebuild cycle terminates.
    @discardableResult
    static func recordAspect(of texture: TextureResource, forSourceId sourceId: String) -> Bool {
        recordAspect(Float(texture.width) / Float(texture.height), forSourceId: sourceId)
    }
    #endif

    /// Testable core of `recordAspect(of:forSourceId:)`.
    @discardableResult
    static func recordAspect(_ aspect: Float, forSourceId sourceId: String) -> Bool {
        guard aspect.isFinite, aspect > 0, knownAspects[sourceId] != aspect else { return false }
        knownAspects[sourceId] = aspect
        return true
    }

    /// Area-preserving dimensions for a card: `width * height == area` in
    /// every case, with `width / height == aspect` (or `fallback` when the
    /// aspect is unknown or degenerate).
    nonisolated static func dimensions(
        area: Float, aspect rawAspect: Float?, fallback: Float
    ) -> (width: Float, height: Float) {
        let aspect: Float = {
            guard let rawAspect, rawAspect.isFinite, rawAspect > 0 else { return fallback }
            return rawAspect
        }()
        let width = (area * aspect).squareRoot()
        return (width, width / aspect)
    }
}
