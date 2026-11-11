@testable import Fichero
import Foundation
import Testing

/// A sidebar row is skipped when nothing it draws changed, and rebuilt when anything in its
/// subtree did (#4228). The selected-row case keeps the whole selection, so a context menu on a
/// selected row still acts on every selected row (#6528).
@MainActor
@Suite("Sidebar rows rebuild only when what they draw changed (#4228)")
struct SidebarRowSkipTests {

    private let libraryId = UUID()

    private func folder(_ id: String, children: [SidebarItem]? = nil) -> SidebarItem {
        var item = SidebarItem.fromDocument(Document(id: id, parentId: nil, docType: .folder, name: id), libraryId: libraryId)
        item.children = children
        return item
    }

    private func key(
        _ item: SidebarItem, selection: Set<String>, selected: String? = nil, expanded: Set<String> = []
    ) -> SidebarRowInputs {
        SidebarRowInputs(
            item: item,
            selection: Set(selection.compactMap { SidebarDestination(serializedID: $0) }),
            selectedItemId: selected,
            expanded: expanded,
            mergeAbove: false,
            mergeBelow: false
        )
    }

    @Test("a click on another row leaves an unselected row's key unchanged")
    func clickElsewhereSkipsTheRow() {
        let row = folder("a")
        let other = folder("b").id
        #expect(key(row, selection: []) == key(row, selection: [other], selected: other))
    }

    @Test("selecting a child changes its expanded parent's key")
    func childSelectionRebuildsTheParent() {
        let child = folder("c")
        let parent = folder("p", children: [child])
        #expect(key(parent, selection: []) != key(parent, selection: [child.id], selected: child.id))
    }

    @Test("a selected row is rebuilt when another row joins the selection")
    func selectedRowSeesTheWholeSelection() {
        let row = folder("a")
        let other = folder("b").id
        #expect(key(row, selection: [row.id], selected: row.id)
            != key(row, selection: [row.id, other], selected: row.id))
    }

    @Test("expanding a descendant changes the key; expanding elsewhere does not")
    func expansionIsScopedToTheSubtree() {
        let child = folder("c")
        let parent = folder("p", children: [child])
        #expect(key(parent, selection: [], expanded: []) != key(parent, selection: [], expanded: [child.id]))
        #expect(key(parent, selection: [], expanded: []) == key(parent, selection: [], expanded: ["elsewhere"]))
    }

    @Test("a renamed row is rebuilt")
    func renameRebuildsTheRow() {
        let before = folder("a")
        let after = SidebarItem.fromDocument(
            Document(id: "a", parentId: nil, docType: .folder, name: "renamed"), libraryId: libraryId
        )
        #expect(key(before, selection: []) != key(after, selection: []))
    }
}
