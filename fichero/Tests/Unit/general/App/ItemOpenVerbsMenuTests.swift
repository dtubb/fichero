import Foundation
@testable import Fichero
import Testing

/// #5652 slice 4, group 2: Open, Open in New Tab, Open in New Window, Duplicate, Make Alias, Show Original in Finder,
/// Quick Look and New Folder are one item each, which the sidebar's and the Items list's context menus and File
/// render on one `ItemVerbsTarget`. What breaks without these: a File item on when it can do nothing (or off with no
/// word), the open items calling something other than the surface's own open, or the sidebar's selection in File
/// reaching the wrong action.
@MainActor
@Suite("Opening, copying and finding an item, one component each (#5652 slice 4)")
struct ItemOpenVerbsMenuTests {
    private let page = Document(id: "p1", docType: .file, fileType: .image, name: "0970.jpg")
    private let folder = Document(id: "f1", docType: .folder, name: "Letters")

    private func target(_ documents: [Document]) -> ItemVerbsTarget {
        var target = ItemVerbsTarget(ids: documents.map(\.id), documents: documents)
        if documents.count == 1 {
            target.open = {}
            target.openInNewTab = {}
            target.openInNewWindow = {}
            target.duplicate = {}
            target.makeAlias = {}
            if documents.first?.docType != .folder { target.quickLook = {} }
        }
        return target
    }

    @Test("one document: every verb acts")
    func oneDocument() {
        let one = target([page])
        #expect(ItemVerbs.openReason(one, action: one.open) == nil)
        #expect(ItemVerbs.openReason(one, action: one.openInNewTab) == nil)
        #expect(ItemVerbs.duplicateReason(one) == nil)
        #expect(ItemVerbs.makeAliasReason(one) == nil)
        #expect(ItemVerbs.quickLookReason(one) == nil)
        #expect(ItemVerbs.revealReason(one, revealable: { _ in true }) == nil)
    }

    @Test("nothing, several, or a folder: each says why it cannot act")
    func reasons() {
        #expect(ItemVerbs.openReason(nil, action: nil) == ItemVerbs.nothingSelected)
        let two = target([page, folder])
        #expect(ItemVerbs.openReason(two, action: two.open) == "Select one item to open")
        #expect(ItemVerbs.duplicateReason(two) == "Select one item to duplicate")
        #expect(ItemVerbs.makeAliasReason(two) == "Select one item to make an alias of")
        #expect(ItemVerbs.quickLookReason(target([folder])) == "A folder has no file to preview")
        #expect(ItemVerbs.revealReason(target([page]), revealable: { _ in false }) == "Its original is not on this Mac")
        #expect(ItemVerbs.revealReason(two, revealable: { _ in true }) == "Select one document to show in Finder")
        // A pane whose own menu has the verb but whose selection does not: it says where.
        let bare = ItemVerbsTarget(ids: ["doc:p1"], documents: [page])
        #expect(ItemVerbs.duplicateReason(bare) == "Select it in Items to duplicate it")
        #expect(ItemVerbs.openReason(bare, action: bare.open) == "This item does not open here")
    }

    @Test("the open items call the surface's own open, new tab and new window")
    func openingTarget() {
        var calls: [String] = []
        let target = ItemVerbsTarget.opening(
            id: "", open: { calls.append("open") }, openInNewTab: { calls.append("tab") },
            openInNewWindow: { calls.append("window") }
        )
        target.open?()
        target.openInNewTab?()
        target.openInNewWindow?()
        #expect(calls == ["open", "tab", "window"])
        let noOpen = ItemVerbsTarget.opening(id: "", open: nil, openInNewTab: {}, openInNewWindow: {})
        #expect(noOpen.open == nil && noOpen.openInNewTab != nil)
    }

    @Test("File on the sidebar's selection opens it through the sidebar's own actions")
    func sidebarOpens() {
        var calls: [String] = []
        let actions = SidebarActions(
            createFolder: {}, importFiles: { _ in }, renameItem: {}, deleteItem: {},
            createChat: {}, createWorkflow: {}, createChain: {}, createComparison: {}, createSchedule: {},
            createTrigger: {}, openSelectionInNewTab: { calls.append("tab") },
            openSelectionInNewWindow: { calls.append("window") }
        )
        let row = SidebarItem(
            id: "doc:p1", name: page.name, icon: "doc", category: .folder, itemType: .document(page),
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
        let info = SidebarSelectionInfo(selectedItem: row, canRename: true, canDelete: true, deletableCount: 1)
        let sidebar = FocusedItemVerbs.target(items: nil, actions: actions, info: info)
        sidebar?.openInNewTab?()
        sidebar?.openInNewWindow?()
        #expect(calls == ["tab", "window"])
        // Duplicate and Make Alias are the row's own (per row, across projects): the sidebar's selection says so.
        #expect(ItemVerbs.duplicateReason(sidebar) == "Select it in Items to duplicate it")
    }

    @Test("titles are the Finder words")
    func titles() {
        #expect([ItemVerbs.openTitle, ItemVerbs.openInNewTabTitle, ItemVerbs.openInNewWindowTitle,
                  ItemVerbs.duplicateTitle, ItemVerbs.makeAliasTitle, ItemVerbs.quickLookTitle, ItemVerbs.newFolderTitle]
            == ["Open", "Open in New Tab", "Open in New Window", "Duplicate", "Make Alias", "Quick Look", "New Folder"])
    }
}
