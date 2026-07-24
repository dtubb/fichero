import SwiftUI

// MARK: - Focused Values for Menu Commands

/// Actions for image preview zoom controls
struct ImageZoomActions {
    let zoomIn: () -> Void
    let zoomOut: () -> Void
    let actualSize: () -> Void
    let zoomToFit: () -> Void
    let canZoomIn: Bool
    let canZoomOut: Bool
}

/// FocusedValue key for image zoom actions
struct ImageZoomActionsKey: FocusedValueKey {
    typealias Value = ImageZoomActions
}

/// Actions that can be performed on the sidebar selection.
///
/// Equatable returns `true` unconditionally: all instances constructed by
/// `sidebarFocusedValues(config:)` capture closures over the SAME parent
/// @State bindings, so they're functionally interchangeable. Without this,
/// every body re-evaluation publishes a "new" `SidebarActions` to the
/// focus system (closures aren't Equatable by default), tripping the
/// "FocusedValue update tried to update multiple times per frame"
/// runtime warning that shows in red in Xcode's console. With `== true`,
/// SwiftUI short-circuits the republish and the menu commands still
/// work correctly because the captured bindings read current state
/// regardless of which SidebarActions instance holds the closure.
struct SidebarActions: Equatable {
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createChain: () -> Void
    let createComparison: () -> Void
    let createSchedule: () -> Void
    let createTrigger: () -> Void

    static func == (lhs: SidebarActions, rhs: SidebarActions) -> Bool {
        true
    }
}

/// Information about the current sidebar selection.
///
/// `Equatable` so `.focusedValue(\.sidebarSelectionInfo, ...)` short-circuits
/// when the selection hasn't actually changed between body evaluations —
/// otherwise the machinery trips the "FocusedValue update tried to update
/// multiple times per frame" warning on every body re-evaluation, since
/// SwiftUI otherwise treats each fresh struct instance as a new value.
struct SidebarSelectionInfo: Equatable {
    let selectedItem: SidebarItem?
    let canRename: Bool
    let canDelete: Bool

    static func == (lhs: SidebarSelectionInfo, rhs: SidebarSelectionInfo) -> Bool {
        lhs.selectedItem?.id == rhs.selectedItem?.id
            && lhs.canRename == rhs.canRename
            && lhs.canDelete == rhs.canDelete
    }
}

/// FocusedValue key for sidebar actions
struct SidebarActionsKey: FocusedValueKey {
    typealias Value = SidebarActions
}

/// FocusedValue key for sidebar selection info
struct SidebarSelectionInfoKey: FocusedValueKey {
    typealias Value = SidebarSelectionInfo
}

/// FocusedValue key for triggering library file picker
struct OpenLibraryActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for opening a new window on current library
struct NewWindowActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for creating a new library in-place in the current window
/// (saves to a chosen location, then selects the new library in this window's
/// sidebar — no new window). Distinct from NewWindowActionKey, which opens a
/// fresh window on the current library. (#4062)
struct NewLibraryActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for duplicating the current window — clones its library,
/// selection, and active lens into a new window via `openWindow(value:)` (#2262).
struct DuplicateWindowActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for saving the current library (Save As for Untitled libraries)
struct SaveLibraryActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for closing the current library from the active window.
struct CloseLibraryActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for running a workflow on selected documents
struct RunWorkflowOnSelectionKey: FocusedValueKey {
    typealias Value = () -> Void
}

/// FocusedValue key for navigating to the current folder's parent. Bound to
/// Cmd+\` so users can ascend the hierarchy when the sidebar is hidden. (#786)
struct NavigateToParentActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for undoing the most recent navigation change.
struct NavigationUndoActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue keys for the per-window back/forward history (#3581). Distinct
/// from `navigationUndoAction` — that stays the ⌘Z audited-undo fallback; these
/// drive the ⌘'/⌘⇧' menu items that mirror the content-column toolbar buttons.
struct NavigateBackActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

struct NavigateForwardActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

extension FocusedValues {
    var imageZoomActions: ImageZoomActionsKey.Value? {
        get { self[ImageZoomActionsKey.self] }
        set { self[ImageZoomActionsKey.self] = newValue }
    }

    var sidebarActions: SidebarActionsKey.Value? {
        get { self[SidebarActionsKey.self] }
        set { self[SidebarActionsKey.self] = newValue }
    }

    var sidebarSelectionInfo: SidebarSelectionInfoKey.Value? {
        get { self[SidebarSelectionInfoKey.self] }
        set { self[SidebarSelectionInfoKey.self] = newValue }
    }

    var openLibraryAction: OpenLibraryActionKey.Value? {
        get { self[OpenLibraryActionKey.self] }
        set { self[OpenLibraryActionKey.self] = newValue }
    }

    var newWindowAction: NewWindowActionKey.Value? {
        get { self[NewWindowActionKey.self] }
        set { self[NewWindowActionKey.self] = newValue }
    }

    var newLibraryAction: NewLibraryActionKey.Value? {
        get { self[NewLibraryActionKey.self] }
        set { self[NewLibraryActionKey.self] = newValue }
    }

    var duplicateWindowAction: DuplicateWindowActionKey.Value? {
        get { self[DuplicateWindowActionKey.self] }
        set { self[DuplicateWindowActionKey.self] = newValue }
    }

    var saveLibraryAction: SaveLibraryActionKey.Value? {
        get { self[SaveLibraryActionKey.self] }
        set { self[SaveLibraryActionKey.self] = newValue }
    }

    var closeLibraryAction: CloseLibraryActionKey.Value? {
        get { self[CloseLibraryActionKey.self] }
        set { self[CloseLibraryActionKey.self] = newValue }
    }

    var runWorkflowOnSelection: RunWorkflowOnSelectionKey.Value? {
        get { self[RunWorkflowOnSelectionKey.self] }
        set { self[RunWorkflowOnSelectionKey.self] = newValue }
    }

    var navigateToParentAction: NavigateToParentActionKey.Value? {
        get { self[NavigateToParentActionKey.self] }
        set { self[NavigateToParentActionKey.self] = newValue }
    }

    var navigationUndoAction: NavigationUndoActionKey.Value? {
        get { self[NavigationUndoActionKey.self] }
        set { self[NavigationUndoActionKey.self] = newValue }
    }

    var navigateBackAction: NavigateBackActionKey.Value? {
        get { self[NavigateBackActionKey.self] }
        set { self[NavigateBackActionKey.self] = newValue }
    }

    var navigateForwardAction: NavigateForwardActionKey.Value? {
        get { self[NavigateForwardActionKey.self] }
        set { self[NavigateForwardActionKey.self] = newValue }
    }
}
