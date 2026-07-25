import OSLog
import SwiftUI

/// Structured logger for sidebar action operations
private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarActions")

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
            _ = try await library.importService.importFiles(urls, mode: mode, parentId: parentId)
            logger.info("Imported \(urls.count) files using mode: \(mode.rawValue)")
        } catch {
            logger.error("Failed to import files: \(error)")
        }
        // Refresh twice — once immediately, again after 500ms — to catch the
        // race where the backend hasn't finished indexing when the first
        // refresh fires (same hardening the drop path already has).
        await library.documentStore.refresh()
        try? await Task.sleep(for: .milliseconds(500))
        await library.documentStore.refresh()
        rebuildCaches()
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

    /// Delete the selected item
    func handleDeleteSelectedItem() {
        guard let item = selectedItem else { return }
        switch item.itemType {
        case .libraryHeader:
            logger.warning("Cannot delete library header")
        default:
            deleteState.showDeleteConfirmation(for: item)
        }
    }

    /// Delete the whole multi-selection (Delete key / batch). Confirms once for
    /// every deletable row in the selection; a no-op if nothing is deletable.
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
            logger.error("Failed to delete: \(error.localizedDescription)")
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
            logNondeletableItem(itemType)
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

    private func logNondeletableItem(_ itemType: SidebarItem.ItemType) {
        switch itemType {
        case .comparison, .activityRun:
            logger.warning("This item type cannot be deleted")
        case .folder:
            logger.info("Folder deletion not yet implemented")
        case .libraryHeader:
            logger.warning("Cannot delete library header")
        default:
            break
        }
    }
}
