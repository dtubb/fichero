import CoreGraphics
import Foundation
import simd

// MARK: - 3D projection of canonical world space (#3104 / #3103)

/// The perspective-3D 'Space' renderer's projection of a placeable's canonical
/// WORLD position (#3103) into the scene: `(x, y, z)` — z is USED (the whole
/// point of 3D), unlike the 2D ortho renderer's `Canvas2DProjection` which drops
/// z. Both renderers read the SAME saved layout row; this is the second
/// projection that makes a move in 2D show up in 3D and vice-versa.
enum Canvas3DProjection {
    /// World `(x, y, z)` → scene `(x, y, z)` (identity — 3D keeps all three axes).
    static func scenePosition(_ world: SIMD3<Double>) -> SIMD3<Float> {
        SIMD3<Float>(Float(world.x), Float(world.y), Float(world.z))
    }

    /// Scene `(x, y, z)` → world `(x, y, z)`.
    static func worldPosition(_ scene: SIMD3<Float>) -> SIMD3<Double> {
        SIMD3<Double>(Double(scene.x), Double(scene.y), Double(scene.z))
    }

    // MARK: - Camera projection (§18.1 defect 1)

    /// `PerspectiveCamera`'s default vertical field of view, in radians. The
    /// manual screen projection has always assumed it; the ortho conversion
    /// below needs it for the same reason.
    static let defaultVerticalFieldOfView: Float = 60 * .pi / 180

    /// The orthographic scale that shows the SAME amount of the look-at plane a
    /// perspective camera showed from `distance` — half the visible vertical
    /// extent, which is `Canvas2DProjection`'s convention for ortho scale too
    /// (`worldPerPoint = 2 · orthoScale / viewHeight`).
    ///
    /// This is what lets the board go orthographic without touching the orbit
    /// rig: `distance` stays the single zoom variable, so `CanvasZoomRange`,
    /// the detail tiers, pinch, pan speed, `fit()` and the double-click focus
    /// all keep working unchanged — the camera merely stops foreshortening.
    static func orthoScale(
        forDistance distance: Float, verticalFieldOfView: Float = defaultVerticalFieldOfView
    ) -> Float {
        max(distance, 0.0001) * tan(verticalFieldOfView / 2)
    }

    /// A point in camera-basis coordinates → a view-space screen point, under
    /// an ORTHOGRAPHIC camera: no division by depth, so two identical pages at
    /// different depths are the same size — the whole point of defect 1, and
    /// what the ⇧⌥ marquee has to agree with or it selects the wrong cards.
    static func orthoScreenPoint(
        lateral: Float, vertical: Float, orthoScale: Float, viewSize: CGSize
    ) -> CGPoint {
        let worldPerPoint = (2 * orthoScale) / Float(max(viewSize.height, 1))
        guard worldPerPoint > 0 else { return .zero }
        return CGPoint(
            x: CGFloat(Float(viewSize.width) / 2 + lateral / worldPerPoint),
            y: CGFloat(Float(viewSize.height) / 2 - vertical / worldPerPoint)
        )
    }

    /// The same for a PERSPECTIVE camera — kept because the shell can still be
    /// put in perspective (§18.1 reserves it for panel-sequence and station
    /// shells, where depth carries the sequence and foreshortening IS the cue).
    static func perspectiveScreenPoint(
        lateral: Float, vertical: Float, depth: Float, viewSize: CGSize,
        verticalFieldOfView: Float = defaultVerticalFieldOfView
    ) -> CGPoint {
        let focal = Float(viewSize.height) / (2 * tan(verticalFieldOfView / 2))
        return CGPoint(
            x: CGFloat(Float(viewSize.width) / 2 + focal * lateral / depth),
            y: CGFloat(Float(viewSize.height) / 2 - focal * vertical / depth)
        )
    }
}
