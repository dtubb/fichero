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
        let child = item("c", "Child")
        // The delete of the only child leaves the PARENT selected (Finder rule: no sibling, so the parent), in the row ids
        // the sidebar uses ("doc:<id>", as `item.id` and `selectedItemId` have them) ...
        let inherited = selectionAfterDelete(deleted: child.id, siblings: [child.id], parent: parent.id)
        #expect(inherited == parent.id)
        // ... and the next Backspace, "-" or Edit > Delete finds nothing to delete.
        #expect(sidebarDeleteTargets([parent], inheritedSelectionId: inherited).isEmpty)
    }

    @Test func aRowThePersonSelectsIsTheirsToDelete() {
        let parent = item("p", "Parent")
        #expect(sidebarDeleteTargets([parent], inheritedSelectionId: nil).map(\.id) == [parent.id])
        #expect(sidebarDeleteTargets([parent], inheritedSelectionId: "doc:other").map(\.id) == [parent.id])
    }

    @Test func aMultiSelectionKeepsEveryRowButTheInheritedOne() {
        let rows = [item("a", "A"), item("b", "B")]
        #expect(sidebarDeleteTargets(rows, inheritedSelectionId: rows[0].id).map(\.id) == [rows[1].id])
    }

    @Test func theRowIdsTheSelectionRuleGetsAreTheSidebarsOwn() {
        #expect(item("c", "Child").id == SidebarDestination.document("c").serializedID)
    }

    @Test func theInheritedRowSurvivesOnlyTheListEchoingItAndClearsOnAnyOtherSelection() {
        #expect(inheritedSelection(afterProposing: ["p"], inherited: "p") == "p")
        #expect(inheritedSelection(afterProposing: ["other"], inherited: "p") == nil)
        #expect(inheritedSelection(afterProposing: ["p", "other"], inherited: "p") == nil)
        #expect(inheritedSelection(afterProposing: [], inherited: "p") == nil)
        #expect(inheritedSelection(afterProposing: ["p"], inherited: nil) == nil)
    }
}

extension SidebarDeleteTests {
    @Test func theBatchStepIsNamedByHowManyItemsItHolds() {
        let name = UndoableChange.named("Move", count: 3, one: "Item to Trash", many: "Items to Trash")
        #expect(name == "Move 3 Items to Trash")
    }
}

extension SidebarDeleteTests {
    /// The owner's case (2026-10-26): the sidebar showed the child selected while Edit > Delete acted on the Items list's
    /// selection (the parent). Whatever the menu will take is NAMED in its title before it is pressed.
    @Test func theDeleteMenuAndItsConfirmationNameWhatTheyWillTake() {
        #expect(ItemVerbs.deleteTitle(1, name: "Parent") == "Delete “Parent”")
        #expect(ItemVerbs.deleteTitle(1) == "Delete")
        #expect(ItemVerbs.deleteTitle(3, name: "Parent") == "Delete 3 Items")
    }
}
