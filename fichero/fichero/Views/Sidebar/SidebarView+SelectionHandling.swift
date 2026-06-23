import SwiftUI

// MARK: - Selection Handling

extension SidebarView {
    // Routes a `selectedItemId` value to the matching `sidebarMode` / `viewMode`.
    //
    // Extracted from the inline `.onChange(of: selectedItemId)` closure so the
    // SAME routing can also be invoked to reconcile a restored selection once
    // the sidebar caches are ready (#2548) — see `sidebarShouldReconcileSelection`.
    // `lastHandledSelectionId` keeps this idempotent: re-invoking with the same
    // id is a no-op, so the reconcile path never double-handles a live click.
    // swiftlint:disable:next cyclomatic_complexity function_body_length
    func handleSelectionChange(_ newId: String?) {
        sidebarViewLogger.info("selectedItemId changed to: \(newId ?? "nil")")
        if newId == nil || !(newId?.hasPrefix("run:") ?? false) {
            selectedActivityItemIds.removeAll()
        } else if let runId = newId {
            selectedActivityItemIds = [runId]
        }
        guard let id = newId else {
            lastHandledSelectionId = nil
            return
        }
        if lastHandledSelectionId == id {
            return
        }
        lastHandledSelectionId = id
        if let libraryId = selectedLibraryId(from: id) {
            if windowState.libraryId != libraryId {
                windowState.libraryId = libraryId
            }
            sidebarMode = .library
            viewMode = .library(nil)
            return
        }
        if id == "activity-browser" {
            sidebarMode = .activity
            viewMode = .activity(nil)
            return
        }
        if id == "workflows-browser" {
            sidebarMode = .workflows
            viewMode = .workflow(nil)
            return
        }
        if id == "batches-browser" {
            viewMode = .batches
            return
        }
        if id == "entities-browser" {
            sidebarMode = .library
            viewMode = .library(nil)
            return
        }
        if id == "comparison-browser" {
            sidebarMode = .chat
            viewMode = .comparison(nil)
            return
        }
        if id == "research-browser" {
            sidebarMode = .research
            return
        }
        if id.hasPrefix("run:"),
           let selectedRun = unifiedSelectedRun(forSidebarId: id) {
            viewMode = .activity(selectedRun.toSelectedRun())
            return
        }
        let item = findItemById(id, in: allCachedItems)
        handleSelection(item)
    }

    /// Drives a restored/persisted `selectedItemId` into the view mode when it
    /// hasn't been handled yet (#2548). Idempotent via `lastHandledSelectionId`.
    func reconcileRestoredSelection() {
        guard sidebarShouldReconcileSelection(
            selectedId: selectedItemId,
            lastHandled: lastHandledSelectionId
        ) else { return }
        handleSelectionChange(selectedItemId)
    }

    // Handle sidebar item selection and update view mode
    // swiftlint:disable:next cyclomatic_complexity function_body_length
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
            sidebarMode = .library
            viewMode = .library(doc)
        case .savedSearch(let search):
            sidebarViewLogger.info("Switching to search view with search: \(search.name)")
            sidebarMode = .search
            viewMode = .search(search)
        case .conversation(let conversation):
            sidebarViewLogger.info("Switching to chat view with conversation: \(conversation.id)")
            sidebarMode = .chat
            viewMode = .chat(conversation)
        case .workflow(let workflow):
            sidebarViewLogger.info("Switching to workflow view with workflow: \(workflow.name)")
            sidebarMode = .workflows
            viewMode = .workflow(workflow)
        case .activityRun(let activity):
            let selectedRun = SelectedActivityRun(
                id: activity.threadId ?? activity.id,
                name: activityExtractWorkflowName(from: activity),
                workflowId: activity.workflowId,
                threadId: activity.threadId ?? activity.batchId.map { "batch:\($0)" },
                timestamp: activity.parsedTimestamp ?? Date(),
                status: activityMapActivityType(activity.type).toStatusType(),
                isLive: false,
                childType: nil
            )
            sidebarViewLogger.info("Switching to activity view with run: \(selectedRun.id)")
            sidebarMode = .activity
            viewMode = .activity(selectedRun)
        case .chain, .comparison, .schedule, .trigger, .batch:
            // These item types are handled by their specialized sidebar modes
            sidebarViewLogger.info("Item type \(item.category.rawValue) clicked - detail views handled by mode sidebar")
        case .folder:
            // Check if this is a category folder (Search, Chat, Workflow)
            // and switch to that view mode even if empty
            sidebarViewLogger.info("Folder clicked: category = \(item.category.rawValue)")
            switch item.category {
            case .search:
                sidebarViewLogger.info("Switching to empty search view")
                sidebarMode = .search
                viewMode = .search(nil)
            case .chat:
                sidebarViewLogger.info("Switching to empty chat view")
                sidebarMode = .chat
                viewMode = .chat(nil)
            case .workflow:
                sidebarViewLogger.info("Switching to empty workflow view")
                sidebarMode = .workflows
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
