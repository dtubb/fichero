import OSLog
import SwiftUI

private let libraryKeysLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "LibraryKeys"
)

// MARK: - Keyboard Shortcuts Extension

extension LibraryView {
    /// Whether `mode` can service the ROW keyboard grammar — arrows, type-ahead,
    /// Return-to-open, Space-to-preview (#4412).
    ///
    /// These handlers used to be applied to every mode, because they wrap
    /// `libraryContent` as a whole. On the canvas and in 3D that meant an arrow
    /// key moved the LIST selection while the user was looking at a spatial
    /// arrangement: the app changed state behind their back, with no visible
    /// cause, and they found out later. That is worse than the feature being
    /// absent — a missing key does nothing and says so.
    ///
    /// Spatial modes do nothing here for now. If they should get their own
    /// arrow behaviour (move the selected node? pan the camera?) that is a real
    /// design question and its own issue, not a default inherited by accident.
    ///
    /// Exhaustive switch on purpose: a new mode must decide, rather than
    /// silently inheriting row semantics the way canvas and space did.
    static func servicesRowKeyboardGrammar(_ mode: ViewDisplayMode) -> Bool {
        switch mode {
        case .icon, .list, .table, .columns: return true
        // The Data mode's renderers own their interactions (calendar day
        // cells, map pins); inheriting row semantics by accident is the
        // regression class this switch exists to prevent.
        case .canvas, .space, .grid, .cards, .timeline, .calendar, .geoMap: return false
        // Not changed here: `.workspace` keeps today's behaviour because I could
        // not establish what it renders without running it, and removing a key
        // that DOES work is its own regression (#4412).
        case .workspace: return true
        }
    }

    /// Applies the row keyboard grammar — but only to modes that can service it.
    @ViewBuilder
    func withKeyboardShortcuts(_ content: some View) -> some View {
        if Self.servicesRowKeyboardGrammar(displayMode) {
            applyDeleteConfirmation(
                to: applyFocusedActions(
                    to: applyArrowKeyHandlers(to: applyPrimaryKeyHandlers(to: content))
                )
            )
        } else {
            // Delete + focused actions still apply: ⌫ and the menu commands act
            // on the selection, which is shared across modes and meaningful on a
            // canvas. It is the ROW-ordinal handlers (arrows, type-ahead) that
            // have no meaning in a spatial arrangement.
            applyDeleteConfirmation(to: applyFocusedActions(to: content))
        }
    }

    /// The row keyboard grammar stands down while the user is TYPING
    /// somewhere: an inline rename, the quick-filter field, or the summoned
    /// search field (#4521). Ancestor `.onKeyPress` handlers intercept keys
    /// BEFORE a focused descendant TextField sees them, so any handler that
    /// claims a printable key (or Return/Space/arrows) makes that field look
    /// dead unless it yields here (2026-08-11: "it won't even let me search
    /// by typing into search box").
    var isTextEntryActive: Bool {
        renamingDocumentId != nil || filterFieldFocused || searchFieldFocused
    }

    @ViewBuilder
    private func applyPrimaryKeyHandlers(to content: some View) -> some View {
        content
            #if os(macOS)
            .onDeleteCommand(perform: promptDeleteSelected)
            #endif
            .onKeyPress(.return) {
                // Yield Return to a focused text field — there the key means
                // `.onSubmit`, not open-the-selected-row.
                guard !isTextEntryActive else { return .ignored }
                openSelectedDocument()
                return .handled
            }
            // Space → Quick Look of the cursor document, Finder-style
            // (#4160). Toggles: a second press closes the panel.
            .onKeyPress(.space) {
                guard !isTextEntryActive else { return .ignored }
                return quickLookSelectedDocument()
            }
            .quickLookPreview($quickLookURL)
            .onKeyPress(characters: .alphanumerics.union(.punctuationCharacters)) { keyPress in
                guard !isTextEntryActive else { return .ignored }
                handleTypeToSelect(keyPress.characters)
                return .handled
            }
    }

    @ViewBuilder
    private func applyArrowKeyHandlers(to content: some View) -> some View {
        content
            .onKeyPress(.upArrow, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .upDir)
            }
            .onKeyPress(.downArrow, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .down)
            }
            .onKeyPress(.leftArrow, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .left)
            }
            .onKeyPress(.rightArrow, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .right)
            }
            .onKeyPress(.pageUp, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .pageUp)
            }
            .onKeyPress(.pageDown, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .pageDown)
            }
            .onKeyPress(.home, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .home)
            }
            .onKeyPress(.end, phases: .down) { _ in
                guard !isTextEntryActive else { return .ignored }
                return handleArrowKey(direction: .end)
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
        // ONE writer per focused key (2026-08-12): a horizontal/vertical
        // library split mounts TWO LibraryViews, and both wrote
        // librarySelectAll/librarySortField/… every frame — SwiftUI's
        // "FocusedValue update tried to update multiple times per frame"
        // fault, which re-invalidated the scene graph recursively at launch
        // and deepened the stack under the #4331 menu-build crash. The
        // PRIMARY pane owns the menu commands; a secondary split renders
        // rows only.
        if isSecondarySplitPane {
            content
        } else {
            applyPrimaryFocusedActions(to: content)
        }
    }

    @ViewBuilder
    private func applyPrimaryFocusedActions(to content: some View) -> some View {
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
        // ONE presentation modifier serves both the normal confirmation and
        // the #4198 child-only-selection notice (empty `documentsToDelete`
        // → "Nothing Deleted" + OK). Stacking a second `.alert` on this node
        // trapped non-deterministically at launch — same attribute-machinery
        // family as #3163 (duplicate .searchable) and #4189 (Optional view
        // under .safeAreaInset). Never add a sibling presentation here.
        content
            .confirmationDialog(
                documentsToDelete.isEmpty
                    ? "Nothing Deleted"
                    : "Delete \(documentsToDelete.count) document\(documentsToDelete.count == 1 ? "" : "s")?",
                isPresented: $showDeleteConfirmation,
                titleVisibility: .visible
            ) {
                if documentsToDelete.isEmpty {
                    Button("OK", role: .cancel) { deleteSkippedNote = nil }
                } else {
                    Button("Delete", role: .destructive) {
                        Task {
                            await performDeleteSelected()
                        }
                    }
                    Button("Cancel", role: .cancel) {
                        documentsToDelete = []
                        deleteSkippedNote = nil
                    }
                }
            } message: {
                if !documentsToDelete.isEmpty {
                    deleteConfirmationMessage
                }
                // #4198: the selection held child outline rows — say plainly
                // that they are not part of this delete.
                if let note = deleteSkippedNote {
                    Text(note)
                }
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
            // #4416: the raw `name` is the engine's upload temp name for every
            // page child, and this is the last thing shown before a delete the
            // user cannot undo. Naming the file `fichero_upload_c84fgjke.pdf`
            // here asks them to confirm the destruction of something they have
            // no way to recognise.
            let title = DocumentTitle.displayName(for: doc)
            switch doc.ingestMode {
            case .link:
                if let path = doc.path {
                    Text(
                        "Remove the Fichero reference to \"\(title)\"? "
                            + "The original file at \(path) will stay on disk."
                    )
                } else {
                    Text(
                        "Remove the Fichero reference to \"\(title)\"? "
                            + "The original file will stay on disk."
                    )
                }
            case .copy:
                Text(
                    "Delete Fichero's copy of \"\(title)\"? "
                        + "The file you imported from is untouched."
                )
            case .move:
                Text(
                    "Permanently delete \"\(title)\"? "
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
