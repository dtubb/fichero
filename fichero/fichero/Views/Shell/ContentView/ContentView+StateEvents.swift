import OSLog
import SwiftUI

// MARK: - ContentView Event & State Change Handlers

private let stateEventsLogger = Logger(
    subsystem: "app.fichero.fichero", category: "ContentViewStateEvents"
)

extension ContentView {

    // MARK: - onChange Handlers — Sidebar & Selection

    /// Handles `.onChange(of: sidebarSelectionState.selectedItemId)` — the single
    /// runtime source (#3036). @SceneStorage `selectedSidebarItemId` is now purely
    /// a persistence adapter (restore-once + write-through), not a second source.
    /// Restores per-folder view mode and drives the inspector from sidebar selection.
    func handleSidebarSelectionChange(_ newFolderId: String?) {
        if isRestoringNavigationHistory { return }
        if newFolderId == "entities-browser" {
            viewDisplayMode = .list
            browserSelection.removeAll()
            detailDocument = nil
            kgFocusState.clear()
            return
        }
        kgFocusState.clear()
        // Restore per-folder view mode when switching folders.
        // Priority: per-folder save > per-scene @SceneStorage value > global default.
        // The @SceneStorage value holds the user's last choice for this window/tab
        // and should win for new or unsaved folders so spatial is not forced (#2311).
        if let saved = displayMode(for: newFolderId) {
            viewDisplayMode = normalizedViewDisplayMode(saved)
        } else {
            let normalizedSceneValue = normalizedViewDisplayMode(viewDisplayMode)
            let normalizedDefault = normalizedViewDisplayMode(defaultLibraryViewDisplayMode)
            // If the scene value is unset or unavailable for this context, fall
            // back to the global default rather than forcing a spatial/canvas mode.
            if normalizedSceneValue != normalizedDefault {
                viewDisplayMode = normalizedSceneValue
            } else if viewDisplayMode != normalizedDefault {
                viewDisplayMode = normalizedDefault
            }
        }

        // Clear grid selection on sidebar folder change so the folder
        // inspector shows by default. Without this, a stale browserSelection
        // from a previous folder can resolve to a child of the new folder
        // (when ids happen to be present in the new folder's children),
        // suppressing the folder inspector. (#712)
        // EXCEPT the library-root row: clicking "/library" is a re-root of
        // the listing, not a folder change — clearing there cascaded
        // detailDocument = nil and blanked the preview while an image was
        // still selected (#4299).
        if BrowserSelectionPreviewPolicy.shouldClearBrowseContext(onSidebarItemChangeTo: newFolderId) {
            browserSelection.removeAll()
            // #4523: a NEW library container is a new browse context, so the
            // remembered run selection is stale scope — drop it. Navigation to
            // workflow/chain/section rows does NOT reach this branch, which is
            // the carve-out that lets "select a file, click the workflow, Run"
            // keep the file as the run's scope instead of the whole folder.
            windowState.preservedDocumentSelection = []
        }

        // Drive the inspector from sidebar selection so clicking a folder
        // (or any document row) in the sidebar populates the inspector.
        // Sidebar IDs are prefixed "doc:UUID" — extract the bare doc ID
        // before looking up. (#696 — folder inspector blank after sidebar
        // click. MEMORY: SidebarItem.id is 'doc:UUID', strip prefix.)
        guard let prefixedId = newFolderId,
              prefixedId.hasPrefix("doc:") else { return }
        let docId = String(prefixedId.dropFirst("doc:".count))
        // Force-clear any previewed document immediately so the inspector
        // reflects the newly-selected folder before the async applyDoc
        // resolution completes. Without this, detailDocument stays set to
        // the previously-previewed file and inspectorDocument step 1 can
        // match it against the stale browserSelection. (#795)
        detailDocument = nil
        // Closure to apply a resolved Document — sets detailDocument (#961).
        // Folders now keep the current layout so the WebKit/reading pane
        // stays visible for folder-level aggregate content (#1405).
        // #4523 live regression (2026-08-04): the apply also feeds the
        // window's run selection — see `applySidebarSelectedDocument`.
        let applyDoc: (Document) -> Void = { doc in
            applySidebarSelectedDocument(doc)
        }
        if detailDocument?.id != docId {
            if let doc = documentStore.currentDocuments.first(where: { $0.id == docId }) {
                applyDoc(doc)
            } else {
                Task { @MainActor in
                    let fetched = try? await documentStore.documentService.getDocument(docId)
                    if let fetched, sidebarSelectionState.selectedItemId == prefixedId {
                        applyDoc(fetched)
                    }
                }
            }
        }
    }

    /// Handles `.onChange(of: columnVisibility)`.
    /// Persists column visibility and keeps explicit sidebar state in sync.
    func handleColumnVisibilityChange(_ newVisibility: NavigationSplitViewVisibility) {
        if horizontalSizeClass == .compact || shouldUseRuntimeSidebarCollapse {
            return
        }

        // Persist column visibility to @SceneStorage
        // Map NavigationSplitViewVisibility to raw int for @SceneStorage
        columnVisibilityRaw = Self.persistedColumnVisibilityRaw(for: newVisibility)

        // Keep explicit left-sidebar state in sync with split-view visibility.
        // In this app's layout, `.doubleColumn` is sidebar + content.
        if newVisibility == .detailOnly {
            showSidebar = false
        } else if newVisibility == .all || newVisibility == .doubleColumn || newVisibility == .automatic {
            showSidebar = true
        }
    }

    /// The selection a workflow run honors from THIS window (#4523): the live
    /// library-pane selection, or — when navigation already cleared it on the
    /// way to the run surface — the preserved snapshot. One accessor so every
    /// launch surface agrees; the editor's widening gate fires only when BOTH
    /// are empty, which is the genuine run-on-everything case that must ask.
    var effectiveWorkflowRunSelection: [String] {
        browserSelection.isEmpty
            ? windowState.preservedDocumentSelection
            : Array(browserSelection)
    }

    /// Handles `.onChange(of: browserSelection)`.
    /// Persists browser selection to @SceneStorage.
    func handleBrowserSelectionChange(_ newSelection: Set<String>) {
        // Persist browser selection to @SceneStorage
        if let encoded = try? JSONEncoder().encode(newSelection) {
            browserSelectionData = encoded
        }
        // #4523: remember every NON-empty selection so the run surfaces can
        // honor it even after #712's clear-on-navigate empties
        // `browserSelection` on the way to the workflow the user is about to
        // run. An empty set does not overwrite — emptiness here is usually
        // the navigation clear, not the user deselecting.
        if !newSelection.isEmpty {
            windowState.preservedDocumentSelection = Array(newSelection)
        }
        let primaryId = shellPrimarySelectionId(
            in: newSelection, orderedBy: documentStore.currentDocuments
        )
        if isEntityLibrarySelection {
            guard let firstId = primaryId else {
                kgFocusState.clear()
                detailDocument = nil
                return
            }
            kgFocusState.focusEntity(entityId: firstId)
            detailDocument = nil
            return
        }
        if kgFocusState.focusedEntityId != nil {
            kgFocusState.clear()
        }
        guard let firstId = primaryId,
              BrowserSelectionPreviewPolicy.shouldPromoteSelectionToDetail(
                layoutMode: currentLayoutMode,
                selectedDocumentId: firstId,
                currentDetailDocumentId: detailDocument?.id
              ) else {
            if newSelection.isEmpty {
                detailDocument = nil
            }
            return
        }
        if let doc = documentStore.currentDocuments.first(where: { $0.id == firstId }) {
            detailDocument = doc
            return
        }
        // Selection promotion must not silently fall through when the selected
        // row isn't in currentDocuments yet (restore-before-load, columns-mode
        // child columns, tree-rebuild reload in flight — #4297's family). The
        // sidebar path already fetches; mirror it here so a selected image
        // always reaches the preview pane instead of an empty state (#4299).
        Task { @MainActor in
            let fetched = try? await documentStore.documentService.getDocument(firstId)
            if let fetched,
               shellPrimarySelectionId(
                   in: browserSelection, orderedBy: documentStore.currentDocuments
               ) == firstId {
                detailDocument = fetched
            }
        }
    }

    /// Handles `.onChange(of: detailDocument)`.
    /// Keeps documentStore.selectedDocument in sync and records navigation.
    func handleDetailDocumentChange(from oldDoc: Document?, to newDoc: Document?) {
        // Keep documentStore.selectedDocument in sync so WorkflowEditor
        // toolbar button sees the current document at run time.
        documentStore.selectedDocument = newDoc
        // Clear page focus so the inspector starts fresh on a DIFFERENT
        // document — never on a refresh of the same one (#1463, corrected
        // 2026-08-09): this cleared UNCONDITIONALLY, so any background
        // refresh that merely replaced the detailDocument snapshot (a status
        // poll, a change-stream splice) dropped the reader to page 1 with no
        // user action ('snaps back to page 1', #4558). Same id = same
        // document; the reader keeps its place.
        if oldDoc?.id != newDoc?.id {
            pageFocusDocument = nil
        }
        guard !isRestoringNavigationHistory else { return }
        recordNavigationEntry()
    }

    /// Handles `.onChange(of: windowState.libraryId)` — the ONE teardown for
    /// "this window now shows a different library" (#4518).
    ///
    /// Closing a library falls back to the Global library
    /// (`closeLibraryFromCurrentWindow` / the sidebar close path), and
    /// `LibraryWorkspaceRoot` swaps the per-library stores WITHOUT remounting
    /// ContentView — so the `@State` `Document` snapshots survived the close
    /// and every pane derived a per-document empty state from a document
    /// belonging to nothing: Preview offered Retry for a file of a closed
    /// library, Reader reported "no transcript for this selection", and the
    /// inspector counted 0 artifacts under a stale workflow chip.
    ///
    /// Clears ONLY the per-document snapshots. Deliberately does NOT touch
    /// `sidebarSelectionState.selectedItemId`: a cross-library sidebar click
    /// writes `windowState.libraryId` FIRST and its new selection second
    /// (`handleLibrarySwitching`), so wiping the selection id here could
    /// clobber the very click being handled. The document snapshots are safe
    /// either way — the selection handler immediately re-derives them.
    func handleLibraryChange() {
        // Cascades: `handleDetailDocumentChange` clears `pageFocusDocument`
        // and `syncFocusedDocumentSelection(nil)` clears the focused-document
        // toolbar context (the stale workflow chip's source).
        detailDocument = nil
        browserSelection.removeAll()
        if activeSearchQuery != nil {
            clearTransientSearch()
        }
        kgFocusState.clear()
    }

    // MARK: - Event Handlers

    /// Handles `.onReceive` of `NSApplication.willTerminateNotification`.
    /// Auto-saves the editing workflow when the app quits.
    func handleWillTerminate() {
        // Auto-save workflow when app quits
        if case .workflow(let workflow) = viewMode, let workflowItem = workflow {
            let workflowToSave = editingWorkflow
            Task { @MainActor in
                await autoSaveWorkflow(workflowId: workflowItem.id, workflow: workflowToSave)
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
                    stateEventsLogger.error("smart-search save failed: \(error.localizedDescription)")
                }
            }
        }
    }

    /// Handles typed source-open requests from inspector/KG/search surfaces.
    /// Navigates to a claim's source document with the page scrolled into view.
    func handleOpenClaimSource() {
        // Claim card source-doc link → navigate to the document
        // with the page scrolled into view. The typed request carries
        // documentId (required) + pageLabel / charStart / charEnd /
        // claimId (all optional). For now this lights up doc
        // selection + posts an internal navigation event the
        // PDF preview will consume to scroll to pageLabel. The
        // highlight-span overlay lands in a later phase (#995). (#978/#979/#982)
        guard let request = claimSourceNavigationState.currentRequest else { return }
        let docId = request.documentId
        // Switch to library view if we're in another mode (KG /
        // Activity / Workflow) — the source preview lives there.
        if sidebarMode != .library {
            sidebarMode = .library
        }
        showInspectorSidebar = true
        focusedPane = .inspector
        if let claimId = request.claimId {
            claimFocusState.selectClaim(
                claimId: claimId,
                claimText: request.claimText,
                sourceDocumentId: docId,
                pageLabel: request.pageLabel,
                charStart: request.charStart,
                charEnd: request.charEnd
            )
        }
        // Resolve page-child source documents to their parent file and
        // select it — now via the ONE engine route (#3577) instead of the
        // inline client-side walk. Then forward the SAME page-navigation
        // request that PDFPageView consumes for scrolling/highlighting.
        Task { @MainActor in
            await revealResolvedSource(request)
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
            sidebarMode = .knowledgeGraph
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
