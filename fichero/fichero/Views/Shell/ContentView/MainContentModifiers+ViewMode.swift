import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ContentViewModifiers")

// Split from ContentViewModifiers.swift (file_length ratchet, 2026-08-09):
// the view-mode routing is the largest single concern in that file and the
// one that keeps growing rulings (#156 single-leaf scope, #161 root set).
extension MainContentModifiers {
    func handleViewModeChange(_ newMode: AppViewMode) {
        // IDENTITY ONLY, never the payload (Daniel, 2026-08-10: "why is all
        // that text in the log?"): String(describing: viewMode) dumped the
        // ENTIRE Document — pageContent included, 584k characters of book —
        // into os_log, and FORMATTING it on the main thread was itself a
        // measured stall (the 1.3s CoreText/CFStringAppend samples).
        logger.info("handleViewModeChange called with mode: \(newMode.logDescription)")

        // #4882: workflow loading moved OFF this `viewMode`-only trigger —
        // it never fired for a Library-driven active workflow (`viewMode`
        // stays `.library` by design), which is how the first delivery of
        // this fix lost edits (autosave was ALSO `viewMode`-gated). See
        // `handleActiveWorkflowChange(old:new:)` / `loadEditingWorkflow(for:)`
        // below, triggered by `.onChange(of: activeWorkflowItem)` instead —
        // ONE trigger, whichever axis chose the workflow.

        // Load children from backend when a library container is selected.
        // Containers = folders (contents) + PDFs (pages, per #568/#570). Using
        // Document.isNavigableContainer keeps this check in sync with
        // double-click routing and sidebar-filter semantics — one property,
        // one definition of "container." Everything else (plain files) shows
        // as a single item in the gallery.
        if case .library(let doc) = newMode, let document = doc {
            guard !isSidebarMultiSelect() else {
                logger.info("Sidebar multi-selection active — the scope handler owns the library set")
                return
            }
            handleLibraryDocumentSelection(document)
        } else if case .library(nil) = newMode {
            handleLibraryRootSelection()
        }
    }

    /// The routed `.library(document)` half of `handleViewModeChange`, split
    /// for the complexity/body ratchets (2026-08-09).
    private func handleLibraryDocumentSelection(_ document: Document) {
            if document.isNavigableContainer {
                logger.info("Loading children for container: \(document.name) (id: \(document.id))")
                selectionLoadTask?.cancel()
                selectionLoadTask = Task {
                    await documentStore.selectCollection(document)
                    guard !Task.isCancelled else { return }
                    // Promote the container into the reader ONLY if the user has
                    // not already landed on a specific item INSIDE it. A search-hit
                    // reveal / claim-source jump (navigateToResolvedSource) selects
                    // this container and then sets detailDocument to the matched
                    // PAGE — a child of THIS container. Loading the children is async
                    // (~1s); this write used to fire AFTER and re-root the reader onto
                    // the container's first page, erasing the result the user picked
                    // (Daniel, 2026-09-07: "shows up for a second, then redraws the
                    // page based on its original folder, not the search result"). A
                    // child of the just-loaded container IS that specific target —
                    // keep it; a stale/unrelated focus is replaced as before. (#1463)
                    let focusPointsInside = detailDocument.map { focused in
                        focused.id == document.id
                            || focused.parentId == document.id
                            || pdfParentDocumentId(of: focused) == document.id
                    } ?? false
                    if !focusPointsInside {
                        detailDocument = document
                    }
                    let docCount = documentStore.currentDocuments.count
                    logger.info("selectCollection completed. currentDocuments count: \(docCount)")
                }
            } else {
                // A sidebar PAGE click must drive the PDF canvas to THAT page
                // (Daniel, 2026-08-08: "the preview for it shows the first
                // page"). Same seam as reader scroll/click (#1463): move the
                // page-focus cursor; re-root detailDocument only when the
                // page belongs to a DIFFERENT document than the one on canvas.
                //
                // And for a page, DON'T stomp currentDocuments (Daniel,
                // 2026-08-09 morning: "if I change page in a sidebar, it
                // reloads the PDF and resets to first page"): replacing the
                // loaded sibling set with [page] fired the whole
                // currentDocuments-change cascade — detail re-resolution,
                // grid rebuild — which re-rooted the canvas and threw the
                // cursor away. The parent's pages are already the loaded
                // collection; only the cursor moves.
                if document.docType == .page {
                    pageFocusDocument = document
                    if sidebarPageParentPDFId(for: document) != sidebarDetailPDFId(for: detailDocument) {
                        detailDocument = document
                    }
                } else {
                    logger.info("Showing single file in gallery: \(document.name)")
                    // Apply status overrides so failed/processing state
                    // survives navigation to single-file gallery — direct
                    // assignment bypassed the override layer other load paths
                    // use, so the red-X workflow-error icon vanished on
                    // click-away while success checkmarks persisted (#791).
                    documentStore.currentDocuments =
                        documentStore.applyStatusOverrides([document])
                }
            }
    }

    /// Selecting a LIBRARY header shows its top-level children, like a folder
    /// (Daniel #161, 2026-08-09: 'when global library is selected view should
    /// show children items'). This branch used to log and load NOTHING —
    /// 'No Documents' over a full library.
    private func handleLibraryRootSelection() {
        logger.info("Library mode with no document selected — showing the root set")
        selectionLoadTask?.cancel()
        selectionLoadTask = Task {
            if documentStore.collections.isEmpty {
                await documentStore.loadCollections()
            }
            guard !Task.isCancelled else { return }
            documentStore.currentDocuments =
                documentStore.applyStatusOverrides(documentStore.collections)
        }
    }

    // MARK: - #4882 active workflow: one load, whichever axis chose it

    /// Whether `editingWorkflow` has unsaved edits against the last-synced
    /// baseline (the SAME `lastSyncedWorkflow` #2278's cross-window resync
    /// already uses) — `nil` baseline (never successfully loaded, or a load
    /// failure) is treated as dirty: safer to attempt a save than to
    /// silently drop edits on an unknown baseline.
    var isEditingWorkflowDirty: Bool {
        guard let lastSyncedWorkflow else { return true }
        return editingWorkflow != lastSyncedWorkflow
    }

    /// The `.onChange(of: activeWorkflowItem)` handler (registered in
    /// `ContentViewModifiers.swift`'s `body`) — the ONE trigger for both
    /// halves of #4882's fix: autosave `old` if it had unsaved edits AND the
    /// editor actually holds `old`'s content (`ContentView
    /// .shouldAutoSaveWorkflow`, HOLE 2 fix — delegated UP via
    /// `onAutoSaveWorkflow` since `autoSaveWorkflow` itself is a ContentView
    /// method this modifier struct does not own, logged loudly when
    /// refused for the id mismatch specifically), then react to the id
    /// change per `ContentView.workflowChangeAction` (HOLE 1 fix: a
    /// same-id field change — a rename, a nodeCount bump, any
    /// `workflowStore.workflows` refresh reaching `activeWorkflowItem` via
    /// the Library path — must NOT reload and clobber unsaved edits; only a
    /// genuine id change loads).
    func handleActiveWorkflowChange(old: WorkflowSidebarItem?, new: WorkflowSidebarItem?) {
        if let old, old.id != new?.id {
            let hasBaseline = lastSyncedWorkflow != nil
            if ContentView.shouldAutoSaveWorkflow(
                old: old, new: new, isDirty: isEditingWorkflowDirty,
                editingWorkflowId: editingWorkflow.id, hasBaseline: hasBaseline
            ) {
                onAutoSaveWorkflow(old.id, editingWorkflow)
            } else if editingWorkflow.id != old.id {
                // HOLE 2: the editor does NOT hold `old`'s content —
                // refusing loudly rather than silently dropping what would
                // have been a corrupting save (see `shouldAutoSaveWorkflow`'s
                // doc comment).
                logger.error(
                    "Refusing autosave: editor holds workflow \(self.editingWorkflow.id), not the outgoing \(old.id) — a load for \(old.id) likely never completed"
                )
            } else if !hasBaseline, !editingWorkflow.nodes.isEmpty || !editingWorkflow.edges.isEmpty {
                // HOLE 3, 2026-09-19: `old` never got a baseline (its own
                // load never succeeded), so there is nothing of the user's
                // to save — but the editor holds a NON-EMPTY graph (not
                // just the failure path's bare-name placeholder), which
                // means this is very likely real, unsaved work about to be
                // silently dropped by refusing the save. Loud on purpose —
                // Daniel wants to SEE this.
                logger.error(
                    "Refusing autosave for \(old.id): no baseline (never successfully loaded), but the editor holds a non-empty graph (\(self.editingWorkflow.nodes.count) nodes) — POSSIBLE UNSAVED WORK IS BEING DROPPED"
                )
            }
        }
        switch ContentView.workflowChangeAction(oldId: old?.id, newId: new?.id) {
        case .load:
            if let new { loadEditingWorkflow(for: new) }
        case .alignMetadataOnly:
            if let new { alignEditingWorkflowMetadata(with: new) }
        case .none:
            break
        }
    }

    /// The metadata-only half of the old load body (#4882 HOLE 1) —
    /// keeps `editingWorkflow.name`/`.description` aligned with a same-id
    /// field change (a rename reaching `activeWorkflowItem` without the
    /// editor's own id changing) WITHOUT reloading the graph itself. Reused
    /// by `loadEditingWorkflow` below for its own immediate alignment
    /// before the async fetch — one function, two callers, never copied.
    private func alignEditingWorkflowMetadata(with item: WorkflowSidebarItem) {
        if editingWorkflow.id == item.id {
            editingWorkflow.name = item.name
            editingWorkflow.description = item.description ?? ""
        }
    }

    /// The extracted load body (#4882) — ONE loader for both the sidebar's
    /// `viewMode == .workflow(_)` path and a Library row's single workflow
    /// selection, called from `handleActiveWorkflowChange` above (only on a
    /// genuine id change — same-id field changes take
    /// `alignEditingWorkflowMetadata` instead), never duplicated. Guarded by
    /// `loadingWorkflowId` against the stale-load race: a slow `getWorkflow(A)`
    /// that returns AFTER the user has moved to workflow B must not overwrite
    /// `editingWorkflow` with A's content — `loadingWorkflowId` holds
    /// whichever id was MOST RECENTLY requested, so a superseded request's
    /// own id no longer matches when it returns.
    func loadEditingWorkflow(for item: WorkflowSidebarItem) {
        loadingWorkflowId = item.id
        // Keep editable metadata aligned immediately to avoid rename races
        // while the full workflow payload is loading asynchronously.
        alignEditingWorkflowMetadata(with: item)

        Task {
            do {
                let fullWorkflow = try await workflowStore.getWorkflow(item.id)
                guard !Self.isStaleWorkflowLoad(resultId: item.id, mostRecentlyRequestedId: loadingWorkflowId) else {
                    logger.info("Discarding stale workflow load for \(item.id) — a newer selection superseded it")
                    return
                }
                // Use the initializer that copies ALL fields (nodes, edges, provider, model, etc.)
                editingWorkflow = Workflow(from: fullWorkflow)
                // Freshly loaded from the server → this IS the baseline for
                // cross-window re-sync (#2278): no local edits yet.
                lastSyncedWorkflow = editingWorkflow
            } catch {
                guard !Self.isStaleWorkflowLoad(resultId: item.id, mostRecentlyRequestedId: loadingWorkflowId) else {
                    return
                }
                logger.error("Failed to load workflow: \(error.localizedDescription)")
                editingWorkflow = Workflow(id: item.id, name: item.name, description: item.description ?? "")
                lastSyncedWorkflow = nil
            }
        }
    }

    /// #4882: the stale-load race, reduced to a pure comparison — a result
    /// for any id OTHER than the most recently requested one is stale and
    /// must be discarded. Extracted so the shape is directly testable
    /// without spinning up an async `Task`/network stub.
    static func isStaleWorkflowLoad(resultId: String, mostRecentlyRequestedId: String?) -> Bool {
        resultId != mostRecentlyRequestedId
    }
}
