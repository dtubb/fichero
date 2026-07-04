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
}
