import Observation
import SwiftUI

/// Shared, observable home for the Library view's toolbar-facing controls —
/// sort field, sort direction, and inline-filter-bar visibility.
///
/// These three values used to be `@State` inside `LibraryView`, which made them
/// unreachable from the in-content mode rail (a sibling view that owns the
/// view-mode buttons). Lifting them into one `ObservableObject` — owned by
/// `ContentView` and shared with both `LibraryView` and the mode rail — lets the
/// Sort and Filter controls live at the Library view's top-right next to the
/// display-mode buttons (#1477) while `LibraryView` keeps its per-folder sort
/// persistence (the `*ByFolder` @SceneStorage stays in `LibraryView` and simply
/// reads/writes these values).
@MainActor
@Observable
final class LibraryToolbarState {
    /// Raw value of the active `LibrarySortField` (kept as `String` to match the
    /// existing per-folder persistence + FocusedValue plumbing).
    var sortFieldRaw: String = LibrarySortField.name.rawValue
    /// Sort direction — `true` ascending.
    var sortAscending: Bool = true
    /// Whether the inline ⌘F filter bar is shown inside the library content.
    var showFilterBar: Bool = false
    /// True once the user picks a sort WHILE a transient search is showing
    /// (#11): search results default to the engine's relevance order, and
    /// only an explicit choice re-sorts them. Reset on every new search.
    var userChoseSortDuringSearch: Bool = false
    /// Whether transient search results are the rows on screen. The sort menu
    /// offers Relevance only here, and shows it as the selected field until
    /// the user picks something else — which is what stops a correctly-ranked
    /// list from reading as name-sorted (Daniel, 2026-09-04).
    var searchIsActive: Bool = false
    /// The tier a SAVED search imposed on the toolbar, if one did (#4112/S8).
    /// Non-nil only between running a saved search and the next fresh query or
    /// dismissal — it is what lets `restoreDefaultRetrievalTier` tell a tier
    /// nobody chose from one the user picked in the options menu.
    ///
    /// Here rather than on `ContentView` for two reasons, and the second is
    /// the load-bearing one: it collaborates with `userChoseSortDuringSearch`
    /// and `searchIsActive`, which already live here — and every stored
    /// property on `ContentView` is copied on every main-thread graph update
    /// (`ViewValueSizeTests`, stalls.log 2026-08-24). A `String?` there cost
    /// 24 bytes of per-update copying for a value read twice per search.
    var savedSearchAppliedTier: String?

    /// Convenience typed accessor for the active sort field.
    var sortField: LibrarySortField {
        LibrarySortField(rawValue: sortFieldRaw) ?? .name
    }
}
