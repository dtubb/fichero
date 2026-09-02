import SwiftUI

// Column-path seeding (#222) and the root column's document set — split from
// ColumnsView for the file-length budget.
extension LibraryView {
    /// What column 0 shows.
    ///
    /// Browsing, it is the library's TOP LEVEL (Daniel, 2026-08-10 #222: "the
    /// column view should begin at the current top level, and not with the
    /// selection") — selecting a page in the sidebar used to make column one
    /// that PDF's pages with no path context to browse left through.
    /// `collections` is the store's root listing; the current listing remains
    /// the fallback until roots have loaded.
    ///
    /// A SEARCH replaces the browse root (2026-09-02). While results are
    /// showing there is no browse, there is a result set, and the root listing
    /// is not it. Columns were the last mode still rendering the folder scope
    /// under a query — list, icon, table and the dataset views all show the
    /// hits — so one window said two different things depending on which mode
    /// was up. `filteredDocuments` IS the hit set here (the shell swaps this
    /// pane's `documents` input to `searchResultDocuments`), in the engine's
    /// relevance order.
    ///
    /// Deeper columns are deliberately unaffected: drilling INTO a hit's
    /// folder is browsing again, and that column means that folder's children.
    var columnsRootDocuments: [Document] {
        if activeSearchQuery != nil { return filteredDocuments }
        let roots = documentStore.collections
        return roots.isEmpty ? filteredDocuments : roots
    }

    /// Seed the column path from the CURRENT selection's ancestry so
    /// entering columns mode shows the selected item in place — root at the
    /// left, every ancestor disclosed (Finder). Only runs when the path is
    /// empty (a user-built path is never clobbered) and walks parent ids
    /// through the document service.
    func seedColumnsPathFromSelection() async {
        guard columnsPath.isEmpty,
              let id = orderedPrimarySelectionId,
              let service = libraryReference?.documentService else { return }
        guard var doc = try? await service.getDocument(id) else { return }
        var chain: [String] = []
        var hops = 0
        while let parentId = doc.parentId, hops < 32 {
            chain.insert(parentId, at: 0)
            guard let parent = try? await service.getDocument(parentId) else { break }
            doc = parent
            hops += 1
        }
        guard !chain.isEmpty, columnsPath.isEmpty else { return }
        columnsPath = chain
    }

    /// The trailing preview column's document: a SINGLE selected non-folder,
    /// wherever it lives in the open columns. Multi-select or a folder
    /// selection shows no preview column (Finder behavior — folders disclose
    /// their children instead).
}
