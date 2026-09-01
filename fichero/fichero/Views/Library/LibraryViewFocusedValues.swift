import SwiftUI

// MARK: - FocusedValue Equatable Wrappers

/// Equatable wrapper for a library action (selectAll / deleteSelection).
///
/// Closures are non-Equatable, so publishing a raw `() -> Void` via
/// `focusedSceneValue` causes SwiftUI to see a new value on every `body` pass
/// → republishes → cascading invalidation ("FocusedValue update tried to update
/// multiple times per frame"). This wrapper keys equality on the SMALL
/// description of what the action will do; the `run` closure is excluded
/// (closures are non-Equatable).
///
/// ## Why `target` exists (2026-09-01 — "⌘A still does nothing")
///
/// Equality on `isEnabled` ALONE is not merely a coarse key, it is a stale
/// one. `run` is a closure over a `LibraryView` **struct value** — a snapshot
/// of that view's state at the instant it was published. When SwiftUI finds
/// the new value equal to the published one it keeps the OLD value, closure
/// included. So the very first publish that said `isEnabled: true` won the
/// key for the rest of the session: every later publish — a new folder, a new
/// view mode, a filter, a re-sort — compared equal and was dropped, and ⌘A
/// went on calling `selectAll()` over the row list of whichever folder
/// happened to be open when the action first became enabled. Selecting a set
/// of ids that are not in the current list looks exactly like doing nothing,
/// which is what it was reported as. #4376 published the action correctly and
/// #4436's table fix claimed focus correctly; both were downstream of this.
///
/// `target` is a cheap signature of what the action ACTS ON (the row set for
/// ⌘A, the selection for Delete). It changes only when the answer genuinely
/// changes, so the anti-churn property the wrapper exists for is intact: a
/// body pass that changes nothing still publishes an equal value.
struct FocusedLibraryAction: Equatable {
    /// Whether the action is currently available (non-empty list or selection).
    let isEnabled: Bool
    /// A cheap signature of what `run` will act on. Two actions with the same
    /// `isEnabled` and the same `target` are interchangeable; a change in
    /// either MUST republish, or the stale closure is kept.
    let target: String
    /// Execute the action.
    let run: () -> Void

    /// `target` defaults to empty for the callers whose closure captures
    /// nothing that can go stale (an `@Observable` store, a binding).
    init(isEnabled: Bool, target: String = "", run: @escaping () -> Void) {
        self.isEnabled = isEnabled
        self.target = target
        self.run = run
    }

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.isEnabled == rhs.isEnabled && lhs.target == rhs.target
    }
}

/// The `target` signature for a list of ids, without paying for the whole list.
///
/// Count plus the two ends plus the mode name distinguishes every change that
/// matters here — a different folder, a different view mode, a filter that
/// removed rows, a re-sort that moved the ends — while staying O(1) per body
/// pass. Deliberately NOT the joined id list: that is O(n) string building on
/// every body pass of a 600-row folder, which is the cost this wrapper was
/// invented to avoid.
func focusedActionTarget(mode: String, ids: [String]) -> String {
    "\(mode)|\(ids.count)|\(ids.first ?? "-")|\(ids.last ?? "-")"
}

/// The same signature for an UNORDERED selection. `min`/`max` rather than
/// `sorted()`: a set has no visual order to take ends from, and sorting a
/// 600-row ⌘A selection on every body pass is exactly the per-frame cost this
/// wrapper exists to avoid. Lexical ends are deterministic, which is all an
/// identity needs to be.
func focusedActionTarget(mode: String, selection: Set<String>) -> String {
    "\(mode)|\(selection.count)|\(selection.min() ?? "-")|\(selection.max() ?? "-")"
}

/// Equatable wrapper for the library sort-field focused value.
///
/// `Binding<String>` is non-Equatable — publishing it directly via
/// `focusedSceneValue` causes the same per-frame churn as raw closures.
/// This wrapper captures the current value (for equality and display) plus a
/// setter (for mutation), excluding the setter from equality.
struct FocusedSortField: Equatable {
    /// The current raw sort-field value (e.g. `LibrarySortField.name.rawValue`).
    let value: String
    /// Update the sort field to a new raw value.
    let set: (String) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.value == rhs.value
    }
}

/// Equatable wrapper for the library sort direction focused value.
///
/// Publishing a raw `Binding<Bool>` re-triggers the focus system on every body
/// pass even when the direction did not change. Mirror `FocusedSortField` so
/// the View menu only sees a new focused value when the actual ascending flag
/// changes, not whenever the view re-renders.
struct FocusedSortAscending: Equatable {
    /// The current ascending/descending flag.
    let value: Bool
    /// Update the direction.
    let set: (Bool) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.value == rhs.value
    }
}

// MARK: - FocusedValue Keys for Library Actions

/// FocusedValue key for selecting all documents in the library
struct LibrarySelectAllKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for deleting selected documents in the library
struct LibraryDeleteSelectionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for the library sort field
struct LibrarySortFieldKey: FocusedValueKey {
    typealias Value = FocusedSortField
}

/// FocusedValue key for the library sort direction binding
struct LibrarySortAscendingKey: FocusedValueKey {
    typealias Value = FocusedSortAscending
}

extension FocusedValues {
    var librarySelectAll: LibrarySelectAllKey.Value? {
        get { self[LibrarySelectAllKey.self] }
        set { self[LibrarySelectAllKey.self] = newValue }
    }

    var libraryDeleteSelection: LibraryDeleteSelectionKey.Value? {
        get { self[LibraryDeleteSelectionKey.self] }
        set { self[LibraryDeleteSelectionKey.self] = newValue }
    }

    var librarySortField: LibrarySortFieldKey.Value? {
        get { self[LibrarySortFieldKey.self] }
        set { self[LibrarySortFieldKey.self] = newValue }
    }

    var librarySortAscending: LibrarySortAscendingKey.Value? {
        get { self[LibrarySortAscendingKey.self] }
        set { self[LibrarySortAscendingKey.self] = newValue }
    }
}
