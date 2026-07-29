//
//  CanvasInteractionControllerTests.swift
//  FicheroTests
//
//  Unit tests for the renderer-agnostic interaction controller (#3103): the drag
//  state machine, single-row persist, snap-on-release, rollback, CRUD, the
//  move-into hook, and the disappear flush. Spy stores stand in for the real
//  #3082 stores so nothing touches the network.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import simd
import SwiftUI
import Testing

// MARK: - Spies

@MainActor
private final class SpyLayoutStore: CanvasLayoutPersisting {
    var rows: [CanvasItemLayout] = []
    private(set) var savedItems: [CanvasItemLayout]?
    var saveResult = true
    var loadError: String?

    func layout(for scopeId: String) -> [CanvasItemLayout] { rows }

    func saveLayout(folderId: String, items: [CanvasItemLayout]) async -> Bool {
        savedItems = items
        if saveResult { rows = items } else { loadError = "save failed" }
        return saveResult
    }
}

@MainActor
private final class SpyItemStore: CanvasItemMutating {
    struct Created: Equatable { let source: String?; let target: String? }
    private(set) var links: [Created] = []
    private(set) var createdKinds: [String] = []
    private(set) var deletes: [String] = []
    private(set) var edits: [String: String] = [:]
    var loadError: String?
    var nextId = "new-item"

    func items(for scopeId: String) -> [CanvasItemDisplay] { [] }

    func createItem(
        folderId: String,
        kind: Components.Schemas.CanvasItemKind,
        text: String?,
        sourceItemId: String?,
        targetItemId: String?
    ) async -> CanvasItemDisplay? {
        createdKinds.append(kind.rawValue)
        if kind == .link { links.append(Created(source: sourceItemId, target: targetItemId)) }
        return try? Self.decode(id: nextId, kind: kind.rawValue)
    }

    func updateItem(
        folderId: String, itemId: String, kind: Components.Schemas.CanvasItemKind?,
        text: String?, sourceItemId: String?, targetItemId: String?
    ) async -> Bool {
        edits[itemId] = text ?? ""
        return true
    }

    func deleteItem(folderId: String, itemId: String) async -> Bool {
        deletes.append(itemId)
        return true
    }

    static func decode(id: String, kind: String) throws -> CanvasItemDisplay {
        let data = try JSONSerialization.data(withJSONObject: ["id": id, "folderId": "scope", "kind": kind])
        return try JSONDecoder().decode(CanvasItemDisplay.self, from: data)
    }
}

@MainActor
private func makeController(
    layout: SpyLayoutStore,
    items: SpyItemStore,
    selection box: Box<String?>
) -> CanvasInteractionController {
    CanvasInteractionController(
        layoutStore: layout,
        itemStore: items,
        scopeId: "scope",
        selection: Binding(get: { box.value }, set: { box.value = $0 })
    )
}

@MainActor private final class Box<T> { var value: T; init(_ value: T) { self.value = value } }

// MARK: - Tests

@MainActor
@Suite("CanvasInteractionController (#3103)")
struct CanvasInteractionControllerTests {

    @Test("tap selects; tap(nil) clears; marquee sets the whole set")
    func selection() {
        let layout = SpyLayoutStore(), items = SpyItemStore(), box = Box<String?>(nil)
        let controller = makeController(layout: layout, items: items, selection: box)

        controller.select("a")
        #expect(controller.selectionSet == ["a"])
        #expect(box.value == "a")

        controller.selectMany(["a", "b"])
        #expect(controller.selectionSet == ["a", "b"])

        controller.select(nil)
        #expect(controller.selectionSet.isEmpty)
        #expect(box.value == nil)
    }

    @Test("mid-drag echo suppression: only the dragged id reports isDragging")
    func echoSuppression() {
        let controller = makeController(layout: SpyLayoutStore(), items: SpyItemStore(), selection: Box(nil))
        controller.beginDrag("a")
        #expect(controller.isDragging("a"))
        #expect(!controller.isDragging("b"))
    }

    @Test("drag-end persists exactly ONE row, snapped to the grid")
    func singleRowPersistSnapped() async {
        let layout = SpyLayoutStore()
        let controller = makeController(layout: layout, items: SpyItemStore(), selection: Box(nil))

        controller.beginDrag("drag")
        await controller.endDrag(
            id: "drag", position: SIMD3<Double>(1.13, -0.37, 0.12), dropTarget: nil, modifiers: []
        )

        #expect(layout.savedItems?.count == 1)
        let row = layout.savedItems?.first
        #expect(row?.itemId == "drag")
        #expect(row?.x == 1.25)     // snap(1.13) → 1.25 on the 0.25 grid
        #expect(row?.y == -0.25)
        #expect(row?.z == 0.0)
    }

    @Test("a failed persist rolls the entity back to its pre-drag position")
    func rollbackOnFailure() async {
        let layout = SpyLayoutStore()
        layout.rows = [CanvasItemLayout(itemId: "drag", x: 1, y: 1, z: 1)]
        layout.saveResult = false
        let controller = makeController(layout: layout, items: SpyItemStore(), selection: Box(nil))

        var rolledBack: (String, SIMD3<Double>)?
        controller.onRollback = { rolledBack = ($0, $1) }

        controller.beginDrag("drag")
        await controller.endDrag(id: "drag", position: SIMD3<Double>(5, 5, 5), dropTarget: nil, modifiers: [])

        #expect(rolledBack?.0 == "drag")
        #expect(rolledBack?.1 == SIMD3<Double>(1, 1, 1))
        #expect(controller.lastError == "save failed")   // surfaced, not silent
    }

    @Test("dropping on a container fires the move-into hook and does not persist a row")
    func moveIntoHook() async {
        let layout = SpyLayoutStore()
        let controller = makeController(layout: layout, items: SpyItemStore(), selection: Box(nil))
        var moved: (String, String)?
        controller.onMoveInto = { moved = ($0, $1) }

        controller.beginDrag("drag")
        await controller.endDrag(
            id: "drag", position: .zero,
            dropTarget: CanvasDropTarget(id: "folder", kind: .container), modifiers: []
        )

        #expect(moved?.0 == "drag")
        #expect(moved?.1 == "folder")
        #expect(layout.savedItems == nil)   // move-into does not persist a canvas row here
    }

    @Test("dropping on a leaf creates a link and persists the dragged row")
    func dropCreatesLink() async {
        let layout = SpyLayoutStore(), items = SpyItemStore()
        let controller = makeController(layout: layout, items: items, selection: Box(nil))

        controller.beginDrag("drag")
        await controller.endDrag(
            id: "drag", position: SIMD3<Double>(1, 1, 0),
            dropTarget: CanvasDropTarget(id: "target", kind: .leaf), modifiers: []
        )

        #expect(items.links == [.init(source: "drag", target: "target")])
        #expect(layout.savedItems?.count == 1)
    }

    @Test("addItem creates the item and drops an immediate layout row at the point")
    func addItemPlacesRow() async {
        let layout = SpyLayoutStore(), items = SpyItemStore()
        items.nextId = "note-1"
        let controller = makeController(layout: layout, items: items, selection: Box(nil))

        await controller.addItem(kind: .note, position: SIMD3<Double>(2, 2, 0))

        #expect(items.createdKinds == ["note"])
        #expect(layout.savedItems?.first?.itemId == "note-1")
        #expect(layout.savedItems?.first?.x == 2.0)
    }

    @Test("editItem and deleteItem reach the item store")
    func editDelete() async {
        let items = SpyItemStore()
        let controller = makeController(layout: SpyLayoutStore(), items: items, selection: Box(nil))
        await controller.editItem(id: "x", text: "hello")
        await controller.deleteItem(id: "y")
        #expect(items.edits["x"] == "hello")
        #expect(items.deletes == ["y"])
    }

    @Test("moveItem persists exactly one snapped row (undo/redo primitive)")
    func moveItemSnaps() async {
        let layout = SpyLayoutStore()
        let controller = makeController(layout: layout, items: SpyItemStore(), selection: Box(nil))
        await controller.moveItem(id: "x", to: SIMD3<Double>(1.13, -0.37, 0.12))
        #expect(layout.savedItems?.count == 1)
        #expect(layout.savedItems?.first?.itemId == "x")
        #expect(layout.savedItems?.first?.x == 1.25)   // snapped to the 0.25 grid
        #expect(layout.savedItems?.first?.y == -0.25)
    }

    @Test("moveItem persists a z push/pull (3D z-placement round-trips, #3090)")
    func moveItemPersistsZ() async {
        let layout = SpyLayoutStore()
        let controller = makeController(layout: layout, items: SpyItemStore(), selection: Box(nil))
        await controller.moveItem(id: "x", to: SIMD3<Double>(1, 1, 2.0))
        #expect(layout.savedItems?.first?.z == 2.0)   // z on the grid, kept end-to-end
    }

    @Test("disappear flush persists the in-flight drag position")
    func flushActiveDrag() async {
        let layout = SpyLayoutStore()
        let controller = makeController(layout: layout, items: SpyItemStore(), selection: Box(nil))

        controller.beginDrag("d")
        controller.dragMoved(id: "d", position: SIMD3<Double>(3, 3, 0))
        await controller.flushActiveDrag()

        #expect(layout.savedItems?.count == 1)
        #expect(layout.savedItems?.first?.x == 3.0)
        #expect(!controller.isDragging("d"))
    }
}
