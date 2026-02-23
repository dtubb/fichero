import SwiftUI

// MARK: - Keyboard Shortcuts Extension

extension LibraryView {
    // Applies keyboard shortcut handlers to the LibraryView content
    // swiftlint:disable:next function_body_length
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
            .onKeyPress(characters: .alphanumerics.union(.punctuationCharacters)) { keyPress in
                // Skip if a rename is in progress
                guard renamingDocumentId == nil else { return .ignored }
                handleTypeToSelect(keyPress.characters)
                return .handled
            }
            .onKeyPress(.upArrow) {
                handleArrowKey(direction: .upDir)
            }
            .onKeyPress(.downArrow) {
                handleArrowKey(direction: .down)
            }
            .onKeyPress(.leftArrow) {
                handleArrowKey(direction: .left)
            }
            .onKeyPress(.rightArrow) {
                handleArrowKey(direction: .right)
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

    // MARK: - Arrow Key Navigation

    enum ArrowDirection {
        case upDir, down, left, right
    }

    /// Handle arrow key press for navigating documents in icon/grid view.
    /// List and Table views get native arrow key support from AppKit.
    func handleArrowKey(direction: ArrowDirection) -> KeyPress.Result {
        let docs = filteredDocuments
        guard !docs.isEmpty else { return .ignored }

        // List/table modes get native AppKit arrow key handling — don't interfere
        if displayMode == .list || displayMode == .table {
            return .ignored
        }

        // Find the current selection index
        let currentIndex: Int
        if let firstSelected = selection.first,
           let index = docs.firstIndex(where: { $0.id == firstSelected }) {
            currentIndex = index
        } else {
            // Nothing selected — select first document
            selection = [docs[0].id]
            selectionAnchor = docs[0].id
            return .handled
        }

        // Calculate the target index based on direction and display mode
        let step: Int
        switch direction {
        case .left:
            step = -1
        case .right:
            step = 1
        case .upDir:
            // In icon/grid mode, move up by column count; in map mode, move by 1
            step = displayMode == .icon ? -gridColumnCount : -1
        case .down:
            step = displayMode == .icon ? gridColumnCount : 1
        }

        let targetIndex = currentIndex + step

        // Bounds check
        guard targetIndex >= 0, targetIndex < docs.count else { return .handled }

        let targetDoc = docs[targetIndex]
        let modifiers = NSEvent.modifierFlags

        if modifiers.contains(.shift) {
            // Shift+Arrow: extend selection from anchor to target
            if let anchor = selectionAnchor,
               let anchorIndex = docs.firstIndex(where: { $0.id == anchor }) {
                let range = min(anchorIndex, targetIndex)...max(anchorIndex, targetIndex)
                selection = Set(docs[range].map(\.id))
            } else {
                selection.insert(targetDoc.id)
                selectionAnchor = targetDoc.id
            }
        } else {
            // Plain arrow: move selection
            selection = [targetDoc.id]
            selectionAnchor = targetDoc.id
        }

        return .handled
    }

    // MARK: - Type-to-Select

    /// Handle a typed character for type-to-select navigation
    func handleTypeToSelect(_ characters: String) {
        // Cancel any pending reset timer
        typeSelectTask?.cancel()

        // Append to the buffer
        typeSelectBuffer += characters.lowercased()

        // Find the first document whose name starts with the buffer
        if let match = filteredDocuments.first(where: {
            $0.name.lowercased().hasPrefix(typeSelectBuffer)
        }) {
            selection = [match.id]
        }

        // Reset buffer after 0.5s of inactivity
        typeSelectTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(500))
            guard !Task.isCancelled else { return }
            typeSelectBuffer = ""
        }
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
