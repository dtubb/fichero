import SwiftUI

// swiftlint:disable file_length

private struct DocumentDeleteActionParams: Encodable {
    let docId: String

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
    }
}

// MARK: - Keyboard Shortcuts Extension

extension LibraryView {
    // Applies keyboard shortcut handlers to the LibraryView content
    // swiftlint:disable:next function_body_length
    func withKeyboardShortcuts(_ content: some View) -> some View {
        content
            #if os(macOS)
            .onDeleteCommand(perform: promptDeleteSelected)
            #endif
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
            #if os(macOS)
            .onMoveCommand { direction in
                handleMoveCommand(direction)
            }
            #endif
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
        guard let library = libraryManager.getLibrary(id: windowState.libraryId) else { return }
        for doc in documentsToDelete {
            do {
                let result = try await library.actionsService.invokeAction(
                    name: "document.delete",
                    params: DocumentDeleteActionParams(docId: doc.id)
                )
                LastAction.shared.record(auditId: result.auditId, actionName: "document.delete")
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

    // MARK: - Arrow Key Navigation

    enum ArrowDirection {
        case upDir, down, left, right, pageUp, pageDown
    }

    #if os(macOS)
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
    #endif

    /// Handle arrow key press for navigating documents.
    /// All four arrows navigate within the content area (like Finder).
    /// Tab/Shift+Tab cycle focus between panes.
    func handleArrowKey(direction: ArrowDirection) -> KeyPress.Result {
        let ids: [String]
        if isShowingEntitiesCollection {
            ids = filteredEntities.map { entitySelectionId(for: $0) }
        } else {
            ids = filteredDocuments.map(\.id)
        }
        guard !ids.isEmpty else { return .ignored }

        // Select first item if nothing is selected yet
        guard let currentIndex = currentSelectionIndex(in: ids) else {
            selection = [ids[0]]
            selectionAnchor = ids[0]
            focusSelectedEntityIfNeeded()
            return .handled
        }

        let step = stepSize(for: direction)
        guard step != 0 else { return .ignored }
        let targetIndex = currentIndex + step
        guard targetIndex >= 0, targetIndex < ids.count else { return .handled }

        applySelection(targetIndex: targetIndex, ids: ids)
        if displayMode == .icon || displayMode == .list || displayMode == .table {
            listScrollTarget = ids[targetIndex]
        }
        focusSelectedEntityIfNeeded()
        return .handled
    }

    private func currentSelectionIndex(in ids: [String]) -> Int? {
        guard let firstSelected = selection.first else { return nil }
        return ids.firstIndex(of: firstSelected)
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

    private func applySelection(targetIndex: Int, ids: [String]) {
        let targetId = ids[targetIndex]
        #if os(macOS)
        if NSEvent.modifierFlags.contains(.shift),
           let anchor = selectionAnchor,
           let anchorIndex = ids.firstIndex(of: anchor) {
            let range = min(anchorIndex, targetIndex)...max(anchorIndex, targetIndex)
            selection = Set(range.map { ids[$0] })
        } else if NSEvent.modifierFlags.contains(.shift) {
            selection.insert(targetId)
            selectionAnchor = targetId
        } else {
            selection = [targetId]
            selectionAnchor = targetId
        }
        #else
        // iOS: keyboard modifier flags aren't available on .onKeyPress;
        // collapse to plain selection. Modifier-aware keyboard selection
        // is a separate iPad UI pass.
        selection = [targetId]
        selectionAnchor = targetId
        #endif
    }

    // MARK: - Type-to-Select

    /// Handle a typed character for type-to-select navigation
    func handleTypeToSelect(_ characters: String) {
        // Cancel any pending reset timer
        typeSelectTask?.cancel()

        // Append to the buffer
        typeSelectBuffer += characters.lowercased()

        if isShowingEntitiesCollection,
           let match = filteredEntities.first(where: {
               $0.canonicalName.lowercased().hasPrefix(typeSelectBuffer)
           }) {
            selection = [entitySelectionId(for: match)]
            focusEntityIfPossible(match)
        } else if let match = filteredDocuments.first(where: {
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

    private func focusSelectedEntityIfNeeded() {
        guard isShowingEntitiesCollection,
              let firstId = selection.first,
              let entity = filteredEntities.first(where: { entitySelectionId(for: $0) == firstId }) else { return }
        focusEntityIfPossible(entity)
    }
}

// MARK: - FocusedValue Equatable Wrappers

/// Equatable wrapper for a library action (selectAll / deleteSelection).
///
/// Closures are non-Equatable, so publishing a raw `() -> Void` via
/// `focusedSceneValue` causes SwiftUI to see a new value on every `body` pass
/// → republishes → cascading invalidation ("FocusedValue update tried to update
/// multiple times per frame"). This wrapper keys equality on `isEnabled` only;
/// the `run` closure is excluded (closures are non-Equatable). Because the
/// enable state is the only part readers query for menu-item enable/disable, this
/// is semantically identical to the old nil-means-disabled pattern while being
/// stable across re-renders.
struct FocusedLibraryAction: Equatable {
    /// Whether the action is currently available (non-empty list or selection).
    let isEnabled: Bool
    /// Execute the action.
    let run: () -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.isEnabled == rhs.isEnabled
    }
}

/// Equatable wrapper for the library sort-field focused value.
///
/// `Binding<String>` is non-Equatable — publishing it directly via
/// `focusedSceneValue` causes the same per-frame churn as raw closures.
/// This wrapper captures the current value (for equality and display) plus a
/// setter (for mutation), excluding the setter from equality.
struct FocusedSortField: Equatable {
    /// The current raw sort-field value (e.g. `LibrarySortField.name.rawValue`).
    let value: String
    /// Update the sort field to a new raw value.
    let set: (String) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.value == rhs.value
    }
}

/// Equatable wrapper for the library sort direction focused value.
///
/// Publishing a raw `Binding<Bool>` re-triggers the focus system on every body
/// pass even when the direction did not change. Mirror `FocusedSortField` so
/// the View menu only sees a new focused value when the actual ascending flag
/// changes, not whenever the view re-renders.
struct FocusedSortAscending: Equatable {
    /// The current ascending/descending flag.
    let value: Bool
    /// Update the direction.
    let set: (Bool) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.value == rhs.value
    }
}

// MARK: - FocusedValue Keys for Library Actions

/// FocusedValue key for selecting all documents in the library
struct LibrarySelectAllKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for deleting selected documents in the library
struct LibraryDeleteSelectionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for the library sort field
struct LibrarySortFieldKey: FocusedValueKey {
    typealias Value = FocusedSortField
}

/// FocusedValue key for the library sort direction binding
struct LibrarySortAscendingKey: FocusedValueKey {
    typealias Value = FocusedSortAscending
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

// swiftlint:enable file_length
