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

/// Daniel's composition rule: ALL PDFs → the union of their pages; anything
/// mixed → the selected documents themselves.
func sidebarScopeShowsPages(_ docs: [Document]) -> Bool {
    !docs.isEmpty && docs.allSatisfy { $0.fileType == .pdf }
}

extension ContentView {
    /// Multi-selection → the library shows EXACTLY the selection (or the
    /// union of pages for an all-PDF selection). Single selections keep the
    /// existing navigate-into path; empties are the clear path.
    func handleSidebarMultiSelectionChange(_ destinations: Set<SidebarDestination>) {
        let ids = sidebarScopeDocumentIds(destinations)
        guard ids.count > 1 else { return }
        Task { @MainActor in
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
            // The selection may have moved while we fetched — never apply a
            // stale scope over a newer one.
            guard sidebarScopeDocumentIds(sidebarSelectionState.selectedDestinations) == ids else { return }
            if sidebarScopeShowsPages(docs) {
                var pages: [Document] = []
                for doc in docs {
                    pages += await documentStore.cacheSidebarChildren(of: doc)
                        .filter { $0.docType == .page }
                }
                if !pages.isEmpty {
                    documentStore.currentDocuments = documentStore.applyStatusOverrides(pages)
                    return
                }
                // No page children anywhere (unprocessed PDFs) — fall through
                // to showing the PDFs themselves rather than an empty grid.
            }
            documentStore.currentDocuments = documentStore.applyStatusOverrides(docs)
        }
    }
}
