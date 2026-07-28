import SwiftUI

private struct DocumentDeleteActionParams: Encodable {
    let docId: String

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
    }
}

// MARK: - Delete Actions

extension LibraryView {
    /// Prompt user to confirm deletion of selected documents
    func promptDeleteSelected() {
        let selectedDocs = filteredDocuments.filter { selection.contains($0.id) }
        guard !selectedDocs.isEmpty else { return }
        documentsToDelete = selectedDocs
        showDeleteConfirmation = true
    }

    /// Perform the actual deletion after confirmation
    func performDeleteSelected() async {
        guard let library = libraryManager.getLibrary(id: windowState.libraryId) else { return }
        for doc in documentsToDelete {
            do {
                _ = try await library.actionsService.invokeAction(
                    name: "document.delete",
                    params: DocumentDeleteActionParams(docId: doc.id)
                )
            } catch {
                ErrorService.shared.reportError(
                    ErrorModel.fileSystemError(
                        message: "Failed to delete \"\(doc.name)\".",
                        context: [
                            "operation": "delete_document",
                            "document_id": doc.id,
                            "underlying_error": error.localizedDescription
                        ]
                    )
                )
            }
        }
        // Clear selection for deleted items
        for doc in documentsToDelete {
            selection.remove(doc.id)
        }
        documentsToDelete = []
        await library.documentStore.refresh()
    }

    /// Return-to-open (#4160): acts on the KEYBOARD CURSOR row (visual order,
    /// never Set hash order) and matches double-click exactly — navigate into
    /// containers, otherwise show in the detail pane.
    func openSelectedDocument() {
        guard let primaryId = orderedPrimarySelectionId else { return }
        if isShowingEntitiesCollection,
           let entity = filteredEntities.first(where: { entitySelectionId(for: $0) == primaryId }) {
            focusEntityIfPossible(entity)
            return
        }
        guard let doc = navigableDocument(for: primaryId) else { return }
        openDocument(doc)
    }

    /// Select all visible documents
    func selectAll() {
        if isShowingEntitiesCollection {
            selection = Set(filteredEntities.map { entitySelectionId(for: $0) })
        } else {
            selection = Set(filteredDocuments.map(\.id))
        }
    }
}
