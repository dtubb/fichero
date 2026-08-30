@testable import Fichero
import Foundation
import simd
import Testing

/// #4410: dragging an item in the 3D view resets its position.
///
/// One candidate was a FRAME MISMATCH. The gesture takes its origin from the
/// entity — `Canvas3DProjection.worldPosition(entity.position(relativeTo: nil))`
/// — while `CanvasInteractionController.beginDrag` takes its rollback origin
/// from the layout store row. Two sources for "where this item was", and the
/// final position is `origin + delta`. If the projection and its inverse were
/// not exact inverses, the value would be computed in one frame and written
/// into another.
///
/// These tests settle that without running the app, and are worth keeping
/// whatever the answer: a projection whose inverse is not its inverse produces
/// "it drifts a bit" reports forever, and this is the pair both canvas
/// renderers read the same saved layout row through (#3103/#3104).
struct Canvas3DProjectionRoundTripTests {

    private let positions: [SIMD3<Double>] = [
        SIMD3(0, 0, 0),
        SIMD3(1, 2, 3),
        SIMD3(-1, -2, -3),
        SIMD3(0.25, -0.25, 0.5),        // on the 0.25 snap grid
        SIMD3(-0.75, 12.5, -100),
        SIMD3(1_000, -1_000, 0)
    ]

    /// The property the frame hypothesis turns on: world → scene → world is
    /// identity. Any axis flip, scale factor or offset shows up here.
    @Test("world → scene → world is identity")
    func worldRoundTripIsIdentity() {
        for world in positions {
            let round = Canvas3DProjection.worldPosition(Canvas3DProjection.scenePosition(world))
            #expect(round.x == world.x, Comment(rawValue: "x of \(world)"))
            #expect(round.y == world.y, Comment(rawValue: "y of \(world)"))
            #expect(round.z == world.z, Comment(rawValue: "z of \(world)"))
        }
    }

    /// No axis is swapped or negated — the failure that would move an item to a
    /// mirrored position and read as "it jumped somewhere else".
    @Test("no axis is flipped or transposed")
    func axesAreNotFlippedOrTransposed() {
        let scene = Canvas3DProjection.scenePosition(SIMD3(1, 2, 3))
        #expect(scene.x == 1)
        #expect(scene.y == 2)
        #expect(scene.z == 3)
    }

    /// A drag is `origin + delta`, so the projection must be additive: moving
    /// by a delta in world space and projecting must equal projecting and then
    /// moving by the same delta. A scale factor would break this while leaving
    /// the identity test above intact for zero.
    @Test("a delta survives the projection unchanged")
    func deltasSurviveTheProjection() {
        let origin = SIMD3<Double>(2, -3, 4)
        let delta = SIMD3<Double>(0.5, 0.25, -1.5)

        let movedThenProjected = Canvas3DProjection.scenePosition(origin + delta)
        let projectedThenMoved = Canvas3DProjection.scenePosition(origin)
            + SIMD3<Float>(Float(delta.x), Float(delta.y), Float(delta.z))

        #expect(movedThenProjected == projectedThenMoved)
    }

    /// The snap grid is coarse enough to see, so it is pinned: a drop quantises
    /// to 0.25, and an item live-moved to an unsnapped position settles onto
    /// the grid. That is a visible settle of at most an eighth of a unit — NOT
    /// a reset, which is why it is recorded here rather than treated as the
    /// cause of #4410.
    @Test("the drop grid is fine enough that snapping is not a reset")
    func snapGridIsFinerThanAReset() {
        for value in [0.0, 0.1, 0.24, 1.13, -2.6] {
            let snapped = SpatialNode.snap(value)
            #expect(abs(snapped - value) <= 0.125 + 1e-9, Comment(rawValue: "\(value) → \(snapped)"))
        }
    }
}
