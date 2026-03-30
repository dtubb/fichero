import SwiftUI
import OSLog

/// Structured logger for sidebar action operations
private let logger = Logger(subsystem: "com.fichero.app", category: "SidebarActions")

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
        logger.info("Importing \(urls.count) files to library: \(library.displayName)")
        do {
            _ = try await library.importService.importFiles(urls, mode: mode)
            logger.info("Imported \(urls.count) files using mode: \(mode.rawValue)")
        } catch {
            logger.error("Failed to import files: \(error)")
        }
        await library.documentStore.refresh()
        rebuildCaches()
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
                try await library.documentStore.deleteDocument(doc)
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
            rebuildCaches()
            selectedItemId = nil
        } catch {
            logger.error("Failed to delete: \(error.localizedDescription)")
        }
    }
}
