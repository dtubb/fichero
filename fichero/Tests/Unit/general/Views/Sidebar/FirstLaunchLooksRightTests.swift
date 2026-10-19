@testable import Fichero
import FicheroAPIClient
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

    @Test("an empty folder: blank in every mode (no header, no placeholder rows, #5826), '0 items', no words")
    func emptyFolder() {
        for mode in [ViewDisplayMode.list, .table, .icon] {
            #expect(!LibraryEmptyFolder.showsTable(mode))
        }
        #expect(LibraryEmptyFolder.footer(count: 0) == "0 items")
        #expect(LibraryEmptyFolder.footer(count: 1) == "1 item")
        #expect(LibraryEmptyFolder.looksLikeAnEmptyFolder(.noCollectionSelected), "a folder being browsed")
        #expect(!LibraryEmptyFolder.looksLikeAnEmptyFolder(.filteredOut(query: "x")), "a filter keeps its message")
        #expect(!LibraryEmptyFolder.looksLikeAnEmptyFolder(.searchFoundNothing(query: "x")))
    }

    // MARK: 5. The always-there project's root is never a destination

    @Test("whatever selects the always-there project's root selects its Sources; anything else routes as itself")
    func alwaysThereRootRoutesToSources() {
        let sources = Document(id: "src", docType: .folder, name: OpeningSelection.sourcesFolderName)
        let workflows = Document(id: SidebarTopOrder.workflowsFolderId, docType: .folder, name: "Workflows")
        let root = SidebarDestination.library(LibraryManager.globalLibraryId)
        #expect(OpeningSelection.destination(for: root, alwaysThereRoots: [workflows, sources]) == .document("src"))
        // Before its top level loads there is nowhere to go, so nothing is selected, never the root.
        #expect(OpeningSelection.destination(for: root, alwaysThereRoots: []) == nil)
        // Another project's root, and any other row, route as themselves.
        let project = SidebarDestination.library(UUID())
        #expect(OpeningSelection.destination(for: project, alwaysThereRoots: [sources]) == project)
        #expect(OpeningSelection.destination(for: .document("x"), alwaysThereRoots: [sources]) == .document("x"))
        // A window that restored the root opens on Sources instead.
        #expect(root.serializedID == OpeningSelection.alwaysThereRootId)
        #expect(OpeningSelection.selectionId(restoredId: OpeningSelection.alwaysThereRootId, viewModeType: "library",
                                             roots: [workflows, sources]) == "doc:src")
    }

    // MARK: 6. Workflows › Default Workflows, never a second top-level row

    @Test("a root the engine has moved into a folder sits in that folder only, by the folder's newer listing")
    func movedRootFollowsItsFolder() {
        let store = DocumentStore(apiClient: APIClient(client: FicheroClient(libraryPath: nil)))
        let defaults = Document(id: Document.defaultWorkflowsContainerID, docType: .folder, name: "Default Workflows")
        let workflows = Document(id: SidebarTopOrder.workflowsFolderId, docType: .folder, name: "Workflows")
        let sources = Document(id: "src", docType: .folder, name: OpeningSelection.sourcesFolderName)
        // Roots fetched before the move still list Default Workflows at the top; the Workflows folder's listing,
        // fetched since, has it inside.
        store.collections = [sources, workflows, defaults]
        var moved = defaults
        moved.parentId = workflows.id
        store.childrenCache[workflows.id] = [moved]
        let docs = store.sidebarDocuments
        #expect(docs.filter { $0.id == defaults.id }.map(\.parentId) == [workflows.id])
        let tree = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: Self.lib)
        #expect(tree.map(\.name).sorted() == ["Sources", "Workflows"])
        #expect(tree.first { $0.name == "Workflows" }?.children?.map(\.name) == ["Default Workflows"])
    }
}
