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

    /// `safety.trash.is-a-folder-in-the-sidebar`, owner ruling 2026-11-11 (#6536): the chevron is on the leading edge, as
    /// for every folder, so the Trash is a real disclosure group, and only while it holds something.
    @Test func theTrashOpensOnlyWhileItHoldsSomething() {
        #expect(SidebarTrashNode.opens(isEmpty: false))
        #expect(!SidebarTrashNode.opens(isEmpty: true))
    }

    @Test func theTrashIsARealDisclosureGroupTaggedOnTheGroup() throws {
        let node = try AppSource.code("Views/Sidebar/Trash/SidebarTrashNode.swift")
        let row = try AppSource.code("Views/Sidebar/Trash/SidebarTrashRow.swift")
        #expect(node.contains("DisclosureGroup(isExpanded: $isExpanded)"))
        // The List reads the selection from the row itself: the tag is on the group, not inside its label.
        #expect(node.contains(".tag(SidebarDestination.trash(libraryId: libraryId))"))
        #expect(!row.contains(".tag("))
        // No hand-drawn chevron at the trailing edge, and no hand-made indent for the children.
        #expect(!row.contains("chevron"))
        #expect(!node.contains("padding(.leading"))
    }
}
