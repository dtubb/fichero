import SwiftUI

// MARK: - Keyboard Shortcuts Extension

extension LibraryView {
    /// Applies keyboard shortcut handlers to the LibraryView content
    func withKeyboardShortcuts(_ content: some View) -> some View {
        content
            .onDeleteCommand(perform: promptDeleteSelected)
            .onKeyPress(.return) {
                openSelectedDocument()
                return .handled
            }
            .onKeyPress(.space) {
                toggleQuickLook()
                return .handled
            }
            .focusedSceneValue(\.librarySelectAll, !filteredDocuments.isEmpty ? {
                selectAll()
            } : nil)
            .focusedSceneValue(\.libraryDeleteSelection, !selection.isEmpty ? {
                promptDeleteSelected()
            } : nil)
            .confirmationDialog(
                "Delete \(documentsToDelete.count) document\(documentsToDelete.count == 1 ? "" : "s")?",
                isPresented: $showDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    Task {
                        await performDeleteSelected()
                    }
                }
                Button("Cancel", role: .cancel) {
                    documentsToDelete = []
                }
            } message: {
                if documentsToDelete.count == 1, let doc = documentsToDelete.first {
                    Text("Are you sure you want to delete \"\(doc.name)\"? This cannot be undone.")
                } else {
                    Text("Are you sure you want to delete \(documentsToDelete.count) documents? This cannot be undone.")
                }
            }
    }

    // MARK: - Actions

    /// Prompt user to confirm deletion of selected documents
    func promptDeleteSelected() {
        let selectedDocs = filteredDocuments.filter { selection.contains($0.id) }
        guard !selectedDocs.isEmpty else { return }
        documentsToDelete = selectedDocs
        showDeleteConfirmation = true
    }

    /// Perform the actual deletion after confirmation
    private func performDeleteSelected() async {
        guard let library = libraryManager.globalLibrary else { return }
        for doc in documentsToDelete {
            do {
                try await library.documentStore.deleteDocument(doc)
            } catch {
                print("Failed to delete document \(doc.name): \(error)")
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
        guard let firstId = selection.first,
              let doc = filteredDocuments.first(where: { $0.id == firstId }) else { return }
        detailDocument = doc
    }

    /// Toggle quick look for the selected document
    func toggleQuickLook() {
        guard let firstId = selection.first,
              let doc = filteredDocuments.first(where: { $0.id == firstId }) else { return }
        if detailDocument?.id == doc.id {
            detailDocument = nil
        } else {
            detailDocument = doc
        }
    }

    /// Select all visible documents
    func selectAll() {
        selection = Set(filteredDocuments.map(\.id))
    }
}

// MARK: - FocusedValue Keys for Library Actions

/// FocusedValue key for selecting all documents in the library
struct LibrarySelectAllKey: FocusedValueKey {
    typealias Value = () -> Void
}

/// FocusedValue key for deleting selected documents in the library
struct LibraryDeleteSelectionKey: FocusedValueKey {
    typealias Value = () -> Void
}

extension FocusedValues {
    var librarySelectAll: LibrarySelectAllKey.Value? {
        get { self[LibrarySelectAllKey.self] }
        set { self[LibrarySelectAllKey.self] = newValue }
    }

    var libraryDeleteSelection: LibraryDeleteSelectionKey.Value? {
        get { self[LibraryDeleteSelectionKey.self] }
        set { self[LibraryDeleteSelectionKey.self] = newValue }
    }
}
