import Foundation

// MARK: - The shared ancestor walk (relocated 2026-08-24)
//
// Lived in LibraryPathStatusBar.swift; the status bar is deleted (crumbs are
// pane-head business now) but this walk is what every pane head's breadcrumb
// resolves through until the outline endpoint's ancestors[] replaces it.
// DatasetSelectionStatus rides along: the dataset renderers still publish
// their selection in its shape (consumed by the island's noun logic next).

/// What a DATA view's selection looks like to the status line — reported up
/// by DatasetModeView so the pane's bottom row speaks the dataset's language
/// instead of the browser's ("1 of 63 selected" over a cards pane of 160
/// dated entries, 2026-08-16).
struct DatasetSelectionStatus: Equatable {
    var count: Int
    var total: Int
    var noun: String
    var detail: String?
}

/// Ancestry for the path bar: the anchor document first resolved, then its
/// parent chain walked through `resolve`, root-first. Capped so a cyclic or
/// absurdly deep chain can't hang the bar.
func libraryPathCrumbs(
    anchorId: String?,
    resolve: (String) -> Document?
) -> [Document] {
    guard let anchorId, let anchor = resolve(anchorId) else { return [] }
    var crumbs: [Document] = [anchor]
    var cursor = anchor
    var hops = 0
    while hops < 8, let parentId = cursor.parentId, let parent = resolve(parentId) {
        // Cycle guard: a bad parent chain must not loop forever.
        guard !crumbs.contains(where: { $0.id == parent.id }) else { break }
        crumbs.insert(parent, at: 0)
        cursor = parent
        hops += 1
    }
    return crumbs
}
