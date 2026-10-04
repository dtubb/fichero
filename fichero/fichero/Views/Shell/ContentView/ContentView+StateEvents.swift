import SwiftUI

// MARK: - ContentView Event & State Change Handlers

extension ContentView {

    // MARK: - onChange Handlers — Sidebar & Selection

    /// Handles `.onChange(of: sidebarSelectionState.selectedItemId)` — the single
    /// runtime source (#3036). @SceneStorage `selectedSidebarItemId` is now purely
    /// a persistence adapter (restore-once + write-through), not a second source.
    /// Restores per-folder view mode and drives the inspector from sidebar selection.
    func handleSidebarSelectionChange(_ newFolderId: String?) {
        // #4834: a real sidebar selection always outranks a knowledge-
        // surface reveal — clear it unconditionally, restore or not.
        sourceRevealDocument = nil
        if isRestoringNavigationHistory { return }
        // Either KG collection (entities / claims), per-library or legacy, is a
        // library-wide table, not a folder listing — reset the browse context the
        // same way (P4).
        if let id = newFolderId, SidebarDestination.isKnowledgeCollectionId(id) {
            // #4575: no `viewDisplayMode = .list` here. That line dates to
            // when the Entities table was a `.list`-mode-only rendering
            // INSIDE LibraryView (d5b5e5c31, "entities as a first-class
            // collection in LIST VIEW") — forcing list mode was the only way
            // to make the table visible at all. Entities and Claims are now
            // their own content kind (`effectiveContentKind`, driven by
            // `contentCollection`, in `LibraryView+ContentBranches.swift`),
            // rendered independent of `viewDisplayMode` — neither
            // `EntitiesLibraryContent` nor `ClaimsLibraryContent` reads it.
            // Leaving the line in place meant the window's document view
            // mode silently changed and then STUCK on returning to a folder
            // (`library.modes.persists-until-changed` — the mode is ONE
            // choice per window, the same ruling two lines below in the
            // non-KG branch already states and follows).
            browserSelection.removeAll()
            detailDocument = nil
            kgFocusState.clear()
            return
        }
        kgFocusState.clear()
        // NO per-folder view-mode restore (Daniel, 2026-08-09 morning: "it
        // changes views depending on the folder open. I don't think we want
        // that — it's confusing to have things jumping around"). This
        // supersedes both the original implicit memory and the explicit-only
        // #4575 middle step: the mode is ONE choice per window. Folder
        // changes only re-normalize the current mode for the new context
        // (a mode unavailable here falls back rather than sticking).
        let normalized = normalizedViewDisplayMode(viewDisplayMode)
        if normalized != viewDisplayMode {
            viewDisplayMode = normalized
        }

        // Clear grid selection on sidebar folder change so the folder
        // inspector shows by default. Without this, a stale browserSelection
        // from a previous folder can resolve to a child of the new folder
        // (when ids happen to be present in the new folder's children),
        // suppressing the folder inspector. (#712)
        // A PROJECT row too (#5422, `sidebar.project.click-selects-and-inspects`):
        // the project is now the selection and the Inspector shows it, so a grid
        // pick left over from before cannot stand in for it. This retires
        // #4299's carve-out, which kept that pick when the row only re-rooted
        // the listing.
        browserSelection.removeAll()
        // #4523: a NEW library container is a new browse context, so the
        // remembered run selection is stale scope — drop it. Navigation to
        // workflow/chain/section rows does NOT reach this branch, which is
        // the carve-out that lets "select a file, click the workflow, Run"
        // keep the file as the run's scope instead of the whole folder.
        windowState.preservedDocumentSelection = []

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
        // The results-library name is per-RESULTS state, and this window now
        // shows a different library (Daniel, 2026-09-03). `clearTransientSearch`
        // above nils it, but only when a query was up — so a dismissed search
        // left the OLD library's name behind for the chrome to keep showing.
        chromeUX.resultsLibraryName = nil
        kgFocusState.clear()
    }
}
