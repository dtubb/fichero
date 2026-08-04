import OSLog
import SwiftUI

/// Structured logger for sidebar action operations
private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarActions")

/// Raised when a delete reaches the action layer for a type that cannot be
/// deleted (#4454). Surfaced in the sidebar's Delete Failed alert.
enum SidebarDeleteError: LocalizedError {
    case notDeletable

    var errorDescription: String? {
        "This item can't be deleted."
    }
}

private struct DocumentDeleteActionParams: Encodable {
    let docId: String

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
    }
}

// MARK: - Import/Delete/Rename Extension

extension SidebarView {
    /// Import files to the library that owns the selected item (or Global if none)
    func importFiles(mode: IngestMode = .link) {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard targetLibrary != nil else {
            logger.error("No library available for import")
            return
        }
        sidebarState.selectedImportMode = mode
        sidebarState.showingFileImporter = true
    }

    /// Handle imported files from file picker
    func handleImportedFiles(_ urls: [URL]) async {
        let targetLibrary = selectedItemLibrary ?? libraryManager.globalLibrary
        guard let library = targetLibrary else {
            logger.error("No library available for import")
            return
        }
        let mode = sidebarState.selectedImportMode

        // Resolve a destination folder, mirroring the drag-drop path
        // (handleExternalFileDrop): import into the selected folder if one is
        // selected, otherwise route to the library Inbox. A nil parentId lands
        // documents at the bare library root, where they don't render in the
        // sidebar — so a successful menu/file-picker import looked like a
        // no-op. That missing routing was the broken-import root cause.
        let parentId = importDestinationFolderId(in: library)

        logger.info("Importing \(urls.count) files to library: \(library.displayName)")
        do {
            let outcome = try await library.importService.importFiles(urls, mode: mode, parentId: parentId)
            logger.info("Imported \(urls.count) files using mode: \(mode.rawValue)")
            // A menu/file-picker import that lost some files must say so
            // (#3276) — this path threw only when EVERY file failed, so a
            // partial loss read as a clean import. Same banner the drop paths
            // use, so there is one place a failed import is reported.
            if let message = outcome.partialFailureMessage {
                logger.error("Import completed partially: \(message)")
                sidebarState.dropErrorMessage = message
            }
        } catch {
            logger.error("Failed to import files: \(error)")
            sidebarState.dropErrorMessage = "Import failed: \(error.localizedDescription)"
        }
        // ONE trailing refresh, matching the row-drop path (#4067). The engine
        // emits a per-file `document.created` as each file lands, so the store
        // patches the sidebar incrementally while the import runs; this is the
        // completion signal and the backstop for a lost event.
        //
        // The second refresh behind a 500ms sleep — and the explicit
        // `rebuildCaches()` after it — are deleted, not moved. #4067 removed
        // exactly this pattern from the drop path because every refresh ends in
        // `loadCollections()`, which drops the whole `childrenCache` and
        // rebuilds every row; the sleep made the sidebar visibly redraw a
        // second time half a second after the import already looked finished
        // (#4522). `SidebarObservers` rebuilds the caches from the store
        // change, so the explicit call was a third rebuild of the same data.
        await library.documentStore.refresh()
    }

    /// Folder a menu/file-picker import should land in: the selected folder if
    /// one is selected, otherwise the library Inbox. Never returns nil-to-root
    /// silently — root-level documents are invisible in the sidebar tree.
    private func importDestinationFolderId(in library: LibraryManager.LibraryReference) -> String? {
        if let selectedItem,
           case .document(let doc) = selectedItem.itemType,
           doc.docType == .folder {
            return doc.id
        }
        return library.documentStore.collections.first {
            $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
        }?.id
    }

    /// Rename the selected item
    func handleRenameSelectedItem() {
        guard let item = selectedItem else { return }
        renameState.startRename(itemId: item.id, currentName: item.name)
    }

    /// Delete the whole (deletable) multi-selection, confirming once. The ONE
    /// delete path for every entry point — Delete key, Edit ▸ Delete (⌘⌫), and
    /// the bottom-toolbar remove button — so a multi-selection is never
    /// silently narrowed to just the primary row by the menu/toolbar variants.
    /// A single selection resolves to exactly the primary, unchanged. No-op if
    /// nothing in the selection is deletable (headers etc. are filtered).
    func handleDeleteSelection() {
        let items = sidebarDeletableItems(selectedItems)
        guard !items.isEmpty else { return }
        deleteState.showDeleteConfirmation(for: items)
    }

    #if os(macOS)
    /// Finder-style double-click (#2496): open the primary selected row in a
    /// new tab or window via the shared `WindowOpener` path, honoring the
    /// system "Prefer tabs" setting. Single click keeps its existing
    /// select-in-place semantics; multi-selection is untouched (the primary
    /// is the routed anchor). Keyboard/VoiceOver equivalents: the row context
    /// menu and the File-menu Open in New Tab / New Window commands.
    func handleSidebarDoubleClick() {
        openPrimarySelection(asTab: sidebarOpenPrefersTab(NSWindow.userTabbingPreference))
    }

    private func openPrimarySelection(asTab: Bool) {
        guard let target = sidebarAuxiliaryOpenTarget(
            item: selectedItem,
            fallbackLibraryId: libraryManager.currentLibraryId
        ) else { return }
        WindowOpener.open(
            libraryId: target.libraryId,
            documentId: target.documentId,
            asTab: asTab,
            using: openWindow
        )
    }
    #endif

    /// File-menu / keyboard paths (#2496): an EXPLICIT tab or window choice,
    /// unlike double-click which follows the system tabbing preference.
    /// No-ops on iOS, where `WindowOpener` (macOS window/tab management)
    /// doesn't exist — the menu commands are macOS-only anyway.
    func handleOpenSelectionInNewTab() {
        #if os(macOS)
        openPrimarySelection(asTab: true)
        #endif
    }

    func handleOpenSelectionInNewWindow() {
        #if os(macOS)
        openPrimarySelection(asTab: false)
        #endif
    }

    // Perform the actual deletion
    func performDelete(item: SidebarItem) async {
        logger.info("performDelete for: \(item.name)")
        guard let libraryId = item.libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else {
            logger.error("Could not find library for deletion")
            return
        }
        do {
            try await performDeleteAction(item.itemType, library: library)
            logger.info("Delete successful")
            rebuildCaches(for: libraryId)
            selectedItemId = nil
        } catch {
            // Surface it. `DeleteStateManager` has carried a complete error
            // surface — `deleteErrorMessage`, `showingDeleteError`,
            // `showError(message:)` and a "Delete Failed" alert — with ZERO
            // callers, so every delete failure so far has been a log line
            // nobody reads while the row stayed put unexplained (#4454).
            logger.error("Failed to delete: \(error.localizedDescription)")
            deleteState.showError(message: error.localizedDescription)
        }
    }

    // Dispatches by item-type group — grouping keeps this switch's branch
    // count (and thus complexity) low; each group's real per-case logic
    // lives in its own helper below.
    private func performDeleteAction(
        _ itemType: SidebarItem.ItemType,
        library: LibraryManager.LibraryReference
    ) async throws {
        switch itemType {
        case .document(let doc):
            try await deleteDocumentItem(doc, library: library)
        case .savedSearch, .conversation, .workflow, .chain:
            try await deleteSimpleItem(itemType, library: library)
        case .schedule, .trigger, .batch:
            try await deleteAutomationItem(itemType, library: library)
        case .comparison, .activityRun, .folder, .libraryHeader:
            try rejectNondeletableItem(itemType)
        }
    }

    private func deleteDocumentItem(_ doc: Document, library: LibraryManager.LibraryReference) async throws {
        _ = try await library.actionsService.invokeAction(
            name: "document.delete",
            params: DocumentDeleteActionParams(docId: doc.id)
        )
        undoManager?.registerUndo(withTarget: library.documentStore) { store in
            Task { @MainActor in
                do {
                    try await store.documentService.restoreDocument(doc.id)
                    await store.refresh()
                } catch {
                    logger.error("Failed to restore deleted document: \(error.localizedDescription)")
                }
            }
        }
        undoManager?.setActionName("Move to Trash")
        await library.documentStore.refresh()
    }

    private func deleteSimpleItem(
        _ itemType: SidebarItem.ItemType,
        library: LibraryManager.LibraryReference
    ) async throws {
        switch itemType {
        case .savedSearch(let search):
            try await library.savedSearchService.deleteSavedSearch(search.id)
        case .conversation(let conversation):
            try await library.conversationService.deleteConversation(conversation.id)
        case .workflow(let workflow):
            try await library.workflowStore.deleteWorkflow(workflow.id)
        case .chain(let chain):
            try await library.chainService.deleteChain(chain.id)
        default:
            break
        }
    }

    private func deleteAutomationItem(
        _ itemType: SidebarItem.ItemType,
        library: LibraryManager.LibraryReference
    ) async throws {
        switch itemType {
        case .schedule(let schedule):
            try await library.automationService.deleteSchedule(scheduleId: schedule.scheduleId)
            await loadAutomationData()  // Refresh automation sidebar
        case .trigger(let trigger):
            try await library.automationService.deleteTrigger(triggerId: trigger.triggerId)
            await loadAutomationData()  // Refresh automation sidebar
        case .batch(let batch):
            try await library.batchService.deleteBatch(batchId: batch.batchId)
            await loadActivityData()  // Refresh unified activity sidebar
        default:
            break
        }
    }

    /// Reached only if a type whose `canBeDeleted` is false somehow arrives
    /// here. It THROWS rather than logs (rule zero): swallowing an action the
    /// user explicitly confirmed is how #4454 stayed invisible — the delete was
    /// never issued, `performDelete` reported "Delete successful" anyway, and
    /// the only evidence was a log line. Now it lands in the Delete Failed
    /// alert instead.
    private func rejectNondeletableItem(_ itemType: SidebarItem.ItemType) throws -> Never {
        logger.warning("Refusing delete for non-deletable item type: \(String(describing: itemType))")
        throw SidebarDeleteError.notDeletable
    }
}
