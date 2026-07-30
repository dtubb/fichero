//
//  CanvasGridPlacementTests.swift
//  FicheroTests
//
//  #4290 — the 2D canvas rendered every item as one fixed row and nothing could
//  be moved. Two stacked causes, both pinned here:
//
//  1. NO 2D DEFAULT LAYOUT. `SpatialLibraryProjector` lays documents out with a
//     phyllotaxis on the XZ plane — correct for the 3D 'Space' floor, where the
//     camera looks across x/z. The 2D ortho renderer projects `(x, −y)` and
//     drops z, so every one of those defaults has y == 0 and the whole folder
//     collapses onto ONE LINE.
//  2. THE OVERLAP BROKE DRAGGING. `CanvasDropResolver` reads any release within
//     `defaultThreshold` of another placeable as a drop-ONTO. Cards piled within
//     a card's width of each other meant moving one became a link — or, over a
//     folder, a move-INTO that took it off the canvas. Cause 1 CAUSED cause 2,
//     which is why "dragging does nothing" and "everything is in a row" were the
//     same bug.
//
//  So the spacing assertions below are not cosmetic: `gridSlotsNeverReadAsDrops`
//  is the one that keeps dragging working at all.
//
//  Pure — no renderer, no network.
//

import CoreGraphics
@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import SwiftUI
import Testing

// MARK: - Helpers

/// A node shaped like the projector's XZ-plane output: y is always 0, only x/z
/// vary. This is exactly the input that produced the one-row render.
private func xzNode(_ id: String, positionX: Double, positionZ: Double) -> SpatialNode {
    SpatialNode(
        id: id, roomId: "room", nodeType: .source, label: id,
        positionX: positionX, positionY: 0, positionZ: positionZ
    )
}

private func noteItem(_ id: String, kind: String = "note") throws -> CanvasItemDisplay {
    let data = try JSONSerialization.data(withJSONObject: ["id": id, "folderId": "scope", "kind": kind])
    return try JSONDecoder().decode(CanvasItemDisplay.self, from: data)
}

// MARK: - Grid math

@Suite("CanvasGridPlacement (#4290)")
struct CanvasGridPlacementTests {

    @Test("the first slot is the origin and slots march right, then down")
    func slotsMarchRightThenDown() {
        let width = CanvasGridPlacement.cellWidth
        let height = CanvasGridPlacement.cellHeight

        #expect(CanvasGridPlacement.position(index: 0, columns: 3) == SIMD3<Double>(0, 0, 0))
        #expect(CanvasGridPlacement.position(index: 1, columns: 3) == SIMD3<Double>(width, 0, 0))
        #expect(CanvasGridPlacement.position(index: 2, columns: 3) == SIMD3<Double>(2 * width, 0, 0))
        // Wraps to the next line, and y DECREASES — canonical space is y-up and
        // the 2D projection flips it, so lower y reads as further down the board.
        #expect(CanvasGridPlacement.position(index: 3, columns: 3) == SIMD3<Double>(0, -height, 0))
        #expect(CanvasGridPlacement.position(index: 4, columns: 3) == SIMD3<Double>(width, -height, 0))
    }

    @Test("a single item sits at the origin, not offset into nowhere")
    func singleItem() {
        #expect(CanvasGridPlacement.position(index: 0, columns: 1) == SIMD3<Double>(0, 0, 0))
    }

    @Test("placement is deterministic: same index and columns, same slot")
    func deterministic() {
        for index in 0..<12 {
            #expect(
                CanvasGridPlacement.position(index: index, columns: 4)
                    == CanvasGridPlacement.position(index: index, columns: 4)
            )
        }
    }

    @Test("a one-column grid is a vertical stack, never a pile at the origin")
    func oneColumn() {
        let height = CanvasGridPlacement.cellHeight
        #expect(CanvasGridPlacement.position(index: 0, columns: 1) == SIMD3<Double>(0, 0, 0))
        #expect(CanvasGridPlacement.position(index: 1, columns: 1) == SIMD3<Double>(0, -height, 0))
        #expect(CanvasGridPlacement.position(index: 2, columns: 1) == SIMD3<Double>(0, -2 * height, 0))
    }

    @Test("a non-positive column count degrades to one column, never divides by zero")
    func degenerateColumns() {
        for columns in [0, -1, -99] {
            #expect(CanvasGridPlacement.position(index: 0, columns: columns) == SIMD3<Double>(0, 0, 0))
            #expect(
                CanvasGridPlacement.position(index: 1, columns: columns)
                    == SIMD3<Double>(0, -CanvasGridPlacement.cellHeight, 0)
            )
        }
    }

    @Test("a negative index clamps to the first slot rather than marching backwards")
    func negativeIndex() {
        #expect(CanvasGridPlacement.position(index: -3, columns: 4) == SIMD3<Double>(0, 0, 0))
    }

    // MARK: Column count

    @Test("column count is how many cells fit across the world width")
    func columnCountFromWorldWidth() {
        // 6 world units / 1.5 per cell = 4 columns.
        #expect(CanvasGridPlacement.columnCount(worldWidth: 6) == 4)
        #expect(CanvasGridPlacement.columnCount(worldWidth: 6.4) == 4)   // partial cell doesn't count
        #expect(CanvasGridPlacement.columnCount(worldWidth: 7.5) == 5)
    }

    @Test("a narrow, empty, or nonsense viewport still yields at least one column")
    func columnCountFloor() {
        #expect(CanvasGridPlacement.columnCount(worldWidth: 0.1) == 1)     // narrower than one cell
        #expect(CanvasGridPlacement.columnCount(worldWidth: 0) == 1)
        #expect(CanvasGridPlacement.columnCount(worldWidth: -5) == 1)
        #expect(CanvasGridPlacement.columnCount(worldWidth: .nan) == 1)
        #expect(CanvasGridPlacement.columnCount(worldWidth: .infinity) == 1)
    }

    @Test("a viewport converts through world-per-point to a column count")
    func columnCountFromViewport() {
        // worldPerPoint = 2 * 8 / 800 = 0.02 → 1250pt wide ≈ 25 world units, so
        // 16 whole cells fit with a partial one left over. Deliberately not an
        // exact multiple of the cell: Float world-per-point makes an exact
        // boundary land either side of the truncation, which would make the
        // expectation a coin flip rather than a check.
        let worldPerPoint = Canvas2DProjection.worldPerPoint(orthoScale: 8, viewHeight: 800)
        let columns = CanvasGridPlacement.columnCount(
            viewportSize: CGSize(width: 1250, height: 800), worldPerPoint: worldPerPoint
        )
        #expect(columns == 16)   // 25 / 1.5 = 16.67

        // A sliver of a window: one column, not a stack.
        let narrow = CanvasGridPlacement.columnCount(
            viewportSize: CGSize(width: 20, height: 800), worldPerPoint: worldPerPoint
        )
        #expect(narrow == 1)
    }

    // MARK: The invariant that keeps dragging alive

    @Test("grid slots are far enough apart that a release never reads as a drop-onto")
    func gridSlotsNeverReadAsDrops() {
        // THE #4290 regression guard. If cell pitch ever drops to (or below) the
        // drop threshold, dropping a card at its own clean grid slot resolves
        // onto a neighbour — and the move silently becomes a link or a
        // move-into-folder. That is the bug, not a near-miss of it.
        #expect(CanvasGridPlacement.cellWidth > CanvasDropResolver.defaultThreshold)
        #expect(CanvasGridPlacement.cellHeight > CanvasDropResolver.defaultThreshold)

        let columns = 4
        let slots = (0..<12).map { index in
            (id: "s\(index)", position: CanvasGridPlacement.position(index: index, columns: columns))
        }
        for slot in slots {
            let target = CanvasDropResolver.nearestId(to: slot.position, among: slots, excluding: slot.id)
            #expect(target == nil, "slot \(slot.id) resolved onto \(target ?? "-") — a move would become a link")
        }
    }
}

// MARK: - resolve() with a grid default

@Suite("CanvasSceneState.resolve default placement (#4290)")
struct CanvasResolveDefaultPlacementTests {

    @Test("row-less nodes land on distinct grid slots instead of one row")
    func gridSpreadsRowlessNodes() {
        // The projector's actual shape: y == 0 for every document, only x/z vary.
        let nodes = (0..<6).map { xzNode("n\($0)", positionX: Double($0) * 0.3, positionZ: Double($0) * 0.2) }
        let state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 3)
        )

        #expect(state.placeables.count == 6)
        // The defect was a single y value across the whole folder.
        let distinctY = Set(state.placeables.map(\.position.y))
        #expect(distinctY.count == 2)   // 6 cards, 3 columns → 2 lines
        // No two cards share a position, and none is within drop-onto range of
        // another — the two symptoms of #4290, both gone.
        let placed = state.placeables.map { (id: $0.id, position: $0.position) }
        #expect(Set(placed.map { "\($0.position)" }).count == 6)
        for card in placed {
            #expect(CanvasDropResolver.nearestId(to: card.position, among: placed, excluding: card.id) == nil)
        }
    }

    @Test("an empty scope resolves to no placeables at all")
    func emptyScope() {
        let state = CanvasSceneState.resolve(
            nodes: [], connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 4)
        )
        #expect(state.placeables.isEmpty)
    }

    @Test("one node takes the first slot")
    func singleNode() {
        let state = CanvasSceneState.resolve(
            nodes: [xzNode("only", positionX: 3, positionZ: 4)], connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 4)
        )
        #expect(state.placeables.first?.position == SIMD3<Double>(0, 0, 0))
    }

    @Test("a narrow viewport's single column stacks the folder vertically")
    func narrowViewportStacks() {
        let nodes = (0..<3).map { xzNode("n\($0)", positionX: 0, positionZ: 0) }
        let state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 1)
        )
        #expect(state.placeables.map(\.position.x) == [0, 0, 0])
        #expect(
            state.placeables.map(\.position.y)
                == [0, -CanvasGridPlacement.cellHeight, -2 * CanvasGridPlacement.cellHeight]
        )
    }

    @Test("a saved row still wins over the grid, and does not shift its neighbours")
    func savedRowsUntouched() {
        let nodes = (0..<4).map { xzNode("n\($0)", positionX: 0, positionZ: 0) }
        let state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [],
            layoutRows: [CanvasItemLayout(itemId: "n1", x: 42, y: -7, z: 1.5)], items: [],
            defaultPlacement: .grid(columns: 2)
        )
        let byId = Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })

        // The dragged card keeps exactly what was persisted, z included.
        #expect(byId["n1"] == SIMD3<Double>(42, -7, 1.5))
        // And every other card keeps the slot it had — a row for one item must
        // never re-flow the board, or nothing would ever stay put.
        #expect(byId["n0"] == CanvasGridPlacement.position(index: 0, columns: 2))
        #expect(byId["n2"] == CanvasGridPlacement.position(index: 2, columns: 2))
        #expect(byId["n3"] == CanvasGridPlacement.position(index: 3, columns: 2))
    }

    @Test("nodes and standalone items share ONE slot sequence, so they never collide")
    func nodesAndItemsShareTheGrid() throws {
        let state = CanvasSceneState.resolve(
            nodes: [xzNode("n0", positionX: 0, positionZ: 0), xzNode("n1", positionX: 0, positionZ: 0)],
            connections: [], links: [], layoutRows: [],
            items: [try noteItem("i0"), try noteItem("i1")],
            defaultPlacement: .grid(columns: 2)
        )
        let byId = Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })
        #expect(byId["n0"] == CanvasGridPlacement.position(index: 0, columns: 2))
        #expect(byId["n1"] == CanvasGridPlacement.position(index: 1, columns: 2))
        #expect(byId["i0"] == CanvasGridPlacement.position(index: 2, columns: 2))
        #expect(byId["i1"] == CanvasGridPlacement.position(index: 3, columns: 2))
    }

    @Test("a link item consumes no slot — it is an edge, not a card")
    func linkItemsTakeNoSlot() throws {
        let state = CanvasSceneState.resolve(
            nodes: [], connections: [], links: [], layoutRows: [],
            items: [try noteItem("i0"), try noteItem("edge", kind: "link"), try noteItem("i1")],
            defaultPlacement: .grid(columns: 3)
        )
        let byId = Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })
        #expect(byId.count == 2)
        #expect(byId["i0"] == CanvasGridPlacement.position(index: 0, columns: 3))
        #expect(byId["i1"] == CanvasGridPlacement.position(index: 1, columns: 3))
    }

    @Test("the 3D default is untouched: backend positions and the item cascade")
    func backendPlacementUnchanged() throws {
        // The 3D 'Space' renderer must keep the projector's XZ plane — the grid
        // is a 2D-only correction, not a change to the shared contract.
        let state = CanvasSceneState.resolve(
            nodes: [xzNode("n0", positionX: 1.5, positionZ: 2.5)], connections: [], links: [], layoutRows: [],
            items: [try noteItem("i0"), try noteItem("i1")]
        )
        let byId = Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })
        #expect(byId["n0"] == SIMD3<Double>(1.5, 0, 2.5))
        #expect(byId["i0"] == CanvasSceneState.cascadePosition(0))
        #expect(byId["i1"] == CanvasSceneState.cascadePosition(1))
    }
}

// MARK: - Drag → persist → re-resolve

/// Reference cell for the selection binding — mirrors the `Box` in
/// `CanvasInteractionControllerTests`.
@MainActor private final class SelectionBox { var value: Set<String> = [] }

@MainActor
private final class GridSpyLayoutStore: CanvasLayoutPersisting {
    var rows: [CanvasItemLayout] = []
    private(set) var saveCallCount = 0
    var loadError: String?

    func layout(for scopeId: String) -> [CanvasItemLayout] { rows }

    func saveLayout(folderId: String, items: [CanvasItemLayout]) async -> Bool {
        saveCallCount += 1
        rows = items
        return true
    }
}

@MainActor
private final class GridSpyItemStore: CanvasItemMutating {
    var loadError: String?
    func items(for scopeId: String) -> [CanvasItemDisplay] { [] }
    func createItem(
        folderId: String, kind: Components.Schemas.CanvasItemKind, text: String?,
        sourceItemId: String?, targetItemId: String?
    ) async -> CanvasItemDisplay? { nil }
    // swiftlint:disable:next function_parameter_count
    func updateItem(   // mirrors the CanvasItemMutating signature (unchanged)
        folderId: String, itemId: String, kind: Components.Schemas.CanvasItemKind?,
        text: String?, sourceItemId: String?, targetItemId: String?
    ) async -> Bool { true }
    func deleteItem(folderId: String, itemId: String) async -> Bool { true }
}

@MainActor
@Suite("Canvas move persistence round-trip (#4290)")
struct CanvasMovePersistenceRoundTripTests {

    @Test("dragging a grid-default card persists ONE row, and re-resolving honours it")
    func moveOffTheGridSticks() async {
        let layout = GridSpyLayoutStore()
        let selected = SelectionBox()
        let controller = CanvasInteractionController(
            layoutStore: layout,
            itemStore: GridSpyItemStore(),
            scopeId: "scope",
            selection: Binding(get: { selected.value }, set: { selected.value = $0 })
        )
        let nodes = (0..<4).map { xzNode("n\($0)", positionX: 0, positionZ: 0) }

        // Before the drag: n2 sits on its default grid slot, nothing persisted.
        let before = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: layout.rows, items: [],
            defaultPlacement: .grid(columns: 2)
        )
        #expect(before.placeables.first { $0.id == "n2" }?.position
            == CanvasGridPlacement.position(index: 2, columns: 2))
        #expect(layout.rows.isEmpty)

        // Drag it to empty space. No drop target → a plain place, not a link.
        controller.beginDrag("n2")
        controller.dragMoved(id: "n2", position: SIMD3<Double>(9.1, -4.9, 0))
        await controller.endDrag(
            id: "n2", position: SIMD3<Double>(9.1, -4.9, 0), dropTarget: nil, modifiers: []
        )

        // Exactly one row written — never the pin-all-visible batch.
        #expect(layout.saveCallCount == 1)
        #expect(layout.rows.count == 1)
        #expect(layout.rows.first?.itemId == "n2")

        // After the drag: n2 is where it was dropped (snapped to the 0.25 grid),
        // and its neighbours have NOT moved. This is the whole bug report in one
        // assertion — a move that survives the next resolve.
        let after = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: layout.rows, items: [],
            defaultPlacement: .grid(columns: 2)
        )
        let byId = Dictionary(uniqueKeysWithValues: after.placeables.map { ($0.id, $0.position) })
        #expect(byId["n2"] == SIMD3<Double>(9.0, -5.0, 0))
        #expect(byId["n0"] == CanvasGridPlacement.position(index: 0, columns: 2))
        #expect(byId["n1"] == CanvasGridPlacement.position(index: 1, columns: 2))
        #expect(byId["n3"] == CanvasGridPlacement.position(index: 3, columns: 2))
    }

    @Test("a second drag of the same card updates its row in place, not a duplicate")
    func repeatedDragsUpdateOneRow() async {
        let layout = GridSpyLayoutStore()
        let selected = SelectionBox()
        let controller = CanvasInteractionController(
            layoutStore: layout,
            itemStore: GridSpyItemStore(),
            scopeId: "scope",
            selection: Binding(get: { selected.value }, set: { selected.value = $0 })
        )

        for target in [SIMD3<Double>(2, 2, 0), SIMD3<Double>(5, -3, 0)] {
            controller.beginDrag("n0")
            await controller.endDrag(id: "n0", position: target, dropTarget: nil, modifiers: [])
        }

        #expect(layout.rows.count == 1)           // in place, not appended twice
        #expect(layout.rows.first?.x == 5)
        #expect(layout.rows.first?.y == -3)
    }
}
