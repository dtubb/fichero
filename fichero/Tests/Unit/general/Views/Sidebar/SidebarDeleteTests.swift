//
//  SidebarDeleteTests.swift
//  FicheroTests
//
//  delete.after-delete-selection-is-never-a-delete-target (#6175): after a delete the app selects a neighbour or the
//  parent, and that selection is only a place to look; no delete gesture acts on it until the person selects again.
//

@testable import Fichero
import Foundation
import Testing

struct SidebarDeleteTests {
    private func item(_ id: String, _ name: String) -> SidebarItem {
        SidebarItem.fromDocument(Document(id: id, docType: .folder, name: name), libraryId: UUID())
    }

    @Test func deletingAnOnlyChildNeverMakesTheParentTheNextDeleteTarget() {
        let parent = item("p", "Parent")
        // The delete of the only child (c) leaves the PARENT selected (Finder rule: no sibling, so the parent) ...
        let inherited = selectionAfterDelete(deleted: "c", siblings: ["c"], parent: "p")
        #expect(inherited == "p")
        // ... and the next Backspace, "-" or Edit > Delete finds nothing to delete.
        #expect(sidebarDeleteTargets([parent], inheritedSelectionId: inherited).isEmpty)
    }

    @Test func aRowThePersonSelectsIsTheirsToDelete() {
        let parent = item("p", "Parent")
        #expect(sidebarDeleteTargets([parent], inheritedSelectionId: nil).map(\.id) == ["p"])
        #expect(sidebarDeleteTargets([parent], inheritedSelectionId: "other").map(\.id) == ["p"])
    }

    @Test func aMultiSelectionKeepsEveryRowButTheInheritedOne() {
        let rows = [item("a", "A"), item("b", "B")]
        #expect(sidebarDeleteTargets(rows, inheritedSelectionId: "a").map(\.id) == ["b"])
    }

    @Test func theDeleteStateRemembersAndForgetsTheInheritedRow() {
        let state = DeleteStateManager()
        #expect(state.inheritedSelectionId == nil)
        state.inheritedSelectionId = "p"
        state.inheritedSelectionId = nil
        #expect(state.inheritedSelectionId == nil)
    }
}

extension SidebarDeleteTests {
    @Test func theBatchStepIsNamedByHowManyItemsItHolds() {
        let name = UndoableChange.named("Move", count: 3, one: "Item to Trash", many: "Items to Trash")
        #expect(name == "Move 3 Items to Trash")
    }
}
