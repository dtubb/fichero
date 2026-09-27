import SwiftUI

//  Extracted for file_length (#5113). Byte-for-byte, behaviour unchanged. Imports are the
//  SOURCE file's, and the path was checked free before writing — both lessons from
//  earlier batches in this milestone.

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

/// FocusedValue key for the focused window's workspace/layout verbs (Daniel,
/// 2026-08-29): Save Workspace…, apply a saved workspace, apply a layout
/// preset. The View menu's workspace section reads it so the commands act on
/// the focused window, same mechanism as InspectorButton.
struct WindowLayoutCommandsKey: FocusedValueKey {
    typealias Value = WindowLayoutCommands
}

/// The READER's zoom, on its own key (2026-08-24): sharing imageZoomActions
/// with the preview meant two publishers whenever both panes were mounted —
/// the "FocusedValue update tried to update multiple times per frame" fault.
/// The menu prefers the image preview's actions and falls back to these.
struct ReaderZoomActionsKey: FocusedValueKey {
    typealias Value = ImageZoomActions
}

extension FocusedValues {
    var imageZoomActions: ImageZoomActionsKey.Value? {
        get { self[ImageZoomActionsKey.self] }
        set { self[ImageZoomActionsKey.self] = newValue }
    }

    var readerZoomActions: ReaderZoomActionsKey.Value? {
        get { self[ReaderZoomActionsKey.self] }
        set { self[ReaderZoomActionsKey.self] = newValue }
    }

    var sidebarActions: SidebarActionsKey.Value? {
        get { self[SidebarActionsKey.self] }
        set { self[SidebarActionsKey.self] = newValue }
    }

    var libraryImportAction: LibraryImportActionKey.Value? {
        get { self[LibraryImportActionKey.self] }
        set { self[LibraryImportActionKey.self] = newValue }
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

    var canvasViewActions: CanvasViewActionsKey.Value? {
        get { self[CanvasViewActionsKey.self] }
        set { self[CanvasViewActionsKey.self] = newValue }
    }

    var focusedPaneKind: FocusedPaneKindKey.Value? {
        get { self[FocusedPaneKindKey.self] }
        set { self[FocusedPaneKindKey.self] = newValue }
    }

    var windowLayoutCommands: WindowLayoutCommandsKey.Value? {
        get { self[WindowLayoutCommandsKey.self] }
        set { self[WindowLayoutCommandsKey.self] = newValue }
    }

    var inspectorSelectAll: InspectorSelectAllKey.Value? {
        get { self[InspectorSelectAllKey.self] }
        set { self[InspectorSelectAllKey.self] = newValue }
    }

    var sidebarSelectAll: SidebarSelectAllKey.Value? {
        get { self[SidebarSelectAllKey.self] }
        set { self[SidebarSelectAllKey.self] = newValue }
    }

    var previewSelectAll: PreviewSelectAllKey.Value? {
        get { self[PreviewSelectAllKey.self] }
        set { self[PreviewSelectAllKey.self] = newValue }
    }

    var imageEditUndoAction: ImageEditUndoActionKey.Value? {
        get { self[ImageEditUndoActionKey.self] }
        set { self[ImageEditUndoActionKey.self] = newValue }
    }

    var readerLens: ReaderLensKey.Value? {
        get { self[ReaderLensKey.self] }
        set { self[ReaderLensKey.self] = newValue }
    }
}
