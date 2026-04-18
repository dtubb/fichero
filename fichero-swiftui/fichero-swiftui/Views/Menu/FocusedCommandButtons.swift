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

/// Actions that can be performed on the sidebar selection
struct SidebarActions {
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createChain: () -> Void          // No longer optional
    let createComparison: () -> Void     // No longer optional
    let createSchedule: () -> Void       // No longer optional
    let createTrigger: () -> Void        // No longer optional
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
    typealias Value = () -> Void
}

/// FocusedValue key for opening a new window on current library
struct NewWindowActionKey: FocusedValueKey {
    typealias Value = () -> Void
}

/// FocusedValue key for creating a new library and opening it in a new window
struct NewLibraryActionKey: FocusedValueKey {
    typealias Value = () -> Void
}

/// FocusedValue key for saving the current library (Save As for Untitled libraries)
struct SaveLibraryActionKey: FocusedValueKey {
    typealias Value = () -> Void
}

/// FocusedValue key for running a workflow on selected documents
struct RunWorkflowOnSelectionKey: FocusedValueKey {
    typealias Value = () -> Void
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

    var saveLibraryAction: SaveLibraryActionKey.Value? {
        get { self[SaveLibraryActionKey.self] }
        set { self[SaveLibraryActionKey.self] = newValue }
    }

    var runWorkflowOnSelection: RunWorkflowOnSelectionKey.Value? {
        get { self[RunWorkflowOnSelectionKey.self] }
        set { self[RunWorkflowOnSelectionKey.self] = newValue }
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

            Button("Add Files...") {
                sidebarActions?.importFiles(.move)
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that calls the focused sidebar's renameItem action
struct FocusedRenameButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        Button("Rename") {
            sidebarActions?.renameItem()
        }
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

/// Button that triggers the focused window's open library file picker
struct FocusedOpenLibraryButton: View {
    @FocusedValue(\.openLibraryAction) private var openLibraryAction

    var body: some View {
        Button("Open Library...") {
            openLibraryAction?()
        }
        .keyboardShortcut("o", modifiers: [.command])
    }
}

/// Button that triggers the focused window's open library file picker (alias for Database terminology)
struct FocusedOpenDatabaseButton: View {
    @FocusedValue(\.openLibraryAction) private var openLibraryAction

    var body: some View {
        Button("Open Database...") {
            openLibraryAction?()
        }
        .keyboardShortcut("o", modifiers: [.command])
    }
}

/// Button that opens a new window viewing the current library
struct FocusedNewWindowButton: View {
    @FocusedValue(\.newWindowAction) private var newWindowAction

    var body: some View {
        Button("New Window") {
            newWindowAction?()
        }
        .keyboardShortcut("t", modifiers: [.command])
        .disabled(newWindowAction == nil)
    }
}

/// Button that creates a new library and opens it in a new window
struct FocusedNewLibraryButton: View {
    @FocusedValue(\.newLibraryAction) private var newLibraryAction

    var body: some View {
        Button("New Library") {
            newLibraryAction?()
        }
        .keyboardShortcut("n", modifiers: [.command])
    }
}

/// Button that creates a new database in the focused window (alias for Database terminology)
struct FocusedNewDatabaseButton: View {
    @FocusedValue(\.newLibraryAction) private var newLibraryAction

    var body: some View {
        Button("New Database") {
            newLibraryAction?()
        }
        .keyboardShortcut("n", modifiers: [.command])
        .disabled(newLibraryAction == nil)
    }
}

/// Button that saves the current library (Save As for Untitled libraries)
struct FocusedSaveLibraryButton: View {
    @FocusedValue(\.saveLibraryAction) private var saveLibraryAction

    var body: some View {
        Button("Save As...") {
            saveLibraryAction?()
        }
        .keyboardShortcut("s", modifiers: [.command, .shift])
        .disabled(saveLibraryAction == nil)
    }
}

/// Button that saves the current database (alias for Database terminology)
struct FocusedSaveDatabaseButton: View {
    @FocusedValue(\.saveLibraryAction) private var saveLibraryAction

    var body: some View {
        Button("Save Database As...") {
            saveLibraryAction?()
        }
        .keyboardShortcut("s", modifiers: [.command, .shift])
        .disabled(saveLibraryAction == nil)
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

    var body: some View {
        Button("New Chat") {
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

    var body: some View {
        Button("New Schedule") {
            sidebarActions?.createSchedule()
        }
        .disabled(sidebarActions == nil)
    }
}

/// Button that creates a new trigger
struct FocusedNewTriggerButton: View {
    @FocusedValue(\.sidebarActions) private var sidebarActions

    var body: some View {
        Button("New Trigger") {
            sidebarActions?.createTrigger()
        }
        .disabled(sidebarActions == nil)
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
