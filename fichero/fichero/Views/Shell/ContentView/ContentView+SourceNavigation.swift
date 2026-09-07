import OSLog
import SwiftUI

private let workflowLogger = Logger(subsystem: "app.fichero.fichero", category: "ContentView")

extension ContentView {
    // MARK: - Navigation

    func navigateToDocument(_ doc: Document) {
        NavTrace.log("nav.toDocument", "\(doc.id) type=\(doc.docType.rawValue) (re-roots viewMode+sidebar here)")
        viewMode = .library(doc)
        sidebarSelectionState.selectedItemId = "doc:\(doc.id)"
    }

    /// Double-click on a transient-search hit: leave the results and go to
    /// where the item lives in the tree (#4106). A folder OPENS (its contents
    /// show); a file lands SELECTED inside its containing folder. Clearing the
    /// search first re-roots the library column on the real tree; the search
    /// query stays captured in the history entry recorded for these results,
    /// so Back returns to them (see `recordNavigationEntry`).
    @MainActor
    func revealSearchResult(_ doc: Document) {
        NavTrace.log("reveal.searchResult", "\(doc.id) container=\(doc.isNavigableContainer)")
        if doc.isNavigableContainer {
            // A FOLDER result: open it in place (its contents shown), leaving
            // the results — that IS "go here" for a container.
            clearTransientSearch()
            navigateToDocument(doc)
        } else {
            // A file/page result (Option B): land the reader on the source and
            // KEEP the search results + browse context (Daniel: don't lose my
            // place). No search-clear, no container re-root.
            Task { @MainActor in
                await navigateToResolvedSource(doc)
            }
        }
    }

    /// Open the source page behind a KG entity click. The source claim
    /// points at a page-level document (path=nil, parent = the real file
    /// per #701). Resolution:
    ///   1. Fetch the source doc by id.
    ///   2. If it's a page child (no path), walk up to the parent file —
    ///      that's the thing the user actually wants to look at.
    ///   3. Navigate to the parent FOLDER (so the file appears in the
    ///      grid) and select the file via browserSelection so the
    ///      preview pane opens it.
    /// Falls through silently if the source can't be resolved — a click
    /// shouldn't crash and we don't have a UI surface for "couldn't
    /// resolve source" yet. (#833)
    @MainActor
    func navigateToSourcePage(_ sourceDocId: String) async {
        let source: Document
        do {
            source = try await documentStore.documentService.getDocument(sourceDocId)
        } catch {
            workflowLogger.warning("navigateToSourcePage: couldn't fetch \(sourceDocId): \(error.localizedDescription)")
            return
        }

        // Resolve "the file the user wants" — page children (path == nil)
        // bubble up to their parent file; everything else is its own target.
        let target: Document
        let sourceIsPageChild = source.path?.isEmpty ?? true
        if sourceIsPageChild {
            // First try: use the parentId field if available
            if let parentId = source.parentId, !parentId.isEmpty {
                do {
                    target = try await documentStore.documentService.getDocument(parentId)
                } catch {
                    // Fallback: use the new /documents/{id}/parent endpoint
                    do {
                        target = try await documentStore.documentService.getParent(sourceDocId)
                    } catch {
                        workflowLogger.warning(
                            "navigateToSourcePage: couldn't resolve parent for \(sourceDocId): \(error.localizedDescription)"
                        )
                        return
                    }
                }
            } else {
                // No parentId available, use the new endpoint directly
                do {
                    target = try await documentStore.documentService.getParent(sourceDocId)
                } catch {
                    workflowLogger.warning(
                        "navigateToSourcePage: couldn't fetch parent for \(sourceDocId): \(error.localizedDescription)"
                    )
                    return
                }
            }
        } else {
            target = source
        }

        await navigateToResolvedSource(target)
    }

    /// Open the containing folder so `target` shows up in the grid and select
    /// it; if `target` is top-level, just point the sidebar at it. Shared by the
    /// engine-resolved reveal (#3577) and the legacy client-side resolver above.
    @MainActor
    func navigateToResolvedSource(_ target: Document) async {
        // Option B (Daniel, 2026-09-08: "jump to source and HOLD, don't lose my
        // place"): land the reader on the source and select it, WITHOUT
        // re-rooting the library/sidebar to its container.
        //
        // The old path called `navigateToDocument(folder)`, which set
        // `selectedItemId` — firing `handleSidebarSelectionChange`, which
        // `removeAll()`s the selection (→ selChange.emptyClear → detailDocument
        // = nil), force-clears detailDocument, then ASYNC re-roots it to the
        // FOLDER via `applySidebarSelectedDocument`. That async folder-set ran
        // AFTER the `detailDocument = target` here and clobbered it, so the
        // reader jumped to the container's first page instead of the source —
        // the long-standing "the click never worked" bug. Selecting the target
        // without touching `selectedItemId`/`viewMode` never wakes that handler,
        // so the reader keeps the page and the browse context is preserved.
        // Reveal-to-container (#4106) is now an explicit affordance, not the
        // default click.
        NavTrace.log("nav.resolvedSource.B", "land on \(target.id) type=\(target.docType.rawValue) (no re-root)")
        browserSelection = [target.id]
        detailDocument = target
    }

    /// Resolve a source anchor to its parent document + page through the ONE
    /// engine route (#3577) — page-child → parent resolution no longer lives in
    /// the app — then select it. Falls back to the legacy client-side walk if
    /// the engine resolve fails so a reveal never breaks (no regression).
    @MainActor
    func revealResolvedSource(_ request: ClaimSourceNavigationRequest) async {
        do {
            let resolved = try await documentStore.locationService.resolve(request.asLocation)
            let target = try await documentStore.documentService.getDocument(resolved.resolvedDocumentId)
            await navigateToResolvedSource(target)
        } catch {
            workflowLogger.warning(
                "revealResolvedSource: engine resolve failed (\(error.localizedDescription)); falling back to client-side navigation"
            )
            await navigateToSourcePage(request.documentId)
        }
    }

    /// Focus the preview pane on a KG source without changing sidebar or
    /// library-tree selection. Used by KGFocusState for ordinary row/graph
    /// focus; explicit open-source buttons still use navigateToSourcePage.
    @MainActor
    func focusKGSourcePreview(_ sourceDocId: String) async {
        let source: Document
        do {
            source = try await documentStore.documentService.getDocument(sourceDocId)
        } catch {
            workflowLogger.warning("focusKGSourcePreview: couldn't fetch \(sourceDocId): \(error.localizedDescription)")
            return
        }

        let sourceIsPageChild = source.path?.isEmpty ?? true
        if sourceIsPageChild, let parentId = source.parentId, !parentId.isEmpty {
            do {
                detailDocument = try await documentStore.documentService.getDocument(parentId)
            } catch {
                workflowLogger.warning(
                    "focusKGSourcePreview: couldn't fetch parent for \(sourceDocId): \(error.localizedDescription)"
                )
            }
        } else {
            detailDocument = source
        }
    }

    /// Walk up to the current folder's parent. If the current folder is at
    /// the library root (no parent_id), navigate to the library root view
    /// (no selection). Bound to Cmd+` so users can ascend the hierarchy when
    /// the sidebar is hidden. (#786)
    @MainActor
    func navigateToParent() {
        guard let prefixedId = sidebarSelectionState.selectedItemId,
              prefixedId.hasPrefix("doc:") else {
            return
        }
        let docId = String(prefixedId.dropFirst("doc:".count))
        let current = documentStore.currentDocuments.first(where: { $0.id == docId })
            ?? detailDocument
        guard let current else { return }
        if let parentId = current.parentId, !parentId.isEmpty {
            sidebarSelectionState.selectedItemId = "doc:\(parentId)"
        } else {
            sidebarSelectionState.selectedItemId = nil
            detailDocument = nil
            viewMode = .library(nil)
        }
    }

}
