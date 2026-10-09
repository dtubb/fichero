//
//  CanvasOpensSettledTests.swift
//  FicheroTests
//
//  #5629 (`library.canvas.cards-move-only-when-asked`): a canvas opens with every card where it
//  stays and the camera at its fit, and after that no card moves unless the person moves it (a drag,
//  an Arrange). A pane resize, a card arriving, page shapes landing, a refresh or a save round-trip
//  move nothing, and the camera never re-fits unasked.
//
//  Why it broke: the canvas drew on its first frame, before its scope's saved places and items had
//  loaded and before any page's shape was known. It drew the default grid, the saved places then
//  arrived and the cards slid to them (an animated move, many cards at once), page shapes then
//  widened the grid and the board re-flowed with the camera re-fitting behind it. The default grid
//  also followed the pane's shape and the card count, so a resize or a new card re-laid the board.
//
//  #5631 (`library.canvas.selection-ring-is-thin`): the selection ring is about 3 points on screen
//  at every zoom; it was a plate padded by 8% of the card in world units, ~30 points zoomed in.
//

import CoreGraphics
@testable import Fichero
import FicheroAPIClient
import Foundation
import RealityKit
import simd
import Testing

private func card(_ id: String) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: id, positionX: 0, positionY: 0)
}

/// The board as `CanvasSceneView.resolvedState` resolves it, before the hold.
private func resolved(
    _ nodes: [SpatialNode], rows: [CanvasItemLayout] = [], columns: Int, cell: CGSize = CanvasGridPlacement.nominalCell
) -> CanvasSceneState {
    CanvasSceneState.resolve(
        nodes: nodes, connections: [], links: [], layoutRows: rows, items: [],
        defaultPlacement: .grid(columns: columns), gridCell: cell
    )
}

private func positions(_ state: CanvasSceneState) -> [String: SIMD3<Double>] {
    Dictionary(uniqueKeysWithValues: state.placeables.map { ($0.id, $0.position) })
}

@MainActor
@Suite("Canvas: cards move only when the person asks (#5629)")
struct CanvasPlacementMemoryTests {

    // WHY: the default grid's columns follow the pane. Before the fix, widening or narrowing the
    // pane re-laid every never-placed card; now the board keeps the places it opened with.
    @Test("a pane resize changes the default grid and moves no card")
    func resizeMovesNothing() {
        let nodes = (0..<12).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let opened = memory.pin(resolved(nodes, columns: 4), scope: "f", savedIds: [], columns: 4, cell: CanvasGridPlacement.nominalCell)
        let resized = memory.pin(resolved(nodes, columns: 2), scope: "f", savedIds: [], columns: 2, cell: CanvasGridPlacement.nominalCell)

        #expect(positions(resized) == positions(opened))
        #expect(positions(opened) == positions(resolved(nodes, columns: 4)), "the first board is the default layout as resolved")
    }

    // WHY: page shapes landing widen the grid's spacing; that must not slide the cards.
    @Test("page shapes landing after open move no card")
    func lateShapesMoveNothing() {
        let nodes = (0..<6).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let nominal = CanvasGridPlacement.nominalCell
        let tall = CanvasGridPlacement.cell(forAspects: [0.58])
        let opened = memory.pin(resolved(nodes, columns: 3), scope: "f", savedIds: [], columns: 3, cell: nominal)
        let later = memory.pin(resolved(nodes, columns: 3, cell: tall), scope: "f", savedIds: [], columns: 3, cell: tall)

        #expect(positions(later) == positions(opened))
    }

    // WHY: a card that arrives (an import, a refresh) is placed in free space; the column count the
    // grid derives from the card count must not shift the cards already there.
    @Test("a card that arrives takes a free cell and shifts nothing")
    func newcomerTakesAFreeCell() throws {
        let nodes = (0..<5).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let cell = CanvasGridPlacement.nominalCell
        let opened = memory.pin(resolved(nodes, columns: 3), scope: "f", savedIds: [], columns: 3, cell: cell)

        let grown = nodes + [card("doc:new")]
        let after = memory.pin(resolved(grown, columns: 4), scope: "f", savedIds: [], columns: 4, cell: cell)

        for (id, place) in positions(opened) {
            #expect(positions(after)[id] == place, "\(id) moved when a card arrived")
        }
        let newcomer = try #require(positions(after)["doc:new"])
        #expect(newcomer == CanvasGridPlacement.position(index: 5, columns: 3, cell: cell), "the first free cell of the opening grid")
        for (id, place) in positions(opened) {
            #expect(simd_distance(place, newcomer) >= Double(cell.width) * 0.5, "the newcomer sits on \(id)")
        }
    }

    // WHY: a free cell left by a card the person dragged away is filled, rather than a newcomer
    // landing on top of the card that was dropped somewhere.
    @Test("a newcomer never lands on a card the person placed")
    func newcomerAvoidsSavedPlaces() throws {
        let nodes = (0..<3).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let cell = CanvasGridPlacement.nominalCell
        _ = memory.pin(resolved(nodes, columns: 3), scope: "f", savedIds: [], columns: 3, cell: cell)
        // The person drops doc:0 on the next free slot (3).
        let slot3 = CanvasGridPlacement.position(index: 3, columns: 3, cell: cell)
        let rows = [CanvasItemLayout(itemId: "doc:0", x: slot3.x, y: slot3.y)]
        let grown = nodes + [card("doc:new")]
        let after = memory.pin(resolved(grown, rows: rows, columns: 3), scope: "f", savedIds: ["doc:0"], columns: 3, cell: cell)

        #expect(positions(after)["doc:0"] == slot3, "a saved place wins")
        #expect(positions(after)["doc:new"] == CanvasGridPlacement.position(index: 0, columns: 3, cell: cell), "it takes the cell doc:0 left")
    }

    // WHY: a move the person makes (a drag here, a drag in another window, an Arrange) arrives as a
    // saved place, and it must move the card; and the card then stays there even if the row goes.
    @Test("a saved place moves the card, and the card stays there afterwards")
    func savedPlaceMovesAndHolds() {
        let nodes = (0..<4).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let cell = CanvasGridPlacement.nominalCell
        _ = memory.pin(resolved(nodes, columns: 2), scope: "f", savedIds: [], columns: 2, cell: cell)
        let rows = [CanvasItemLayout(itemId: "doc:2", x: 9, y: -4)]
        let moved = memory.pin(resolved(nodes, rows: rows, columns: 2), scope: "f", savedIds: ["doc:2"], columns: 2, cell: cell)
        #expect(positions(moved)["doc:2"] == SIMD3<Double>(9, -4, 0))

        let rowGone = memory.pin(resolved(nodes, columns: 2), scope: "f", savedIds: [], columns: 2, cell: cell)
        #expect(positions(rowGone)["doc:2"] == SIMD3<Double>(9, -4, 0))
    }

    // WHY: a refresh or the save round-trip re-resolves the same board: nothing may move.
    @Test("re-resolving the same board moves nothing")
    func refreshMovesNothing() {
        let nodes = (0..<7).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let cell = CanvasGridPlacement.nominalCell
        let first = memory.pin(resolved(nodes, columns: 3), scope: "f", savedIds: [], columns: 3, cell: cell)
        let again = memory.pin(resolved(nodes, columns: 3), scope: "f", savedIds: [], columns: 3, cell: cell)
        #expect(again == first)
    }

    // WHY: another folder's board is its own; its cards are laid out afresh, not held at the old
    // folder's places.
    @Test("a different scope starts afresh")
    func scopeStartsAfresh() {
        let nodes = (0..<4).map { card("doc:\($0)") }
        let memory = CanvasPlacementMemory()
        let cell = CanvasGridPlacement.nominalCell
        _ = memory.pin(resolved(nodes, columns: 4), scope: "a", savedIds: [], columns: 4, cell: cell)
        let other = memory.pin(resolved(nodes, columns: 1), scope: "b", savedIds: [], columns: 1, cell: cell)
        #expect(positions(other) == positions(resolved(nodes, columns: 1)))
    }
}

@MainActor
@Suite("Canvas: the first frame is the settled one (#5629)")
struct CanvasOpensSettledTests {

    private let viewport = CGSize(width: 900, height: 600)

    // WHY: the gate. Nothing draws before the scope has settled or before the pane has a size.
    @Test("a canvas draws only a settled scope in a sized pane")
    func gate() {
        #expect(!CanvasOpenGate.mayDraw(settledScope: nil, scope: "f", viewport: viewport))
        #expect(!CanvasOpenGate.mayDraw(settledScope: "other", scope: "f", viewport: viewport))
        #expect(!CanvasOpenGate.mayDraw(settledScope: "f", scope: "f", viewport: .zero))
        #expect(CanvasOpenGate.mayDraw(settledScope: "f", scope: "f", viewport: viewport))
    }

    // WHY: "loaded" must mean an answer came back, an empty one included, so an empty folder opens
    // and a folder whose load is still in flight does not.
    @Test("the stores tell a loaded empty scope from one not loaded yet")
    func storesKnowWhatHasLoaded() {
        let client = FicheroClient(libraryPath: "/tmp/test.fichero")
        let layouts = CanvasLayoutStore(client: client), items = CanvasItemStore(client: client)
        #expect(!layouts.hasLoaded("f"))
        #expect(!items.hasLoaded("f"))
        layouts.layouts["f"] = []
        items.itemsByScope["f"] = []
        #expect(layouts.hasLoaded("f"))
        #expect(items.hasLoaded("f"))
    }

    // WHY: only shapes not known yet are fetched, each once, and never more than the limit.
    @Test("page shapes are prefetched only for unknown pages, at most the limit")
    func prefetchList() {
        let run = UUID().uuidString
        let known = "src-known-\(run)"
        CanvasCardGeometry.recordAspect(0.7, forSourceId: known)
        let ids = [known, "a-\(run)", "a-\(run)", "", "b-\(run)", "c-\(run)"]
        #expect(CanvasOpenGate.sourceIdsNeedingAspects(ids, limit: 2) == ["a-\(run)", "b-\(run)"])
    }

    // WHY: an opening board places its cards; it never animates them into place.
    @Test("moves in the opening reconcile are not animated")
    func openingDoesNotAnimate() {
        #expect(CanvasMoveAnimation.duration(for: [.move(id: "a", position: .zero)], opening: true) == 0)
        #expect(CanvasMoveAnimation.duration(for: [.move(id: "a", position: .zero)]) > 0)
    }

    // WHY: a canvas switched to another scope reuses its renderer. The cards the two scopes share
    // must be AT their new places in the opening frame, not gliding there.
    @Test("an opening reconcile puts every card at its final place at once")
    func openingPlacesAtOnce() throws {
        let nodes = (0..<4).map { card("doc:\($0)") }
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = viewport
        renderer.reconcile(to: resolved(nodes, columns: 4))

        renderer.needsFitOnNextContent = true
        let target = resolved(nodes, columns: 1)
        renderer.reconcile(to: target)

        for placeable in target.placeables {
            let entity = try #require(renderer.placeablesRoot.findEntity(named: placeable.id))
            let expected = Canvas2DProjection.scenePosition(placeable.position)
            #expect(entity.position.x == expected.x && entity.position.y == expected.y, "\(placeable.id) is not yet in place")
        }
    }

    // WHY: the camera fits once, on open. Before the fix it re-fitted whenever the board's bounds
    // changed on an untouched camera, so a card arriving re-centred and re-zoomed the view.
    @Test("the camera fits once and never re-fits unasked")
    func cameraFitsOnce() {
        let nodes = (0..<8).map { card("doc:\($0)") }
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = viewport
        renderer.needsFitOnNextContent = true
        renderer.reconcile(to: resolved(nodes, columns: 4))
        let camera = renderer.camera.position, scale = renderer.orthoScale

        renderer.reconcile(to: resolved(nodes + [card("doc:far")], columns: 1))

        #expect(renderer.camera.position == camera)
        #expect(renderer.orthoScale == scale)
    }
}

@MainActor
@Suite("Canvas: the selection ring is thin (#5631)")
struct CanvasSelectionRingTests {

    // WHY: the ring is a constant ~3 points on screen whatever the zoom, and follows the card's
    // corners; before, it was 8% of the card in world units.
    @Test("the ring is three points on screen at every zoom and follows the card's corners")
    func ringGeometry() {
        for worldPerPoint: Float in [0.001, 0.01, 0.1] {
            let ring = CanvasSelectionFrame.ring(cardWidth: 1, cardHeight: 0.75, worldPerPoint: worldPerPoint)
            #expect(abs(ring.thickness / worldPerPoint - 3) < 0.0001)
            #expect(abs(ring.width - (1 + 2 * ring.thickness)) < 0.0001)
            #expect(abs(ring.height - (0.75 + 2 * ring.thickness)) < 0.0001)
            #expect(abs(ring.cornerRadius - (CanvasCardGeometry.cornerRadius(width: 1, height: 0.75) + ring.thickness)) < 0.0001)
        }
    }

    // WHY: the maintainer's screenshot: zoomed onto one card, the old 8% plate was a ~30 pt band.
    // Through the real renderer: zoomed in and out, the ring stays 3 pt and the card stays as it was.
    @Test("a selected card's ring stays three points through a zoom; the card does not change")
    func ringThroughTheRenderer() throws {
        let renderer = CanvasOrtho2DRenderer()
        let viewport = CGSize(width: 900, height: 600)
        renderer.viewportSize = viewport
        renderer.needsFitOnNextContent = true
        var state = resolved([card("doc:0"), card("doc:1")], columns: 2)
        renderer.reconcile(to: state)
        state.selection = ["doc:0"]
        renderer.reconcile(to: state)
        let selected = try #require(renderer.placeablesRoot.findEntity(named: "doc:0"))
        let cardPosition = selected.position, cardScale = selected.scale

        for scale: Float in [0.3, 8, 40] {
            renderer.setOrthoScale(scale)
            let ring = try #require(renderer.platedRings["doc:0"])
            let worldPerPoint = Canvas2DProjection.worldPerPoint(orthoScale: renderer.orthoScale, viewHeight: viewport.height)
            #expect(abs(ring.thickness / worldPerPoint - CanvasSelectionFrame.ringPoints) < 0.001)
            #expect(selected.findEntity(named: "selectionPlate") != nil)
        }
        #expect(selected.position == cardPosition)
        #expect(selected.scale == cardScale)

        state.selection = []
        renderer.reconcile(to: state)
        #expect(selected.findEntity(named: "selectionPlate") == nil)
        #expect(renderer.platedRings.isEmpty)
    }
}
