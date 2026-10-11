@testable import Fichero
import Foundation
import SwiftUI
import Testing

/// Daniel's first launch on a Dev Local build (2026-10-11): what he saw wrong, each pinned.
@MainActor
struct FirstLaunchLooksRightTests {
    private static let lib = UUID()

    // MARK: 1. Sidebar shown, Sources selected, whatever an old window left

    @Test("a first launch is no project known but the always-there one, before first run is done")
    func whatAFirstLaunchIs() {
        #expect(OpeningSelection.isFirstLaunch(firstRunCompleted: false, knownProjectPaths: []))
        #expect(OpeningSelection.isFirstLaunch(
            firstRunCompleted: false, knownProjectPaths: ["/Users/ana/Library/Containers/x/\(AlwaysThereProject.packageName)"]))
        #expect(!OpeningSelection.isFirstLaunch(firstRunCompleted: false, knownProjectPaths: ["/Users/ana/Box 4.fichero"]))
        #expect(!OpeningSelection.isFirstLaunch(firstRunCompleted: true, knownProjectPaths: []))
    }

    @Test("a first launch resets an old window's state: the sidebar shown, Items, nothing of its own selected")
    func firstLaunchState() {
        let fresh = OpeningSelection.FirstLaunchState()
        #expect(fresh.columnVisibilityRaw == 2)
        #if os(macOS)
        #expect(ContentView.restoredColumnVisibility(from: fresh.columnVisibilityRaw) == .all, "the sidebar is shown")
        #endif
        #expect(fresh.viewModeType == "library" && fresh.viewModeItemId == nil && fresh.selectedItemId == nil)
        // With nothing of its own selected, the window opens on Sources, never Workflows.
        let sources = Document(id: "src", docType: .folder, name: OpeningSelection.sourcesFolderName)
        let workflows = Document(id: SidebarTopOrder.workflowsFolderId, docType: .folder, name: "Workflows")
        #expect(OpeningSelection.selectionId(restoredId: fresh.selectedItemId, viewModeType: fresh.viewModeType,
                                             roots: [workflows, sources]) == "doc:src")
    }

    // MARK: 2. Trash lines up with Sources and Workflows

    @Test("the Trash row's label is the folder rows' label: the same icon width and spacing, one pair of numbers")
    func trashLinesUp() {
        // The folder rows (`SidebarItemRow.itemLabel`, `SidebarRowLabelCore`) and the node rows (`SidebarNodeLabel`)
        // take these from one place, so a change to one moves both.
        #expect(SidebarNodeLabel.spacing == 6)
        #expect(SidebarNodeLabel.iconWidth == 16)
        #expect(SidebarTrashRow.name == "Trash")
    }

    // MARK: 3. Sources, then Workflows, then Trash

    @Test("a section's top-level items read Sources, then Workflows, then the rest in the engine's order")
    func topOrder() {
        let inbox = SidebarItem.fromDocument(Document(id: "inbox", docType: .folder, name: "Inbox"), libraryId: Self.lib)
        let workflows = SidebarItem.fromDocument(
            Document(id: SidebarTopOrder.workflowsFolderId, docType: .folder, name: "Workflows"), libraryId: Self.lib)
        let sources = SidebarItem.fromDocument(
            Document(id: "src", docType: .folder, name: OpeningSelection.sourcesFolderName), libraryId: Self.lib)
        let letter = SidebarItem.fromDocument(Document(id: "l1", docType: .file, name: "Letter.pdf"), libraryId: Self.lib)
        #expect(SidebarTopOrder.ordered([inbox, letter, workflows, sources]).map(\.id)
                == [sources.id, workflows.id, inbox.id, letter.id])
        // A folder named Sources inside another folder is not the project's Sources.
        #expect(SidebarTopOrder.rank(Document(id: "x", parentId: "inbox", docType: .folder, name: "Sources")) == 2)
        // And the order holds through the bucket the section is drawn from.
        #expect(SidebarProjectNode.order.last == .trash, "Trash is drawn after every item")
    }

    @Test("Default Workflows, now inside the root Workflows folder, is still locked; Workflows itself is not")
    func defaultWorkflowsOneLevelDown() {
        let workflows = Document(id: SidebarTopOrder.workflowsFolderId, docType: .folder, name: "Workflows")
        let defaults = Document(id: Document.defaultWorkflowsContainerID, parentId: workflows.id, docType: .folder,
                                name: "Default Workflows")
        let preset = Document(id: "books", parentId: defaults.id, docType: .folder, name: "Books")
        let mine = Document(id: "mine", parentId: workflows.id, docType: .folder, name: "My workflows")
        let byId = Dictionary(uniqueKeysWithValues: [workflows, defaults, preset, mine].map { ($0.id, $0) })
        #expect(defaults.isDefaultWorkflowFolder(resolveParent: { byId[$0] }))
        #expect(preset.isDefaultWorkflowFolder(resolveParent: { byId[$0] }), "a preset under it is locked")
        #expect(!workflows.isDefaultWorkflowFolder(resolveParent: { byId[$0] }), "the person's Workflows folder is not")
        #expect(!mine.isDefaultWorkflowFolder(resolveParent: { byId[$0] }))
    }

    // MARK: 4. An empty folder looks like an empty Finder window

    @Test("an empty folder: the table's header and stripes in list and table, blank in icon, '0 items', and a drop target")
    func emptyFolder() {
        #expect(LibraryEmptyFolder.showsTable(.list) && LibraryEmptyFolder.showsTable(.table))
        #expect(!LibraryEmptyFolder.showsTable(.icon))
        #expect(LibraryEmptyFolder.footer(count: 0) == "0 items")
        #expect(LibraryEmptyFolder.footer(count: 1) == "1 item")
        #expect(LibraryEmptyFolder.dropHint == "Drop files or folders here to import")
        #expect(LibraryEmptyFolder.looksLikeAnEmptyFolder(.noCollectionSelected), "a folder being browsed")
        #expect(!LibraryEmptyFolder.looksLikeAnEmptyFolder(.filteredOut(query: "x")), "a filter keeps its message")
        #expect(!LibraryEmptyFolder.looksLikeAnEmptyFolder(.searchFoundNothing(query: "x")))
    }
}
