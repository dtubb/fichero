//
//  CanvasDragFollowsPointerTests.swift
//  FicheroTests
//
//  #5629 follow-up (`library.canvas.a-drag-follows-the-pointer`), maintainer 2026-10-09: dragging
//  works but trails the pointer. A drag must be per-card work only: the dragged card's entity
//  moves, its handles move with it, and nothing is rebuilt, re-resolved or saved until the drop.
//
//  Why it lagged: every mouse event rebuilt the selection handles (new meshes) and the selection
//  plates, searched the whole scene for the card by name, built an array of every card to find a
//  drop target, and wrote the marquee's gesture state, which re-ran the canvas view's body and so
//  re-resolved the whole board.
//

import CoreGraphics
@testable import Fichero
import Foundation
import RealityKit
import simd
import Testing

@MainActor
@Suite("Canvas: a drag follows the pointer (#5629)")
struct CanvasDragFollowsPointerTests {

    private func board(selecting selection: Set<String>) -> (CanvasOrtho2DRenderer, CanvasSceneState) {
        let nodes = (0..<3).map {
            SpatialNode(id: "doc:\($0)", roomId: "room", nodeType: .source, label: "\($0)", positionX: 0, positionY: 0)
        }
        var state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [], defaultPlacement: .grid(columns: 3)
        )
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = CGSize(width: 900, height: 600)
        renderer.needsFitOnNextContent = true
        renderer.reconcile(to: state)
        state.selection = selection
        renderer.reconcile(to: state)
        return (renderer, state)
    }

    private func handles(_ renderer: CanvasOrtho2DRenderer) -> [Entity] {
        var found: [Entity] = []
        func walk(_ entity: Entity) {
            if CanvasSelectionFrame.handle(fromEntityName: entity.name) != nil { found.append(entity) }
            entity.children.forEach(walk)
        }
        walk(renderer.decorator.root)
        return found
    }

    // WHY: the lag itself. The handles were rebuilt on every mouse event; now the SAME entities
    // move with the card, so a drag builds no mesh.
    @Test("dragging a selected card moves its handles with it and rebuilds none")
    func handlesMoveNotRebuild() throws {
        let (renderer, _) = board(selecting: ["doc:0"])
        let before = handles(renderer)
        #expect(!before.isEmpty, "a single selected card shows its handles")
        let cornerBefore = try #require(before.first).position(relativeTo: nil)
        let start = try #require(renderer.worldPosition(of: "doc:0"))

        renderer.liveMove(id: "doc:0", toWorld: start + SIMD3<Double>(2, 1, 0))

        let after = handles(renderer)
        #expect(after.map(ObjectIdentifier.init) == before.map(ObjectIdentifier.init), "the handles were rebuilt")
        let cornerAfter = try #require(after.first).position(relativeTo: nil)
        // World +x is scene +x; world +y is scene −y.
        #expect(abs((cornerAfter.x - cornerBefore.x) - 2) < 0.0001)
        #expect(abs((cornerAfter.y - cornerBefore.y) + 1) < 0.0001)
    }

    // WHY: the move is visual only until the drop: nothing the board resolves from changes.
    @Test("a live move changes the card's entity, not the board's model")
    func liveMoveTouchesOnlyTheEntity() throws {
        let (renderer, _) = board(selecting: [])
        let start = try #require(renderer.worldPosition(of: "doc:1"))
        renderer.liveMove(id: "doc:1", toWorld: start + SIMD3<Double>(3, 0, 0))
        #expect(renderer.worldPosition(of: "doc:1") == start)
        let entity = try #require(renderer.cardEntity("doc:1"))
        #expect(abs(entity.position.x - (Float(start.x) + 3)) < 0.0001)
    }

    // WHY: the card index must follow a card rebuilt for its page texture, or the drag would move a
    // card that is no longer on screen.
    @Test("the card index follows a rebuilt card")
    func indexFollowsRebuild() throws {
        let (renderer, _) = board(selecting: [])
        let old = try #require(renderer.cardEntity("doc:2"))
        renderer.reskinCard("doc:2")
        let rebuilt = try #require(renderer.cardEntity("doc:2"))
        #expect(old !== rebuilt)
        #expect(rebuilt.parent != nil)
    }

    // WHY: a redraw of the selection after the drop puts the handles back on the cards' model
    // positions, so a drag's offset never outlives it.
    @Test("a selection redraw spends the drag's offset")
    func refreshResetsOffset() throws {
        let (renderer, _) = board(selecting: ["doc:0"])
        let start = try #require(renderer.worldPosition(of: "doc:0"))
        renderer.liveMove(id: "doc:0", toWorld: start + SIMD3<Double>(1, 0, 0))
        #expect(renderer.decorator.root.position != .zero)
        renderer.refreshSelectionDecoration()
        #expect(renderer.decorator.root.position == .zero)
    }

    // WHY: drop-target lookup runs per event; it now reads the cards lazily. Same answers as before.
    @Test("drop targets resolve the same from a lazy sequence")
    func lazyDropTargets() {
        let placeables: [String: SIMD3<Double>] = ["a": .zero, "b": SIMD3(1.1, 0, 0), "c": SIMD3(5, 0, 0)]
        let lazy = placeables.lazy.map { (id: $0.key, position: $0.value) }
        #expect(CanvasDropResolver.nearestId(to: SIMD3(1.0, 0, 0), among: lazy, excluding: "a") == "b")
        #expect(CanvasDropResolver.nearestId(to: SIMD3(3.0, 0, 0), among: lazy, excluding: "a") == nil)
    }
}
