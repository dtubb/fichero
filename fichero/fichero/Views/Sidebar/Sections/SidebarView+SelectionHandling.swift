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
    //
    // `reason` says which of the two callers this is — it only reaches the opt-in diagnostic
    // line (`RenderDiagnostics`), so a doubled selection in the console names its second source.
    func handleSelectionChange(_ newDestination: SidebarDestination?, reason: String) {
        sidebarViewLogger.info("selectedItemId changed to: \(newDestination?.serializedID ?? "nil")")
        if RenderDiagnostics.printChanges {
            let alreadyHandled = lastHandledSelectionDestination == newDestination
            sidebarViewLogger.info(
                "◆ handleSelectionChange reason: \(reason, privacy: .public), already handled: \(alreadyHandled)"
            )
        }
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

    /// Drives a restored/persisted `selectedItemId` into the view mode when it
    /// hasn't been handled yet (#2548). Idempotent via `lastHandledSelectionId`.
    func reconcileRestoredSelection() {
        guard sidebarShouldReconcileSelection(
            selectedId: selectedDestination?.serializedID,
            lastHandled: lastHandledSelectionDestination?.serializedID
        ) else { return }
        handleSelectionChange(selectedDestination, reason: "reconcile")
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

        // Kind + id ONLY — String(describing: itemType) dumped the whole
        // Document (pageContent = an entire book) into os_log; see
        // MainContentModifiers+ViewMode for the measured cost.
        sidebarViewLogger.info(
            "handleSelection: \(item.name) (category: \(item.category.rawValue), id: \(item.id))"
        )

        handleLibrarySwitching(for: item)
        handleItemTypeSelection(item)
    }

    private func handleLibrarySwitching(for item: SidebarItem) {
        // Switch window's library if the selected item belongs to a different library
        if let itemLibraryId = item.libraryId, itemLibraryId != windowState.libraryId {
            sidebarViewLogger.info("Switching window from library \(windowState.libraryId) to library \(itemLibraryId)")
            // Unreached for a sidebar click since #4995/#4996: `handleSelectionDestination`
            // switches the library FIRST and routes only once it has landed
            // (`CrossLibraryRoute`). Kept as the last line of defence for any other caller.
            windowState.libraryId = itemLibraryId
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
            routeAutomationFamilySelection(item.itemType)
        case .folder:
            handleFolderSelection(item)
        case .libraryHeader:
            // Library headers just toggle expansion
            sidebarViewLogger.info("Library header clicked - just toggling expansion")
        }
    }

    /// #4525 (V8): these four clicks were DROPPED ("handled by mode sidebar" —
    /// no such handling existed), so selecting a chain, schedule, trigger or
    /// batch changed the sidebar highlight and nothing else — every pane went
    /// stale relative to it, and the existing editors (ChainEditorView,
    /// Schedule/TriggerDetailView) were reachable only on create or not at
    /// all. Every sidebar selection now sets `viewMode`; the panes follow one
    /// axis.
    private func routeAutomationFamilySelection(_ itemType: SidebarItem.ItemType) {
        switch itemType {
        case .chain(let chain):
            sidebarViewLogger.info("Switching to chain view: \(chain.name)")
            sidebarMode = .workflows
            viewMode = .chain(chain)
        case .schedule(let schedule):
            sidebarViewLogger.info("Switching to schedule view: \(schedule.id)")
            sidebarMode = .automation
            viewMode = .schedule(schedule)
        case .trigger(let trigger):
            sidebarViewLogger.info("Switching to trigger view: \(trigger.id)")
            sidebarMode = .automation
            viewMode = .trigger(trigger)
        case .batch(let batch):
            // `AppViewMode.batch` DELETED (#4705 increment 4a) — batch
            // monitoring has been unified under Activity for a while
            // (restore already redirected the persisted string the same
            // way); this construction site now does directly what it used
            // to do indirectly via the placeholder.
            sidebarViewLogger.info("Switching to batch view: \(batch.id)")
            sidebarMode = .activity
            viewMode = .activity(nil)
        default:
            sidebarViewLogger.error("routeAutomationFamilySelection got a non-family item type")
        }
    }

    /// One typed routing seam for every document-row flavor (#4335): alias →
    /// its target (#2591), workflow mirror → the editor (#4292), everything
    /// else (including a workspace folder — #4705 "5a", #4812) → the library
    /// view. Order matters: the specialized flavors must win over the
    /// generic library fallback.
    ///
    /// A workspace USED to divert here to the Research surface (#4308/#4335,
    /// 229f76368: "selecting a workspace routes to the Research surface") —
    /// that need is now 5b/5c's (a research project's own chat/tasks/browser
    /// rendition), not this document-row's. A workspace is an ordinary
    /// folder `Document` (`isWorkspace: Bool` is a marker, not a different
    /// KIND of row) and selects exactly like any other folder now.
    func routeDocumentSelection(_ doc: Document, libraryId: UUID?) {
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
            // Expansion only (Daniel, 2026-08-10): a workflow section folder
            // must not hijack the pane into the empty 'Select a Workflow'
            // surface; selecting an actual WORKFLOW opens its editor.
            sidebarViewLogger.info("Workflow folder — just toggling expansion")
        case .automation, .batch, .activity:
            // Automation-related folders
            sidebarViewLogger.info("Automation folder - just toggling expansion")
        case .folder, .library:
            // Regular folders just toggle expansion
            sidebarViewLogger.info("Regular folder - just toggling expansion")
        }
    }
}

// MARK: - Reveal in sidebar (2026-08-23)

extension Notification.Name {
    /// Ask the sidebar to expand, load, and select the row for a document —
    /// posted by the relaunch-restore path (and usable by any future
    /// "Reveal in Sidebar" verb). userInfo: `documentId`.
    static let sidebarRevealDocument = Notification.Name("sidebarRevealDocument")
}

extension SidebarView {
    /// Expand the ancestor chain, LOAD each level so the row exists, then
    /// select through the same proposal seam a click uses. Tries each open
    /// library — `sidebarRevealPath` answers nil for a library that does not
    /// know the document.
    func revealDocument(_ documentId: String) async {
        for library in libraryManager.openLibraries {
            let store = library.documentStore
            guard let path = await store.sidebarRevealPath(to: documentId) else { continue }
            for ancestor in path {
                sidebarState.expandedItems.insert(ancestor.id)
            }
            for ancestor in path {
                await store.cacheSidebarChildren(of: ancestor)
            }
            applySidebarSelectionProposal([.document(documentId)])
            return
        }
        sidebarViewLogger.info("revealDocument: \(documentId) not found in any open library")
    }
}
