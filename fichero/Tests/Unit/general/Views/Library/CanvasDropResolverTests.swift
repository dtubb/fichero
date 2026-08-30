//
//  CanvasDropResolverTests.swift
//  FicheroTests
//
//  Drag-onto target resolution (#3086): the pure world-proximity resolver both
//  renderers use, and the doc-node-id → document-id mapping that reaches
//  document.move. DropOutcome.classify itself is already tested in #3103.
//

@testable import Fichero
import Foundation
import simd
import Testing

@Suite("CanvasDropResolver (#3086)")
struct CanvasDropResolverTests {
    private let placeables: [(id: String, position: SIMD3<Double>)] = [
        (id: "a", position: SIMD3<Double>(0, 0, 0)),
        (id: "b", position: SIMD3<Double>(1, 0, 0)),
        (id: "c", position: SIMD3<Double>(10, 0, 0))
    ]

    @Test("resolves the nearest placeable within the threshold")
    func nearest() {
        #expect(CanvasDropResolver.nearestId(to: SIMD3<Double>(1.1, 0, 0), among: placeables, excluding: "a") == "b")
    }

    @Test("never targets the dragged id itself")
    func excludesSelf() {
        // Dropped right on 'a', but 'a' is the dragged id → 'b' is 1.0 away (> 0.6) → nil.
        #expect(CanvasDropResolver.nearestId(to: SIMD3<Double>(0, 0, 0), among: placeables, excluding: "a") == nil)
    }

    @Test("empty space (beyond threshold) resolves to nil → a plain place")
    func emptySpace() {
        #expect(CanvasDropResolver.nearestId(to: SIMD3<Double>(5, 0, 0), among: placeables, excluding: "z") == nil)
    }

    @Test("documentId strips the doc: prefix; nil for entity / canvas-item ids")
    func documentIdMapping() {
        #expect(SpatialLibraryProjector.documentId(fromNodeId: "doc:abc-123") == "abc-123")
        #expect(SpatialLibraryProjector.documentId(fromNodeId: "entity:x") == nil)
        #expect(SpatialLibraryProjector.documentId(fromNodeId: "note-1") == nil)
    }
}
