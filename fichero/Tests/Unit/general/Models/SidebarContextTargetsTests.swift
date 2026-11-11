@testable import Fichero
import Foundation
import Testing

/// `sidebar.context-menu.acts-on-the-clicked-row` (#6528)
struct SidebarContextTargetsTests {
    private func makeItem(_ id: String, children: [SidebarItem]? = nil) -> SidebarItem {
        var item = SidebarItem.fromDocument(Document(id: id, docType: .folder, name: id), libraryId: UUID())
        item.children = children
        return item
    }

    @Test("a child row acts on itself, never on its parent")
    func childRowActsOnItself() {
        #expect(sidebarContextTargetIds(clicked: "child", selection: ["parent"]) == ["child"])
        #expect(sidebarContextTargetIds(clicked: "child", selection: []) == ["child"])
    }

    @Test("a row inside a multi-selection acts on the whole selection")
    func rowInsideSelectionActsOnSelection() {
        #expect(sidebarContextTargetIds(clicked: "b", selection: ["a", "b", "c"]) == ["a", "b", "c"])
    }

    @Test("a row outside the selection acts on itself alone")
    func rowOutsideSelectionActsAlone() {
        #expect(sidebarContextTargetIds(clicked: "z", selection: ["a", "b"]) == ["z"])
    }

    @Test("a lone selected row acts on itself")
    func loneSelectedRow() {
        #expect(sidebarContextTargetIds(clicked: "a", selection: ["a"]) == ["a"])
    }

    @Test("an expanded group does not carry the menu; a collapsed or childless one does")
    func groupCarriesMenuOnlyWithoutChildRows() {
        let parent = makeItem("parent", children: [makeItem("child")])
        #expect(!sidebarGroupCarriesContextMenu(parent, isExpanded: true))
        #expect(sidebarGroupCarriesContextMenu(parent, isExpanded: false))
        #expect(sidebarGroupCarriesContextMenu(makeItem("empty", children: []), isExpanded: true))
    }

    /// `sidebar.selection.a-click-on-a-child-never-selects-its-parent` (#6534)
    @Test("an expanded row's fallback tap does not act, so a click on a child never reaches the parent")
    func expandedRowFallbackTapDoesNotAct() {
        let parent = makeItem("parent", children: [makeItem("child")])
        #expect(!sidebarFallbackTapActs(parent, true))
        #expect(sidebarFallbackTapActs(parent, false))
        #expect(sidebarFallbackTapActs(makeItem("leaf"), true))
    }

    /// `sidebar.selection.an-expanded-folder-selects-from-its-name`
    @Test("an expanded folder's name takes the click the whole row gives up, and exactly one handler acts")
    func expandedFolderNameTakesTheClick() {
        let parent = makeItem("parent", children: [makeItem("child")])
        let leaf = makeItem("leaf")
        #expect(sidebarExpandedLabelTapActs(parent, true))
        #expect(!sidebarExpandedLabelTapActs(parent, false))
        #expect(!sidebarExpandedLabelTapActs(leaf, true))
        for item in [parent, leaf] {
            for expanded in [true, false] {
                #expect(sidebarExpandedLabelTapActs(item, expanded) != sidebarFallbackTapActs(item, expanded))
            }
        }
    }

    @Test("a Command click on a selected child takes it out, and the parent stays out")
    func commandClickOnSelectedChildDeselectsIt() {
        let parent = SidebarDestination.document("parent")
        let first = SidebarDestination.document("first")
        let second = SidebarDestination.document("second")
        let out = sidebarFallbackProposal(
            clicked: first, current: [first, second], anchor: first, orderedSiblings: [first, second],
            modifiers: (shift: false, command: true))
        #expect(out == [second])
        #expect(!out.contains(parent))
    }

    @Test("a Command click on an unselected child adds it alone; a Shift click extends a continuous range")
    func commandAddsOneAndShiftExtendsARange() {
        let first = SidebarDestination.document("first")
        let second = SidebarDestination.document("second")
        let third = SidebarDestination.document("third")
        let siblings = [first, second, third]
        let added = sidebarFallbackProposal(
            clicked: third, current: [first], anchor: first, orderedSiblings: siblings,
            modifiers: (shift: false, command: true))
        let ranged = sidebarFallbackProposal(
            clicked: third, current: [first], anchor: first, orderedSiblings: siblings,
            modifiers: (shift: true, command: false))
        #expect(added == [first, third])
        #expect(ranged == [first, second, third])
    }
}
