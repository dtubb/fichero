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

    /// Open the first selected document in the inspector
    func openSelectedDocument() {
        guard let firstId = selection.first else { return }
        if isShowingEntitiesCollection,
           let entity = filteredEntities.first(where: { entitySelectionId(for: $0) == firstId }) {
            focusEntityIfPossible(entity)
            return
        }
        guard let doc = filteredDocuments.first(where: { $0.id == firstId }) else { return }
        detailDocument = doc
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
