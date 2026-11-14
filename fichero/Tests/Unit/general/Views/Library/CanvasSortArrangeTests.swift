@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private func sourceNode(_ id: String, label: String) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: label, positionX: 0, positionY: 0, positionZ: 0)
}

/// The bar's Sort on the Canvas and the Space (`panes.chrome.one-filter-pattern`, #6575).
@MainActor
struct CanvasSortArrangeTests {
    /// `panes.chrome.one-filter-pattern` (owner 2026-11-13): Sort on the Canvas arranges the cards in the order the
    /// Sort gave the nodes, once, whatever Arrange by holds; a dragged card goes to its slot too. If this goes red,
    /// Sort on the Canvas is back to doing nothing a person can see.
    @Test("Sort arranges every card in the sorted order, a dragged one too, keeping its size")
    func sortArrangesInTheSortedOrder() throws {
        let sorted = [
            sourceNode("doc:3", label: "Charlie"),
            sourceNode("doc:1", label: "alpha"),
            sourceNode("doc:2", label: "Bravo")
        ]
        let dragged = CanvasItemLayout(itemId: "doc:2", x: 99, y: -42, z: 0, w: 2.5, h: 3)
        let asFiled = CanvasSceneState.resolve(
            nodes: sorted, connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 3), arrangement: .asFiled
        )
        let rows = CanvasArrangement.rowsBySort(asFiled, keeping: [dragged])

        let byX = rows.sorted { $0.x < $1.x }.map(\.itemId)
        #expect(byX == ["doc:3", "doc:1", "doc:2"], "left to right in the Sort's order, not by name")
        let bravo = try #require(rows.first { $0.itemId == "doc:2" })
        #expect(bravo.x != 99, "the dragged card moved to its slot")
        #expect(bravo.w == 2.5, "its size is kept")
    }

    @Test("Sort's save is canvas.layout.save with the folder and every row")
    func sortSavesThroughTheActionsDoor() throws {
        let params = CanvasLayoutSaveAction(
            folderId: "folder-1", items: [CanvasItemLayout(itemId: "doc:1", x: 1, y: 2, z: 0).asSaveItem]
        )
        let json = try #require(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(params)) as? [String: Any]
        )
        #expect(CanvasLayoutSaveAction.name == "canvas.layout.save")
        #expect(json["folder_id"] as? String == "folder-1")
        let items = try #require(json["items"] as? [[String: Any]])
        #expect(items.first?["item_id"] as? String == "doc:1")
    }
}
