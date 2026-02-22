import SwiftUI

// MARK: - Selection Handling

extension SidebarView {
    /// Handle sidebar item selection and update view mode
    func handleSelection(_ item: SidebarItem?) {
        guard let item = item else {
            sidebarViewLogger.info("handleSelection called with nil item")
            return
        }

        let itemTypeDesc = String(describing: item.itemType)
        sidebarViewLogger.info(
            "handleSelection: \(item.name) (category: \(item.category.rawValue), type: \(itemTypeDesc))"
        )

        // Switch window's library if the selected item belongs to a different library
        if let itemLibraryId = item.libraryId, itemLibraryId != windowState.libraryId {
            sidebarViewLogger.info("Switching window from library \(windowState.libraryId) to library \(itemLibraryId)")
            windowState.libraryId = itemLibraryId
            // Wait for next run loop to allow SwiftUI to update environment objects
            // This ensures the new library's services are injected before we try to use them
        } else {
            sidebarViewLogger.info("Item belongs to current library: \(windowState.libraryId)")
        }

        // Update view mode based on item type
        switch item.itemType {
        case .document(let doc):
            sidebarViewLogger.info("Switching to library view with document: \(doc.name)")
            viewMode = .library(doc)
        case .savedSearch(let search):
            sidebarViewLogger.info("Switching to search view with search: \(search.name)")
            viewMode = .search(search)
        case .conversation(let conversation):
            sidebarViewLogger.info("Switching to chat view with conversation: \(conversation.id)")
            viewMode = .chat(conversation)
        case .workflow(let workflow):
            sidebarViewLogger.info("Switching to workflow view with workflow: \(workflow.name)")
            viewMode = .workflow(workflow)
        case .chain, .comparison, .schedule, .trigger, .batch, .activityRun:
            // These item types are handled by their specialized sidebar modes
            sidebarViewLogger.info("Item type \(item.category.rawValue) clicked - detail views handled by mode sidebar")
        case .folder:
            // Check if this is a category folder (Search, Chat, Workflow)
            // and switch to that view mode even if empty
            sidebarViewLogger.info("Folder clicked: category = \(item.category.rawValue)")
            switch item.category {
            case .search:
                sidebarViewLogger.info("Switching to empty search view")
                viewMode = .search(nil)
            case .chat:
                sidebarViewLogger.info("Switching to empty chat view")
                viewMode = .chat(nil)
            case .workflow:
                sidebarViewLogger.info("Switching to empty workflow view")
                viewMode = .workflow(nil)
            case .automation, .batch, .activity:
                // Automation-related folders
                sidebarViewLogger.info("Automation folder - just toggling expansion")
            case .folder, .library:
                // Regular folders just toggle expansion
                sidebarViewLogger.info("Regular folder - just toggling expansion")
            }
        case .libraryHeader:
            // Library headers just toggle expansion
            sidebarViewLogger.info("Library header clicked - just toggling expansion")
        }
    }
}
