import OSLog
import SwiftUI

extension SidebarItemRow {
    func commitRename() {
        let newName = renameState.editingName.trimmingCharacters(in: .whitespacesAndNewlines)

        guard let itemIdToRename = renameState.renamingItemId else {
            sidebarRowLogger.warning("commitRename called but no item is being renamed")
            renameState.cancelRename()
            return
        }

        sidebarRowLogger.debug("Committing rename for item ID: \(itemIdToRename), new name: \(newName)")
        sidebarRowLogger.debug("  - Current row's item: \(item.name) (id: \(item.id))")
        sidebarRowLogger.debug("  - renameState.renamingItemId: \(itemIdToRename)")

        guard !newName.isEmpty else {
            renameState.cancelRename()
            return
        }

        guard newName.count <= SidebarConstants.maxNameLength else {
            renameState.cancelRename()
            return
        }

        isCommittingRename = true

        Task {
            await performRename(itemId: itemIdToRename, newName: newName)
            await MainActor.run {
                renameState.cancelRename()
                isCommittingRename = false
            }
        }
    }

    func performRename(itemId: String, newName: String) async {
        sidebarRowLogger.debug("performRename called with itemId: \(itemId), newName: \(newName)")
        sidebarRowLogger.debug("  - Current row's item: \(item.name) (id: \(item.id))")

        guard let itemToRename = findItemById(itemId, in: allCachedItems) else {
            sidebarRowLogger.warning("Could not find item with ID \(itemId) in cached items")
            return
        }

        sidebarRowLogger.debug("  - Found item to rename: \(itemToRename.name) (id: \(itemToRename.id))")

        if case .document(let document) = itemToRename.itemType {
            await renameDocument(document, to: newName)
        } else {
            await renameNonDocumentItem(itemToRename, itemId: itemId, newName: newName)
        }
    }

    func renameDocument(_ document: Document, to newName: String) async {
        sidebarRowLogger.debug("  - Renaming document: \(document.name) (id: \(document.id))")
        guard let documentStore = documentStore else { return }
        do {
            let updated = try await documentStore.renameDocument(document, to: newName)
            sidebarRowLogger.debug(" Renamed document to '\(updated.name)'")
        } catch {
            sidebarRowLogger.error(" Failed to rename document: \(error.localizedDescription)")
            sidebarState.renameErrorMessage = error.localizedDescription
        }
    }

    func renameNonDocumentItem(
        _ itemToRename: SidebarItem,
        itemId: String,
        newName: String
    ) async {
        guard let itemLibraryId = itemToRename.libraryId,
              let itemLibrary = libraryManager.getLibrary(id: itemLibraryId) else {
            sidebarRowLogger.error("Cannot rename: item has no libraryId or library not found")
            return
        }

        do {
            switch itemToRename.itemType {
            case .savedSearch(let search):
                _ = try await itemLibrary.savedSearchService.renameSavedSearch(search.id, newName: newName)
                sidebarRowLogger.debug(" Renamed saved search \(search.id) to '\(newName)'")
            case .conversation(let conversation):
                _ = try await itemLibrary.conversationService.renameConversation(
                    conversation.id,
                    newTitle: newName
                )
                sidebarRowLogger.debug(" Renamed conversation \(conversation.id) to '\(newName)'")
            case .workflow(let workflow):
                _ = try await itemLibrary.workflowStore.renameWorkflow(workflow.id, to: newName)
                // Force refresh from backend to guarantee persistence + sidebar consistency.
                await itemLibrary.workflowStore.loadWorkflows()
                sidebarRowLogger.debug(" Renamed workflow \(workflow.id) to '\(newName)'")
            case .chain(var chain):
                chain.name = newName
                _ = try await itemLibrary.chainService.updateChain(chain)
                sidebarRowLogger.debug(" Renamed chain \(chain.id) to '\(newName)'")
            case .schedule(let schedule):
                _ = try await itemLibrary.automationService.updateSchedule(
                    scheduleId: schedule.scheduleId,
                    newName: newName
                )
                sidebarRowLogger.debug(" Renamed schedule \(schedule.scheduleId) to '\(newName)'")
            case .trigger(let trigger):
                _ = try await itemLibrary.automationService.updateTrigger(
                    triggerId: trigger.triggerId,
                    newName: newName
                )
                sidebarRowLogger.debug(" Renamed trigger \(trigger.triggerId) to '\(newName)'")
            case .libraryHeader:
                libraryManager.renameLibrary(id: itemLibrary.id, to: newName)
                sidebarRowLogger.debug(" Renamed library \(itemLibrary.id.uuidString) to '\(newName)'")
            default:
                sidebarRowLogger.debug(" Unknown item type for rename (itemId: \(itemId))")
            }
        } catch {
            sidebarRowLogger.error(" Failed to rename item: \(error.localizedDescription)")
            sidebarState.renameErrorMessage = error.localizedDescription
        }
    }
}
