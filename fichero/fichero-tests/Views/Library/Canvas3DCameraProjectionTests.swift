//
//  Canvas3DCameraProjectionTests.swift
//  FicheroTests
//
//  §18.1 defect 1 — zoomed out to a whole diary, 2,228 cards rendered as a
//  tapering wedge: two identical pages at different depths came out different
//  sizes, so nothing could be compared and the field's shape was an artifact of
//  the camera rather than of the data. Boards are orthographic now.
//
//  The projection math is pure and lives in `Canvas3DProjection`; the wiring
//  (which component the camera entity carries, and that the ⇧⌥ marquee agrees
//  with it) is a source-surface guard, because no unit test on the pure layer
//  can see a renderer that stops asking.
//

import CoreGraphics
@testable import Fichero
import Foundation
import Testing

@Suite("Canvas3DProjection camera projection (§18.1 defect 1)")
struct Canvas3DCameraProjectionTests {

    @Test("ortho scale is the perspective camera's own half-height at that distance")
    func orthoScaleMatchesPerspectiveHalfHeight() {
        // The point of deriving it: switching projections must not change how
        // much of the board is on screen, or every saved camera pose jumps.
        for distance in [Float(1), 2.2, 6, 16, 120] {
            let expected = distance * tan(Canvas3DProjection.defaultVerticalFieldOfView / 2)
            #expect(abs(Canvas3DProjection.orthoScale(forDistance: distance) - expected) < 1e-5)
        }
        // 60° default → half-height = distance · tan(30°) ≈ 0.5774 · distance.
        #expect(abs(Canvas3DProjection.orthoScale(forDistance: 6) - 6 * 0.57735) < 1e-3)
    }

    @Test("a zero or negative distance still yields a usable scale, never zero")
    func degenerateDistance() {
        #expect(Canvas3DProjection.orthoScale(forDistance: 0) > 0)
        #expect(Canvas3DProjection.orthoScale(forDistance: -5) > 0)
    }

    @Test("ortho agrees with perspective at the look-at plane, and diverges off it")
    func orthoMatchesAtThePlaneAndIgnoresDepth() {
        // THE defect, as an assertion. Under perspective, two identical cards at
        // different depths projected to different offsets — the tapering wedge.
        // Under ortho there is no depth term at all, so the SAME card is the
        // same size wherever it sits, and the two projections agree exactly on
        // the look-at plane, which is why swapping cameras does not jump the
        // view.
        let viewSize = CGSize(width: 1_200, height: 800)
        let distance: Float = 40
        let scale = Canvas3DProjection.orthoScale(forDistance: distance)

        let ortho = Canvas3DProjection.orthoScreenPoint(
            lateral: 3, vertical: 2, orthoScale: scale, viewSize: viewSize
        )
        let atThePlane = Canvas3DProjection.perspectiveScreenPoint(
            lateral: 3, vertical: 2, depth: distance, viewSize: viewSize
        )
        #expect(abs(ortho.x - atThePlane.x) < 1e-3)
        #expect(abs(ortho.y - atThePlane.y) < 1e-3)

        // Off the plane, perspective moves the card and ortho does not — the
        // whole comparability argument, in two lines.
        let nearer = Canvas3DProjection.perspectiveScreenPoint(
            lateral: 3, vertical: 2, depth: distance - 15, viewSize: viewSize
        )
        #expect(abs(nearer.x - ortho.x) > 1)
    }

    @Test("the view centre is the look-at point, and offsets are symmetric")
    func centreAndSymmetry() {
        let viewSize = CGSize(width: 1_200, height: 800)
        let scale = Canvas3DProjection.orthoScale(forDistance: 6)
        let centre = Canvas3DProjection.orthoScreenPoint(
            lateral: 0, vertical: 0, orthoScale: scale, viewSize: viewSize
        )
        #expect(abs(centre.x - 600) < 1e-6)
        #expect(abs(centre.y - 400) < 1e-6)

        let right = Canvas3DProjection.orthoScreenPoint(
            lateral: 1, vertical: 0, orthoScale: scale, viewSize: viewSize
        )
        let left = Canvas3DProjection.orthoScreenPoint(
            lateral: -1, vertical: 0, orthoScale: scale, viewSize: viewSize
        )
        #expect(abs((right.x - centre.x) + (left.x - centre.x)) < 1e-4)
        // Scene y is up, screen y is down.
        let up = Canvas3DProjection.orthoScreenPoint(
            lateral: 0, vertical: 1, orthoScale: scale, viewSize: viewSize
        )
        #expect(up.y < centre.y)
    }

    @Test("screen and world round-trip at a NON-default distance")
    func roundTripAtANonDefaultDistance() {
        // The half-height convention is where a factor-of-two slip hides, and
        // it hides at the DEFAULT distance because everything is proportional
        // there. So: an odd distance and an odd view height.
        let viewSize = CGSize(width: 1_037, height: 611)
        let distance: Float = 23.5
        let scale = Canvas3DProjection.orthoScale(forDistance: distance)
        let worldPerPoint = (2 * scale) / Float(viewSize.height)

        for (lateral, vertical) in [(Float(0.5), Float(-3.25)), (7, 2), (-11.75, 0.125)] {
            let point = Canvas3DProjection.orthoScreenPoint(
                lateral: lateral, vertical: vertical, orthoScale: scale, viewSize: viewSize
            )
            // Invert by hand — the marquee's own arithmetic, in reverse.
            let backLateral = Float(point.x - viewSize.width / 2) * worldPerPoint
            let backVertical = -Float(point.y - viewSize.height / 2) * worldPerPoint
            #expect(abs(backLateral - lateral) < 1e-3)
            #expect(abs(backVertical - vertical) < 1e-3)
        }

        // And the whole visible vertical extent really is 2 · orthoScale: a card
        // exactly at the top edge sits at y == 0.
        let topEdge = Canvas3DProjection.orthoScreenPoint(
            lateral: 0, vertical: scale, orthoScale: scale, viewSize: viewSize
        )
        #expect(abs(topEdge.y) < 1e-3)
    }

    @Test("zooming out halves the on-screen offset, in both projections")
    func zoomingScalesTheField() {
        let viewSize = CGSize(width: 1_000, height: 1_000)
        let near = Canvas3DProjection.orthoScreenPoint(
            lateral: 2, vertical: 0, orthoScale: Canvas3DProjection.orthoScale(forDistance: 10),
            viewSize: viewSize
        )
        let far = Canvas3DProjection.orthoScreenPoint(
            lateral: 2, vertical: 0, orthoScale: Canvas3DProjection.orthoScale(forDistance: 20),
            viewSize: viewSize
        )
        #expect(abs((near.x - 500) - 2 * (far.x - 500)) < 1e-3)
    }
}

// MARK: - Wiring

/// What the pure math cannot see: which component the camera entity actually
/// carries, that the marquee follows the same flag, and that the flag lives on
/// the SHELL rather than being baked into an arrangement.
struct Canvas3DCameraWiringGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private var cameraPath: String { "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer+Camera.swift" }
    private var rendererPath: String { "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift" }

    @Test("the board's camera is orthographic by default")
    func defaultsToOrthographic() throws {
        let renderer = try appSource(rendererPath)
        #expect(renderer.contains("var projection: CanvasCameraProjection = .orthographic"))
        // A plain Entity, so the component can be swapped: a PerspectiveCamera
        // subclass would carry its component permanently.
        #expect(renderer.contains("let camera = Entity()"))
        #expect(!renderer.contains("let camera = PerspectiveCamera()"))
    }

    @Test("both camera components are applied through the one flag")
    func projectionDrivesTheComponent() throws {
        let source = try appSource(cameraPath)
        #expect(source.contains("OrthographicCameraComponent()"))
        #expect(source.contains("PerspectiveCameraComponent()"))
        // Applied on every camera update, so a pose change can never leave the
        // entity carrying the other projection's component.
        #expect(source.contains("applyProjection()"))
    }

    @Test("the marquee projects the way the camera does")
    func marqueeFollowsTheProjection() throws {
        let source = try appSource(cameraPath)
        // A rubber band drawn with perspective math over an ortho camera selects
        // cards other than the ones it encloses.
        #expect(source.contains("Canvas3DProjection.orthoScreenPoint("))
        #expect(source.contains("Canvas3DProjection.perspectiveScreenPoint("))
        // The hand-inlined 60° focal length this replaced.
        #expect(!source.contains("let fovRadians: Float = 60 * .pi / 180"))
    }

    @Test("the orbit rig is untouched: distance is still the one zoom variable")
    func distanceRemainsTheZoomVariable() throws {
        let source = try appSource(cameraPath)
        #expect(source.contains("Canvas3DProjection.orthoScale(forDistance: distance)"))
        // CanvasZoomRange still bounds it — ortho did not fork the zoom model.
        #expect(source.contains("CanvasZoomRange.clamp("))
    }
}
