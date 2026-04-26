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
            .onKeyPress(characters: .alphanumerics.union(.punctuationCharacters)) { keyPress in
                // Skip if a rename is in progress
                guard renamingDocumentId == nil else { return .ignored }
                handleTypeToSelect(keyPress.characters)
                return .handled
            }
            .onKeyPress(.upArrow, phases: .down) { _ in
                handleArrowKey(direction: .upDir)
            }
            .onKeyPress(.downArrow, phases: .down) { _ in
                handleArrowKey(direction: .down)
            }
            .onKeyPress(.leftArrow, phases: .down) { _ in
                handleArrowKey(direction: .left)
            }
            .onKeyPress(.rightArrow, phases: .down) { _ in
                handleArrowKey(direction: .right)
            }
            .onKeyPress(.pageUp, phases: .down) { _ in
                handleArrowKey(direction: .pageUp)
            }
            .onKeyPress(.pageDown, phases: .down) { _ in
                handleArrowKey(direction: .pageDown)
            }
            .onMoveCommand { direction in
                handleMoveCommand(direction)
            }
            .focusedSceneValue(\.librarySelectAll, !filteredDocuments.isEmpty ? {
                selectAll()
            } : nil)
            .focusedSceneValue(\.libraryDeleteSelection, !selection.isEmpty ? {
                promptDeleteSelected()
            } : nil)
            .focusedSceneValue(\.librarySortField, $sortFieldRaw)
            .focusedSceneValue(\.librarySortAscending, $sortAscending)
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
                // #603 Part 2: branch the copy by ingest mode so users see
                // an accurate description of what delete actually does for
                // their file. LINK preserves the original; COPY removes our
                // copy but the user's source file is untouched; MOVE is the
                // only mode where delete is genuinely terminal.
                if documentsToDelete.count == 1, let doc = documentsToDelete.first {
                    switch doc.ingestMode {
                    case .link:
                        if let path = doc.path {
                            Text("Remove the Fichero reference to \"\(doc.name)\"? The original file at \(path) will stay on disk.")
                        } else {
                            Text("Remove the Fichero reference to \"\(doc.name)\"? The original file will stay on disk.")
                        }
                    case .copy:
                        Text("Delete Fichero's copy of \"\(doc.name)\"? The file you imported from is untouched.")
                    case .move:
                        Text("Permanently delete \"\(doc.name)\"? This file was moved into Fichero, so there's no other copy.")
                    }
                } else {
                    let modes = Set(documentsToDelete.map { $0.ingestMode })
                    if modes == [.link] {
                        Text("Remove \(documentsToDelete.count) Fichero references? The original files will stay on disk.")
                    } else if modes == [.move] {
                        Text("Permanently delete \(documentsToDelete.count) documents? These files were moved into Fichero, so there are no other copies.")
                    } else {
                        Text("Delete \(documentsToDelete.count) documents from Fichero? Items imported via LINK reference originals on disk; COPY items are removed; MOVE items are gone for good.")
                    }
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
        guard let firstId = selection.first,
              let doc = filteredDocuments.first(where: { $0.id == firstId }) else { return }
        detailDocument = doc
    }

    /// Select all visible documents
    func selectAll() {
        selection = Set(filteredDocuments.map(\.id))
    }

    // MARK: - Arrow Key Navigation

    enum ArrowDirection {
        case upDir, down, left, right, pageUp, pageDown
    }

    func handleMoveCommand(_ direction: MoveCommandDirection) {
        switch direction {
        case .up:
            _ = handleArrowKey(direction: .upDir)
        case .down:
            _ = handleArrowKey(direction: .down)
        case .left:
            _ = handleArrowKey(direction: .left)
        case .right:
            _ = handleArrowKey(direction: .right)
        default:
            break
        }
    }

    /// Handle arrow key press for navigating documents.
    /// All four arrows navigate within the content area (like Finder).
    /// Tab/Shift+Tab cycle focus between panes.
    func handleArrowKey(direction: ArrowDirection) -> KeyPress.Result {
        let docs = filteredDocuments
        guard !docs.isEmpty else { return .ignored }

        // Select first item if nothing is selected yet
        guard let currentIndex = currentSelectionIndex(in: docs) else {
            selection = [docs[0].id]; selectionAnchor = docs[0].id; return .handled
        }

        let step = stepSize(for: direction)
        guard step != 0 else { return .ignored }
        let targetIndex = currentIndex + step
        guard targetIndex >= 0, targetIndex < docs.count else { return .handled }

        applySelection(targetIndex: targetIndex, docs: docs)
        if displayMode == .icon || displayMode == .list || displayMode == .table {
            listScrollTarget = docs[targetIndex].id
        }
        return .handled
    }

    private func currentSelectionIndex(in docs: [Document]) -> Int? {
        guard let firstSelected = selection.first else { return nil }
        return docs.firstIndex(where: { $0.id == firstSelected })
    }

    private func stepSize(for direction: ArrowDirection) -> Int {
        switch direction {
        case .upDir:  return displayMode == .icon ? -gridColumnCount : -1
        case .down:   return displayMode == .icon ?  gridColumnCount :  1
        case .left:   return -1
        case .right:  return  1
        case .pageUp: return -pageStepSize()
        case .pageDown: return pageStepSize()
        }
    }

    private func pageStepSize() -> Int {
        if displayMode == .icon {
            // Approximate one visual page in icon grid navigation.
            return max(gridColumnCount * 4, gridColumnCount)
        }
        return 10
    }

    private func applySelection(targetIndex: Int, docs: [Document]) {
        let targetDoc = docs[targetIndex]
        if NSEvent.modifierFlags.contains(.shift),
           let anchor = selectionAnchor,
           let anchorIndex = docs.firstIndex(where: { $0.id == anchor }) {
            let range = min(anchorIndex, targetIndex)...max(anchorIndex, targetIndex)
            selection = Set(docs[range].map(\.id))
        } else if NSEvent.modifierFlags.contains(.shift) {
            selection.insert(targetDoc.id)
            selectionAnchor = targetDoc.id
        } else {
            selection = [targetDoc.id]
            selectionAnchor = targetDoc.id
        }
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

/// FocusedValue key for the library sort field binding
struct LibrarySortFieldKey: FocusedValueKey {
    typealias Value = Binding<String>
}

/// FocusedValue key for the library sort direction binding
struct LibrarySortAscendingKey: FocusedValueKey {
    typealias Value = Binding<Bool>
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

    var librarySortField: LibrarySortFieldKey.Value? {
        get { self[LibrarySortFieldKey.self] }
        set { self[LibrarySortFieldKey.self] = newValue }
    }

    var librarySortAscending: LibrarySortAscendingKey.Value? {
        get { self[LibrarySortAscendingKey.self] }
        set { self[LibrarySortAscendingKey.self] = newValue }
    }
}
