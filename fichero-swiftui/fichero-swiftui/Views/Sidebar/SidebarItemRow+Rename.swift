import SwiftUI
import OSLog

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
            sidebarRowLogger.warning("⚠️ Could not find item with ID \(itemId) in cached items")
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
            sidebarRowLogger.debug(" Failed to rename document: \(error.localizedDescription)")
        }
    }

    func renameNonDocumentItem(
        _ itemToRename: SidebarItem,
        itemId: String,
        newName: String
    ) async {
        let actualId: String
        if itemId.contains(":") {
            actualId = String(itemId.split(separator: ":")[1])
        } else {
            actualId = itemId
        }

        guard let itemLibraryId = itemToRename.libraryId,
              let itemLibrary = libraryManager.getLibrary(id: itemLibraryId) else {
            sidebarRowLogger.error("Cannot rename: item has no libraryId or library not found")
            return
        }

        do {
            switch itemToRename.itemType {
            case .savedSearch:
                _ = try await itemLibrary.savedSearchServiceGenerated.renameSavedSearch(actualId, newName: newName)
                sidebarRowLogger.debug(" Renamed saved search \(actualId) to '\(newName)'")
            case .conversation:
                _ = try await itemLibrary.conversationServiceGenerated.renameConversation(actualId, newTitle: newName)
                sidebarRowLogger.debug(" Renamed conversation \(actualId) to '\(newName)'")
            case .workflow:
                _ = try await itemLibrary.workflowStore.renameWorkflow(actualId, to: newName)
                sidebarRowLogger.debug(" Renamed workflow \(actualId) to '\(newName)'")
            case .chain(var chain):
                chain.name = newName
                _ = try await itemLibrary.chainService.updateChain(chain)
                sidebarRowLogger.debug(" Renamed chain \(actualId) to '\(newName)'")
            case .schedule(let schedule):
                _ = try await itemLibrary.automationService.updateSchedule(
                    scheduleId: schedule.scheduleId,
                    newName: newName
                )
                sidebarRowLogger.debug(" Renamed schedule \(actualId) to '\(newName)'")
            case .trigger(let trigger):
                _ = try await itemLibrary.automationService.updateTrigger(
                    triggerId: trigger.triggerId,
                    newName: newName
                )
                sidebarRowLogger.debug(" Renamed trigger \(actualId) to '\(newName)'")
            default:
                sidebarRowLogger.debug(" ⚠️ Unknown item type for rename")
            }
        } catch {
            sidebarRowLogger.error(" Failed to rename item: \(error.localizedDescription)")
        }
    }
}
