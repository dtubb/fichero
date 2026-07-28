import OSLog
import SwiftUI

private let libraryKeysLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "LibraryKeys"
)

// MARK: - Keyboard Shortcuts Extension

extension LibraryView {
    // Applies keyboard shortcut handlers to the LibraryView content
    func withKeyboardShortcuts(_ content: some View) -> some View {
        applyDeleteConfirmation(
            to: applyFocusedActions(
                to: applyArrowKeyHandlers(to: applyPrimaryKeyHandlers(to: content))
            )
        )
    }

    @ViewBuilder
    private func applyPrimaryKeyHandlers(to content: some View) -> some View {
        content
            #if os(macOS)
            .onDeleteCommand(perform: promptDeleteSelected)
            #endif
            .onKeyPress(.return) {
                openSelectedDocument()
                return .handled
            }
            // Space → Quick Look of the cursor document, Finder-style
            // (#4160). Toggles: a second press closes the panel.
            .onKeyPress(.space) {
                guard renamingDocumentId == nil else { return .ignored }
                return quickLookSelectedDocument()
            }
            .quickLookPreview($quickLookURL)
            .onKeyPress(characters: .alphanumerics.union(.punctuationCharacters)) { keyPress in
                // Skip if a rename is in progress
                guard renamingDocumentId == nil else { return .ignored }
                handleTypeToSelect(keyPress.characters)
                return .handled
            }
    }

    @ViewBuilder
    private func applyArrowKeyHandlers(to content: some View) -> some View {
        content
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
            .onKeyPress(.home, phases: .down) { _ in
                handleArrowKey(direction: .home)
            }
            .onKeyPress(.end, phases: .down) { _ in
                handleArrowKey(direction: .end)
            }
            #if os(macOS)
            .onMoveCommand { direction in
                handleMoveCommand(direction)
            }
            #endif
    }

    /// Space → Quick Look (#4160): fetch the cursor document's source file
    /// through the storage service to a temp file (the engine may be remote —
    /// never a local path) and hand it to `.quickLookPreview`.
    func quickLookSelectedDocument() -> KeyPress.Result {
        if quickLookURL != nil {
            quickLookURL = nil
            return .handled
        }
        guard !isShowingEntitiesCollection,
              let primaryId = orderedPrimarySelectionId,
              let doc = navigableDocument(for: primaryId),
              doc.docType != .folder else { return .ignored }
        quickLook(doc)
        return .handled
    }

    /// Shared Quick Look entry — Space and the context menu item (#4160)
    /// both land here.
    func quickLook(_ doc: Document) {
        Task { @MainActor in
            do {
                quickLookURL = try await SidebarDragID.exportSourceFile(
                    for: SidebarDragID(document: doc, libraryId: windowState.libraryId)
                )
            } catch {
                libraryKeysLogger.error(
                    "Quick Look fetch for \(doc.id, privacy: .public) failed: \(error.localizedDescription)"
                )
            }
        }
    }

    @ViewBuilder
    private func applyFocusedActions(to content: some View) -> some View {
        content
            .focusedSceneValue(
                \.librarySelectAll,
                FocusedLibraryAction(
                    isEnabled: !(isShowingEntitiesCollection ? filteredEntities.isEmpty : filteredDocuments.isEmpty),
                    run: { selectAll() }
                )
            )
            .focusedSceneValue(
                \.libraryDeleteSelection,
                FocusedLibraryAction(
                    isEnabled: !isShowingEntitiesCollection && !selection.isEmpty,
                    run: { promptDeleteSelected() }
                )
            )
            .focusedSceneValue(
                \.librarySortField,
                FocusedSortField(
                    value: libraryToolbar.sortFieldRaw,
                    set: { libraryToolbar.sortFieldRaw = $0 }
                )
            )
            .focusedSceneValue(
                \.librarySortAscending,
                FocusedSortAscending(
                    value: libraryToolbar.sortAscending,
                    set: { libraryToolbar.sortAscending = $0 }
                )
            )
    }

    @ViewBuilder
    private func applyDeleteConfirmation(to content: some View) -> some View {
        content
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
                deleteConfirmationMessage
            }
    }

    // #603 Part 2: branch the copy by ingest mode so users see
    // an accurate description of what delete actually does for
    // their file. LINK preserves the original; COPY removes our
    // copy but the user's source file is untouched; MOVE is the
    // only mode where delete is genuinely terminal.
    @ViewBuilder
    private var deleteConfirmationMessage: some View {
        if documentsToDelete.count == 1, let doc = documentsToDelete.first {
            switch doc.ingestMode {
            case .link:
                if let path = doc.path {
                    Text(
                        "Remove the Fichero reference to \"\(doc.name)\"? "
                            + "The original file at \(path) will stay on disk."
                    )
                } else {
                    Text(
                        "Remove the Fichero reference to \"\(doc.name)\"? "
                            + "The original file will stay on disk."
                    )
                }
            case .copy:
                Text(
                    "Delete Fichero's copy of \"\(doc.name)\"? "
                        + "The file you imported from is untouched."
                )
            case .move:
                Text(
                    "Permanently delete \"\(doc.name)\"? "
                        + "This file was moved into Fichero, so there's no other copy."
                )
            }
        } else {
            let modes = Set(documentsToDelete.map { $0.ingestMode })
            if modes == [.link] {
                Text(
                    "Remove \(documentsToDelete.count) Fichero references? "
                        + "The original files will stay on disk."
                )
            } else if modes == [.move] {
                Text(
                    "Permanently delete \(documentsToDelete.count) documents? "
                        + "These files were moved into Fichero, so there are no other copies."
                )
            } else {
                Text(
                    "Delete \(documentsToDelete.count) documents from Fichero? "
                        + "Items imported via LINK reference originals on disk; "
                        + "COPY items are removed; MOVE items are gone for good."
                )
            }
        }
    }
}
