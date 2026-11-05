//
//  SidebarTrashNodeTests.swift
//  FicheroTests
//
//  safety.trash.is-a-folder-in-the-sidebar (#5243, #2077): the Trash row opens onto what is in it; the rows drawn are
//  capped and the rest are left to the pane.
//

@testable import Fichero
import Testing

struct SidebarTrashNodeTests {
    private func entries(_ count: Int) -> [TrashEntry] {
        (0..<count).map { TrashEntry(id: "d\($0)", name: "Item \($0)", fromWhere: "Box 3", why: "Deleted by ana") }
    }

    @Test func fewEntriesAreAllDrawnAndNothingIsHidden() {
        let drawn = SidebarTrashNode.shown(entries(3))
        #expect(drawn.entries.map(\.id) == ["d0", "d1", "d2"])
        #expect(drawn.hidden == 0)
    }

    @Test func manyEntriesAreCappedInOrderAndTheRestAreCounted() {
        let drawn = SidebarTrashNode.shown(entries(SidebarTrashNode.childLimit + 7))
        #expect(drawn.entries.count == SidebarTrashNode.childLimit)
        #expect(drawn.entries.first?.id == "d0")
        #expect(drawn.hidden == 7)
    }

    @Test func anEmptyTrashDrawsNothing() {
        let drawn = SidebarTrashNode.shown([])
        #expect(drawn.entries.isEmpty && drawn.hidden == 0)
    }
}
