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
}
