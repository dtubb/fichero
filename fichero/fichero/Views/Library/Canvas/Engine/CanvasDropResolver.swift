import Foundation
import simd

// MARK: - Drop-target resolution (#3086)

/// Finds the placeable a dragged item was dropped ONTO, by world-space proximity
/// — renderer-agnostic (both the 2D ortho and 3D perspective renderers know
/// every placeable's canonical world position, so the SAME resolver works for
/// both, unlike a per-engine screen raycast). Pure + unit-tested; the renderers
/// call it with their live placeable positions and feed the result to
/// `DropOutcome.classify`.
enum CanvasDropResolver {
    /// World-distance within which a drop counts as "onto" a target — roughly a
    /// card's own extent, so you must release over the target, not merely near it.
    static let defaultThreshold = 0.6

    /// The nearest placeable to `world`, excluding `excluding` (the dragged item
    /// never targets itself), within `threshold`. `nil` when the drop is over
    /// empty space → a plain place.
    static func nearestId(
        to world: SIMD3<Double>,
        among placeables: [(id: String, position: SIMD3<Double>)],
        excluding: String,
        within threshold: Double = defaultThreshold
    ) -> String? {
        var best: (id: String, distance: Double)?
        for placeable in placeables where placeable.id != excluding {
            let distance = simd_distance(placeable.position, world)
            guard distance <= threshold else { continue }
            if best == nil || distance < best!.distance {
                best = (placeable.id, distance)
            }
        }
        return best?.id
    }
}
