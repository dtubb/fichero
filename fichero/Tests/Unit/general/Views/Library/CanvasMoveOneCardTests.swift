//
//  CanvasMoveOneCardTests.swift
//  FicheroTests
//
//  `library.canvas.moving-one-card-moves-only-it` (#5423): moving one card on the 2D canvas moves
//  only that card and saves its place; every other card keeps where it was; the automatic layout
//  places only cards that have never been placed.
//
//  Why it broke: the saved rows were right, but the 2D renderer's automatic camera re-fitted
//  whenever the board's bounds changed. A moved card changes the bounds, so the camera re-centred
//  and re-zoomed and every other card jumped on screen. The board looked re-laid out.
//

import CoreGraphics
@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import SwiftUI
import Testing

private func card(_ id: String) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: id, positionX: 0, positionY: 0, positionZ: 0)
}

/// Stands in for `CanvasLayoutStore` behind the protocol the controller writes through; it keeps
/// what was saved, as the store's optimistic publish does.
@MainActor
private final class RowsStore: CanvasLayoutPersisting {
    var rows: [CanvasItemLayout] = []
    var loadError: String?
    func layout(for scopeId: String) -> [CanvasItemLayout] { rows }
    func saveLayout(folderId: String, items: [CanvasItemLayout]) async -> Bool {
        rows = items
        return true
    }
}

@MainActor
private final class NoItems: CanvasItemMutating {
    var loadError: String?
    func items(for scopeId: String) -> [CanvasItemDisplay] { [] }
    func createItem(
        folderId: String, kind: Components.Schemas.CanvasItemKind, text: String?,
        sourceItemId: String?, targetItemId: String?
    ) async -> CanvasItemDisplay? { nil }
    func updateItem(
        folderId: String, itemId: String, kind: Components.Schemas.CanvasItemKind?,
        text: String?, sourceItemId: String?, targetItemId: String?
    ) async -> Bool { true }
    func deleteItem(folderId: String, itemId: String) async -> Bool { true }
}

@MainActor
@Suite("Canvas: moving one card moves only it (#5423)")
struct CanvasMoveOneCardTests {

    private let viewport = CGSize(width: 900, height: 600)

    /// The board as `CanvasSceneView.resolvedState` resolves it: the shared grid columns for this
    /// viewport, saved rows winning.
    private func board(_ nodes: [SpatialNode], rows: [CanvasItemLayout]) -> CanvasSceneState {
        CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: rows, items: [],
            defaultPlacement: .grid(columns: CanvasGridPlacement.sharedColumnCount(
                itemCount: nodes.count, viewportSize: viewport
            ))
        )
    }

    private func positions(_ state: CanvasSceneState) -> [String: SIMD3<Double>] {
        Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })
    }

    // WHY: the spec line itself, through the controller's real drag-end save and the real resolve.
    // A save that dropped the other rows, or a layout that re-slotted the unplaced cards around the
    // moved one, would move a card the person never touched.
    @Test("a moved card lands where it was dropped; every other card stays exactly where it was")
    func moveOneLeavesTheRest() async {
        let nodes = (0..<8).map { card("doc:\($0)") }
        let store = RowsStore()
        let controller = CanvasInteractionController(
            layoutStore: store, itemStore: NoItems(), scopeId: "folder-1",
            selection: Binding(get: { [] }, set: { _ in })
        )
        let before = positions(board(nodes, rows: store.rows))

        controller.beginDrag("doc:3")
        await controller.endDrag(
            id: "doc:3", position: SIMD3<Double>(9, -4, 0), dropTarget: nil, modifiers: []
        )
        let after = positions(board(nodes, rows: store.rows))

        let dropped = controller.snap(SIMD3<Double>(9, -4, 0))
        #expect(after["doc:3"] == dropped)
        #expect(store.rows.map(\.itemId) == ["doc:3"], "only the moved card is saved")
        for id in before.keys where id != "doc:3" {
            #expect(after[id] == before[id], "\(id) moved without being touched")
        }
    }

    // WHY: "the automatic layout places only cards that have never been placed". A card added later
    // gets a slot from the layout; the card the person placed keeps its place.
    @Test("a card added afterwards is placed by the layout; the placed card does not move")
    func newCardIsPlacedWithoutMovingThePlacedOne() async {
        let nodes = (0..<8).map { card("doc:\($0)") }
        let store = RowsStore()
        let controller = CanvasInteractionController(
            layoutStore: store, itemStore: NoItems(), scopeId: "folder-1",
            selection: Binding(get: { [] }, set: { _ in })
        )
        controller.beginDrag("doc:3")
        await controller.endDrag(
            id: "doc:3", position: SIMD3<Double>(9, -4, 0), dropTarget: nil, modifiers: []
        )
        let placed = positions(board(nodes, rows: store.rows))["doc:3"]

        let grown = nodes + [card("doc:new")]
        let state = positions(board(grown, rows: store.rows))

        #expect(state["doc:3"] == placed)
        let columns = CanvasGridPlacement.sharedColumnCount(itemCount: grown.count, viewportSize: viewport)
        let expectedSlot = CanvasGridPlacement.position(
            index: grown.count - 1, columns: columns, cell: CanvasGridPlacement.nominalCell
        )
        #expect(state["doc:new"] == expectedSlot)
        #expect(!store.rows.contains { $0.itemId == "doc:new" }, "the layout places it; nothing is saved")
    }

    // WHY: the bug itself. The rows were right and the board still looked re-laid out, because the
    // automatic camera re-fitted to the moved card's new bounds and every other card jumped on screen.
    @Test("moving a card does not re-fit the camera, so no other card moves on screen")
    func moveDoesNotRefitTheCamera() {
        let nodes = (0..<8).map { card("doc:\($0)") }
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = viewport
        renderer.needsFitOnNextContent = true
        renderer.reconcile(to: board(nodes, rows: []))
        let camera = renderer.camera.position, scale = renderer.orthoScale

        let far = SIMD3<Double>(30, -20, 0)
        renderer.liveMove(id: "doc:3", toWorld: far)
        renderer.reconcile(to: board(nodes, rows: [CanvasItemLayout(itemId: "doc:3", x: far.x, y: far.y)]))

        #expect(renderer.camera.position == camera)
        #expect(renderer.orthoScale == scale)
        #expect(renderer.placeablesById["doc:3"]?.position == far)
    }

    // WHY: the fix must stay narrow. A board that re-flows by itself (page aspects load and the grid
    // widens) on a camera nobody has touched is still fitted again, so a first open shows every card.
    @Test("a board that re-flows by itself is still fitted again")
    func selfReflowStillRefits() {
        let nodes = (0..<8).map { card("doc:\($0)") }
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = viewport
        renderer.needsFitOnNextContent = true
        renderer.reconcile(to: board(nodes, rows: []))
        let scale = renderer.orthoScale

        renderer.reconcile(to: CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 1)
        ))

        #expect(renderer.orthoScale != scale)
    }
}
