import SwiftUI

// MARK: - The reader pane head's breadcrumb (split from ReadingPaneView for
// the file-length lint threshold, 2026-08-29).

extension ReadingPaneView {
    /// The pane's title line IS its breadcrumb (R1), not "Reader" — and it is
    /// the FULL ancestry (Daniel, 2026-08-23: "it's important"):
    /// "Marshall Diaries v4 › Inbox › 1933".
    ///
    /// Through `libraryPathCrumbs`, the walk the library's path bar already
    /// uses — root-first, cycle-guarded, depth-capped. A second ancestor walk
    /// for the same question is how two surfaces come to disagree about where
    /// you are.
    ///
    /// ponytail: names today. Daniel's proxy-icon crumbs (parents collapse to
    /// icons with chevrons, expanding on hover) are a later slice; the capsule
    /// truncates from the leading edge until then, so a deep path still shows
    /// the part that identifies it.
    var readerCrumbs: [PaneCrumb] {
        // The library is the root crumb: a path that starts at a folder does
        // not say WHICH library's Inbox you are in, and several are open at
        // once in the normal case. Navigable (#5218): it shows the library's top level.
        var crumbs: [PaneCrumb] = []
        if let library = LibraryManager.shared.getLibrary(id: windowState.libraryId) {
            crumbs.append(.library(library))
        }
        // Breadcrumb honesty (Daniel, 2026-08-29): N>1 selected means the
        // pane shows N items, and the crumb must say so — the shared parent's
        // ancestry for context, then "N items", never one document's name.
        if multiDocuments.count > 1 {
            if let parentId = multiReaderCommonPageParent(multiDocuments) {
                crumbs += libraryPathCrumbs(
                    anchorId: parentId,
                    resolve: { documentStore.resolveDocument($0) }
                ).map(PaneCrumb.init)
            }
            crumbs.append(.multiSelection(count: multiDocuments.count))
            return crumbs
        }
        guard let document = effectiveDocument else { return [] }
        let ancestry = libraryPathCrumbs(
            anchorId: document.id,
            resolve: { documentStore.resolveDocument($0) }
        )
        crumbs += ancestry.isEmpty ? [PaneCrumb(document)] : ancestry.map(PaneCrumb.init)
        return crumbs
    }
}
