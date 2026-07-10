// swiftlint:disable file_length
import OSLog
import SwiftUI

#if canImport(AppKit)
import AppKit
#endif

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

/// FocusedValue key for creating a new library and opening it in a new window
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

}

// MARK: - Focused Command Buttons

/// Button that calls the focused sidebar's createFolder action
struct FocusedNewFolderButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Folder") {
            sidebarActions?.createFolder()
        }
        .keyboardShortcut("n", modifiers: [.command, .shift])
        .disabled(sidebarActions == nil)
    }
}

/// Button that calls the focused sidebar's importFiles action
struct FocusedImportFilesButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Menu("Import") {
            Button("Link Files...") {
                sidebarActions?.importFiles(.link)
            }
            .keyboardShortcut("i", modifiers: [.command])

            Button("Copy Files...") {
                sidebarActions?.importFiles(.copy)
            }
            .keyboardShortcut("i", modifiers: [.command, .option])

            Button("Move Files...") {
                sidebarActions?.importFiles(.move)
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that calls the focused sidebar's renameItem action.
///
/// Keyboard shortcut: plain Return (no modifier) — matches Finder's
/// sidebar convention where pressing Return on a selected row starts
/// rename. Scoped via `@FocusedValue` so the shortcut is only active
/// when the sidebar has focus.
struct FocusedRenameButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Rename") {
            sidebarActions?.renameItem()
        }
        .keyboardShortcut(.return, modifiers: [])
        .disabled(!(selectionInfo?.canRename ?? false))
    }
}

/// Button that calls the focused sidebar's deleteItem action
struct FocusedDeleteButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Delete") {
            sidebarActions?.deleteItem()
        }
        .disabled(!(selectionInfo?.canDelete ?? false))
    }
}

// MARK: - Creation Buttons

/// Button that creates a new search
struct FocusedNewSearchButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        if featureManager.isSearchEnabled {
            Button("New Search") {
                sidebarActions?.createSearch()
            }
            .keyboardShortcut("n", modifiers: [.command, .option])
            .disabled(sidebarActions == nil)
        }
    }
}

/// Button that creates a new chat
struct FocusedNewChatButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        Button(featureManager.badgedLabel("New Chat", for: .chat)) {
            sidebarActions?.createChat()
        }
        .keyboardShortcut("n", modifiers: [.command, .control])
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new workflow
struct FocusedNewWorkflowButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Workflow") {
            sidebarActions?.createWorkflow()
        }
        .keyboardShortcut("n", modifiers: [.command, .control, .shift])
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new chain
struct FocusedNewChainButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Chain") {
            sidebarActions?.createChain()
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new comparison
struct FocusedNewComparisonButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Comparison") {
            sidebarActions?.createComparison()
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new schedule
struct FocusedNewScheduleButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        Button(featureManager.badgedLabel("New Schedule", for: .automation)) {
            sidebarActions?.createSchedule()
        }
        .disabled(sidebarActions == nil)
    }
}

// MARK: - Undo (audited actions)

/// ⌘Z — undo the last audited action via `POST /api/actions/audit/{id}/undo` (#2015).
///
/// MVP **single-level** undo: it reverses the most recent action recorded in the
/// shared `LastAction` holder (seeded today by the entity-merge button), then
/// clears the holder so a repeated ⌘Z can't double-undo the same audit row.
/// The observable change stream propagates the reversed state back into the open
/// views, so there is no manual refresh here.
///
/// Multi-level undo — a per-window stack that walks the `/api/actions/audit`
/// log row by row — is a deliberate follow-up. This replaces SwiftUI's default
/// `.undoRedo` menu items so there is exactly one "Undo", and so the view-local
/// `UndoManager` isn't fighting the audited backend undo.
struct UndoLastActionButton: View {
    /// `@State` over the `@Observable` shared holder so the menu item's title +
    /// enabled state track the last recorded action without manual republishing.
    @State private var lastAction = LastAction.shared
    @FocusedValue(\.navigationUndoAction) private var navigationUndoAction

    private var logger: Logger {
        Logger(subsystem: "app.fichero.fichero", category: "ActionUndo")
    }

    var body: some View {
        Button(undoTitle) {
            performUndo()
        }
        .keyboardShortcut("z", modifiers: .command)
        .disabled(!isEnabled)
    }

    /// "Undo Merge" when an action is recorded, plain "Undo" otherwise.
    private var undoTitle: String {
        if navigationUndoAction != nil {
            return "Undo"
        }
        guard let name = lastAction.actionName else { return "Undo" }
        return "Undo \(Self.menuLabel(for: name))"
    }

    private var isEnabled: Bool {
        navigationUndoAction?.isEnabled == true || lastAction.auditId != nil
    }

    /// `"entity.merge"` → `"Merge"`. Falls back to the raw name if unverbed.
    private static func menuLabel(for actionName: String) -> String {
        let verb = actionName.split(separator: ".").last.map(String.init) ?? actionName
        guard let first = verb.first else { return verb }
        return first.uppercased() + verb.dropFirst()
    }

    private func performUndo() {
        if let navigationUndoAction, navigationUndoAction.isEnabled {
            navigationUndoAction.run()
            return
        }
        guard let auditId = lastAction.auditId,
              let service = LibraryManager.shared.globalLibrary?.actionsService else { return }
        let previousActionName = lastAction.actionName
        // Clear up front so a second ⌘Z can't replay the inverse of the same row
        // (single-level undo). Re-records nothing: redo is a follow-up.
        lastAction.auditId = nil
        lastAction.actionName = nil
        Task {
            do {
                _ = try await service.undoAction(auditId: auditId)
                logger.info("⌘Z undo of audit \(auditId) succeeded")
            } catch {
                // A failed undo must not leave the user with nothing undone AND
                // Undo silently disabled (#3302 / raise-not-silent). Restore the
                // holder so ⌘Z can retry, and surface the failure.
                lastAction.auditId = auditId
                lastAction.actionName = previousActionName
                logger.error("⌘Z undo of audit \(auditId) failed: \(error.localizedDescription)")
                presentUndoError(error)
            }
        }
    }

    private func presentUndoError(_ error: Error) {
        #if canImport(AppKit)
        let alert = NSAlert()
        alert.messageText = "Couldn’t Undo"
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .warning
        alert.runModal()
        #endif
    }
}

/// Button that runs a workflow on selected documents
struct FocusedRunWorkflowOnSelectionButton: View {
    @FocusedValue(\.runWorkflowOnSelection) private var runWorkflowOnSelection
    @ObservedObject var featureManager = FeatureManager.shared

    var body: some View {
        if featureManager.isWorkflowRunOnSelectionEnabled {
            Button("Run Workflow on Selection...") {
                runWorkflowOnSelection?()
            }
            .keyboardShortcut("r", modifiers: [.command, .shift])
            .disabled(runWorkflowOnSelection == nil)
        }
    }
}
