import SwiftUI

// MARK: - Inline Editing Extension

extension LibraryView {
    /// Start renaming a document
    func startRename(for document: Document) {
        renamingDocumentId = document.id
        editingName = document.name
    }

    /// Commit the rename
    func commitRename() {
        guard let docId = renamingDocumentId,
              let doc = filteredDocuments.first(where: { $0.id == docId }),
              !editingName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              editingName != doc.name else {
            cancelRename()
            return
        }

        let newName = editingName.trimmingCharacters(in: .whitespacesAndNewlines)
        renamingDocumentId = nil
        editingName = ""

        Task {
            guard let library = libraryManager.globalLibrary else { return }
            do {
                _ = try await library.documentStore.renameDocument(doc, to: newName)
            } catch {
                ErrorService.shared.reportError(
                    ErrorModel.fileSystemError(
                        message: "Failed to rename \"\(doc.name)\" to \"\(newName)\".",
                        context: [
                            "operation": "rename_document",
                            "document_id": doc.id
                        ]
                    )
                )
            }
        }
    }

    /// Cancel the rename
    func cancelRename() {
        renamingDocumentId = nil
        editingName = ""
    }
}

// MARK: - Editable Document Name View

/// A view that shows either a static Text or an editable TextField for document names.
/// Used across all LibraryView display modes for consistent inline editing.
struct EditableDocumentName: View {
    let document: Document
    let isRenaming: Bool
    @Binding var editingName: String
    let font: Font
    let lineLimit: Int
    let alignment: TextAlignment
    let onCommit: () -> Void
    let onCancel: () -> Void

    init(
        document: Document,
        isRenaming: Bool,
        editingName: Binding<String>,
        font: Font = .body,
        lineLimit: Int = 1,
        alignment: TextAlignment = .leading,
        onCommit: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        self.document = document
        self.isRenaming = isRenaming
        self._editingName = editingName
        self.font = font
        self.lineLimit = lineLimit
        self.alignment = alignment
        self.onCommit = onCommit
        self.onCancel = onCancel
    }

    var body: some View {
        if isRenaming {
            TextField("Document name", text: $editingName)
                .font(font)
                .textFieldStyle(.plain)
                .multilineTextAlignment(alignment)
                .onSubmit {
                    onCommit()
                }
                .onKeyPress(.escape) {
                    onCancel()
                    return .handled
                }
                .onAppear {
                    // Focus happens automatically via TextField
                }
        } else {
            // #4416: a page's `name` is the engine's upload temp file.
            Text(DocumentTitle.displayName(for: document))
                .font(font)
                .lineLimit(lineLimit)
                .multilineTextAlignment(alignment)
        }
    }
}
