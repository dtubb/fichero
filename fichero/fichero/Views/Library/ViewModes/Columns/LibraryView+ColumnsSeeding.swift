import SwiftUI

// Column-path seeding (#222) — split from ColumnsView for the
// file-length budget.
extension LibraryView {
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
