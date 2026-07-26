@testable import Fichero
import Foundation
import Testing

struct SidebarDeleteAlertsTests {
    @Test("delete copy uses trash semantics for regular documents")
    func regularDocumentCopyMentionsTrash() {
        let document = Document(id: "doc-1", docType: .folder, name: "Folder")
        let item = SidebarItem.fromDocument(document, libraryId: UUID())

        let message = sidebarDeleteConfirmationMessage(for: item)

        #expect(message.contains("Trash"))
        #expect(message.contains("put it back later"))
    }

    @Test("delete copy keeps linked-file explanation")
    func linkedDocumentCopyKeepsDiskSafetyNote() {
        let document = Document(
            id: "doc-2",
            docType: .file,
            fileType: .pdf,
            name: "Paper",
            path: "/tmp/paper.pdf",
            metadata: ["ingest_mode": AnyCodable("link")]
        )
        let item = SidebarItem.fromDocument(document, libraryId: UUID())

        let message = sidebarDeleteConfirmationMessage(for: item)

        #expect(message.contains("stays on disk"))
        #expect(message.contains("/tmp/paper.pdf"))
    }

    // MARK: - Batch (multi-selection) delete

    private func makeItem(_ id: String, _ name: String) -> SidebarItem {
        SidebarItem.fromDocument(Document(id: id, docType: .folder, name: name), libraryId: UUID())
    }

    @Test("batch delete title counts items; single names it")
    func batchTitleUsesCount() {
        #expect(sidebarDeleteConfirmationTitle(for: []) == "Delete?")
        #expect(sidebarDeleteConfirmationTitle(for: [makeItem("a", "Alpha")]) == "Delete \"Alpha\"?")
        #expect(
            sidebarDeleteConfirmationTitle(for: [makeItem("a", "Alpha"), makeItem("b", "Beta")])
                == "Delete 2 items?"
        )
    }

    @Test("batch delete message counts items; single reuses per-item copy")
    func batchMessageUsesCount() {
        let batch = sidebarDeleteConfirmationMessage(for: [makeItem("a", "A"), makeItem("b", "B")])
        #expect(batch == "Move 2 items to Trash? You can put them back later.")
        // One item falls back to the existing per-item message.
        let single = sidebarDeleteConfirmationMessage(for: [makeItem("a", "Alpha")])
        #expect(single.contains("\"Alpha\""))
    }

    @Test("deletable filter drops non-deletable rows (library headers)")
    func deletableFilterDropsHeaders() {
        let doc = makeItem("a", "Alpha")
        let header = SidebarItem(
            id: "lib:x", name: "Lib", icon: "book", category: .library, itemType: .libraryHeader,
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
        let deletable = sidebarDeletableItems([doc, header])
        #expect(deletable.map(\.id) == ["doc:a"])
    }

    // MARK: - Context-menu delete targets (Finder semantics)

    @Test("right-click inside a multi-selection targets the whole selection")
    func contextDeleteInsideSelectionTargetsAll() {
        let alpha = makeItem("a", "Alpha")
        let beta = makeItem("b", "Beta")
        let targets = sidebarContextDeleteTargets(clicked: alpha, selection: [alpha, beta])
        #expect(targets.map(\.id) == ["doc:a", "doc:b"])
    }

    @Test("right-click outside the selection targets only the clicked row")
    func contextDeleteOutsideSelectionTargetsClicked() {
        let alpha = makeItem("a", "Alpha")
        let beta = makeItem("b", "Beta")
        let gamma = makeItem("c", "Gamma")
        let targets = sidebarContextDeleteTargets(clicked: gamma, selection: [alpha, beta])
        #expect(targets.map(\.id) == ["doc:c"])
    }

    @Test("single-row selection behaves like a lone row")
    func contextDeleteSingleSelection() {
        let alpha = makeItem("a", "Alpha")
        let targets = sidebarContextDeleteTargets(clicked: alpha, selection: [alpha])
        #expect(targets.map(\.id) == ["doc:a"])
    }

    @Test("non-deletable rows are dropped from a batch target")
    func contextDeleteFiltersNonDeletable() {
        let alpha = makeItem("a", "Alpha")
        let header = SidebarItem(
            id: "lib:x", name: "Lib", icon: "book", category: .library, itemType: .libraryHeader,
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
        let targets = sidebarContextDeleteTargets(clicked: alpha, selection: [alpha, header])
        #expect(targets.map(\.id) == ["doc:a"])
    }

    @Test("all-non-deletable selection falls back to the clicked row")
    func contextDeleteAllNonDeletableFallsBack() {
        let headerA = SidebarItem(
            id: "lib:x", name: "LibX", icon: "book", category: .library, itemType: .libraryHeader,
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
        let headerB = SidebarItem(
            id: "lib:y", name: "LibY", icon: "book", category: .library, itemType: .libraryHeader,
            children: nil, libraryId: UUID(), folderPath: "/", sortOrder: 0, isFolder: false
        )
        let targets = sidebarContextDeleteTargets(clicked: headerA, selection: [headerA, headerB])
        #expect(targets.map(\.id) == ["lib:x"])
    }

    /// Every delete entry point — Delete key, Edit ▸ Delete (⌘⌫), and the
    /// bottom-toolbar remove button — must share ONE batch path. A previous
    /// split (menu/toolbar → single-item delete, key → batch) silently
    /// narrowed a multi-selection delete to just the primary row.
    @Test("menu, toolbar, and Delete key share one batch delete path")
    func allDeleteEntryPointsShareBatchPath() throws {
        let actions = try appSource("Views/Sidebar/Components/SidebarActions.swift")
        #expect(!actions.contains("func handleDeleteSelectedItem"))

        let focusedConfig = try appSource("Views/Sidebar/SidebarView.swift")
        #expect(focusedConfig.contains("deleteItem: handleDeleteSelection,"))

        let toolbarConfig = try appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        #expect(toolbarConfig.contains("deleteItem: handleDeleteSelection,"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @MainActor
    @Test("DeleteStateManager batch confirmation sets items and shows dialog")
    func deleteStateBatchConfirmation() {
        let state = DeleteStateManager()
        state.showDeleteConfirmation(for: [makeItem("a", "A"), makeItem("b", "B")])
        #expect(state.itemsToDelete.count == 2)
        #expect(state.itemToDelete == nil)            // batch → no single convenience item
        #expect(state.showingDeleteConfirmation)
        // A single-item confirmation keeps the convenience accessor populated.
        state.showDeleteConfirmation(for: makeItem("c", "C"))
        #expect(state.itemToDelete?.id == "doc:c")
        // Empty is a no-op; cancel clears.
        state.cancelDelete()
        #expect(state.itemsToDelete.isEmpty)
        #expect(!state.showingDeleteConfirmation)
        state.showDeleteConfirmation(for: [])
        #expect(!state.showingDeleteConfirmation)
    }
}
