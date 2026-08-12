import SwiftUI

// MARK: - Library pane toggle (#4288)

/// What the shell toolbar's library-list-pane toggle should show and do, derived
/// from the ONE pane-visibility value (`PaneVisibility`) rather than from a
/// second, parallel bool. The button is a thin renderer over this model so the
/// interesting parts — symbol, help text, whether hiding is even permitted —
/// are unit-testable without a window.
///
/// Pane state itself is not owned here: it stays in `ContentView`'s per-window
/// `@SceneStorage("showDocumentGrid")`, so each window keeps remembering its own
/// layout across relaunch (the #1696 Option-A storage), which is exactly the
/// "remembered per window" the issue asks for — no new persistence key.
struct LibraryPaneToggleModel: Equatable {
    /// Whether the library list pane is currently showing.
    let isVisible: Bool
    /// Whether hiding it is allowed — the ≥1-visible-pane invariant refuses to
    /// hide the last pane, and a button that silently does nothing is worse
    /// than a disabled one.
    let canHide: Bool

    init(paneVisibility: PaneVisibility) {
        isVisible = paneVisibility.grid
        canHide = !paneVisibility.settingVisible(.grid, false).grid
    }

    /// Menu/toolbar title. Matches the "… Pane" wording of the neighbouring
    /// preview/reading toggles.
    var title: String { "Library Pane" }

    /// ONE constant, position-encoded glyph (#4360). Visibility state is the
    /// native `Toggle` on-state on the toolbar's glass, not a glyph swap: the
    /// half-inset family has no outline variant, so the old hidden state fell
    /// back to a bare `rectangle` — the same bare `rectangle` the preview-pane
    /// toggle used, two meanings on one symbol.
    var systemImage: String { ToolbarSymbols.libraryPane }

    /// The button is disabled only when hiding is refused by the invariant.
    var isEnabled: Bool { isVisible ? canHide : true }

    /// What a tap should set the pane to.
    var nextVisibility: Bool { !isVisible }

    /// The keyboard equivalent is the EXISTING View ▸ Panes ▸ Show/Hide Library
    /// Browser command (`PaneVisibilitySection`), which already toggles this
    /// same pane through the same focused binding. The toolbar button
    /// advertises that shortcut instead of registering a second one for one
    /// action.
    static let shortcutHint = "⇧⌘G"

    var help: String {
        if !isVisible { return "Show library pane (\(Self.shortcutHint))" }
        return canHide
            ? "Hide library pane (\(Self.shortcutHint))"
            : "The library pane is the only pane showing"
    }
}

// MARK: - Sort menu (#4289)

/// The toolbar sort menu's model. It carries no storage of its own: it is
/// projected from `LibraryToolbarState` (the single sort model that the View
/// menu, the table headers, and per-folder persistence already share) and
/// applied back to it. Routing the toolbar through the same state is what keeps
/// there from being a second sort path — the #4282 defect class.
struct LibrarySortMenuModel: Equatable {
    let selectedField: LibrarySortField
    let ascending: Bool

    /// Fields offered by the menu, in declaration order.
    var fields: [LibrarySortField] { LibrarySortField.allCases }

    func isSelected(_ field: LibrarySortField) -> Bool { field == selectedField }

    /// A copy sorted by `field`, keeping the current direction. Re-picking the
    /// already-selected field is a no-op rather than a hidden direction flip:
    /// direction has its own explicit Ascending/Descending pair, exactly like
    /// the View menu's Sort By section.
    func selecting(_ field: LibrarySortField) -> LibrarySortMenuModel {
        LibrarySortMenuModel(selectedField: field, ascending: ascending)
    }

    func settingAscending(_ isAscending: Bool) -> LibrarySortMenuModel {
        LibrarySortMenuModel(selectedField: selectedField, ascending: isAscending)
    }

    /// Toolbar label — the active field, so the current sort is legible without
    /// opening the menu (Finder shows the same).
    var label: String { selectedField.rawValue }

    var systemImage: String { ToolbarSymbols.sortMenu }

    /// Direction indicator drawn beside the checked field.
    var directionSystemImage: String { ascending ? "arrow.up" : "arrow.down" }

    var help: String {
        "Sorted by \(selectedField.rawValue), \(ascending ? "ascending" : "descending")"
    }
}

// MARK: - Filter toggle (#4289)

/// The toolbar's per-view filter affordance. This surfaces the EXISTING inline
/// ⌘F filter bar (which narrows the rows already on screen) — deliberately not
/// the toolbar `.searchable` field, which fires a global search.
struct LibraryFilterToggleModel: Equatable {
    /// Whether the inline filter bar feature is available at all.
    let isAvailable: Bool
    /// Whether the filter bar is currently showing.
    let isActive: Bool

    var title: String { "Filter" }

    /// ONE constant glyph (#4360); the active state is the native `Toggle`
    /// on-state, consistent with the pane toggles.
    var systemImage: String { ToolbarSymbols.filter }

    var nextActive: Bool { !isActive }

    var help: String {
        isActive ? "Hide the filter bar (⌘F)" : "Filter the items in this view (⌘F)"
    }
}

// MARK: - LibraryToolbarState bridge

extension LibraryToolbarState {
    /// The sort menu projected from the shared state.
    var sortMenuModel: LibrarySortMenuModel {
        LibrarySortMenuModel(selectedField: sortField, ascending: sortAscending)
    }

    /// Write a sort menu choice back into the shared state, touching only the
    /// values that actually changed so observers don't re-render wholesale.
    func apply(_ model: LibrarySortMenuModel) {
        if sortFieldRaw != model.selectedField.rawValue {
            sortFieldRaw = model.selectedField.rawValue
        }
        if sortAscending != model.ascending {
            sortAscending = model.ascending
        }
        // apply() is only reachable from the sort MENU — an explicit choice.
        // While a search is showing this overrides the relevance default (#11).
        userChoseSortDuringSearch = true
    }

    /// The ONE mutation path for filter-bar visibility from the toolbar. Hiding
    /// the bar must never leave rows silently filtered out, so `LibraryView`
    /// clears the filter text whenever this flips to `false` — the same rule the
    /// bar's own Escape/Clear buttons already follow.
    func setFilterBar(_ shown: Bool) {
        if showFilterBar != shown { showFilterBar = shown }
    }
}
