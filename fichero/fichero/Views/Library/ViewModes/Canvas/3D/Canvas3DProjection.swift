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
}
