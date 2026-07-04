import CoreGraphics
import Foundation
import simd

// MARK: - 2D projection of canonical world space (#3083 / #3103)

/// The ortho-2D renderer's projection of a placeable's canonical WORLD position
/// (#3103) onto its flat plane: `(x, −y)`, z ignored. Pure + unit-tested — every
/// card and connector is placed through this, so the 2D and 3D RealityKit
/// renderers agree on x/y from the SAME saved layout row.
///
/// y is negated because canonical space is y-up (the 3D convention) while the 2D
/// canvas reads y-down (larger y → lower on screen), matching the retired
/// SwiftUI `Spatial2DCanvas`.
enum Canvas2DProjection {
    /// World `(x, y, z)` → flat scene point `(x, −y, 0)`.
    static func scenePosition(_ world: SIMD3<Double>) -> SIMD3<Float> {
        SIMD3<Float>(Float(world.x), Float(-world.y), 0)
    }

    /// Inverse of the x/y projection: a flat scene point back to world `(x, y, 0)`.
    /// Used to turn a camera-plane delta / drop point into a world position.
    static func worldPosition(_ scene: SIMD3<Float>) -> SIMD3<Double> {
        SIMD3<Double>(Double(scene.x), Double(-scene.y), 0)
    }

    // MARK: - Ortho camera ↔ screen (drag + marquee, #3084)

    /// World-units per screen point at a given ortho scale and view height. The
    /// visible vertical extent is `2 · orthoScale` (the camera's full height), so
    /// `wpp = 2·orthoScale / viewHeight`. The single calibration knob shared by
    /// pan, drag, and marquee — tune once, all three follow.
    static func worldPerPoint(orthoScale: Float, viewHeight: CGFloat) -> Float {
        (2 * orthoScale) / Float(max(viewHeight, 1))
    }

    /// A screen-space drag translation → a scene-plane delta. y flips (screen
    /// down → scene −y, the y-up plane).
    static func sceneDelta(screenTranslation: CGSize, orthoScale: Float, viewHeight: CGFloat) -> SIMD3<Float> {
        let wpp = worldPerPoint(orthoScale: orthoScale, viewHeight: viewHeight)
        return SIMD3<Float>(Float(screenTranslation.width) * wpp, Float(-screenTranslation.height) * wpp, 0)
    }

    /// Project a scene-plane point to a screen point, given the camera's plane
    /// position and ortho scale — the inverse used for marquee hit-testing.
    /// (0,0) scene under a centered camera maps to the view centre.
    static func screenPoint(scene: SIMD3<Float>, cameraX: Float, cameraY: Float, orthoScale: Float, viewSize: CGSize) -> CGPoint {
        let wpp = worldPerPoint(orthoScale: orthoScale, viewHeight: viewSize.height)
        guard wpp > 0 else { return .zero }
        let deltaX = (scene.x - cameraX) / wpp
        let deltaY = (scene.y - cameraY) / wpp   // scene y-up → screen y-down below
        return CGPoint(
            x: CGFloat(Float(viewSize.width) / 2 + deltaX),
            y: CGFloat(Float(viewSize.height) / 2 - deltaY)
        )
    }
}
