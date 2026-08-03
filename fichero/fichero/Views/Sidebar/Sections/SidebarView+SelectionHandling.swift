import SwiftUI

// MARK: - Selection Handling

extension SidebarView {
    // Routes a typed sidebar selection to the matching `sidebarMode` / `viewMode`.
    //
    // Extracted from the inline `.onChange(of: selectedItemId)` closure so the
    // SAME routing can also be invoked to reconcile a restored selection once
    // the sidebar caches are ready (#2548) — see `sidebarShouldReconcileSelection`.
    // `lastHandledSelectionDestination` keeps this idempotent: re-invoking with the same
    // id is a no-op, so the reconcile path never double-handles a live click.
    func handleSelectionChange(_ newDestination: SidebarDestination?) {
        sidebarViewLogger.info("selectedItemId changed to: \(newDestination?.serializedID ?? "nil")")
        guard let destination = newDestination else {
            lastHandledSelectionDestination = nil
            return
        }
        if lastHandledSelectionDestination == destination {
            return
        }
        lastHandledSelectionDestination = destination
        handleSelectionDestination(destination)
        // The routed `sidebarMode`/`viewMode` are written: the click is
        // committed and the content column is now the thing we are waiting on
        // (#4228). Handing straight from one interval to the next means the two
        // bars in Instruments abut, so a gap between them is a real gap.
        InteractionProfile.end(.selectionCommit)
        InteractionProfile.begin(.selectionToContent, detail: destination.serializedID)
    }

    private func handleSelectionDestination(_ destination: SidebarDestination) {
        switch destination {
        case .library(let libraryId):
            if windowState.libraryId != libraryId {
                windowState.libraryId = libraryId
            }
            sidebarMode = .library
            viewMode = .library(nil)
            return
        case .browser(let section):
            handleBrowserSelectionDestination(section)
            return
        case .run:
            guard let selectedRun = unifiedSelectedRun(forSidebarId: destination.serializedID) else { return }
            viewMode = .activity(selectedRun.toSelectedRun())
            return
        default:
            let item = cachedItem(id: destination.serializedID)
            if item == nil {
                // Launch-restore can arrive before the sidebar caches are
                // built; the id resolves to nothing yet. Un-stamp the
                // destination so `reconcileRestoredSelection()` (#2548)
                // re-drives it once caches exist — otherwise the restored
                // selection is marked handled without ever being applied
                // and the highlighted row never matches the detail view.
                lastHandledSelectionDestination = nil
            }
            handleSelection(item)
        }
    }

    // `SidebarBrowserDestination` has exactly these 6 cases (see
    // `SidebarStateManagers.swift`), each routing to a distinct sidebar
    // mode/view mode — split out of `handleSelectionDestination` to keep
    // that switch's complexity low.
    private func handleBrowserSelectionDestination(_ section: SidebarBrowserDestination) {
        switch section {
        case .activity:
            sidebarMode = .activity
            viewMode = .activity(nil)
        case .workflows:
            sidebarMode = .workflows
            viewMode = .workflow(nil)
        case .batches:
            viewMode = .batches
        case .entities:
            sidebarMode = .library
            viewMode = .library(nil)
        case .comparison:
            sidebarMode = .chat
            viewMode = .comparison(nil)
        case .research:
            sidebarMode = .research
        }
    }

    /// Drives a restored/persisted `selectedItemId` into the view mode when it
    /// hasn't been handled yet (#2548). Idempotent via `lastHandledSelectionId`.
    func reconcileRestoredSelection() {
        guard sidebarShouldReconcileSelection(
            selectedId: selectedDestination?.serializedID,
            lastHandled: lastHandledSelectionDestination?.serializedID
        ) else { return }
        handleSelectionChange(selectedDestination)
    }

    // Handle sidebar item selection and update view mode
    /// Resolve an alias row to its live target and route the library view
    /// there. Dangling (target deleted) → `aliasErrorMessage` alert.
    private func resolveAliasSelection(_ doc: Document, libraryId: UUID?) {
        guard let targetId = doc.aliasTargetId,
              let libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else {
            // #116/#4416: raw `doc.name` here named the alias by its storage
            // filename in an alert — the same shape as the delete-confirmation
            // leak, on a message the user can only act on if it names the thing
            // they recognise.
            sidebarState.aliasErrorMessage =
                "The original item for “\(DocumentTitle.displayName(for: doc))” can’t be found."
            return
        }
        Task { @MainActor in
            do {
                let target = try await library.documentService.getDocument(targetId)
                // The user may have selected something else while the fetch
                // was in flight — never clobber the newer selection.
                guard selectedItemId == "doc:\(doc.id)" else { return }
                sidebarViewLogger.info("Alias \(doc.id) resolved to target \(target.id)")
                sidebarMode = .library
                viewMode = .library(target)
            } catch {
                guard selectedItemId == "doc:\(doc.id)" else { return }
                sidebarViewLogger.error(
                    "Dangling alias \(doc.id): target \(targetId) unavailable — \(error.localizedDescription)"
                )
                sidebarState.aliasErrorMessage =
                    "The original item for “\(DocumentTitle.displayName(for: doc))” can’t be found."
            }
        }
    }

    func handleSelection(_ item: SidebarItem?) {
        guard let item = item else {
            sidebarViewLogger.info("handleSelection called with nil item")
            return
        }

        let itemTypeDesc = String(describing: item.itemType)
        sidebarViewLogger.info(
            "handleSelection: \(item.name) (category: \(item.category.rawValue), type: \(itemTypeDesc))"
        )

        handleLibrarySwitching(for: item)
        handleItemTypeSelection(item)
    }

    private func handleLibrarySwitching(for item: SidebarItem) {
        // Switch window's library if the selected item belongs to a different library
        if let itemLibraryId = item.libraryId, itemLibraryId != windowState.libraryId {
            sidebarViewLogger.info("Switching window from library \(windowState.libraryId) to library \(itemLibraryId)")
            windowState.libraryId = itemLibraryId
            // Wait for next run loop to allow SwiftUI to update environment objects
            // This ensures the new library's services are injected before we try to use them
        } else {
            sidebarViewLogger.info("Item belongs to current library: \(windowState.libraryId)")
        }
    }

    private func handleItemTypeSelection(_ item: SidebarItem) {
        // Update view mode based on item type
        switch item.itemType {
        case .document(let doc):
            routeDocumentSelection(doc, libraryId: item.libraryId)
        case .savedSearch(let search):
            // Saved searches run through the transient toolbar-search path
            // (#4106/S2) — results render INTO the Library view; there is no
            // separate search mode anymore.
            sidebarViewLogger.info("Running saved search: \(search.name)")
            sidebarMode = .library
            viewMode = .library(nil)
            onRunSavedSearch?(search)
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
                libraryId: item.libraryId,
                libraryName: item.libraryId.flatMap { libraryManager.getLibrary(id: $0)?.displayName },
                childType: nil
            )
            sidebarViewLogger.info("Switching to activity view with run: \(selectedRun.id)")
            sidebarMode = .activity
            viewMode = .activity(selectedRun)
        case .comparison(let summary):
            // #4335: a comparison history row opens the comparison detail
            // surface — same mode `browser(.comparison)` uses for the empty
            // state, here carrying the clicked summary.
            sidebarViewLogger.info("Switching to comparison view: \(summary.comparisonId)")
            sidebarMode = .chat
            viewMode = .comparison(summary)
        case .chain, .schedule, .trigger, .batch:
            // These item types are handled by their specialized sidebar modes
            sidebarViewLogger.info("Item type \(item.category.rawValue) clicked - detail views handled by mode sidebar")
        case .folder:
            handleFolderSelection(item)
        case .libraryHeader:
            // Library headers just toggle expansion
            sidebarViewLogger.info("Library header clicked - just toggling expansion")
        }
    }

    /// One typed routing seam for every document-row flavor (#4335): alias →
    /// its target (#2591), workflow mirror → the editor (#4292), workspace →
    /// the Research surface (#4308), everything else → the library view.
    /// Order matters: the specialized flavors must win over the generic
    /// library fallback.
    private func routeDocumentSelection(_ doc: Document, libraryId: UUID?) {
        if doc.isAlias {
            // Finder semantics (#2591): selecting an alias opens its TARGET.
            // Resolution fetches from the backend (caches are lazy, so a
            // cache miss is NOT proof of a dangling alias); a genuinely
            // missing target surfaces a loud alert, never a stand-in.
            resolveAliasSelection(doc, libraryId: libraryId)
            return
        }
        if doc.isWorkflowNode {
            routeWorkflowMirrorSelection(doc, libraryId: libraryId)
            return
        }
        if doc.isWorkspace {
            // #4308/#4335: a workspace node opens the Research surface (the
            // agent workspace), not the plain folder browse.
            sidebarViewLogger.info("Routing workspace node \(doc.id) to the Research surface")
            sidebarMode = .research
            return
        }
        sidebarViewLogger.info("Switching to library view with document: \(doc.name)")
        sidebarMode = .library
        viewMode = .library(doc)
    }

    /// #4292: a workflow mirror node is an editor surface, never a preview.
    /// Routing it like a plain document sent it to the library/preview path,
    /// whose container fallback is "No Preview available".
    private func routeWorkflowMirrorSelection(_ doc: Document, libraryId: UUID?) {
        let workflows = (
            libraryId.flatMap { libraryManager.getLibrary(id: $0) }
                ?? libraryManager.globalLibrary
        )?.workflowStore.workflows ?? []
        sidebarViewLogger.info("Routing workflow mirror node \(doc.id) to the workflow editor")
        sidebarMode = .workflows
        viewMode = .workflow(sidebarWorkflowDestination(for: doc, workflows: workflows))
    }

    private func handleFolderSelection(_ item: SidebarItem) {
        // Check if this is a category folder (Search, Chat, Workflow)
        // and switch to that view mode even if empty
        sidebarViewLogger.info("Folder clicked: category = \(item.category.rawValue)")
        switch item.category {
        case .search:
            // Saved-search section folders just toggle expansion — search
            // itself lives in the toolbar field (#4106/S2).
            sidebarViewLogger.info("Saved-search folder - just toggling expansion")
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
    }
}
