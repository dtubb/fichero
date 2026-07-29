//
//  CanvasScene3DTests.swift
//  FicheroTests
//
//  Tests for the perspective-3D renderer (#3104): the xyz projection (z kept,
//  unlike 2D) and the granular ops-application entity graph (no GPU needed —
//  RealityKit scene-graph mutations are plain data).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import Testing

private func node(_ id: String) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: id, positionX: 0, positionY: 0, positionZ: 0)
}

private func placeable(_ id: String, at position: SIMD3<Double>) -> CanvasPlaceable {
    CanvasPlaceable(id: id, content: .node(node(id)), position: position, size: nil, zIndex: 0)
}

@Suite("Canvas3DProjection (#3104)")
struct Canvas3DProjectionTests {
    @Test("world (x, y, z) projects to scene (x, y, z) — z is USED, unlike 2D")
    func keepsZ() {
        #expect(Canvas3DProjection.scenePosition(SIMD3<Double>(1, 2, 3)) == SIMD3<Float>(1, 2, 3))
        #expect(Canvas3DProjection.worldPosition(SIMD3<Float>(4, 5, 6)) == SIMD3<Double>(4, 5, 6))
    }
}

@MainActor
@Suite("CanvasScene3DRenderer ops (#3104)")
struct CanvasScene3DRendererTests {

    @Test("insert / move / remove yields the expected entity graph and xyz positions")
    func opsSequence() {
        let renderer = CanvasScene3DRenderer()
        renderer.apply([
            .insert(placeable("a", at: SIMD3<Double>(1, 2, 3))),
            .insert(placeable("b", at: .zero))
        ])
        #expect(renderer.root.findEntity(named: "a")?.position == SIMD3<Float>(1, 2, 3))   // z kept
        #expect(renderer.root.findEntity(named: "b") != nil)

        renderer.apply([.move(id: "a", position: SIMD3<Double>(5, 6, 7))])
        #expect(renderer.root.findEntity(named: "a")?.position == SIMD3<Float>(5, 6, 7))

        renderer.apply([.remove(id: "b")])
        #expect(renderer.root.findEntity(named: "b") == nil)
        #expect(renderer.root.findEntity(named: "a") != nil)
    }

    @Test("a store move for the id being dragged is suppressed (doesn't fight the gesture)")
    func midDragSuppression() {
        let renderer = CanvasScene3DRenderer()
        renderer.apply([.insert(placeable("a", at: .zero))])
        renderer.isDragSuppressed = { $0 == "a" }

        renderer.apply([.move(id: "a", position: SIMD3<Double>(9, 9, 9))])
        #expect(renderer.root.findEntity(named: "a")?.position == SIMD3<Float>(0, 0, 0))   // unmoved
    }

    @Test("reportedZoomScale rises as the camera flies in (drives CanvasDetailTier)")
    func zoomScale() {
        let renderer = CanvasScene3DRenderer()
        let far = renderer.reportedZoomScale
        renderer.setDistance(CanvasScene3DRenderer.defaultDistance / 3)   // closer
        #expect(renderer.reportedZoomScale > far)
    }
}
