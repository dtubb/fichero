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
