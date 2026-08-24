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

    /// The contract a `.move` op carries, since moves became ANIMATED
    /// (2026-08-22, R10): **the model is immediately the truth; the view eases
    /// toward it.** `placeablesById` holds the new position the instant `apply`
    /// returns, while the entity's own transform is mid-flight — so a test that
    /// reads `entity.position` right after a move is asking the view a question
    /// only the model can answer.
    ///
    /// An INSERT is placed outright (there is nowhere to ease from), so entity
    /// position is still the right thing to assert there.
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
        #expect(renderer.placeablesById["a"]?.position == SIMD3<Double>(5, 6, 7))
        // The card is still there and still the same entity — a move must never
        // become a rebuild, animated or not.
        #expect(renderer.root.findEntity(named: "a") != nil)

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
        // Suppressed means the op is DROPPED, so neither the model nor the view
        // moves — no animation is started either.
        #expect(renderer.placeablesById["a"]?.position == SIMD3<Double>(0, 0, 0))
        #expect(renderer.root.findEntity(named: "a")?.position == SIMD3<Float>(0, 0, 0))
    }

    @Test("reportedZoomScale rises as the camera flies in (drives CanvasDetailTier)")
    func zoomScale() {
        let renderer = CanvasScene3DRenderer()
        let far = renderer.reportedZoomScale
        renderer.setDistance(CanvasScene3DRenderer.defaultDistance / 3)   // closer
        #expect(renderer.reportedZoomScale > far)
    }
}

// MARK: - Textures follow the zoom (live bug, 2026-08-23)

/// Daniel: "all cards are blue rectangles" on the 3D board, with one textured.
///
/// Cards take their page texture when they are BUILT, and only at `.thumbnail`
/// or above. A large board frames itself at the glyph tier, so every card was
/// built flat — and a reconcile that changes nothing builds nothing, so zooming
/// in never fetched them. The one textured card was one that happened to be
/// built while the tier was high.
@MainActor
struct CanvasZoomTextureCatchUpTests {

    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static func code(of source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let marker = line.range(of: "//") else { return line }
                return line[line.startIndex..<marker.lowerBound]
            }
            .joined(separator: "\n")
    }

    private func code(at relativePath: String) throws -> String {
        Self.code(of: try appSource(relativePath))
    }

    private let renderers = [
        ["Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer.swift",
         "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer+Thumbnails.swift"],
        ["Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift",
         "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer+Thumbnails.swift"],
    ]

    private func combined(_ paths: [String]) throws -> String {
        try paths.map { try code(at: $0) }.joined(separator: "\n")
    }

    @Test("a tier RISE fetches the textures the glyph tier skipped")
    func tierRiseFetchesMissingTextures() throws {
        for paths in renderers {
            let source = try combined(paths)
            #expect(source.contains("guard detailTier >= .thumbnail, oldValue < .thumbnail else { return }"),
                    "\(paths) does not act on a tier rise")
            #expect(source.contains("func loadMissingThumbnails()"))
            // Bounded by the same gate as makeCard, so a zoomed-out board still
            // issues zero requests.
            #expect(source.contains("guard !texturedIds.contains(id)"))
        }
    }

    @Test("the zoom itself moves the tier — a plain class republishes nothing")
    func zoomDrivesTheTier() throws {
        // The renderers are not @Observable, so a pinch that only changes
        // distance/scale triggers no SwiftUI update and the host's assignment
        // may never re-run. The tier follows the zoom at its source.
        #expect(try code(at: "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer+Camera.swift")
            .contains("detailTier = CanvasDetailTier.forZoomScale(reportedZoomScale)"))
        #expect(try code(at: "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer.swift")
            .contains("detailTier = CanvasDetailTier.forZoomScale(reportedZoomScale)"))
    }

    @Test("'has a texture' tracks the ENTITY, not the aspect memo")
    func texturedIsTrackedNotInferred() throws {
        // `CanvasCardGeometry.knownAspect` says a texture was measured once,
        // which stays true after a rebuild that left the new card flat — so
        // inferring from it would skip exactly the cards that need reloading.
        for paths in renderers {
            let source = try combined(paths)
            #expect(source.contains("var texturedIds: Set<String> = []"))
            #expect(source.contains("texturedIds.insert(entity.name)"))
            // A rebuilt or removed card forgets its texture.
            #expect(source.contains("texturedIds.remove(id)"))
        }
    }
}
