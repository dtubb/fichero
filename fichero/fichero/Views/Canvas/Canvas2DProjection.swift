import CoreGraphics
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
}
