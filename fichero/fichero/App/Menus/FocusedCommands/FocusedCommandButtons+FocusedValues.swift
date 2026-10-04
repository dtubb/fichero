import SwiftUI

// MARK: - Focused Values for Menu Commands

/// Actions for image preview zoom controls
struct ImageZoomActions: Equatable {
    let zoomIn: () -> Void
    let zoomOut: () -> Void
    let actualSize: () -> Void
    let zoomToFit: () -> Void
    let canZoomIn: Bool
    let canZoomOut: Bool

    /// Same rationale as `SidebarActions.==` below: the closures capture the
    /// same parent state, so only the flags distinguish instances. Without
    /// this, every preview body pass published a "new" value and tripped the
    /// "FocusedValue update tried to update multiple times per frame" fault
    /// (×31 in the 2026-08-19 live log).
    static func == (lhs: ImageZoomActions, rhs: ImageZoomActions) -> Bool {
        lhs.canZoomIn == rhs.canZoomIn && lhs.canZoomOut == rhs.canZoomOut
    }
}

/// FocusedValue key for image zoom actions
struct ImageZoomActionsKey: FocusedValueKey {
    typealias Value = ImageZoomActions
}

/// Camera commands for the focused canvas — zoom to fit, and the Back/Forward
/// jump history (§16, R10 step 4).
///
/// Published only by the canvas modes, so it is nil in List, Table or Reader —
/// which is what makes the View menu's Canvas section disable itself outside a
/// canvas instead of teasing a control that cannot apply.
///
/// Equatable on the FLAGS only, for the reason `ImageZoomActions` documents:
/// the closures capture the same view state, so comparing them republishes on
/// every body pass and trips the "FocusedValue update tried to update multiple
/// times per frame" fault.
struct CanvasViewActions: Equatable {
    let zoomToFit: () -> Void
    let jumpBack: () -> Void
    let jumpForward: () -> Void
    let canJumpBack: Bool
    let canJumpForward: Bool

    static func == (lhs: CanvasViewActions, rhs: CanvasViewActions) -> Bool {
        lhs.canJumpBack == rhs.canJumpBack && lhs.canJumpForward == rhs.canJumpForward
    }
}

struct CanvasViewActionsKey: FocusedValueKey {
    typealias Value = CanvasViewActions
}

/// Which PANE holds focus, published by the shell.
///
/// ⌘A needs this because the select-all publications are scene-scoped: the
/// library publishes whenever a library pane is in the focused scene, whether
/// or not the user's last click went to the inspector. "Who published" cannot
/// decide precedence; "who has focus" can.
struct FocusedPaneKindKey: FocusedValueKey {
    typealias Value = PaneFocus
}

/// A selectable list in the inspector answering ⌘A over its own rows.
struct InspectorSelectAllKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// The sidebar answering ⌘A over the CURRENT library's visible rows.
struct SidebarSelectAllKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// The preview answering ⌘A by selecting the whole image.
struct PreviewSelectAllKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// The image editor answering ⌘Z by dropping its last committed edit step
/// (Daniel, 2026-08-31). Its own key — never a second publisher of
/// `navigationUndoAction` (two publishers of one key = the per-frame
/// FocusedValue fault, see `ReaderZoomActionsKey`).
struct ImageEditUndoActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// The focused Reader's current lens, and the setter for it (R3).
///
/// The pane head and the View menu render the SAME value through this: one
/// binding shown twice, never two switches that can disagree. Equatable on the
/// VALUE only, the `FocusedSortField` shape — comparing the setter would
/// republish on every body pass.
struct FocusedReaderLens: Equatable {
    let value: ReaderLens
    let set: (ReaderLens) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.value == rhs.value }
}

struct ReaderLensKey: FocusedValueKey {
    typealias Value = FocusedReaderLens
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
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createChain: () -> Void
    let createComparison: () -> Void
    let createSchedule: () -> Void
    let createTrigger: () -> Void
    /// Open the primary selected row in a new tab / new window (#2496) —
    /// keyboard/menu parity with double-click and the trailing affordance.
    let openSelectionInNewTab: () -> Void
    let openSelectionInNewWindow: () -> Void

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
    /// How many rows of the CURRENT multi-selection are deletable. Drives the
    /// Edit ▸ Delete title ("Delete N Items") and its enabled state, so the
    /// menu matches what the Delete key would actually remove — previously it
    /// gated on the primary row alone and could disable while the key worked.
    var deletableCount: Int = 0

    static func == (lhs: SidebarSelectionInfo, rhs: SidebarSelectionInfo) -> Bool {
        lhs.selectedItem?.id == rhs.selectedItem?.id
            && lhs.canRename == rhs.canRename
            && lhs.canDelete == rhs.canDelete
            && lhs.deletableCount == rhs.deletableCount
    }
}

/// FocusedValue key for sidebar actions
struct SidebarActionsKey: FocusedValueKey {
    typealias Value = SidebarActions
}

/// FocusedValue key for the library content pane's own import action
/// (#4452). Deliberately narrower than `SidebarActionsKey` — LibraryView
/// only has a real implementation for import, and `SidebarActions`'
/// other 10 closures (rename/delete/chat/workflow/schedule/trigger/…)
/// have no honest LibraryView-scoped meaning. Stubbing them as no-ops to
/// reuse `SidebarActionsKey` would silently enable Data-menu items that do
/// nothing while the library pane has focus — the exact silent-failure
/// class #4449 closed. `impossible > checked > documented`: a menu item
/// this pane cannot honor stays disabled, never wired to a no-op.
struct LibraryImportActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryImportAction
}

/// Equatable wrapper for the library pane's import action (#4452).
///
/// The key's Value used to be a RAW `(IngestMode) -> Void` closure — the one
/// focused value in the app still published unwrapped. Closures are
/// non-Equatable, so LibraryView re-published a "new" value on every body
/// pass; on iPhone that invalidation storm livelocked the navigation-pop
/// layout transition outright — the "no selection → back → stalls" hang, and
/// the "FocusedValue update multiple times per frame" launch spam (Daniel,
/// 2026-08-29; sampled: 100% of the hang inside ViewGraph re-render during
/// `_UINavigationParallaxTransition`). Same cure as `SidebarActions` /
/// `FocusedLibraryAction` above: `==` is unconditionally true because every
/// instance LibraryView constructs captures the same parent @State bindings,
/// so the focus system short-circuits the republish.
struct FocusedLibraryImportAction: Equatable {
    /// Present the file importer for the given ingest mode.
    let run: (IngestMode) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        true
    }
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

/// FocusedValue key for opening a new TAB on the current library, in the key
/// window's tab group (⌘T, #5286). New Window (⌘N) is always a separate window.
struct NewTabActionKey: FocusedValueKey {
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

/// FocusedValue key for File › Set Up Project…: asks for setup of the key window's project
/// (`source.onboard.reachable`, #5421).
struct SetUpProjectActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for closing the current library from the active window.
struct CloseLibraryActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for running a workflow on selected documents.
///
/// `FocusedLibraryAction` (not a raw closure) is load-bearing: a bare
/// `() -> Void` is non-Equatable, so AttributeGraph byte-compares the fresh
/// closure minted on every `LibraryView.body` pass, always sees a change, and
/// cascades focus invalidations — an unbounded update storm that hangs the
/// main thread and can crash inside `AG::LayoutDescriptor::Compare`.
struct RunWorkflowOnSelectionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for navigating to the current folder's parent. Bound to
/// Cmd+\` so users can ascend the hierarchy when the sidebar is hidden. (#786)
struct NavigateToParentActionKey: FocusedValueKey {
    typealias Value = FocusedLibraryAction
}

/// FocusedValue key for undoing the most recent navigation change.
