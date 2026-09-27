import OSLog
import SwiftUI

/// This file's own log category, rather than widening `ContentView+StateEvents.swift`'s
/// `private let eventHandlersLogger`.
///
/// A file-scope `private` is invisible to a DIFFERENT file even in the same module, so splitting
/// a file along a `// MARK:` boundary breaks every reference to one — and `swiftc -parse` cannot
/// see it, because the syntax is fine. Dropping the `private` would widen access across the whole
/// target to satisfy one extraction; a category of its own costs three lines and makes
/// `category == "ContentViewEventHandlers"` show these handlers without the state-event traffic.
/// Same choice, same reasoning, as `DocumentService+PageIO.swift` made a few hours earlier.
private let eventHandlersLogger = Logger(
    subsystem: "app.fichero.fichero", category: "ContentViewEventHandlers"
)

// MARK: - Event Handlers

extension ContentView {

    /// Handles `.onReceive` of `NSApplication.willTerminateNotification`.
    /// Auto-saves the editing workflow when the app quits.
    func handleWillTerminate() {
        // Auto-save workflow when app quits (#4882: `activeWorkflowItem`,
        // not `viewMode` — a Library-driven active workflow must save on
        // quit exactly like a sidebar-driven one). HOLE 2 (2026-09-19): the
        // SAME id-mismatch guard `shouldAutoSaveWorkflow` applies elsewhere —
        // `autoSaveWorkflow`'s real save target is `editingWorkflow.id`
        // (`Workflow.toAPIFormat().id`), not `item.id`; if `item`'s own load
        // never completed, `editingWorkflow` holds a DIFFERENT workflow's
        // content and saving it under the belief it's `item`'s would
        // silently write to whatever id it actually carries.
        if let item = activeWorkflowItem {
            guard editingWorkflow.id == item.id else {
                eventHandlersLogger.error(
                    "Refusing quit-time autosave: editor holds workflow \(self.editingWorkflow.id), not the active \(item.id)"
                )
                return
            }
            // HOLE 3 (2026-09-19): never autosave without a baseline —
            // `lastSyncedWorkflow == nil` means `item` was never
            // successfully loaded, so there is nothing of the user's to
            // save. Loud when the editor holds a non-empty graph anyway:
            // that would be real work about to be silently dropped.
            guard lastSyncedWorkflow != nil else {
                if !editingWorkflow.nodes.isEmpty || !editingWorkflow.edges.isEmpty {
                    eventHandlersLogger.error(
                        """
                        Refusing quit-time autosave for \(item.id): never loaded, yet the editor \
                        holds \(self.editingWorkflow.nodes.count) nodes. UNSAVED WORK MAY BE DROPPED
                        """
                    )
                }
                return
            }
            let workflowToSave = editingWorkflow
            Task { @MainActor in
                await autoSaveWorkflow(workflowId: item.id, workflow: workflowToSave)
            }
        }
    }

    /// Handles typed entity-search requests from inspector/KG lozenges.
    /// Fires the toolbar search for an entity-lozenge click.
    func handleEntitySearchRequested() {
        // Click on a blue entity lozenge anywhere in the UI fires the
        // toolbar search for that name. Same code path as typing in
        // the toolbar — the TRANSIENT pipeline (#4086/#4106), persisting
        // nothing unless the request explicitly asks for a smart search.
        //
        // When the lozenge knows its entity_type (people / places /
        // keywords / etc.), we construct a SCOPED query like
        // `keywords:"social license"` so the search hits only that
        // artifact type — exactly the docs the user is asking about.
        // Free-text fallback when the type isn't tagged so older
        // call sites still work.
        guard let name = entitySearchState.requestedName,
              !name.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        let entityType = entitySearchState.requestedEntityType
        let query: String
        if let entityType, !entityType.isEmpty {
            let needsQuoting = name.contains(" ")
            query = needsQuoting
                ? "\(entityType):\"\(name)\""
                : "\(entityType):\(name)"
        } else {
            query = name
        }
        toolbarSearchText = query
        runToolbarSearch(query)
        // Smart folder in one click (#4114): the entity menu's "Save Mentions
        // as Smart Search" persists the SAME scoped query to the sidebar.
        if entitySearchState.requestedSaveAsSmartSearch {
            Task { @MainActor in
                do {
                    _ = try await savedSearchService.saveSearch(
                        query: query,
                        isSmartSearch: true,
                        searchType: "hybrid",
                        sortBy: "relevance",
                        sortDirection: "desc"
                    )
                    try await savedSearchService.loadSavedSearches()
                } catch {
                    eventHandlersLogger.error("smart-search save failed: \(error.localizedDescription)")
                }
            }
        }
    }

    /// Handles typed source-open requests from inspector/KG/search surfaces.
    ///
    /// `.reader` requests NAVIGATE — today's behavior, unchanged except the
    /// mode switch is now gated on `isTakeoverMode` instead of firing
    /// unconditionally, so the one remaining bespoke takeover (`.research`)
    /// is the only mode a reader-destined reveal still switches away from.
    /// `.preview`/`.both` requests REVEAL (#4834): Preview and/or the
    /// Reader's transcript show the source, through `sourceRevealDocument`,
    /// WITHOUT writing the sidebar mode, `browserSelection`/`detailDocument`,
    /// or the inspector sidebar/pane focus — a knowledge-surface click keeps
    /// you exactly where you were. Both destinations share ONE
    /// `locationService.resolve` (inside `revealResolvedSource`) and post to
    /// BOTH highlight channels — the passage (`postClaimPassageAnchor`, the
    /// Reader transcript) and the region (`.ficheroNavigateToPage`'s `bbox`,
    /// the source image) — so a `.both` request always lights both, and a
    /// `.reader`/`.preview` request lights whichever channel is honest for
    /// what it asked to change. (#978/#979/#982/#2105/#3449)
    func handleOpenClaimSource() {
        guard let request = claimSourceNavigationState.currentRequest else { return }
        let docId = request.documentId
        let isKnowledgeSurface = request.destination != .reader

        if !isKnowledgeSurface {
            // Navigational surfaces legitimately ask to GO there — switch
            // out of a bespoke takeover, but never for a knowledge-surface
            // reveal, which must never move the sidebar.
            if Self.isTakeoverMode(sidebarMode) {
                sidebarMode = .library
            }
            showInspectorSidebar = true
            focusedPane = .inspector
        }
        if let claimId = request.claimId {
            // Focus/highlight state, not selection (KGFocusState's own
            // doc comment: "intentionally separate from document/sidebar
            // selection") — safe to update for either destination.
            claimFocusState.selectClaim(
                claimId: claimId,
                claimText: request.claimText,
                sourceDocumentId: docId,
                pageLabel: request.pageLabel,
                charStart: request.charStart,
                charEnd: request.charEnd
            )
            if isKnowledgeSurface {
                revealingClaimId = claimId
                // Preserve whatever entity is currently focused (#4834): the
                // default `entityId: nil` on `focusClaim` is a trap — omitting
                // it here CLEARS `kgFocusState.focusedEntityId`, which flips
                // `DocumentInspector.inspectorArm` away from `.entity` and
                // tears the biography down mid-click (maintainer test,
                // 2026-09-19, finding A1).
                kgFocusState.focusClaim(
                    claimId: claimId,
                    entityId: kgFocusState.focusedEntityId,
                    sourceDocumentId: docId,
                    sourcePageLabel: request.pageLabel
                )
            }
        }
        recordClaimPassageAnchor(request)
        // Resolve page-child source documents to their parent file — now via
        // the ONE engine route (#3577) instead of the inline client-side
        // walk — then either navigate or reveal per destination, and post
        // to both highlight channels either way.
        Task { @MainActor in
            await revealResolvedSource(request)
            if isKnowledgeSurface { revealingClaimId = nil }
            postClaimPassageAnchor(documentId: docId)
            var info: [String: Any] = ["documentId": docId]
            if let claimId = request.claimId { info["claimId"] = claimId }
            if let pageLabel = request.pageLabel { info["pageLabel"] = pageLabel }
            if let charStart = request.charStart { info["charStart"] = charStart }
            if let charEnd = request.charEnd { info["charEnd"] = charEnd }
            // Forward the source region so the page reader can highlight the
            // exact bbox — the "reveal in Preview + highlight" tier (#2105/#3449).
            // Only present when the anchor actually carries a bbox.
            if let bbox = request.bbox, !bbox.isEmpty { info["bbox"] = bbox }
            NotificationCenter.default.post(
                name: .ficheroNavigateToPage,
                object: nil,
                userInfo: info
            )
        }
    }

    /// Handles `.onReceive` of `.ficheroSelectDocumentRequested`.
    /// AppleScript command path for `select document id "..."`.
    func handleAppleScriptSelectDocument(_ note: Notification) {
        guard let documentId = note.userInfo?["id"] as? String,
              !documentId.isEmpty else { return }
        sidebarMode = .library
        showSidebar = true
        showInspectorSidebar = true
        focusedPane = .inspector
        browserSelection = [documentId]
        sidebarSelectionState.selectedItemId = "doc:\(documentId)"
    }

    /// Handles `.onReceive` of `.ficheroShowPanelRequested`.
    /// AppleScript command path for `show panel "library|inspector|kg|activity"`.
    func handleAppleScriptShowPanel(_ note: Notification) {
        guard let rawPanel = note.userInfo?["panel"] as? String else { return }
        switch rawPanel.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "library":
            sidebarMode = .library
            showSidebar = true
            focusedPane = .content
        case "inspector":
            showInspectorSidebar = true
            focusedPane = .inspector
        case "kg", "knowledge graph", "knowledge-graph":
            // #4705 increment 3: the KG sidebar mode retired; "kg" now opens
            // the library-wide Entities table instead.
            sidebarMode = .library
            showSidebar = true
            sidebarSelectionState.selectedItemId = "entities-browser"
            focusedPane = .content
        case "activity":
            sidebarMode = .activity
            showSidebar = true
            sidebarSelectionState.selectedItemId = "activity-browser"
            focusedPane = .content
        default:
            return
        }
    }
}
