import CoreGraphics
@testable import Fichero
import Foundation
import simd
import Testing

// The 2D canvas gesture SEMANTICS, extracted from `CanvasSceneView` so every 2D
// renderer host shares them (#4192 S1). The SwiftUI gesture plumbing cannot be
// shared — the RealityKit host picks its subject with `.targetedToAnyEntity()`
// while a SceneKit host must hit-test — so these rules are the part that would
// otherwise be copied per host and drift apart unnoticed.
//
// They were untested while they lived inline in the view. Pinning them here is
// what makes "the two renderers behave the same" checkable rather than asserted.
@Suite("Canvas2DProjection gesture semantics (#4192 S1)")
struct Canvas2DGestureMathTests {

    private let orthoScale: Float = 8
    private let viewHeight: CGFloat = 800

    /// worldPerPoint = 2 * 8 / 800 = 0.02 world units per point.
    private var worldPerPoint: Float {
        Canvas2DProjection.worldPerPoint(orthoScale: orthoScale, viewHeight: viewHeight)
    }

    @Test("a drag adds the screen translation in world units, y flipped")
    func draggedWorldFollowsTranslation() {
        let world = Canvas2DProjection.draggedWorldPosition(
            startScene: SIMD3<Float>(1, 2, 0),
            screenTranslation: CGSize(width: 100, height: 50),
            orthoScale: orthoScale,
            viewHeight: viewHeight,
            preservingZ: 0
        )
        // Screen +x → world +x; screen +y (down) → world −y (y-up plane), and
        // the scene→world inverse flips y again, so a downward drag increases y.
        #expect(abs(world.x - Double(1 + 100 * worldPerPoint)) < 0.0001)
        #expect(abs(world.y - Double(-(2 - 50 * worldPerPoint))) < 0.0001)
    }

    // #3090: one layout row, two projections. A 2D drag must never clobber the z
    // the 3D renderer wrote, or the two renderers diverge on the same row.
    @Test("a drag preserves the row's existing z untouched")
    func draggedWorldPreservesZ() {
        let world = Canvas2DProjection.draggedWorldPosition(
            startScene: SIMD3<Float>(0, 0, 0),
            screenTranslation: CGSize(width: 10, height: 10),
            orthoScale: orthoScale,
            viewHeight: viewHeight,
            preservingZ: 4.25
        )
        #expect(world.z == 4.25)
    }

    @Test("zero translation leaves the card exactly where it started")
    func draggedWorldIsIdentityForNoTranslation() {
        let world = Canvas2DProjection.draggedWorldPosition(
            startScene: SIMD3<Float>(3, -4, 0),
            screenTranslation: .zero,
            orthoScale: orthoScale,
            viewHeight: viewHeight,
            preservingZ: 1
        )
        #expect(world == SIMD3<Double>(3, 4, 1))
    }

    // The content must move WITH the finger, so the camera moves opposite. Get
    // this backwards and the canvas feels inverted — easy to mis-copy per host.
    @Test("the camera pans opposite the finger so content follows it")
    func cameraPanIsInverted() {
        let delta = Canvas2DProjection.cameraPanDelta(
            screenTranslation: CGSize(width: 100, height: 0),
            orthoScale: orthoScale,
            viewHeight: viewHeight
        )
        #expect(delta.x < 0, "dragging right pans the camera left")
        #expect(abs(delta.x + 100 * worldPerPoint) < 0.0001)
    }

    @Test("pan and drag share one calibration, so they move by the same amount")
    func panAndDragShareCalibration() {
        let translation = CGSize(width: 60, height: -30)
        let pan = Canvas2DProjection.cameraPanDelta(
            screenTranslation: translation, orthoScale: orthoScale, viewHeight: viewHeight
        )
        let dragged = Canvas2DProjection.draggedWorldPosition(
            startScene: .zero,
            screenTranslation: translation,
            orthoScale: orthoScale,
            viewHeight: viewHeight,
            preservingZ: 0
        )
        // Same magnitude in x, opposite sign — one knob drives both.
        #expect(abs(Double(-pan.x) - dragged.x) < 0.0001)
    }

    @Test("the marquee rect is normalized whichever way the drag goes")
    func marqueeRectNormalizes() {
        let downRight = Canvas2DProjection.marqueeRect(
            from: CGPoint(x: 10, y: 20), to: CGPoint(x: 110, y: 220)
        )
        let upLeft = Canvas2DProjection.marqueeRect(
            from: CGPoint(x: 110, y: 220), to: CGPoint(x: 10, y: 20)
        )
        #expect(downRight == upLeft)
        #expect(downRight == CGRect(x: 10, y: 20, width: 100, height: 200))
    }

    @Test("a zero-distance marquee is an empty rect, not a negative one")
    func marqueeRectDegenerate() {
        let rect = Canvas2DProjection.marqueeRect(from: CGPoint(x: 5, y: 5), to: CGPoint(x: 5, y: 5))
        #expect(rect.width == 0)
        #expect(rect.height == 0)
    }

    @Test("pinching out zooms in, which is a smaller ortho scale")
    func zoomInShrinksOrthoScale() {
        #expect(Canvas2DProjection.orthoScale(zoomBaseline: 8, magnification: 2) == 4)
        #expect(Canvas2DProjection.orthoScale(zoomBaseline: 8, magnification: 0.5) == 16)
        #expect(Canvas2DProjection.orthoScale(zoomBaseline: 8, magnification: 1) == 8)
    }

    // A magnification of 0 arrives from a degenerate pinch; without the clamp it
    // divides the camera to infinity and the scene vanishes.
    @Test("a degenerate magnification is clamped, never divided by zero")
    func zoomClampsDegenerateMagnification() {
        let scale = Canvas2DProjection.orthoScale(zoomBaseline: 8, magnification: 0)
        #expect(scale.isFinite)
        #expect(scale == 800)
    }
}
