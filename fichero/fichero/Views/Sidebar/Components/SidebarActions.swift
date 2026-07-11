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

    // Perform the actual deletion
    // swiftlint:disable:next cyclomatic_complexity
    func performDelete(item: SidebarItem) async {
        logger.info("performDelete for: \(item.name)")
        guard let libraryId = item.libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else {
            logger.error("Could not find library for deletion")
            return
        }
        do {
            switch item.itemType {
            case .document(let doc):
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
            case .savedSearch(let search):
                try await library.savedSearchServiceGenerated.deleteSavedSearch(search.id)
            case .conversation(let conversation):
                try await library.conversationServiceGenerated.deleteConversation(conversation.id)
            case .workflow(let workflow):
                try await library.workflowStore.deleteWorkflow(workflow.id)
            case .chain(let chain):
                try await library.chainService.deleteChain(chain.id)
            case .schedule(let schedule):
                try await library.automationService.deleteSchedule(scheduleId: schedule.scheduleId)
                await loadAutomationData()  // Refresh automation sidebar
            case .trigger(let trigger):
                try await library.automationService.deleteTrigger(triggerId: trigger.triggerId)
                await loadAutomationData()  // Refresh automation sidebar
            case .batch(let batch):
                try await library.batchService.deleteBatch(batchId: batch.batchId)
                await loadActivityData()  // Refresh unified activity sidebar
            case .comparison, .activityRun:
                logger.warning("This item type cannot be deleted")
            case .folder:
                logger.info("Folder deletion not yet implemented")
            case .libraryHeader:
                logger.warning("Cannot delete library header")
            }
            logger.info("Delete successful")
            rebuildCaches(for: libraryId)
            selectedItemId = nil
        } catch {
            logger.error("Failed to delete: \(error.localizedDescription)")
        }
    }
}
