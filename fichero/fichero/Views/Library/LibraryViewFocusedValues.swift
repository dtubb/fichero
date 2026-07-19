import SwiftUI

// MARK: - FocusedValue Equatable Wrappers

/// Equatable wrapper for a library action (selectAll / deleteSelection).
///
/// Closures are non-Equatable, so publishing a raw `() -> Void` via
/// `focusedSceneValue` causes SwiftUI to see a new value on every `body` pass
/// → republishes → cascading invalidation ("FocusedValue update tried to update
/// multiple times per frame"). This wrapper keys equality on `isEnabled` only;
/// the `run` closure is excluded (closures are non-Equatable). Because the
/// enable state is the only part readers query for menu-item enable/disable, this
/// is semantically identical to the old nil-means-disabled pattern while being
/// stable across re-renders.
struct FocusedLibraryAction: Equatable {
    /// Whether the action is currently available (non-empty list or selection).
    let isEnabled: Bool
    /// Execute the action.
    let run: () -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.isEnabled == rhs.isEnabled
    }
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
