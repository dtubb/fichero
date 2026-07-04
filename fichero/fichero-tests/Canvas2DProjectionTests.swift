//
//  Canvas2DProjectionTests.swift
//  FicheroTests
//
//  Unit tests for the ortho-2D renderer's pure projection (#3083): canonical
//  world space → flat scene point, and its inverse.
//

@testable import Fichero
import Foundation
import simd
import Testing

@Suite("Canvas2DProjection (#3083)")
struct Canvas2DProjectionTests {

    @Test("world (x, y, z) projects to the flat (x, −y, 0), z dropped")
    func projectsFlat() {
        #expect(Canvas2DProjection.scenePosition(SIMD3<Double>(1, 2, 3)) == SIMD3<Float>(1, -2, 0))
        #expect(Canvas2DProjection.scenePosition(SIMD3<Double>(-4, -5, 9)) == SIMD3<Float>(-4, 5, 0))
        #expect(Canvas2DProjection.scenePosition(.zero) == SIMD3<Float>(0, 0, 0))
    }

    @Test("worldPosition inverts the x/y projection (z is 0 on the plane)")
    func invertsXY() {
        let world = SIMD3<Double>(3, -7, 0)
        #expect(Canvas2DProjection.worldPosition(Canvas2DProjection.scenePosition(world)) == world)
    }

    // MARK: - Camera ↔ screen (#3084)

    @Test("worldPerPoint = 2·orthoScale / viewHeight")
    func worldPerPoint() {
        #expect(Canvas2DProjection.worldPerPoint(orthoScale: 8, viewHeight: 600) == Float(16) / 600)
    }

    @Test("sceneDelta scales the screen translation and flips y")
    func sceneDelta() {
        let wpp = Canvas2DProjection.worldPerPoint(orthoScale: 8, viewHeight: 600)
        let delta = Canvas2DProjection.sceneDelta(
            screenTranslation: CGSize(width: 30, height: -15), orthoScale: 8, viewHeight: 600
        )
        #expect(abs(delta.x - 30 * wpp) < 1e-5)
        #expect(abs(delta.y - 15 * wpp) < 1e-5)   // screen up (−15) → scene +y
    }

    @Test("screenPoint centers a card under a centered camera and offsets correctly")
    func screenPoint() {
        let wpp = Canvas2DProjection.worldPerPoint(orthoScale: 8, viewHeight: 600)
        let size = CGSize(width: 800, height: 600)
        // Camera at origin, card at scene origin → view centre.
        let centre = Canvas2DProjection.screenPoint(scene: .zero, cameraX: 0, cameraY: 0, orthoScale: 8, viewSize: size)
        #expect(abs(centre.x - 400) < 1e-3)
        #expect(abs(centre.y - 300) < 1e-3)
        // 10 points right, 5 up in scene → right + up (screen y smaller) on screen.
        let offset = Canvas2DProjection.screenPoint(
            scene: SIMD3<Float>(10 * wpp, 5 * wpp, 0), cameraX: 0, cameraY: 0, orthoScale: 8, viewSize: size
        )
        #expect(abs(offset.x - 410) < 1e-3)
        #expect(abs(offset.y - 295) < 1e-3)
    }
}
