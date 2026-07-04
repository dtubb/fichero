//
//  CanvasSceneContractTests.swift
//  FicheroTests
//
//  Pure unit tests for the renderer-agnostic canvas contract (#3103): position
//  resolution, the diff/reconcile model, drop classification, and the LOD tier.
//  No renderer, no network.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import Testing

// MARK: - Helpers

private func node(_ id: String, x: Double = 0, y: Double = 0, z: Double = 0, label: String = "N") -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: label, positionX: x, positionY: y, positionZ: z)
}

private func item(_ id: String, kind: String = "note", text: String? = nil, source: String? = nil, target: String? = nil) throws -> CanvasItemDisplay {
    var payload: [String: Any] = ["id": id, "folderId": "scope", "kind": kind]
    if let text { payload["text"] = text }
    if let source { payload["sourceItemId"] = source }
    if let target { payload["targetItemId"] = target }
    let data = try JSONSerialization.data(withJSONObject: payload)
    return try JSONDecoder().decode(CanvasItemDisplay.self, from: data)
}

// MARK: - Position resolution

@Suite("CanvasSceneState.resolve (#3103)")
struct CanvasResolveTests {

    @Test("a saved row wins over the node's backend default, z passes through")
    func rowWins() {
        let state = CanvasSceneState.resolve(
            nodes: [node("n1", x: 1, y: 2, z: 3)],
            connections: [], links: [],
            layoutRows: [CanvasItemLayout(itemId: "n1", x: 10, y: 20, z: 30)],
            items: []
        )
        #expect(state.placeables.first?.position == SIMD3<Double>(10, 20, 30))
    }

    @Test("a node without a row falls back to its backend position")
    func nodeDefault() {
        let state = CanvasSceneState.resolve(
            nodes: [node("n1", x: 1, y: 2, z: 3)],
            connections: [], links: [], layoutRows: [], items: []
        )
        #expect(state.placeables.first?.position == SIMD3<Double>(1, 2, 3))
    }

    @Test("row-less items take the deterministic 3-column cascade")
    func itemCascade() throws {
        let state = CanvasSceneState.resolve(
            nodes: [], connections: [], links: [], layoutRows: [],
            items: [try item("i0"), try item("i1"), try item("i2"), try item("i3")]
        )
        let positions = state.placeables.map(\.position)
        #expect(positions[0] == CanvasSceneState.cascadePosition(0))   // (0, 0, 0)
        #expect(positions[1] == SIMD3<Double>(0.6, 0, 0))
        #expect(positions[3] == SIMD3<Double>(0, -0.6, 0))             // wraps to row 2
    }

    @Test("a link item becomes an edge, not a placeable")
    func linkItemIsEdge() throws {
        let state = CanvasSceneState.resolve(
            nodes: [], connections: [], links: [],
            layoutRows: [], items: [try item("l", kind: "link", source: "a", target: "b")]
        )
        #expect(state.placeables.isEmpty)
        #expect(state.edges == [CanvasEdge(id: "l", sourceId: "a", targetId: "b", style: .userLink)])
    }

    @Test("a typed link becomes a connection edge")
    func typedLinkEdge() {
        let link = SpatialLink(sourceId: "a", targetId: "b", linkType: .citation)
        let state = CanvasSceneState.resolve(
            nodes: [], connections: [], links: [link], layoutRows: [], items: []
        )
        #expect(state.edges == [CanvasEdge(id: link.id, sourceId: "a", targetId: "b", style: .connection(.citation))])
    }

    @Test("a row's w/h becomes the placeable size")
    func rowSize() {
        let row = CanvasItemLayout(itemId: "n1", x: 0, y: 0, w: 120, h: 80)
        let state = CanvasSceneState.resolve(
            nodes: [node("n1")], connections: [], links: [], layoutRows: [row], items: []
        )
        #expect(state.placeables.first?.size == CGSize(width: 120, height: 80))
    }
}

// MARK: - Diff

@Suite("CanvasSceneDiff.compute (#3103)")
struct CanvasDiffTests {

    private func placeable(_ id: String, at position: SIMD3<Double>, size: CGSize? = nil) -> CanvasPlaceable {
        CanvasPlaceable(id: id, content: .node(node(id)), position: position, size: size, zIndex: 0)
    }

    @Test("equal states diff to nothing")
    func noOp() {
        let state = CanvasSceneState(placeables: [placeable("a", at: .zero)], edges: [], selection: [])
        #expect(CanvasSceneDiff.compute(from: state, to: state).isEmpty)
    }

    @Test("a new placeable is a single insert; a gone one a single remove")
    func insertAndRemove() {
        let a = placeable("a", at: .zero)
        let b = placeable("b", at: .zero)
        let insert = CanvasSceneDiff.compute(
            from: CanvasSceneState(placeables: [a], edges: [], selection: []),
            to: CanvasSceneState(placeables: [a, b], edges: [], selection: [])
        )
        #expect(insert == [.insert(b)])
        let remove = CanvasSceneDiff.compute(
            from: CanvasSceneState(placeables: [a, b], edges: [], selection: []),
            to: CanvasSceneState(placeables: [a], edges: [], selection: [])
        )
        #expect(remove == [.remove(id: "b")])
    }

    @Test("a moved placeable emits only .move; siblings stay untouched")
    func moveOnly() {
        let a = placeable("a", at: .zero)
        let b = placeable("b", at: SIMD3<Double>(1, 1, 1))
        let bMoved = placeable("b", at: SIMD3<Double>(2, 2, 2))
        let ops = CanvasSceneDiff.compute(
            from: CanvasSceneState(placeables: [a, b], edges: [], selection: []),
            to: CanvasSceneState(placeables: [a, bMoved], edges: [], selection: [])
        )
        #expect(ops == [.move(id: "b", position: SIMD3<Double>(2, 2, 2))])
    }

    @Test("a resized placeable emits .resize")
    func resize() {
        let before = placeable("a", at: .zero, size: CGSize(width: 10, height: 10))
        let after = placeable("a", at: .zero, size: CGSize(width: 20, height: 30))
        let ops = CanvasSceneDiff.compute(
            from: CanvasSceneState(placeables: [before], edges: [], selection: []),
            to: CanvasSceneState(placeables: [after], edges: [], selection: [])
        )
        #expect(ops == [.resize(id: "a", size: CGSize(width: 20, height: 30))])
    }

    @Test("changed item text emits .updateContent, not .move")
    func contentChange() throws {
        let before = CanvasPlaceable(id: "i", content: .item(try item("i", text: "old")), position: .zero, size: nil, zIndex: 0)
        let after = CanvasPlaceable(id: "i", content: .item(try item("i", text: "new")), position: .zero, size: nil, zIndex: 0)
        let ops = CanvasSceneDiff.compute(
            from: CanvasSceneState(placeables: [before], edges: [], selection: []),
            to: CanvasSceneState(placeables: [after], edges: [], selection: [])
        )
        #expect(ops == [.updateContent(id: "i")])
    }

    @Test("changed edges and selection emit wholesale ops")
    func edgesAndSelection() {
        let edge = CanvasEdge(id: "e", sourceId: "a", targetId: "b", style: .userLink)
        let ops = CanvasSceneDiff.compute(
            from: CanvasSceneState(placeables: [], edges: [], selection: []),
            to: CanvasSceneState(placeables: [], edges: [edge], selection: ["a"])
        )
        #expect(ops.contains(.setEdges([edge])))
        #expect(ops.contains(.setSelection(["a"])))
    }
}

// MARK: - Drop classification

@Suite("DropOutcome.classify (#3103 / #3086)")
struct CanvasDropTests {
    private let pos = SIMD3<Double>(1, 2, 3)

    @Test("drop on a container moves into it")
    func container() {
        let outcome = DropOutcome.classify(
            draggedId: "a", target: CanvasDropTarget(id: "c", kind: .container), position: pos, modifiers: []
        )
        #expect(outcome == .moveInto(containerId: "c"))
    }

    @Test("drop on a leaf links to it")
    func leaf() {
        let outcome = DropOutcome.classify(
            draggedId: "a", target: CanvasDropTarget(id: "b", kind: .leaf), position: pos, modifiers: []
        )
        #expect(outcome == .link(targetId: "b"))
    }

    @Test("⌥ forces a link even over a container")
    func optionForcesLink() {
        let outcome = DropOutcome.classify(
            draggedId: "a", target: CanvasDropTarget(id: "c", kind: .container), position: pos, modifiers: .forceLink
        )
        #expect(outcome == .link(targetId: "c"))
    }

    @Test("no target, or self-drop, is a plain place")
    func placeCases() {
        #expect(DropOutcome.classify(draggedId: "a", target: nil, position: pos, modifiers: []) == .place(position: pos))
        #expect(
            DropOutcome.classify(
                draggedId: "a", target: CanvasDropTarget(id: "a", kind: .leaf), position: pos, modifiers: []
            ) == .place(position: pos)
        )
    }

    @Test("Esc cancels, beating any target")
    func cancel() {
        let outcome = DropOutcome.classify(
            draggedId: "a", target: CanvasDropTarget(id: "c", kind: .container), position: pos, modifiers: .cancel
        )
        #expect(outcome == .cancel)
    }
}

// MARK: - Detail tier

@Suite("CanvasDetailTier (#3103)")
struct CanvasDetailTierTests {
    @Test("zoom scale maps to the right tier, at and across thresholds")
    func tiers() {
        #expect(CanvasDetailTier.forZoomScale(0.3) == .glyph)
        #expect(CanvasDetailTier.forZoomScale(0.6) == .thumbnail)   // threshold is inclusive of thumbnail
        #expect(CanvasDetailTier.forZoomScale(1.0) == .thumbnail)
        #expect(CanvasDetailTier.forZoomScale(2.0) == .fullTexture)
        #expect(CanvasDetailTier.forZoomScale(5.0) == .fullTexture)
    }

    @Test("tiers order glyph < thumbnail < fullTexture")
    func ordering() {
        #expect(CanvasDetailTier.glyph < .thumbnail)
        #expect(CanvasDetailTier.thumbnail < .fullTexture)
    }
}
