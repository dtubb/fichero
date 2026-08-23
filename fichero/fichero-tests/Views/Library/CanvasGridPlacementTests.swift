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
        #expect(CanvasGridPlacement.position(index: 3, columns: 3) == SIMD3<Double>(0, height, 0))
        #expect(CanvasGridPlacement.position(index: 4, columns: 3) == SIMD3<Double>(width, height, 0))
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
        #expect(CanvasGridPlacement.position(index: 1, columns: 1) == SIMD3<Double>(0, height, 0))
        #expect(CanvasGridPlacement.position(index: 2, columns: 1) == SIMD3<Double>(0, 2 * height, 0))
    }

    @Test("a non-positive column count degrades to one column, never divides by zero")
    func degenerateColumns() {
        for columns in [0, -1, -99] {
            #expect(CanvasGridPlacement.position(index: 0, columns: columns) == SIMD3<Double>(0, 0, 0))
            // y INCREASES per line (the projection flips it) — the negative
            // expectation here predated that fix and pinned the old sign.
            #expect(
                CanvasGridPlacement.position(index: 1, columns: columns)
                    == SIMD3<Double>(0, CanvasGridPlacement.cellHeight, 0)
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
        // Expressed in cells, not in literal world units: cell pitch now derives
        // from the board's card extents (§18.1 defect 4), so a literal would
        // pin the gutter rather than the counting rule.
        let cell = CanvasGridPlacement.cellWidth
        #expect(CanvasGridPlacement.columnCount(worldWidth: 4 * cell) == 4)
        #expect(CanvasGridPlacement.columnCount(worldWidth: 4.6 * cell) == 4)  // partial cell doesn't count
        #expect(CanvasGridPlacement.columnCount(worldWidth: 5 * cell + 0.01) == 5)
    }

    @Test("a narrow, empty, or nonsense viewport still yields at least one column")
    func columnCountFloor() {
        #expect(CanvasGridPlacement.columnCount(worldWidth: 0.1) == 1)     // narrower than one cell
        #expect(CanvasGridPlacement.columnCount(worldWidth: 0.1, cell: CGSize(width: 3, height: 3)) == 1)
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
        #expect(columns == Int(25.0 / CanvasGridPlacement.cellWidth))

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
                == [0, CanvasGridPlacement.cellHeight, 2 * CanvasGridPlacement.cellHeight]
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

// MARK: - Cell pitch from the board's ACTUAL card extents (§18.1 defect 4)

/// The gutter was a flat 0.5 against a 1.0-wide card — 50% of card width, where
/// §6.3 asks for ≈0.15 at the `.thumbnail` tier. The fix is not just a smaller
/// constant: because `CanvasCardGeometry` normalises every card on AREA, a
/// double-spread at aspect 2.0 renders 1.22 wide while covering the same area,
/// so a pitch built on the nominal 1.0 × 0.75 would overlap exactly the cards
/// that need the most room. Pitch therefore derives from the board's real
/// extents, and these pin both halves of that.
@Suite("CanvasGridPlacement cell pitch (§18.1 defect 4)")
struct CanvasGridCellPitchTests {

    @Test("the nominal gutter is 0.15 of card width, not 0.5")
    func nominalGutter() {
        let cell = CanvasGridPlacement.nominalCell
        #expect(abs(Double(cell.width) - 1.15) < 1e-9)    // 1.0 + 0.15
        #expect(abs(Double(cell.height) - 0.90) < 1e-9)   // 0.75 + 0.15
        // The gutter is one number on both axes, so the whitespace reads square.
        let gutter = Double(cell.width) - CanvasGridPlacement.cardWidth
        #expect(abs((Double(cell.height) - CanvasGridPlacement.cardHeight) - gutter) < 1e-9)
        #expect(abs(gutter / CanvasGridPlacement.cardWidth - CanvasGridPlacement.gutterFraction) < 1e-9)
    }

    @Test("a double-spread widens the cell to its area-normalised 1.22, not 1.0")
    func wideSpreadWidensThePitch() {
        // area 0.75, aspect 2.0 → width = sqrt(1.5) = 1.2247, height = 0.6124.
        let extents = CanvasGridPlacement.cardExtents(forAspects: [2.0])
        #expect(abs(Double(extents.width) - (0.75 * 2.0).squareRoot()) < 1e-9)
        // The TALLEST card still sets the row pitch, and no page is shorter than
        // the nominal card until one actually loads that way.
        #expect(abs(Double(extents.height) - CanvasGridPlacement.cardHeight) < 1e-9)

        let cell = CanvasGridPlacement.cell(forAspects: [2.0])
        #expect(Double(cell.width) > Double(CanvasGridPlacement.nominalCell.width))
        // Still exactly one gutter of 0.15 × the widest card.
        let gutter = Double(cell.width) - Double(extents.width)
        #expect(abs(gutter / Double(extents.width) - CanvasGridPlacement.gutterFraction) < 1e-9)
    }

    @Test("a tall page raises the row pitch, and the gutter stays width-derived")
    func tallPageRaisesRowPitch() {
        // aspect 0.5 → height = sqrt(0.75 / 0.5) = 1.2247.
        let extents = CanvasGridPlacement.cardExtents(forAspects: [0.5])
        #expect(abs(Double(extents.height) - (0.75 / 0.5).squareRoot()) < 1e-9)
        #expect(abs(Double(extents.width) - CanvasGridPlacement.cardWidth) < 1e-9)

        let cell = CanvasGridPlacement.cell(forAspects: [0.5])
        #expect(Double(cell.height) > Double(CanvasGridPlacement.nominalCell.height))
    }

    @Test("a mixed board is sized by its widest AND its tallest card")
    func mixedBoardTakesBothExtremes() {
        // ONE gutter, from the widest card, on both axes — the whitespace reads
        // square, which is what `nominalGutter` pins. So a mixed board's ROW
        // pitch is its tallest extent plus the WIDEST card's gutter, and it is
        // deliberately NOT equal to the pitch that card would get on a board of
        // its own (that board's widest card is narrower, so its gutter is
        // smaller). Composing the expectation from the extents rather than from
        // another cell is what says which rule is in force.
        let aspects = [2.0, 0.5, 1.33, 1.0]
        let mixed = CanvasGridPlacement.cell(forAspects: aspects)
        let extents = CanvasGridPlacement.cardExtents(forAspects: aspects)
        let gutter = CanvasGridPlacement.gutterFraction * Double(extents.width)

        #expect(abs(Double(extents.width) - Double(CanvasGridPlacement.cardExtents(forAspects: [2.0]).width)) < 1e-9)
        #expect(abs(Double(extents.height) - Double(CanvasGridPlacement.cardExtents(forAspects: [0.5]).height)) < 1e-9)
        #expect(abs(Double(mixed.width) - (Double(extents.width) + gutter)) < 1e-9)
        #expect(abs(Double(mixed.height) - (Double(extents.height) + gutter)) < 1e-9)
        // The same gutter on both axes: pitch minus extent is one number.
        #expect(abs((Double(mixed.width) - Double(extents.width))
                        - (Double(mixed.height) - Double(extents.height))) < 1e-9)
    }

    @Test("an empty or nonsense aspect list falls back to the nominal cell")
    func degenerateAspects() {
        let nominal = CanvasGridPlacement.nominalCell
        for aspects in [[Double](), [0], [-2], [Double.nan], [Double.infinity], [0, -1, Double.nan]] {
            let cell = CanvasGridPlacement.cell(forAspects: aspects)
            #expect(abs(Double(cell.width) - Double(nominal.width)) < 1e-9)
            #expect(abs(Double(cell.height) - Double(nominal.height)) < 1e-9)
        }
    }

    @Test("no aspect, however extreme, can drop a pitch to the drop threshold")
    func pitchNeverReadsAsADrop() {
        // THE invariant `gridSlotsNeverReadAsDrops` protects, restated over the
        // aspect axis: a tighter gutter is only safe while both pitches clear
        // `CanvasDropResolver.defaultThreshold`, or a card released on its own
        // clean slot resolves onto its neighbour and the move becomes a link.
        for aspect in [0.01, 0.1, 0.5, 1.0, 1.33, 2.0, 10.0, 100.0] {
            let cell = CanvasGridPlacement.cell(forAspects: [aspect])
            #expect(Double(cell.width) > CanvasDropResolver.defaultThreshold)
            #expect(Double(cell.height) > CanvasDropResolver.defaultThreshold)
        }
    }

    @Test("slots march at the cell they are given, and default to the nominal one")
    func positionHonoursTheCell() {
        let cell = CGSize(width: 3, height: 2)
        #expect(CanvasGridPlacement.position(index: 1, columns: 2, cell: cell) == SIMD3<Double>(3, 0, 0))
        #expect(CanvasGridPlacement.position(index: 2, columns: 2, cell: cell) == SIMD3<Double>(0, 2, 0))
        #expect(
            CanvasGridPlacement.position(index: 3, columns: 2)
                == CanvasGridPlacement.position(index: 3, columns: 2, cell: CanvasGridPlacement.nominalCell)
        )
    }

    @Test("resolve lays row-less cards out at the pitch the host passes")
    func resolveHonoursGridCell() {
        let nodes = (0..<4).map {
            SpatialNode(id: "n\($0)", roomId: "room", nodeType: .source, label: "n\($0)",
                        positionX: 0, positionY: 0, positionZ: 0)
        }
        let wide = CanvasGridPlacement.cell(forAspects: [2.0])
        let state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 2), gridCell: wide
        )
        let byId = Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })
        #expect(byId["n1"] == SIMD3<Double>(Double(wide.width), 0, 0))
        #expect(byId["n2"] == SIMD3<Double>(0, Double(wide.height), 0))
        // Omitting it is the nominal cell — every existing caller is unchanged.
        let defaulted = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 2)
        )
        #expect(defaulted.placeables[1].position == CanvasGridPlacement.position(index: 1, columns: 2))
    }
}

// MARK: - The board's aspects come from the texture memo

@MainActor
@Suite("CanvasCardGeometry.knownAspects (§18.1 defect 4)")
struct CanvasCardGeometryKnownAspectsTests {

    @Test("only sources whose texture has loaded contribute an aspect")
    func onlyLoadedSourcesContribute() {
        let wide = "pitch-test-wide-\(UUID().uuidString)"
        let unknown = "pitch-test-unknown-\(UUID().uuidString)"
        CanvasCardGeometry.recordAspect(2.0, forSourceId: wide)

        let aspects = CanvasCardGeometry.knownAspects(forSourceIds: [wide, unknown])
        #expect(aspects == [2.0])
        // An all-unknown board is the nominal cell, not a degenerate one.
        #expect(CanvasCardGeometry.knownAspects(forSourceIds: [unknown]).isEmpty)
        #expect(
            CanvasGridPlacement.cell(forAspects: CanvasCardGeometry.knownAspects(forSourceIds: [unknown]))
                == CanvasGridPlacement.nominalCell
        )
    }
}
