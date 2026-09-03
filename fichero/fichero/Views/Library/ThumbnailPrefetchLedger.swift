import Foundation

// MARK: - Thumbnail prefetch bookkeeping (2026-09-02, Daniel: "scrolling
// works upward but barely downward, and selecting anything takes longer
// than it should")

/// The scroll look-ahead's bookkeeping, held by REFERENCE so writing to it
/// never invalidates the library view.
///
/// This was three `@State` properties on `LibraryView`
/// (`prefetchedThumbnailIds`, `thumbnailPrefetchTask`,
/// `folderThumbnailPrefetchTask`), and `scheduleThumbnailPrefetch(around:)`
/// writes all three from a ROW's `.onAppear`. A `@State` write is a view
/// invalidation, so every row that scrolled into view re-evaluated the whole
/// `LibraryView` body — which rebuilds the `LazyVStack`, its `ForEach`, and
/// every visible row's identity. That is the "no wholesale list re-render"
/// rule broken once per appearing row.
///
/// It also explains the asymmetry Daniel reported. Scrolling UP reveals rows
/// whose ids are already in the ledger, so `imageIds` comes back empty and the
/// early `guard` returns BEFORE any write — no invalidation, smooth scroll.
/// Scrolling DOWN reveals unseen rows, so every one of them writes state and
/// re-renders the list under the pointer. Same code, one direction janky.
///
/// A plain `final class` (deliberately NOT the Observable macro) stored in `@State`
/// gives the view a stable box whose contents SwiftUI does not watch: the
/// ledger survives re-renders, and mutating it causes none. Nothing in the
/// view's body reads these values, so there is nothing to observe.
@MainActor
final class ThumbnailPrefetchLedger {
    /// Ids already handed to the storage service, so the folder sweep and the
    /// scroll look-ahead never double-fetch.
    var prefetchedIds: Set<String> = []
    /// The scroll look-ahead task — cancelled and replaced as the window moves.
    var scrollTask: Task<Void, Never>?
    /// The folder-open sweep (#4589). Its OWN task, so a row appearing never
    /// cancels the sweep.
    var folderTask: Task<Void, Never>?

    /// Which ids in `candidates` have not been fetched yet, marking them as
    /// claimed. One place decides, so the folder sweep and the scroll
    /// look-ahead cannot disagree about what is already in flight.
    func claimUnfetched(_ candidates: [String]) -> [String] {
        let fresh = candidates.filter { !prefetchedIds.contains($0) }
        prefetchedIds.formUnion(fresh)
        return fresh
    }

    /// The visible document set changed — forget what was fetched for the old
    /// one and stop the look-ahead. The FOLDER sweep is deliberately left
    /// alone: `prefetchFolderThumbnails()` re-runs on the same key change and
    /// cancels its own task there.
    func resetScrollLookAhead() {
        prefetchedIds.removeAll()
        scrollTask?.cancel()
        scrollTask = nil
    }

    func cancelAll() {
        scrollTask?.cancel()
        scrollTask = nil
        folderTask?.cancel()
        folderTask = nil
    }
}
