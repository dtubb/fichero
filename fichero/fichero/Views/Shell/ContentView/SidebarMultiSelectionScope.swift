import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarMultiScope")

// Sidebar multi-selection SCOPES the library (Daniel, 2026-08-09: "if three
// sidebar items are selected they should all be in library view"; "if
// multiple pdfs are selected, show all the pages"). Pure halves here; the
// handler lives in ContentView+StateEvents.

/// The document ids of a multi-selection, in a stable (lexical) order —
/// the sidebar's visual order is not visible from the shell, and stable
/// beats hash order (the selection-grammar rule 2 discipline).
func sidebarScopeDocumentIds(_ destinations: Set<SidebarDestination>) -> [String] {
    destinations.compactMap {
        if case .document(let id) = $0 { return id }
        return nil
    }.sorted()
}

/// Daniel's composition rule (#114/#115, then #144, 2026-08-09): EVERY
/// selected CONTAINER expands to its contents — a PDF to its pages, a FOLDER
/// to its children ('if you select a folder it should also show contents in
/// multiple selection like a pdf') — and every leaf shows as itself. Adding
/// one image to five PDFs must not collapse the pages back to icons.
func sidebarScopeExpandsToContents(_ docs: [Document]) -> Bool {
    docs.contains(where: sidebarScopeIsExpandableContainer)
}

/// A container the multi-scope opens one level: a PDF document or a folder.
/// One level only, like Finder's flattened selection — never recursive.
func sidebarScopeIsExpandableContainer(_ doc: Document) -> Bool {
    (doc.fileType == .pdf && doc.docType != .page) || doc.docType == .folder
}

/// The shown set is a SET (2026-08-23 crash, sidebar ⌘A in 3D): ⌘A selects
/// every visible row, so an expanded folder arrives alongside its own
/// children — the folder contributes child D via expansion AND D contributes
/// itself as a selected leaf. The duplicate flowed into `currentDocuments`,
/// through `SpatialLibraryProjector` (1:1), and trapped
/// `CanvasArrangement.slotIndices`. First occurrence wins, order kept.
func sidebarScopeDeduped(_ docs: [Document]) -> [Document] {
    var seen = Set<String>()
    return docs.filter { seen.insert($0.id).inserted }
}

/// The #156 single-leaf gate: a lone selected document scopes the library to
/// itself only when NOTHING else owns the selection — containers browse in,
/// pages move the cursor.
func sidebarScopeIsSingleLeaf(_ doc: Document) -> Bool {
    !sidebarScopeIsExpandableContainer(doc)
        && doc.docType != .page
        && !doc.isNavigableContainer
}

/// `library.modes.the-view-follows-the-node` (ruled 2026-10-04, #5428): a sidebar click on a
/// SOURCE (an image, a PDF, any file) opens it the way Finder does. The Library pane lists the
/// source's folder in that pane's own view mode, with the source selected; the Preview shows the
/// source, and opens if the window has none. This replaces #156's narrowing of the library to the
/// one clicked item, which left a remembered Canvas drawing an empty board for an image.
struct SidebarSourceOpen: Equatable {
    /// The folder the Library pane lists: the source's parent, nil for the library's root.
    let folderId: String?
    /// The Library pane's selection: the source.
    let selection: Set<String>
    /// The window has no Preview pane, so one opens.
    let opensPreview: Bool

    /// nil when `doc` is not a source: folders, groups, pages and workflow mirrors keep their own
    /// routes (a folder lists its contents; a page moves the cursor).
    static func plan(for doc: Document, previewShowing: Bool) -> SidebarSourceOpen? {
        guard doc.docType == .file, !doc.isWorkflowNode else { return nil }
        let parentId = doc.parentId.flatMap { $0.isEmpty ? nil : $0 }
        return SidebarSourceOpen(folderId: parentId, selection: [doc.id], opensPreview: !previewShowing)
    }

    /// The sidebar id of the node the Library pane lists, which keys its per-folder canvas and
    /// sort. With a source selected that is the folder shown (`viewMode`), not the source's own
    /// row, so the board drawn is the folder's board.
    static func libraryPaneFolderId(selectedItemId: String?, viewMode: AppViewMode, libraryId: UUID) -> String? {
        guard case .document(let selectedId)? = selectedItemId.flatMap(SidebarDestination.init(serializedID:)),
              case .library(let shown) = viewMode, shown?.id != selectedId else { return selectedItemId }
        return shown.map { SidebarDestination.document($0.id).serializedID }
            ?? SidebarDestination.library(libraryId).serializedID
    }
}

extension ContentView {
    /// The node the Library pane lists (#5428): a selected source's folder, else the selection.
    var libraryPaneFolderId: String? {
        SidebarSourceOpen.libraryPaneFolderId(
            selectedItemId: sidebarSelectionState.selectedItemId, viewMode: viewMode, libraryId: windowState.libraryId
        )
    }

    /// Multi-selection → the library shows EXACTLY the selection (or the
    /// union of pages for an all-PDF selection). Single selections keep the
    /// existing navigate-into path; empties are the clear path.
    func handleSidebarMultiSelectionChange(_ destinations: Set<SidebarDestination>) {
        let ids = sidebarScopeDocumentIds(destinations)
        // A SINGLE selected LEAF also scopes the library to itself (Daniel
        // #156, 2026-08-09: 'one sidebar item is selected, the m4a file, it
        // should only show that in library with the preview') — containers
        // (folders/PDFs/pages) stay with the navigate path, which browses
        // into them.
        if ids.count == 1 {
            // A source no longer narrows (#5428): it opens in its folder, `SidebarSourceOpen`.
            if let doc = documentStore.resolveDocument(ids[0]), sidebarScopeIsSingleLeaf(doc),
               SidebarSourceOpen.plan(for: doc, previewShowing: true) == nil {
                documentStore.currentDocuments = documentStore.applyStatusOverrides([doc])
            }
            return
        }
        guard ids.count > 1 else { return }
        Task { @MainActor in
            let docs = await sidebarScopeResolve(ids)
            // The selection may have moved while we fetched — never apply a
            // stale scope over a newer one.
            guard sidebarScopeDocumentIds(sidebarSelectionState.selectedDestinations) == ids else { return }
            let shown = await sidebarScopeExpand(docs)
            // Re-check — the expansion's child fetches awaited too.
            guard sidebarScopeDocumentIds(sidebarSelectionState.selectedDestinations) == ids else { return }
            documentStore.currentDocuments = documentStore.applyStatusOverrides(shown)
        }
    }

    /// Resolve scope ids to documents (cache first, one fetch fallback each),
    /// logging what the shown set will omit.
    @MainActor
    private func sidebarScopeResolve(_ ids: [String]) async -> [Document] {
        var docs: [Document] = []
        for id in ids {
            if let doc = documentStore.resolveDocument(id) {
                docs.append(doc)
            } else if let fetched = try? await documentStore.documentService.getDocument(id) {
                docs.append(fetched)
            } else {
                logger.error("Sidebar multi-scope could not resolve \(id) — shown set will omit it")
            }
        }
        return docs
    }

    /// Per-container expansion (#114/#115/#144): a PDF contributes its pages,
    /// a FOLDER its children (one level, Finder-style), either contributing
    /// ITSELF while empty/unprocessed so nothing vanishes; leaves ride along.
    @MainActor
    private func sidebarScopeExpand(_ docs: [Document]) async -> [Document] {
        guard sidebarScopeExpandsToContents(docs) else { return docs }
        var shown: [Document] = []
        for doc in docs {
            if sidebarScopeIsExpandableContainer(doc) {
                var contents = await documentStore.cacheSidebarChildren(of: doc)
                if doc.fileType == .pdf {
                    contents = contents.filter { $0.docType == .page }
                }
                shown += contents.isEmpty ? [doc] : contents
            } else {
                shown.append(doc)
            }
        }
        return sidebarScopeDeduped(shown)
    }
}
